"""Persistence and recovery tests; no Qt or personal data required."""

from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

from pgm.storage import Store
from pgm.planning_schema import normalize_planning


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.store = Store(self.root / "application")

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def goal(self, title="가상 테스트 목표"):
        return self.store.save_goal({"title": title, "category": "career", "kind": "deliverable",
                                     "due_date": "2027-01-31", "criteria": "가상 결과물 완성"})

    def test_profile_goals_and_actual_time_survive_restart(self):
        self.store.save_profile({"name": "가상 테스트", "weekly_hours": 7.5, "assets": 123000})
        goal_id = self.goal()
        task_id = self.store.save_task({"goal_id": goal_id, "title": "첫 단계", "minutes": 30,
                                       "scheduled_date": "2026-11-03"})
        self.store.set_task_done(task_id, True, 47)
        self.store.close()
        self.store = Store(self.root / "application")
        self.assertEqual(self.store.profile()["weekly_hours"], 7.5)
        self.assertEqual(self.store.goals()[0]["id"], goal_id)
        task = self.store.tasks()[0]
        self.assertTrue(task["done"])
        self.assertEqual(task["actual_minutes"], 47)
        self.assertTrue(task["completed_at"])
        self.store.set_task_done(task_id, False)
        self.assertFalse(self.store.tasks()[0]["done"])
        self.assertEqual(self.store.tasks()[0]["completed_at"], "")

    def test_partial_updates_preserve_other_goal_fields(self):
        goal_id = self.goal()
        self.store.save_goal({"id": goal_id, "title": "수정한 가상 목표"})
        goal = self.store.goals()[0]
        self.assertEqual(goal["title"], "수정한 가상 목표")
        self.assertEqual(goal["criteria"], "가상 결과물 완성")
        self.assertEqual(goal["due_date"], "2027-01-31")

    def test_planning_context_and_task_explanation_survive_restart_and_backup(self):
        goal_id = self.goal()
        planning = normalize_planning({
            "context": "가상 학습 목표", "requirements": "문제 풀이와 설명 문서",
            "evidence": "가상 사전 평가", "estimated_hours": 18,
            "weekly_hours": 2.5, "monthly_cost": 0,
            "reference_url": "https://example.com/synthetic-standard",
            "monthly_contribution": 75000, "contribution_source": "가상 별도 수입",
            "contribution_confirmed": True, "target_basis": "after_tax_cash",
            "tax_cost_basis": 900000, "tax_assumptions_confirmed": True,
        })
        self.store.save_goal({"id": goal_id, "planning": planning})
        self.store.save_task({"goal_id": goal_id, "title": "가상 실행 항목",
                              "done_when": "설명 문서와 결과를 확인", "rationale": "기준과 현재 결과물의 차이를 확인",
                              "analysis_key": "synthetic:1:2", "not_before": "2027-01-05"})
        archive = self.store.export_backup(self.root / "planning.pgmbackup")
        self.store.close()
        self.store = Store(self.root / "application")
        self.assertEqual(self.store.goals()[0]["planning"], planning)
        self.assertEqual(self.store.tasks()[0]["done_when"], "설명 문서와 결과를 확인")
        self.store.save_goal({"id": goal_id, "planning": normalize_planning()})
        self.store.restore_backup(archive)
        self.assertEqual(self.store.goals()[0]["planning"], planning)
        self.assertEqual(self.store.tasks()[0]["rationale"], "기준과 현재 결과물의 차이를 확인")
        self.assertEqual(self.store.tasks()[0]["analysis_key"], "synthetic:1:2")
        self.assertEqual(self.store.tasks()[0]["not_before"], "2027-01-05")

    def test_legacy_v01_records_and_archive_get_optional_defaults_without_data_loss(self):
        goal_id = self.goal()
        task_id = self.store.save_task({"goal_id": goal_id, "title": "가상 기존 과제"})
        profile = {
            "name": "가상 기존 사용자", "age": "25", "occupation": "가상 직무",
            "experience": "가상 기존 경력", "skills": "가상 기존 역량", "weekly_hours": 10.0,
            "monthly_budget": 0, "assets": 500000, "liabilities": 0,
            "monthly_income": 1000000, "monthly_expenses": 0,
        }
        goal = {k: v for k, v in self.store.goals()[0].items() if k not in {"id", "planning"}}
        task = {k: v for k, v in self.store.tasks()[0].items() if k not in {"id", "done_when", "rationale", "analysis_key", "not_before"}}
        with self.store._conn:
            self.store._conn.execute("UPDATE profile SET data = ? WHERE id = 1", (json.dumps(profile),))
            self.store._conn.execute("UPDATE goals SET data = ? WHERE id = ?", (json.dumps(goal), goal_id))
            self.store._conn.execute("UPDATE tasks SET data = ? WHERE id = ?", (json.dumps(task), task_id))
        archive = self.store.export_backup(self.root / "legacy-v01.pgmbackup")
        self.store.save_goal({"id": goal_id, "title": "복원 전에만 보이는 가상 수정"})
        self.store.restore_backup(archive)
        restored_profile = self.store.profile()
        self.assertEqual(restored_profile["occupation"], profile["occupation"])
        self.assertEqual(restored_profile["experience"], profile["experience"])
        self.assertEqual(restored_profile["skills"], profile["skills"])
        self.assertEqual(restored_profile["assets"], 500000)
        self.assertIsNone(restored_profile["liabilities"])
        self.assertEqual(restored_profile["career"], {})
        restored = self.store.goals()[0]
        self.assertEqual(restored["title"], goal["title"])
        self.assertEqual(restored["planning"], normalize_planning())
        self.assertIsNone(restored["planning"]["monthly_contribution"])
        self.assertEqual(self.store.tasks()[0]["done_when"], "")
        self.assertEqual(self.store.tasks()[0]["rationale"], "")
        self.assertEqual(self.store.tasks()[0]["analysis_key"], "")
        self.assertEqual(self.store.tasks()[0]["not_before"], "")

    def test_profile_validation_and_backup_keep_career_records_and_explicit_zero(self):
        data = {
            "assets": 800000, "liabilities": 0, "valuation_date": "2026-11-01",
            "planned_expenses": "가상 교재비", "career": {
                "desired_role": "가상 웹 개발",
                "skills": [{"name": "Python"}, {"name": "SQL", "evidence": "가상 학습 프로젝트"}],
                "portfolio": [{"title": "가상 결과물", "url": "https://example.com/demo"}],
                "visible_sections": ["education"],
            },
        }
        self.store.save_profile(data)
        original = self.store.profile()
        invalid = [
            {"valuation_date": "2026-02-30"},
            {"career": {"portfolio": [{"title": "가상", "url": "javascript:alert(1)"}]}},
            {"career": {"employment": [{"company": "가상", "start_month": "2026-11", "end_month": "2026-10"}]}},
            {"career": {"skills": [{"level": "가상"}]}},
        ]
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.store.save_profile(values)
            self.assertEqual(self.store.profile(), original)
        archive = self.store.export_backup(self.root / "profile.pgmbackup")
        self.store.save_profile({"career": {}, "liabilities": None})
        self.store.restore_backup(archive)
        self.assertEqual(self.store.profile(), original)
        self.assertEqual(self.store.profile()["liabilities"], 0)
        self.assertIsNone(self.store.profile()["monthly_expenses"])
        self.assertEqual(self.store.profile()["career"]["visible_sections"], ["education"])

    def test_analysis_task_identity_and_start_date_remain_on_partial_update(self):
        goal_id = self.goal()
        task_id = self.store.save_task({"goal_id": goal_id, "title": "가상 후속 단계",
                                       "analysis_key": "synthetic-goal:phase:action", "not_before": "2027-01-04"})
        self.store.save_task({"id": task_id, "scheduled_date": "2027-01-06"})
        self.assertEqual(self.store.tasks()[0]["analysis_key"], "synthetic-goal:phase:action")
        self.assertEqual(self.store.tasks()[0]["not_before"], "2027-01-04")
        original = self.store.tasks()
        with self.assertRaises(ValueError):
            self.store.save_task({"id": task_id, "not_before": "not-a-date"})
        self.assertEqual(self.store.tasks(), original)

    def test_invalid_planning_settings_cannot_replace_saved_goal(self):
        goal_id = self.goal()
        original = self.store.goals()
        for planning in [{"tax_rate": 100}, {"weekly_hours": 169}, {"estimated_hours": float("nan")},
                         {"monthly_contribution": -1}, {"contribution_confirmed": "yes"},
                         {"reference_url": "javascript:alert(1)"}, {"target_basis": []},
                         {"unknown_assumption": "not supported"}]:
            with self.subTest(planning=planning), self.assertRaises(ValueError):
                self.store.save_goal({"id": goal_id, "planning": planning})
            self.assertEqual(self.store.goals(), original)

    def test_unknown_and_confirmed_zero_planning_values_are_distinct(self):
        goal_id = self.goal()
        self.assertIsNone(self.store.goals()[0]["planning"]["monthly_cost"])
        self.store.save_goal({"id": goal_id, "planning": {"monthly_cost": 0, "monthly_contribution": 0}})
        self.assertEqual(self.store.goals()[0]["planning"]["monthly_cost"], 0)
        self.assertEqual(self.store.goals()[0]["planning"]["monthly_contribution"], 0)

    def test_invalid_records_do_not_change_existing_data(self):
        self.store.save_profile({"name": "기존 가상 이름"})
        for values in [{"weekly_hours": -1}, {"weekly_hours": float("nan")}, {"assets": -10}, {"api_key": "not-a-real-key"}]:
            with self.assertRaises(ValueError):
                self.store.save_profile(values)
        self.assertEqual(self.store.profile()["name"], "기존 가상 이름")
        self.assertEqual(self.store.profile()["weekly_hours"], 10)
        for values in [{"title": ""}, {"title": "가상", "category": "unknown"},
                       {"title": "가상", "target": float("inf")}, {"title": "가상", "due_date": "2026-02-30"}]:
            with self.assertRaises(ValueError):
                self.store.save_goal(values)
        self.assertEqual(self.store.goals(), [])

    def test_bulk_tasks_are_atomic_and_goal_links_cannot_break(self):
        goal_id = self.goal()
        with self.assertRaises(ValueError):
            self.store.add_tasks([{"goal_id": goal_id, "title": "정상 가상 과제"},
                                  {"goal_id": goal_id + 100, "title": "연결 없는 과제"}])
        self.assertEqual(self.store.tasks(), [])
        self.store.add_tasks([{"goal_id": goal_id, "title": "가상 과제"}])
        self.store.delete_goal(goal_id)
        self.assertEqual(self.store.goals(), [])
        self.assertEqual(self.store.tasks(), [])

    def test_replan_updates_are_atomic_and_keep_completed_records(self):
        goal_id = self.goal()
        first = self.store.save_task({"goal_id": goal_id, "title": "가상 첫 과제", "scheduled_date": "2026-11-03"})
        second = self.store.save_task({"goal_id": goal_id, "title": "가상 두 번째 과제", "scheduled_date": "2026-11-04"})
        completed = self.store.save_task({"goal_id": goal_id, "title": "가상 완료 과제", "done": True})
        original = self.store.tasks()
        with self.assertRaises(ValueError):
            self.store.apply_task_updates([{"id": first, "scheduled_date": "2026-11-10"},
                                           {"id": second, "goal_id": goal_id + 100}])
        self.assertEqual(self.store.tasks(), original)
        with self.assertRaises(ValueError):
            self.store.apply_task_updates([{"id": first, "scheduled_date": "2026-11-10"},
                                           {"id": completed, "scheduled_date": "2026-11-11"}])
        self.assertEqual(self.store.tasks(), original)
        self.store.apply_task_updates([{"id": first, "scheduled_date": "2026-11-10"},
                                       {"id": second, "scheduled_date": ""}])
        updated = self.store.tasks()
        self.assertEqual(updated[0]["scheduled_date"], "2026-11-10")
        self.assertEqual(updated[1]["scheduled_date"], "")
        self.assertEqual(updated[2], original[2])

    def test_form_task_completion_normalizes_timestamp_on_transitions(self):
        goal_id = self.goal()
        task_id = self.store.save_task({"goal_id": goal_id, "title": "가상 과제", "done": False})
        unfinished = self.store.tasks()[0]
        self.store.save_task({**unfinished, "done": True, "actual_minutes": 45})
        completed = self.store.tasks()[0]
        self.assertTrue(completed["completed_at"])
        self.assertEqual(completed["actual_minutes"], 45)
        self.store.save_task({**completed, "done": False})
        self.assertEqual(self.store.tasks()[0]["completed_at"], "")
        self.assertEqual(self.store.tasks()[0]["id"], task_id)

    def test_completion_never_infers_actual_time_from_estimate(self):
        goal_id = self.goal()
        task_id = self.store.save_task({"goal_id": goal_id, "title": "가상 시간 기록 과제", "minutes": 60})
        self.store.set_task_done(task_id, True)
        self.assertTrue(self.store.tasks()[0]["done"])
        self.assertEqual(self.store.tasks()[0]["actual_minutes"], 0)
        self.store.set_task_done(task_id, True, actual_minutes=43)
        self.assertEqual(self.store.tasks()[0]["actual_minutes"], 43)
        self.store.set_task_done(task_id, False)
        self.assertEqual(self.store.tasks()[0]["actual_minutes"], 43)
        self.store.set_task_done(task_id, True)
        self.assertEqual(self.store.tasks()[0]["actual_minutes"], 43)
        self.store.set_task_done(task_id, True, actual_minutes=0)
        self.assertEqual(self.store.tasks()[0]["actual_minutes"], 0)

    def test_demo_marker_is_portable_and_personal_is_the_default(self):
        self.assertFalse(self.store.is_demo())
        self.store.seed_demo(date(2026, 11, 3))
        self.assertTrue(self.store.is_demo())
        archive = self.store.export_backup(self.root / "demo.pgmbackup")
        other = Store(self.root / "new-workspace")
        try:
            self.assertFalse(other.is_demo())
            before = other.restore_backup(archive)
            self.assertTrue(other.is_demo())
            other.restore_backup(before)
            self.assertFalse(other.is_demo())
            self.assertIsNone(other.profile()["assets"])
            self.assertEqual(other.profile()["name"], "")
        finally:
            other.close()

    def test_habit_toggle_schedule_and_history_when_schedule_changes(self):
        habit_id = self.store.save_habit({"title": "가상 월요일 습관", "weekdays": [0], "minutes": 15})
        self.store.toggle_habit(habit_id, "2026-11-02")  # Monday
        self.assertEqual(self.store.habits()[0]["completions"], ["2026-11-02"])
        with self.assertRaises(ValueError):
            self.store.toggle_habit(habit_id, "2026-11-03")
        self.store.save_habit({"id": habit_id, "weekdays": [1]})
        self.assertEqual(self.store.habits()[0]["completions"], ["2026-11-02"])
        self.store.toggle_habit(habit_id, "2026-11-03")
        self.store.toggle_habit(habit_id, "2026-11-03")
        self.assertEqual(self.store.habits()[0]["completions"], ["2026-11-02"])

    def test_metrics_and_reviews_keep_evidence_and_dates(self):
        self.store.add_metric({"category": "learning", "label": "가상 점수", "value": 620,
            "unit": "점", "evidence_kind": "self", "source": "가상 자기평가", "recorded_date": "2026-11-03"})
        self.store.add_review({"date": "2026-11-02", "good": "가상 회고"})
        self.store.add_review({"date": "2026-11-03", "next_action": "가상 다음 행동"})
        self.assertEqual(self.store.metrics()[0]["source"], "가상 자기평가")
        self.assertEqual(self.store.reviews()[0]["date"], "2026-11-03")
        with self.assertRaises(ValueError):
            self.store.add_review({})

    def test_backup_restores_records_and_unicode_attachments_and_keeps_before_copy(self):
        self.store.save_profile({"name": "백업된 가상 이름"})
        self.goal()
        folder = self.store.attachments_dir / "포트폴리오"
        folder.mkdir()
        (folder / "설명.txt").write_text("가상 첨부 파일", encoding="utf-8")
        backup = self.store.export_backup(self.root / "portable.pgmbackup")
        with zipfile.ZipFile(backup) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertIs(manifest["encrypted"], False)
        self.store.save_profile({"name": "복원 전 가상 이름"})
        (folder / "설명.txt").write_text("복원 전 내용", encoding="utf-8")
        before = self.store.restore_backup(backup)
        self.assertTrue(before.is_file())
        self.assertEqual(self.store.profile()["name"], "백업된 가상 이름")
        self.assertEqual((folder / "설명.txt").read_text(encoding="utf-8"), "가상 첨부 파일")
        self.assertEqual(len(self.store.goals()), 1)
        self.store.restore_backup(before)
        self.assertEqual(self.store.profile()["name"], "복원 전 가상 이름")
        self.assertEqual((folder / "설명.txt").read_text(encoding="utf-8"), "복원 전 내용")

    def test_backup_prevents_overwriting_active_database_or_attachments(self):
        self.goal()
        with self.assertRaises(ValueError):
            self.store.export_backup(self.store.db_path)
        with self.assertRaises(ValueError):
            self.store.export_backup(self.store.attachments_dir / "backup.zip")
        self.assertEqual(len(self.store.goals()), 1)

    def test_truncated_and_arbitrary_zip_do_not_touch_current_database(self):
        self.store.save_profile({"name": "보존할 가상 이름"})
        corrupt = self.root / "corrupt.pgmbackup"
        corrupt.write_bytes(b"not a zip")
        with self.assertRaises(ValueError):
            self.store.restore_backup(corrupt)
        with zipfile.ZipFile(corrupt, "w") as archive:
            archive.writestr("arbitrary.txt", "not a PGM backup")
        with self.assertRaises(ValueError):
            self.store.restore_backup(corrupt)
        self.assertEqual(self.store.profile()["name"], "보존할 가상 이름")
        self.assertFalse((self.store.data_dir / "backups").exists())

    def test_traversal_is_rejected_without_creating_an_outside_file(self):
        self.store.save_profile({"name": "보존할 가상 이름"})
        attack = self.root / "traversal.zip"
        with zipfile.ZipFile(attack, "w") as archive:
            archive.writestr("../outside.txt", "do not extract")
            archive.writestr("manifest.json", "{}")
        with self.assertRaises(ValueError):
            self.store.restore_backup(attack)
        self.assertFalse((self.root / "outside.txt").exists())
        self.assertEqual(self.store.profile()["name"], "보존할 가상 이름")

    def test_modified_file_hash_is_rejected_before_restoration(self):
        self.store.save_profile({"name": "보존할 가상 이름"})
        backup = self.store.export_backup(self.root / "source.zip")
        with zipfile.ZipFile(backup) as archive:
            contents = {name: archive.read(name) for name in archive.namelist()}
        contents["database.sqlite3"] = b"modified"
        attack = self.root / "modified.zip"
        with zipfile.ZipFile(attack, "w") as archive:
            for name, value in contents.items():
                archive.writestr(name, value)
        with self.assertRaises(ValueError):
            self.store.restore_backup(attack)
        self.assertEqual(self.store.profile()["name"], "보존할 가상 이름")

    def tampered_database(self, sql: str, parameters=()) -> Path:
        backup = self.store.export_backup(self.root / "source.zip")
        with zipfile.ZipFile(backup) as archive:
            contents = {name: archive.read(name) for name in archive.namelist()}
        database = self.root / "tampered.sqlite3"
        database.write_bytes(contents["database.sqlite3"])
        connection = sqlite3.connect(database)
        try:
            with connection:
                connection.execute(sql, parameters)
        finally:
            connection.close()
        contents["database.sqlite3"] = database.read_bytes()
        manifest = json.loads(contents["manifest.json"])
        manifest["files"]["database.sqlite3"] = hashlib.sha256(contents["database.sqlite3"]).hexdigest()
        contents["manifest.json"] = json.dumps(manifest).encode()
        attack = self.root / "tampered.zip"
        with zipfile.ZipFile(attack, "w") as archive:
            for name, value in contents.items():
                archive.writestr(name, value)
        return attack

    def test_hash_valid_but_invalid_domain_data_is_rejected(self):
        self.store.save_profile({"name": "보존할 가상 이름"})
        self.goal()
        record = {key: value for key, value in self.store.goals()[0].items() if key != "id"}
        record["category"] = "not-an-existing-category"
        attack = self.tampered_database("UPDATE goals SET data = ?", (json.dumps(record),))
        with self.assertRaises(ValueError):
            self.store.restore_backup(attack)
        self.assertEqual(self.store.goals()[0]["category"], "career")
        self.assertEqual(self.store.profile()["name"], "보존할 가상 이름")

    def test_extra_database_trigger_is_rejected(self):
        self.goal()
        attack = self.tampered_database("CREATE TRIGGER unexpected AFTER INSERT ON goals BEGIN DELETE FROM profile; END")
        with self.assertRaises(ValueError):
            self.store.restore_backup(attack)
        self.assertEqual(len(self.store.goals()), 1)
        self.assertEqual(self.store.profile()["name"], "")

    def test_future_schema_version_is_rejected(self):
        self.goal()
        attack = self.tampered_database("UPDATE meta SET value = '999' WHERE key = 'schema_version'")
        with self.assertRaises(ValueError):
            self.store.restore_backup(attack)
        self.assertEqual(len(self.store.goals()), 1)

    def test_demo_is_explicit_fictional_and_never_overwrites_existing_records(self):
        self.assertTrue(self.store.seed_demo(date(2026, 11, 3)))
        self.assertEqual({goal["category"] for goal in self.store.goals()},
                         {"finance", "career", "learning", "health", "life", "habits"})
        self.assertIn("가상", self.store.profile()["experience"])
        self.assertTrue(all("가상" in metric["source"] for metric in self.store.metrics()))
        count = len(self.store.tasks())
        self.assertFalse(self.store.seed_demo(date(2026, 11, 4)))
        self.assertEqual(len(self.store.tasks()), count)


if __name__ == "__main__":
    unittest.main()
