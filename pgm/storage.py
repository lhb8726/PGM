"""Local records and portable backups for PGM.

Backups are plain ZIP archives, NOT encrypted. They contain application records
and attachments, never an OS credential store. Only use one Store per UI thread.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import tempfile
from typing import Any
from uuid import uuid4
import zipfile

from .planning_schema import normalize_planning
from .profile_schema import FINANCE_AMOUNTS, normalize_career


CATEGORIES = {"finance", "career", "learning", "health", "life", "habits"}
SCHEMA_VERSION = 1
MAX_BACKUP_BYTES = 128 * 1024 * 1024
MAX_BACKUP_FILES = 2000
DEFAULT_PROFILE = {
    "name": "", "age": "", "occupation": "", "experience": "", "skills": "",
    "weekly_hours": 10.0, "monthly_budget": 0,
    **dict.fromkeys(FINANCE_AMOUNTS),
    "valuation_date": "", "planned_expenses": "", "career": {},
}
LEGACY_PROFILE_KEYS = DEFAULT_PROFILE.keys() - {"valuation_date", "planned_expenses", "career"}
SCHEMA = {
    "meta": "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "profile": "CREATE TABLE profile (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL)",
    "goals": "CREATE TABLE goals (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL)",
    "tasks": "CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE, data TEXT NOT NULL)",
    "metrics": "CREATE TABLE metrics (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL)",
    "habits": "CREATE TABLE habits (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL)",
    "reviews": "CREATE TABLE reviews (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL)",
    "history": "CREATE TABLE history (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, summary TEXT NOT NULL, details TEXT NOT NULL)",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _text(value: Any, field: str, *, required: bool = False, limit: int = 20000) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field}: 문자열을 입력하세요.")
    value = value.strip()
    if (required and not value) or len(value) > limit:
        raise ValueError(f"{field}: 값을 확인하세요.")
    return value


def _number(value: Any, field: str, minimum: float | None = None,
            maximum: float | None = None) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field}: 숫자를 입력하세요.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field}: 숫자를 입력하세요.") from exc
    if not math.isfinite(result) or (minimum is not None and result < minimum) or (maximum is not None and result > maximum):
        raise ValueError(f"{field}: 범위를 확인하세요.")
    return result


def _integer(value: Any, field: str, minimum: int = 0, maximum: int = 10**16) -> int:
    number = _number(value, field, minimum, maximum)
    if number != int(number):
        raise ValueError(f"{field}: 정수를 입력하세요.")
    return int(number)


def _choice(value: Any, choices: set[str], field: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"{field}: 허용하지 않는 값입니다.")
    return str(value)


def _date(value: Any, field: str, *, optional: bool = False) -> str:
    if optional and value == "":
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field}: 날짜를 확인하세요.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field}: YYYY-MM-DD 날짜를 입력하세요.") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field}: YYYY-MM-DD 날짜를 입력하세요.")
    return value


def _timestamp(value: Any, field: str, *, optional: bool = False) -> str:
    if optional and value == "":
        return ""
    value = _text(value, field, required=True, limit=64)
    try:
        datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field}: 시간 형식을 확인하세요.") from exc
    return value


def _profile(data: dict) -> dict:
    result = {}
    if set(data) - DEFAULT_PROFILE.keys():
        raise ValueError("프로필에 지원하지 않는 항목이 있습니다.")
    for key in ("name", "occupation", "experience", "skills"):
        result[key] = _text(data.get(key, DEFAULT_PROFILE[key]), key)
    age = data.get("age", "")
    result["age"] = "" if age == "" else str(_integer(age, "나이", 0, 150))
    result["weekly_hours"] = _number(data.get("weekly_hours", 10), "주간 가용 시간", 0, 168)
    result["monthly_budget"] = _integer(data.get("monthly_budget", 0), "월 목표용 가용 예산")
    for key, title in FINANCE_AMOUNTS.items():
        value = data.get(key)
        result[key] = None if value is None else _integer(value, title)
    result["valuation_date"] = _date(data.get("valuation_date", ""), "자산·부채 기준일", optional=True)
    result["planned_expenses"] = _text(data.get("planned_expenses", ""), "예정된 큰 지출")
    result["career"] = normalize_career(data.get("career", {}))
    return result


def _goal(data: dict) -> dict:
    return {
        "title": _text(data.get("title", ""), "목표명", required=True, limit=300),
        "category": _choice(data.get("category", "career"), CATEGORIES, "분야"),
        "kind": _choice(data.get("kind", "deliverable"), {"numeric", "deliverable", "habit"}, "목표 유형"),
        "horizon": _choice(data.get("horizon", "short"), {"short", "medium", "long"}, "목표 기간"),
        "due_date": _date(data.get("due_date", (date.today() + timedelta(days=90)).isoformat()), "목표 기한"),
        "priority": _integer(data.get("priority", 2), "우선순위", 1, 3),
        "baseline": _number(data.get("baseline", 0), "시작값"),
        "current": _number(data.get("current", 0), "현재값"),
        "target": _number(data.get("target", 100), "목표값"),
        "unit": _text(data.get("unit", ""), "단위", limit=30),
        "direction": _choice(data.get("direction", "increase"), {"increase", "decrease"}, "목표 방향"),
        "criteria": _text(data.get("criteria", ""), "완료 기준"),
        "status": _choice(data.get("status", "active"), {"active", "completed"}, "상태"),
        "created_at": _timestamp(data.get("created_at", _now()), "생성 시각"),
        "planning": normalize_planning(data.get("planning")),
    }


def _task(data: dict, goal_ids: set[int]) -> dict:
    goal_id = _integer(data.get("goal_id"), "연결 목표", 1)
    if goal_id not in goal_ids:
        raise ValueError("과제에 연결할 목표가 없습니다.")
    done = data.get("done", False)
    if done not in (False, True, 0, 1):
        raise ValueError("완료 상태를 확인하세요.")
    done = bool(done)
    completed_at = (data.get("completed_at") or _now()) if done else ""
    return {
        "goal_id": goal_id,
        "title": _text(data.get("title", ""), "과제명", required=True, limit=500),
        "scheduled_date": _date(data.get("scheduled_date", ""), "수행 날짜", optional=True),
        "minutes": _integer(data.get("minutes", 30), "예상 시간", 1, 1440),
        "actual_minutes": _integer(data.get("actual_minutes", 0), "실제 시간", 0, 10080),
        "done": done,
        "stage": _text(data.get("stage", "실행"), "단계", limit=200),
        "position": _integer(data.get("position", 0), "정렬 순서", 0, 100000),
        "completed_at": _timestamp(completed_at, "완료 시각", optional=True),
        "done_when": _text(data.get("done_when", ""), "과제 완료 기준", limit=2000),
        "rationale": _text(data.get("rationale", ""), "과제 제안 이유", limit=2000),
        "analysis_key": _text(data.get("analysis_key", ""), "분석 과제 연결", limit=200),
        "not_before": _date(data.get("not_before", ""), "과제 시작 가능일", optional=True),
    }


def _metric(data: dict) -> dict:
    return {
        "category": _choice(data.get("category", "career"), CATEGORIES, "분야"),
        "label": _text(data.get("label", ""), "지표명", required=True, limit=200),
        "value": _number(data.get("value"), "측정값"),
        "unit": _text(data.get("unit", ""), "단위", limit=30),
        "evidence_kind": _choice(data.get("evidence_kind", "self"), {"self", "measured", "document"}, "근거 유형"),
        "source": _text(data.get("source", ""), "근거·출처"),
        "recorded_date": _date(data.get("recorded_date", date.today().isoformat()), "기준일"),
    }


def _habit(data: dict) -> dict:
    days = data.get("weekdays", [0, 1, 2, 3, 4])
    if not isinstance(days, list) or not days:
        raise ValueError("습관 수행 요일을 하나 이상 선택하세요.")
    days = sorted({_integer(day, "요일", 0, 6) for day in days})
    completions = data.get("completions", [])
    if not isinstance(completions, list) or len(completions) > 100000:
        raise ValueError("습관 수행 기록을 확인하세요.")
    completions = sorted({_date(value, "습관 수행일") for value in completions})
    return {
        "title": _text(data.get("title", ""), "습관명", required=True, limit=300),
        "category": _choice(data.get("category", "habits"), CATEGORIES, "분야"),
        "weekdays": days,
        "minutes": _integer(data.get("minutes", 10), "습관 시간", 1, 1440),
        "completions": completions,
    }


def _review(data: dict) -> dict:
    result = {
        "date": _date(data.get("date", date.today().isoformat()), "회고 날짜"),
        "good": _text(data.get("good", ""), "잘한 점"),
        "challenge": _text(data.get("challenge", ""), "어려웠던 점"),
        "next_action": _text(data.get("next_action", ""), "다음 행동"),
    }
    if not any(result[key] for key in ("good", "challenge", "next_action")):
        raise ValueError("회고 내용을 하나 이상 입력하세요.")
    return result


class Store:
    """Thread-bound local SQLite store. Backup archives are not encrypted."""

    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "pgm.sqlite3"
        self.attachments_dir = self.data_dir / "attachments"
        self.attachments_dir.mkdir(exist_ok=True)
        self._connect()
        try:
            with self._conn:
                for sql in SCHEMA.values():
                    self._conn.execute(sql.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1))
                version = self._conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
                if version and version[0] != str(SCHEMA_VERSION):
                    raise ValueError("지원하지 않는 데이터베이스 버전입니다.")
                self._conn.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
                self._conn.execute("INSERT OR IGNORE INTO meta VALUES ('dataset_kind', 'personal')")
                self._conn.execute("INSERT OR IGNORE INTO profile VALUES (1, ?)", (_json(DEFAULT_PROFILE),))
        except Exception:
            self.close()
            raise

    def _connect(self) -> None:
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = DELETE")

    def close(self) -> None:
        self._conn.close()

    def profile(self) -> dict:
        value = json.loads(self._conn.execute("SELECT data FROM profile WHERE id = 1").fetchone()[0])
        if value.keys() == LEGACY_PROFILE_KEYS:
            # Earlier profiles used zero for both blank inputs and actual zeros.
            for key in FINANCE_AMOUNTS:
                if value[key] == 0:
                    value[key] = None
        return _profile(value)

    def is_demo(self) -> bool:
        """Return dataset provenance saved in the DB and carried by backups."""
        row = self._conn.execute("SELECT value FROM meta WHERE key = 'dataset_kind'").fetchone()
        return row is not None and row[0] == "demo"

    def save_profile(self, data: dict) -> None:
        value = _profile({**self.profile(), **data})
        with self._conn:
            self._conn.execute("UPDATE profile SET data = ? WHERE id = 1", (_json(value),))

    def _rows(self, table: str) -> list[dict]:
        rows = []
        for row in self._conn.execute(f"SELECT id, data FROM {table} ORDER BY id"):
            value = json.loads(row["data"])
            if table == "goals":
                value["planning"] = normalize_planning(value.get("planning"))
            elif table == "tasks":
                value.setdefault("done_when", "")
                value.setdefault("rationale", "")
                value.setdefault("analysis_key", "")
                value.setdefault("not_before", "")
            rows.append({**value, "id": row["id"]})
        return rows

    def _existing(self, table: str, record_id: Any) -> dict:
        record_id = _integer(record_id, "항목 ID", 1)
        row = self._conn.execute(f"SELECT id, data FROM {table} WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            raise ValueError("항목을 찾을 수 없습니다.")
        return {**json.loads(row["data"]), "id": row["id"]}

    def _save(self, table: str, data: dict, normalizer) -> int:
        record_id = data.get("id")
        old = self._existing(table, record_id) if record_id is not None else {}
        value = normalizer({**old, **data})
        with self._conn:
            if record_id is not None:
                self._conn.execute(f"UPDATE {table} SET data = ? WHERE id = ?", (_json(value), record_id))
                return int(record_id)
            return int(self._conn.execute(f"INSERT INTO {table} (data) VALUES (?)", (_json(value),)).lastrowid)

    def goals(self) -> list[dict]:
        return self._rows("goals")

    def save_goal(self, data: dict) -> int:
        return self._save("goals", data, _goal)

    def delete_goal(self, record_id: int) -> None:
        self._existing("goals", record_id)
        with self._conn:
            self._conn.execute("DELETE FROM goals WHERE id = ?", (record_id,))

    def tasks(self) -> list[dict]:
        return self._rows("tasks")

    def _normalize_task(self, data: dict) -> dict:
        return _task(data, {row[0] for row in self._conn.execute("SELECT id FROM goals")})

    def save_task(self, data: dict) -> int:
        record_id = data.get("id")
        old = self._existing("tasks", record_id) if record_id is not None else {}
        value = self._normalize_task({**old, **data})
        with self._conn:
            if record_id is not None:
                self._conn.execute("UPDATE tasks SET goal_id = ?, data = ? WHERE id = ?",
                                   (value["goal_id"], _json(value), record_id))
                return int(record_id)
            return int(self._conn.execute("INSERT INTO tasks (goal_id, data) VALUES (?, ?)",
                                          (value["goal_id"], _json(value))).lastrowid)

    def add_tasks(self, tasks: list[dict]) -> None:
        if any("id" in item for item in tasks):
            raise ValueError("새 과제 목록에는 기존 ID를 넣을 수 없습니다.")
        values = [self._normalize_task(item) for item in tasks]
        with self._conn:
            self._conn.executemany("INSERT INTO tasks (goal_id, data) VALUES (?, ?)",
                                   [(item["goal_id"], _json(item)) for item in values])

    def apply_task_updates(self, tasks: list[dict]) -> None:
        """Apply a replan atomically without touching completed records.

        Validate every update before the transaction starts. Each existing,
        unfinished task may appear once; the operation never adds new tasks.
        """
        updates = []
        seen = set()
        for item in tasks:
            record_id = _integer(item.get("id"), "과제 ID", 1)
            if record_id in seen:
                raise ValueError("같은 과제의 변경이 중복되었습니다.")
            seen.add(record_id)
            old = self._existing("tasks", record_id)
            if old["done"]:
                raise ValueError("완료한 과제는 재계획으로 변경할 수 없습니다.")
            value = self._normalize_task({**old, **item})
            if value["done"]:
                raise ValueError("재계획에서는 과제의 완료 상태를 변경할 수 없습니다.")
            updates.append((value["goal_id"], _json(value), record_id))
        with self._conn:
            self._conn.executemany("UPDATE tasks SET goal_id = ?, data = ? WHERE id = ?", updates)

    def set_task_done(self, record_id: int, done: bool, actual_minutes: int | None = None) -> None:
        value = self._existing("tasks", record_id)
        value.update(done=bool(done), completed_at=_now() if done else "")
        # Checking completion does not establish elapsed time. Zero means that
        # actual time has not been recorded; keep an explicit past entry unless
        # the caller supplies a replacement (including an explicit zero).
        if actual_minutes is not None:
            value["actual_minutes"] = actual_minutes
        self.save_task(value)

    def delete_task(self, record_id: int) -> None:
        self._existing("tasks", record_id)
        with self._conn:
            self._conn.execute("DELETE FROM tasks WHERE id = ?", (record_id,))

    def metrics(self) -> list[dict]:
        return self._rows("metrics")

    def add_metric(self, data: dict) -> int:
        if "id" in data:
            raise ValueError("새 측정값에는 기존 ID를 넣을 수 없습니다.")
        return self._save("metrics", data, _metric)

    def habits(self) -> list[dict]:
        return self._rows("habits")

    def save_habit(self, data: dict) -> int:
        return self._save("habits", data, _habit)

    def delete_habit(self, record_id: int) -> None:
        self._existing("habits", record_id)
        with self._conn:
            self._conn.execute("DELETE FROM habits WHERE id = ?", (record_id,))

    def toggle_habit(self, record_id: int, day: str) -> None:
        day = _date(day, "습관 수행일")
        value = self._existing("habits", record_id)
        if date.fromisoformat(day).weekday() not in value["weekdays"]:
            raise ValueError("오늘은 이 습관의 수행 예정일이 아닙니다.")
        completed = set(value["completions"])
        if day in completed:
            completed.remove(day)
        else:
            completed.add(day)
        value["completions"] = sorted(completed)
        self.save_habit(value)

    def reviews(self) -> list[dict]:
        return sorted(self._rows("reviews"), key=lambda row: (row["date"], row["id"]), reverse=True)

    def add_review(self, data: dict) -> int:
        if "id" in data:
            raise ValueError("새 회고에는 기존 ID를 넣을 수 없습니다.")
        return self._save("reviews", data, _review)

    def history(self) -> list[dict]:
        return [dict(row) for row in self._conn.execute("SELECT * FROM history ORDER BY id DESC LIMIT 100")]

    def log_change(self, summary: str, details: str = "") -> None:
        summary = _text(summary, "변경 요약", required=True, limit=500)
        details = _text(details, "변경 내용")
        with self._conn:
            self._conn.execute("INSERT INTO history (created_at, summary, details) VALUES (?, ?, ?)",
                               (_now(), summary, details))

    @staticmethod
    def _archive_name(name: str) -> PurePosixPath:
        if "\\" in name or any(c in name for c in '<>:"|?*'):
            raise ValueError("백업에 호환되지 않는 파일 경로가 있습니다.")
        path = PurePosixPath(name)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in name.split("/")):
            raise ValueError("백업에 안전하지 않은 파일 경로가 있습니다.")
        if name not in {"manifest.json", "database.sqlite3"} and (not path.parts or path.parts[0] != "attachments" or len(path.parts) < 2):
            raise ValueError("백업에 허용하지 않는 파일이 있습니다.")
        return path

    def export_backup(self, path: Path | str) -> Path:
        """Write a portable, non-encrypted ZIP snapshot with integrity hashes."""
        path = Path(path).expanduser().resolve()
        if path == self.db_path or path.is_relative_to(self.attachments_dir):
            raise ValueError("데이터베이스나 첨부 폴더 안에는 백업할 수 없습니다.")
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="pgm-backup-") as directory:
            snapshot = Path(directory) / "database.sqlite3"
            destination = sqlite3.connect(snapshot)
            try:
                self._conn.backup(destination)
            finally:
                destination.close()
            entries = [("database.sqlite3", snapshot)]
            for item in sorted(self.attachments_dir.rglob("*")):
                if item.is_symlink():
                    raise ValueError("첨부 폴더의 심볼릭 링크는 백업할 수 없습니다.")
                if item.is_file():
                    name = "attachments/" + item.relative_to(self.attachments_dir).as_posix()
                    self._archive_name(name)
                    entries.append((name, item))
            if len(entries) > MAX_BACKUP_FILES or sum(item.stat().st_size for _, item in entries) > MAX_BACKUP_BYTES:
                raise ValueError("프로토타입 백업 크기 제한(128MB)을 초과했습니다.")
            manifest = {"format": "pgm-backup", "version": SCHEMA_VERSION,
                        "created_at": _now(), "encrypted": False,
                        "files": {name: hashlib.sha256(item.read_bytes()).hexdigest() for name, item in entries}}
            descriptor, temporary_name = tempfile.mkstemp(prefix=".pgm-", suffix=".tmp", dir=path.parent)
            os.close(descriptor)
            temporary = Path(temporary_name)
            try:
                with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr("manifest.json", _json(manifest))
                    for name, item in entries:
                        archive.write(item, name)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        return path

    @staticmethod
    def _validate_database(path: Path) -> None:
        connection = None
        try:
            connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            with connection:
                connection.execute("PRAGMA query_only = ON")
                connection.execute("PRAGMA trusted_schema = OFF")
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("백업 데이터베이스 무결성 검사에 실패했습니다.")
                objects = connection.execute("SELECT name, type, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
                if {row["name"] for row in objects} != set(SCHEMA):
                    raise ValueError("백업 데이터베이스 구조가 올바르지 않습니다.")
                for row in objects:
                    normalize = lambda sql: " ".join(sql.replace("IF NOT EXISTS ", "").split())
                    if row["type"] != "table" or normalize(row["sql"]) != normalize(SCHEMA[row["name"]]):
                        raise ValueError("백업에 지원하지 않는 데이터베이스 구조가 있습니다.")
                versions = dict(connection.execute("SELECT key, value FROM meta"))
                if (set(versions) - {"schema_version", "dataset_kind"}
                        or versions.get("schema_version") != str(SCHEMA_VERSION)
                        or versions.get("dataset_kind", "personal") not in {"personal", "demo"}):
                    raise ValueError("지원하지 않는 백업 버전입니다.")
                profiles = connection.execute("SELECT id, data FROM profile").fetchall()
                if len(profiles) != 1 or profiles[0]["id"] != 1:
                    raise ValueError("백업 프로필이 올바르지 않습니다.")
                value = json.loads(profiles[0]["data"])
                if not isinstance(value, dict):
                    raise ValueError("백업 프로필 값이 올바르지 않습니다.")
                normalized = _profile(value)
                if value.keys() == LEGACY_PROFILE_KEYS and all(value[key] is not None for key in FINANCE_AMOUNTS):
                    normalized = {key: normalized[key] for key in LEGACY_PROFILE_KEYS}
                if normalized != value:
                    raise ValueError("백업 프로필 값이 올바르지 않습니다.")
                goal_ids = {row[0] for row in connection.execute("SELECT id FROM goals")}
                validators = {"goals": _goal, "tasks": lambda value: _task(value, goal_ids),
                              "metrics": _metric, "habits": _habit, "reviews": _review}
                count = 0
                for table, validator in validators.items():
                    for row in connection.execute(f"SELECT * FROM {table}"):
                        count += 1
                        if count > 100000 or not isinstance(row["id"], int) or row["id"] <= 0:
                            raise ValueError("백업 항목 수 또는 ID가 올바르지 않습니다.")
                        value = json.loads(row["data"])
                        compatible = dict(value) if isinstance(value, dict) else value
                        if isinstance(compatible, dict):
                            # These fields were added to JSON records in v0.2;
                            # v0.1 archives keep their original schema and hashes.
                            if table == "goals":
                                compatible.setdefault("planning", normalize_planning())
                            elif table == "tasks":
                                compatible.setdefault("done_when", "")
                                compatible.setdefault("rationale", "")
                                compatible.setdefault("analysis_key", "")
                                compatible.setdefault("not_before", "")
                        if not isinstance(value, dict) or validator(value) != compatible:
                            raise ValueError("백업 항목 값이 올바르지 않습니다.")
                        if table == "tasks" and row["goal_id"] != value["goal_id"]:
                            raise ValueError("백업의 목표 연결이 올바르지 않습니다.")
                if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise ValueError("백업에 끊어진 목표 연결이 있습니다.")
                for row in connection.execute("SELECT * FROM history"):
                    _timestamp(row["created_at"], "변경 시각")
                    _text(row["summary"], "변경 요약", required=True, limit=500)
                    _text(row["details"], "변경 내용")
        except (sqlite3.Error, json.JSONDecodeError, TypeError, KeyError, AttributeError) as exc:
            raise ValueError("올바른 PGM 데이터베이스가 아닙니다.") from exc
        finally:
            if connection is not None:
                connection.close()

    def restore_backup(self, path: Path | str) -> Path:
        """Validate first, snapshot the current data, then replace atomically.

        Return the pre-restore backup path. This archive is NOT encrypted.
        """
        path = Path(path).expanduser().resolve()
        if not path.is_file() or path.stat().st_size > MAX_BACKUP_BYTES:
            raise ValueError("백업 파일이 없거나 크기 제한(128MB)을 초과했습니다.")
        with tempfile.TemporaryDirectory(prefix=".pgm-restore-", dir=self.data_dir) as directory:
            staging = Path(directory)
            try:
                with zipfile.ZipFile(path, "r") as archive:
                    entries = archive.infolist()
                    names = [entry.filename for entry in entries]
                    if len(entries) > MAX_BACKUP_FILES + 1 or len(set(name.casefold() for name in names)) != len(names):
                        raise ValueError("백업 파일 수 또는 중복 경로가 올바르지 않습니다.")
                    if sum(entry.file_size for entry in entries) > MAX_BACKUP_BYTES:
                        raise ValueError("백업 압축 해제 크기 제한(128MB)을 초과했습니다.")
                    for entry in entries:
                        self._archive_name(entry.filename)
                        if entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                            raise ValueError("지원하지 않는 백업 항목입니다.")
                    if "manifest.json" not in names or "database.sqlite3" not in names:
                        raise ValueError("백업의 필수 파일이 없습니다.")
                    if archive.getinfo("manifest.json").file_size > 1024 * 1024:
                        raise ValueError("백업 정보가 너무 큽니다.")
                    manifest = json.loads(archive.read("manifest.json"))
                    if not isinstance(manifest, dict) or manifest.get("format") != "pgm-backup" or manifest.get("version") != SCHEMA_VERSION or manifest.get("encrypted") is not False:
                        raise ValueError("지원하지 않는 백업 형식입니다.")
                    hashes = manifest.get("files")
                    if not isinstance(hashes, dict) or set(hashes) != set(names) - {"manifest.json"}:
                        raise ValueError("백업 파일 목록이 일치하지 않습니다.")
                    for name in names:
                        if name == "manifest.json":
                            continue
                        contents = archive.read(name)
                        if hashlib.sha256(contents).hexdigest() != hashes[name]:
                            raise ValueError("백업 파일이 변경되었거나 손상되었습니다.")
                        target = staging.joinpath(*PurePosixPath(name).parts)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(contents)
            except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeError, KeyError, TypeError, RuntimeError) as exc:
                raise ValueError("올바른 PGM 백업 파일이 아닙니다.") from exc
            incoming_db = staging / "database.sqlite3"
            incoming_attachments = staging / "attachments"
            incoming_attachments.mkdir(exist_ok=True)
            self._validate_database(incoming_db)
            before = self.data_dir / "backups" / f"before-restore-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}.pgmbackup"
            self.export_backup(before)
            old_db, old_attachments = staging / "previous.sqlite3", staging / "previous-attachments"
            self.close()
            database_moved = attachments_moved = False
            try:
                os.replace(self.db_path, old_db)
                database_moved = True
                os.replace(self.attachments_dir, old_attachments)
                attachments_moved = True
                os.replace(incoming_db, self.db_path)
                os.replace(incoming_attachments, self.attachments_dir)
                self._connect()
                self.log_change("백업 복원", "복원 전 데이터는 자동 백업으로 보관했습니다.")
            except Exception:
                try:
                    self.close()
                except sqlite3.Error:
                    pass
                if database_moved:
                    os.replace(old_db, self.db_path)
                if attachments_moved:
                    if self.attachments_dir.exists():
                        shutil.rmtree(self.attachments_dir)
                    os.replace(old_attachments, self.attachments_dir)
                self._connect()
                raise
        return before

    def seed_demo(self, today: date | None = None) -> bool:
        """Populate an untouched store with clearly fictional example data."""
        if any(self._rows(table) for table in ("goals", "tasks", "metrics", "habits", "reviews")) or self.profile() != DEFAULT_PROFILE:
            return False
        today = today or date.today()
        with self._conn:
            self._conn.execute("INSERT OR REPLACE INTO meta VALUES ('dataset_kind', 'demo')")
        self.save_profile({"name": "데모 사용자", "age": "30", "occupation": "가상 예시 · 서비스 기획자",
                           "experience": "가상 데모 데이터입니다. 실제 경력·자산이 아닙니다.",
                           "skills": "Python 기초, 프로젝트 기획, 영어 학습", "weekly_hours": 14,
                           "monthly_budget": 300000, "assets": 12000000, "liabilities": 2000000,
                           "monthly_income": 3000000, "monthly_expenses": 2100000})
        examples = [
            ("finance", "비상자금 600만 원 만들기", "numeric", 3000000, 3800000, 6000000, "원", 150, "매달 저축액을 기록하고 목표 잔액을 확인하기"),
            ("career", "Python 포트폴리오 완성", "deliverable", 0, 0, 100, "", 90, "동작하는 앱, README, 검증 기록을 포함한 결과물 완성"),
            ("learning", "영어 모의시험 800점 도전", "numeric", 480, 620, 800, "점", 120, "같은 유형의 모의시험 결과를 기록하기"),
            ("health", "주 3회 운동 루틴 만들기", "habit", 0, 0, 12, "회", 60, "수행 예정일에 운동하고 기록 남기기"),
            ("life", "새로운 여행 경험 계획하기", "deliverable", 0, 0, 100, "", 45, "예산·일정·방문지를 정하고 실행 후 회고하기"),
            ("habits", "주간 회고 꾸준히 작성하기", "habit", 0, 0, 8, "회", 60, "잘한 점·어려움·다음 행동을 기록하기"),
        ]
        ids = {}
        for category, title, kind, baseline, current, target, unit, days, criteria in examples:
            ids[category] = self.save_goal({"title": title, "category": category, "kind": kind,
                "baseline": baseline, "current": current, "target": target, "unit": unit,
                "due_date": (today + timedelta(days=days)).isoformat(), "priority": 3 if category == "career" else 2,
                "horizon": "medium" if days >= 90 else "short", "criteria": criteria})
        tasks = [
            ("career", "프로젝트 요구사항 정리", -6, 45, True, "기초 정리"),
            ("learning", "영어 현재 수준 기록", -5, 30, True, "현재 상태"),
            ("finance", "가상 월간 지출 분류", -4, 30, True, "현황 정리"),
            ("career", "첫 화면 와이어프레임 작성", -3, 60, True, "설계"),
            ("health", "운동 가능 요일과 시간 정하기", -2, 20, True, "준비"),
            ("learning", "오답 유형 분류하기", -1, 30, False, "기초 학습"),
            ("career", "핵심 화면 한 개 구현하기", 0, 60, False, "실행"),
            ("learning", "취약 유형 문제 풀기", 0, 30, False, "실행"),
            ("finance", "이번 달 저축 계획 확인", 0, 20, False, "계획"),
            ("life", "여행 후보와 예상 비용 정리", 1, 30, False, "탐색"),
            ("career", "실행 결과와 개선점 기록", 2, 45, False, "검증"),
            ("habits", "이번 주 계획과 실행 비교", 3, 20, False, "회고"),
        ]
        for index, (category, title, offset, minutes, done, stage) in enumerate(tasks):
            day = today + timedelta(days=offset)
            self.save_task({"goal_id": ids[category], "title": title, "scheduled_date": day.isoformat(),
                "minutes": minutes, "actual_minutes": minutes if done else 0, "done": done,
                "stage": stage, "position": index,
                "completed_at": datetime.combine(day, datetime.min.time(), timezone.utc).isoformat() if done else ""})
        for category, label, value, unit in [("finance", "순자산", 10000000, "원"),
                ("career", "포트폴리오 결과물", 1, "개"), ("learning", "영어 모의시험", 620, "점"),
                ("health", "주간 운동", 2, "회"), ("life", "새로운 경험 기록", 1, "개"),
                ("habits", "주간 집중 시간", 8, "시간")]:
            self.add_metric({"category": category, "label": label, "value": value, "unit": unit,
                "evidence_kind": "self", "source": "가상 데모 데이터 · 실제 측정값이 아닙니다.",
                "recorded_date": today.isoformat()})
        for title, category, weekdays, minutes in [("20분 독서", "learning", list(range(7)), 20),
                ("가볍게 몸 움직이기", "health", [0, 2, 4], 20), ("하루 회고", "habits", list(range(7)), 10)]:
            completed = [(today - timedelta(days=offset)).isoformat() for offset in range(1, 5)
                         if (today - timedelta(days=offset)).weekday() in weekdays]
            self.save_habit({"title": title, "category": category, "weekdays": weekdays,
                             "minutes": minutes, "completions": completed})
        self.add_review({"date": (today - timedelta(days=1)).isoformat(),
            "good": "가상 예시: 목표를 작은 결과물로 나누었습니다.",
            "challenge": "가상 예시: 공부 시간을 실제보다 짧게 예상했습니다.",
            "next_action": "가상 예시: 이번 주 과제 수를 줄이고 실제 시간을 기록합니다."})
        self.log_change("가상 데모 데이터 생성", "모든 프로필·자산·목표·기록은 기능 확인용 예시입니다.")
        return True
