"""Explainable, local planning rules for the PGM prototype.

These functions do not call an AI service. Template durations are editable product
assumptions, not scientifically validated learning or health prescriptions.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import math
from typing import Any


CATEGORIES = {
    "finance": "금융 및 자산 관리",
    "career": "커리어 및 전문성",
    "learning": "학습 및 지식",
    "health": "건강 및 체력",
    "life": "경험 및 라이프스타일",
    "habits": "자기관리 및 습관",
}

# Durations are initial estimates. Every generated title is explicitly a draft.
TEMPLATES = {
    "finance": [
        ("01 현황 확인", "자산·부채·현금흐름과 기준일 정리", 45),
        ("02 목표 구체화", "목표 금액·기한·필요 자금 확인", 30),
        ("03 실행 설계", "월별 실행 예산과 확인 항목 작성", 45),
        ("04 점검", "실제 기록과 계획의 차이 검토", 30),
    ],
    "career": [
        ("01 현황 확인", "목표 직무·자격의 요구 기준 확인", 30),
        ("02 역량 보완", "현재 결과물과 필요한 역량 비교", 45),
        ("03 결과물", "핵심 결과물의 작은 초안 제작", 60),
        ("04 검토", "완료 기준으로 결과물 검토·보완", 45),
    ],
    "learning": [
        ("01 수준 확인", "현재 수준을 확인할 문제·자료 선택", 30),
        ("02 핵심 학습", "첫 핵심 주제 학습과 요약", 45),
        ("03 적용", "실전 문제 풀이 또는 결과물 제작", 60),
        ("04 점검", "오답·부족한 부분과 다음 학습 정리", 30),
    ],
    "health": [
        ("01 현황 확인", "운동·수면 기록과 활동 제약 정리", 30),
        ("02 기준 설정", "측정 가능한 생활 목표와 확인 방법 설정", 15),
        ("03 실행 설계", "시간·활동 제약에 맞는 실행 항목 작성", 30),
        ("04 점검", "실제 기록과 지속 가능성 검토", 15),
    ],
    "life": [
        ("01 방향 설정", "원하는 경험과 완료 기준 구체화", 30),
        ("02 자원 확인", "시간·예산·참여 조건 확인", 30),
        ("03 준비", "첫 준비 항목 실행", 45),
        ("04 회고", "경험 기록과 다음 개선점 정리", 30),
    ],
    "habits": [
        ("01 현황 확인", "현재 행동과 방해 요인 기록", 20),
        ("02 행동 설계", "작은 행동·수행 요일·시작 조건 설정", 20),
        ("03 실행 확인", "수행 기록과 실행 어려움 정리", 30),
        ("04 회고", "실행률과 다음 개선 행동 검토", 20),
    ],
}


def _day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _today(value: Any = None) -> date:
    return _day(value) or date.today()


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _minutes(task: dict, actual: bool = False) -> int:
    if actual and _number(task.get("actual_minutes")) > 0:
        return max(0, int(_number(task["actual_minutes"])))
    return max(0, int(_number(task.get("minutes"))))


def _active(goal: dict) -> bool:
    return goal.get("status", "active") == "active"


def _related(goal: dict, tasks: list[dict]) -> list[dict]:
    goal_id = goal.get("id")
    if goal_id is None:
        return list(tasks)
    return [task for task in tasks if task.get("goal_id") == goal_id]


def progress(goal: dict, tasks: list[dict]) -> float:
    """Return bounded progress without ever changing a goal's final status.

    For deliverables, 100% means preparation tasks are done. Actual certification,
    employment or final acceptance still requires explicit goal confirmation.
    """
    if goal.get("status") == "completed":
        return 1.0
    if goal.get("kind") == "numeric":
        values = [goal.get(key) for key in ("baseline", "current", "target")]
        if any(value is None or not math.isfinite(_number(value, math.nan)) for value in values):
            return 0.0
        baseline, current, target = map(float, values)
        if goal.get("direction", "increase") == "decrease":
            if baseline <= target:
                return float(current <= target)
            result = (baseline - current) / (baseline - target)
        else:
            if baseline >= target:
                return float(current >= target)
            result = (current - baseline) / (target - baseline)
        return min(1.0, max(0.0, result))
    related = _related(goal, tasks)
    if not related:
        return 0.0
    return sum(bool(task.get("done")) for task in related) / len(related)


def diagnose(profile: dict, metrics: list[dict], goals: list[dict]) -> list[dict]:
    """Describe saved evidence and missing inputs; never invent ability scores."""
    results = []
    for category, title in CATEGORIES.items():
        recorded = sorted(
            [metric for metric in metrics if metric.get("category") == category],
            key=lambda metric: str(metric.get("recorded_date", "")), reverse=True,
        )
        related_goals = [goal for goal in goals if goal.get("category") == category and _active(goal)]
        evidence_parts = []
        missing = []
        has_confirmed = any(metric.get("evidence_kind") in {"measured", "document"} for metric in recorded)
        for metric in recorded[:3]:
            kind = {"self": "자기 보고", "measured": "측정 기록", "document": "문서·결과물"}.get(
                metric.get("evidence_kind"), "사용자 기록"
            )
            source = str(metric.get("source") or "출처 미입력")
            evidence_parts.append(
                f"{metric.get('label', '지표')} {_number(metric.get('value')):g}{metric.get('unit', '')}"
                f" · {kind} · {metric.get('recorded_date') or '기준일 미입력'} · {source}"
            )
        if not recorded:
            missing.append("현재 상태를 나타내는 지표와 기준일")
        elif not has_confirmed:
            missing.append("수준을 확인할 측정 기록 또는 결과물")
        if recorded and any(not metric.get("source") for metric in recorded):
            missing.append("기록의 출처·측정 방법")
        if not related_goals:
            missing.append("완료 기준과 기한이 있는 목표")
        elif any(not str(goal.get("criteria", "")).strip() for goal in related_goals):
            missing.append("목표의 구체적인 완료 기준")

        summary = f"저장된 지표 {len(recorded)}개 · 진행 중 목표 {len(related_goals)}개."
        if category == "finance":
            financial_keys = ("assets", "liabilities", "monthly_income", "monthly_expenses")
            known = bool(profile.get("financial_confirmed")) or any(_number(profile.get(k)) != 0 for k in financial_keys)
            if known:
                assets, debt, income, expense = [_number(profile.get(k)) for k in financial_keys]
                summary += f" 사용자 입력 기준 순자산 {assets - debt:,.0f}, 월 수입−지출 {income - expense:,.0f}."
                evidence_parts.append("프로필 금액의 통화·기준일·증빙을 별도로 확인하세요.")
                if income > 0:
                    evidence_parts.append(f"내부 지표 (수입−지출)/수입: {(income-expense)/income*100:.1f}% · 투자수익 미반영")
                else:
                    evidence_parts.append("수입이 0이거나 미입력이므로 수입 대비 비율을 계산하지 않았습니다.")
            else:
                missing.append("자산·부채·수입·지출의 실제 확인값")
        elif category == "career" and (profile.get("occupation") or profile.get("skills")):
            evidence_parts.append(f"사용자 입력: {profile.get('occupation') or '직업 미입력'} · {profile.get('skills') or '역량 미입력'}")
            summary += " 프로필 서술만으로 숙련도를 확정하지 않습니다."
        if has_confirmed:
            level = "근거 기록 있음"
        elif evidence_parts:
            level = "자기 보고 확인"
        else:
            level = "정보 부족"
        results.append({
            "category": category, "title": title, "level": level, "summary": summary,
            "evidence": "\n".join(evidence_parts) or "아직 저장된 근거가 없습니다.",
            "missing": list(dict.fromkeys(missing)),
            "next_step": missing[0] + "를 확인하세요." if missing else "같은 기준의 다음 기록을 남기고 목표와 비교하세요.",
        })
    return results


def _habit_minutes(habits: list[dict] | None, day: date) -> int:
    return sum(
        _minutes(habit) for habit in (habits or [])
        if day.weekday() in habit.get("weekdays", [])
    )


def _task_capacity_day(task: dict) -> date | None:
    # Actual execution occupies its execution date, including work completed today
    # that was originally scheduled on another day.
    if task.get("done"):
        return _day(task.get("completed_at")) or _day(task.get("scheduled_date"))
    return _day(task.get("scheduled_date"))


def _calendar(profile: dict, tasks: list[dict], habits: list[dict] | None,
              today: date, horizon_days: int) -> tuple[dict[date, int], int, list[str]]:
    horizon_days = max(0, min(int(horizon_days), 366))
    capacity = max(0, int(_number(profile.get("weekly_hours")) * 60 / 7))
    days = [today + timedelta(days=offset) for offset in range(horizon_days)]
    reserved = defaultdict(int)
    for task in tasks:
        day = _task_capacity_day(task)
        if day is not None:
            reserved[day] += _minutes(task, actual=bool(task.get("done")))
    free = {}
    overfull = 0
    for day in days:
        reserved_minutes = reserved[day] + _habit_minutes(habits, day)
        if reserved_minutes > capacity:
            overfull += 1
        free[day] = max(0, capacity - reserved_minutes)
    warnings = []
    if capacity == 0:
        warnings.append("배치할 가용 시간이 없습니다. 프로필의 주당 순가용 시간을 확인하세요.")
    if overfull:
        warnings.append(f"기존 과제·습관이 {overfull}일에서 일일 가용 시간을 초과합니다. 기존 계획을 조정하세요.")
    return free, capacity, warnings


def _deadline(goal: dict, today: date, end: date, warnings: list[str]) -> date | None:
    title = goal.get("title", "목표")
    value = _day(goal.get("due_date"))
    if value is None:
        warnings.append(f"‘{title}’의 유효한 기한이 없어 계획 범위 안의 초안으로 배치합니다.")
        return end
    if value < today:
        warnings.append(f"‘{title}’의 기한이 지났습니다. 기한·범위·우선순위를 먼저 조정하세요.")
        return None
    return min(value, end)


def _goal_order(goal: dict) -> tuple:
    return (-_number(goal.get("priority"), 2), _day(goal.get("due_date")) or date.max, str(goal.get("id", "")))


def build_plan(goals: list[dict], existing_tasks: list[dict], profile: dict,
               habits: list[dict] | None = None, today: Any = None,
               horizon_days: int = 28) -> dict:
    """Generate editable template drafts against one shared daily time budget.

    Weekly net hours are evenly spread over seven days, rounded down to whole
    minutes per day. A task's real cost, intra-day appointments and proven ability
    are not inferred. Drafts never mark the final goal complete.
    """
    start = _today(today)
    free, capacity, warnings = _calendar(profile, existing_tasks, habits, start, horizon_days)
    available = sum(free.values())
    if not free:
        return {"tasks": [], "warnings": warnings + ["계획 범위가 비어 있습니다."], "summary": "생성된 초안이 없습니다.", "total_minutes": 0, "available_minutes": 0}
    end = max(free)
    generated = []
    for goal in sorted([goal for goal in goals if _active(goal)], key=_goal_order):
        related = _related(goal, existing_tasks)
        title = str(goal.get("title") or "목표")
        if related:
            if any(not task.get("done") for task in related):
                warnings.append(f"‘{title}’에는 미완료 과제가 있어 중복 초안을 만들지 않았습니다. 재계획을 사용하세요.")
            else:
                warnings.append(f"‘{title}’의 준비 과제가 모두 완료되었습니다. 최종 완료 기준을 직접 확인하세요.")
            continue
        deadline = _deadline(goal, start, end, warnings)
        if deadline is None:
            continue
        template = TEMPLATES.get(goal.get("category"), TEMPLATES["habits"])
        earliest = start
        position = 0
        incomplete = False
        for stage, task_title, duration in template:
            remaining = duration
            pieces = []
            for day in free:
                if day < earliest or day > deadline:
                    continue
                block = min(free[day], remaining, 60)
                if block <= 0:
                    continue
                pieces.append((day, block))
                free[day] -= block
                remaining -= block
                earliest = day
                if remaining == 0:
                    break
            for index, (day, minutes) in enumerate(pieces, 1):
                position += 1
                suffix = f" · {index}/{len(pieces)}" if len(pieces) > 1 else ""
                if remaining:
                    suffix += " · 일부"
                generated.append({
                    "goal_id": goal.get("id"), "title": f"{task_title}{suffix}",
                    "scheduled_date": day.isoformat(), "minutes": minutes,
                    "actual_minutes": 0, "done": False, "stage": stage,
                    "position": position, "completed_at": "", "source": "규칙 기반 초안",
                })
            if remaining:
                incomplete = True
                break  # Later stages cannot precede the incomplete stage.
        if incomplete:
            warnings.append(f"‘{title}’의 전체 초안을 기한·가용 시간 안에 배치할 수 없습니다. 기한 연장·범위 축소·시간 조정을 검토하세요.")
    total = sum(task["minutes"] for task in generated)
    summary = f"{len(generated)}개 실행 초안 · {total}분 배치 / 새 과제에 사용 가능한 {available}분."
    summary += " 주당 순가용 시간을 7일에 균등 배분한 시간 기준 계획이며, 소요 시간과 완료 기준은 직접 확인하세요."
    return {"tasks": generated, "warnings": list(dict.fromkeys(warnings)), "summary": summary,
            "total_minutes": total, "available_minutes": available}


def replan(tasks: list[dict], goals: list[dict], profile: dict,
           habits: list[dict] | None = None, today: Any = None,
           horizon_days: int = 28) -> dict:
    """Preview new dates for unfinished tasks; completed records are untouched."""
    start = _today(today)
    goal_map = {goal.get("id"): goal for goal in goals if _active(goal)}
    candidates = [task for task in tasks if not task.get("done") and task.get("goal_id") in goal_map]
    candidate_ids = {id(task) for task in candidates}
    fixed = [task for task in tasks if id(task) not in candidate_ids]
    free, _, warnings = _calendar(profile, fixed, habits, start, horizon_days)
    available = sum(free.values())
    end = max(free) if free else start - timedelta(days=1)
    ordered = sorted(candidates, key=lambda task: (
        _goal_order(goal_map[task.get("goal_id")]),
        _number(task.get("position")), str(task.get("stage", "")),
        str(task.get("scheduled_date", "")), str(task.get("id", "")),
    ))
    updates = []
    earliest = defaultdict(lambda: start)
    blocked = set()
    deadline_cache = {}
    for task in ordered:
        goal_id = task.get("goal_id")
        goal = goal_map[goal_id]
        if goal_id not in deadline_cache:
            deadline_cache[goal_id] = _deadline(goal, start, end, warnings) if free else None
        deadline = deadline_cache[goal_id]
        result = dict(task)
        result["scheduled_date"] = ""
        minutes = _minutes(task)
        if goal_id not in blocked and deadline is not None and minutes > 0:
            for day in free:
                if earliest[goal_id] <= day <= deadline and free[day] >= minutes:
                    result["scheduled_date"] = day.isoformat()
                    free[day] -= minutes
                    earliest[goal_id] = day
                    break
        if not result["scheduled_date"]:
            blocked.add(goal_id)
        updates.append(result)
    unscheduled = sum(not task["scheduled_date"] for task in updates)
    if unscheduled:
        warnings.append(f"{unscheduled}개 과제를 배치하지 못해 미배치 상태로 제안합니다. 과제를 더 작게 나누거나 기한·가용 시간을 조정하세요.")
    total = sum(_minutes(task) for task in updates if task["scheduled_date"])
    return {"tasks": updates, "warnings": list(dict.fromkeys(warnings)),
            "summary": f"미완료 {len(updates)}개 중 {len(updates)-unscheduled}개 재배치 · {unscheduled}개 미배치. 완료 기록은 변경하지 않습니다. 날짜 배치는 시간 기준 초안입니다.",
            "total_minutes": total, "available_minutes": available}


def habit_streak(habit: dict, today: Any = None) -> int:
    """Count consecutive scheduled occurrences, allowing today to remain open."""
    current = _today(today)
    weekdays = {int(day) for day in habit.get("weekdays", []) if isinstance(day, int) and 0 <= day <= 6}
    completions = {_day(value) for value in habit.get("completions", [])}
    completions.discard(None)
    if not weekdays or not completions:
        return 0
    if current not in completions:
        current -= timedelta(days=1)
    earliest = min(completions)
    count = 0
    while current >= earliest:
        if current.weekday() in weekdays:
            if current not in completions:
                break
            count += 1
        current -= timedelta(days=1)
    return count


def activity_series(tasks: list[dict], days: int = 7, today: Any = None) -> list[dict]:
    """Counts by scheduled date, not a claim about when ability increased."""
    end = _today(today)
    count = max(0, min(int(days), 366))
    result = []
    for offset in reversed(range(count)):
        day = end - timedelta(days=offset)
        related = [task for task in tasks if _day(task.get("scheduled_date")) == day]
        result.append({"date": day.isoformat(), "label": "월화수목금토일"[day.weekday()],
                       "planned": len(related), "completed": sum(bool(task.get("done")) for task in related)})
    return result


def insights(profile: dict, goals: list[dict], tasks: list[dict], metrics: list[dict],
             habits: list[dict] | None = None, today: Any = None) -> list[dict]:
    """Local coaching cards; all conclusions refer only to supplied records."""
    start = _today(today)
    end = start + timedelta(days=6)
    result = []
    active_goals = [goal for goal in goals if _active(goal)]
    if not active_goals:
        result.append({"title": "첫 목표를 구체화하세요", "body": "원하는 결과, 완료 기준, 기한을 입력하면 분야별 실행 초안을 만들 수 있습니다.", "kind": "proposal"})
    overdue = [task for task in tasks if not task.get("done") and _day(task.get("scheduled_date")) is not None and _day(task.get("scheduled_date")) < start]
    unscheduled = [task for task in tasks if not task.get("done") and _day(task.get("scheduled_date")) is None]
    if overdue:
        result.append({"title": f"지연 과제 {len(overdue)}개", "body": "미완료 사유를 기록하고 재계획 미리보기에서 새 날짜와 미배치 항목을 확인하세요.", "kind": "warning"})
    if unscheduled:
        result.append({"title": f"날짜가 없는 과제 {len(unscheduled)}개", "body": "가용 시간과 기한을 확인해 날짜를 배정하세요. 미배치 과제는 오늘 할 일에 자동 포함되지 않습니다.", "kind": "warning"})
    cap = max(0, int(_number(profile.get("weekly_hours")) * 60 / 7))
    reserved = sum(
        _minutes(task, actual=bool(task.get("done"))) for task in tasks
        if (day := _task_capacity_day(task)) is not None and start <= day <= end
    ) + sum(_habit_minutes(habits, start + timedelta(days=i)) for i in range(7))
    result.append({
        "title": "앞으로 7일의 시간 배분", "body": f"과제·습관 {reserved}분 / 균등 배분한 가용 {cap*7}분. 주당 순가용 시간을 7일로 나눈 계획 기준입니다. 고정 일정이 제외된 시간을 입력하세요.",
        "kind": "warning" if reserved > cap*7 else "info",
    })
    soon = [goal for goal in active_goals if (due := _day(goal.get("due_date"))) is not None and start <= due <= end]
    if soon:
        result.append({"title": f"7일 안에 마감하는 목표 {len(soon)}개", "body": " · ".join(str(goal.get("title", "목표")) for goal in soon[:3]) + ". 실제 완료 기준을 충족했는지 먼저 확인하세요.", "kind": "warning"})
    recorded = {metric.get("category") for metric in metrics}
    missing = [title for category, title in CATEGORIES.items() if category not in recorded]
    if missing:
        result.append({"title": "진단 근거를 보완하세요", "body": "기록이 없는 분야: " + ", ".join(missing) + ". 자기평가와 실제 측정 기록을 구분해 입력하세요.", "kind": "proposal"})
    prepared = [goal for goal in active_goals if goal.get("kind") != "numeric" and _related(goal, tasks) and all(task.get("done") for task in _related(goal, tasks))]
    if prepared:
        result.append({"title": "준비 완료와 최종 달성을 확인하세요", "body": " · ".join(str(goal.get("title", "목표")) for goal in prepared[:3]) + ": 준비 과제가 끝났습니다. 합격·취득·최종 결과물은 별도로 확인하세요.", "kind": "proposal"})
    income = _number(profile.get("monthly_income"))
    expense = _number(profile.get("monthly_expenses"))
    if expense > income:
        result.append({"title": "입력된 월 현금흐름 확인", "body": f"입력한 수입−지출이 {income-expense:,.0f}입니다. 금액·기준 기간을 확인하고 목표에 쓸 수 있는 예산을 다시 검토하세요. 투자수익은 가정하지 않았습니다.", "kind": "warning"})
    result.append({"title": "이번 주 회고를 다음 행동으로", "body": "잘한 점, 어려웠던 원인, 다음에 바꿀 행동을 하나씩 기록하세요. 아래 제안은 저장된 정보에 따른 규칙 기반 안내입니다.", "kind": "proposal"})
    return result
