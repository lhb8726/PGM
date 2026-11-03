"""Offscreen integration checks for the actual Qt screens and local persistence."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QLabel, QMessageBox

from pgm.app import MainWindow
from pgm.constants import CATEGORIES, NAVIGATION
from pgm.dialogs import GoalDialog, HabitDialog, MetricDialog, ReviewDialog, TaskDialog
from pgm.storage import Store


class DesktopIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="pgm-ui-test-")
        self.data_dir = Path(self.directory.name) / "workspace"
        self.store = Store(self.data_dir)
        self.assertTrue(self.store.seed_demo())
        self.warning_patch = patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Ok)
        self.warning = self.warning_patch.start()
        self.window = MainWindow(self.store, demo=True)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        if self.window is not None:
            self.window.close()
            self.window.deleteLater()
        self.app.processEvents()
        self.warning_patch.stop()
        self.directory.cleanup()

    def assert_no_guard_error(self):
        self.warning.assert_not_called()

    def test_demo_navigation_renders_all_pages_without_guard_errors(self):
        self.assertEqual(len(self.store.goals()), 6)
        for key, _, title in NAVIGATION:
            with self.subTest(page=key):
                self.window.navigate(key)
                self.app.processEvents()
                self.assertEqual(self.window.page_key, key)
                self.assertTrue(self.window.nav[key].isChecked())
                self.assertIn(title, self.window.breadcrumb.text())
                self.assertIsNotNone(self.window.scroll.widget())
        self.assert_no_guard_error()

    def test_empty_workspace_does_not_inject_demo_records(self):
        empty = Store(Path(self.directory.name) / "empty")
        window = MainWindow(empty)
        try:
            for key, _, _ in NAVIGATION:
                window.navigate(key)
                self.app.processEvents()
            self.assertFalse(window.demo)
            self.assertEqual(empty.goals(), [])
            self.assertEqual(empty.tasks(), [])
            self.assertEqual(empty.metrics(), [])
            self.assert_no_guard_error()
        finally:
            window.close()
            window.deleteLater()

    def test_profile_edit_saves_to_sqlite_and_reloads_fields(self):
        self.window.navigate("profile")
        self.window.profile_fields["name"].setText("가상 통합 테스트")
        self.window.profile_fields["occupation"].setText("가상 프로젝트 개발자")
        self.window.profile_fields["weekly_hours"].setValue(9.5)
        self.window.save_profile()
        self.app.processEvents()
        self.assertEqual(self.store.profile()["name"], "가상 통합 테스트")
        self.assertEqual(self.store.profile()["weekly_hours"], 9.5)
        self.assertEqual(self.window.profile_fields["occupation"].text(), "가상 프로젝트 개발자")
        self.assert_no_guard_error()

    def test_delete_actions_require_confirmation_and_remove_linked_records(self):
        goal = self.store.goals()[0]
        dialog = QDialog(self.window)
        self.window.delete_record("goal", goal["id"], dialog)
        self.assertTrue(any(item["id"] == goal["id"] for item in self.store.goals()))
        self.warning.reset_mock()
        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
            self.window.delete_record("goal", goal["id"], dialog)
            self.assertFalse(any(item["goal_id"] == goal["id"] for item in self.store.tasks()))
            habit = self.store.habits()[0]
            self.window.delete_record("habit", habit["id"], dialog)
            self.assertFalse(any(item["id"] == habit["id"] for item in self.store.habits()))
            task = self.store.tasks()[0]
            self.window.delete_record("task", task["id"], dialog)
            self.assertFalse(any(item["id"] == task["id"] for item in self.store.tasks()))
        self.assert_no_guard_error()

    def test_category_and_search_filter_change_visible_goal_selection(self):
        self.window.navigate("goals")
        for category in CATEGORIES:
            self.window.category_combo.setCurrentIndex(self.window.category_combo.findData(category))
            self.app.processEvents()
            self.assertEqual(self.window.category, category)
            self.assertTrue(all(goal["category"] == category for goal in self.window.filtered_goals()))
            self.assertEqual(len(self.window.filtered_goals()), 1)
        self.window.category_combo.setCurrentIndex(0)
        self.window.filter_search("포트폴리오")
        self.assertEqual(self.window.goal_search, "포트폴리오")
        self.assertEqual(self.window.category, "all")
        self.assert_no_guard_error()

    def test_task_checkbox_completion_survives_application_reopen(self):
        self.window.navigate("today")
        target = next(task for task in self.store.tasks()
                      if task["scheduled_date"] == date.today().isoformat() and not task["done"])
        check = next(check for check in self.window.scroll.widget().findChildren(QCheckBox)
                     if check.accessibleName() == f"{target['title']} 완료")
        check.setChecked(True)
        self.app.processEvents()
        saved = next(task for task in self.store.tasks() if task["id"] == target["id"])
        self.assertTrue(saved["done"])
        self.assertTrue(saved["completed_at"])
        self.assertEqual(saved["actual_minutes"], 0)
        self.assertTrue(any("실제 시간 미기록" in item.text()
                            for item in self.window.scroll.widget().findChildren(QLabel)))
        self.assertEqual(next(goal for goal in self.store.goals() if goal["id"] == target["goal_id"])["status"], "active")
        self.window.close()
        self.window.deleteLater()
        self.window = None
        reopened = Store(self.data_dir)
        try:
            self.assertTrue(next(task for task in reopened.tasks() if task["id"] == target["id"])["done"])
        finally:
            reopened.close()
        self.assert_no_guard_error()

    def test_habit_checkbox_tracks_scheduled_day_and_removes_on_second_toggle(self):
        self.window.navigate("today")
        habit = next(habit for habit in self.store.habits() if date.today().weekday() in habit["weekdays"])
        target = next(check for check in self.window.scroll.widget().findChildren(QCheckBox) if check.text() == habit["title"])
        self.assertTrue(target.isEnabled())
        target.setChecked(True)
        self.app.processEvents()
        saved = next(item for item in self.store.habits() if item["id"] == habit["id"])
        self.assertIn(date.today().isoformat(), saved["completions"])
        target = next(check for check in self.window.scroll.widget().findChildren(QCheckBox) if check.text() == habit["title"])
        target.setChecked(False)
        self.app.processEvents()
        saved = next(item for item in self.store.habits() if item["id"] == habit["id"])
        self.assertNotIn(date.today().isoformat(), saved["completions"])
        self.assert_no_guard_error()

    def test_all_dialog_values_are_accepted_by_the_real_store(self):
        dialogs = []
        try:
            goal = GoalDialog(parent=self.window)
            dialogs.append(goal)
            goal.title_input.setText("가상 UI 결과물")
            goal.criteria_input.setPlainText("완성 파일과 검토 기록 확인")
            goal.accept()
            self.assertEqual(goal.result(), QDialog.DialogCode.Accepted)
            goal_id = self.store.save_goal(goal.values())
            task = TaskDialog(self.store.goals(), parent=self.window)
            dialogs.append(task)
            task.goal_input.setCurrentIndex(task.goal_input.findData(goal_id))
            task.title_input.setText("가상 구현 과제")
            task.scheduled_input.setChecked(False)
            task.accept()
            self.assertEqual(task.result(), QDialog.DialogCode.Accepted)
            task_id = self.store.save_task(task.values())
            self.assertEqual(next(item for item in self.store.tasks() if item["id"] == task_id)["scheduled_date"], "")
            metric = MetricDialog("career", self.window)
            dialogs.append(metric)
            metric.label_input.setText("가상 검토 항목")
            metric.unit_input.setText("개")
            metric.value_input.setValue(2)
            metric.accept()
            self.assertEqual(metric.result(), QDialog.DialogCode.Accepted)
            self.store.add_metric(metric.values())
            habit = HabitDialog(parent=self.window)
            dialogs.append(habit)
            habit.title_input.setText("가상 UI 습관")
            habit.accept()
            self.assertEqual(habit.result(), QDialog.DialogCode.Accepted)
            self.store.save_habit(habit.values())
            review = ReviewDialog(self.window)
            dialogs.append(review)
            review.good_input.setPlainText("가상 회고: 작은 과제를 완료했습니다.")
            review.accept()
            self.assertEqual(review.result(), QDialog.DialogCode.Accepted)
            self.store.add_review(review.values())
            self.window.refresh()
            self.app.processEvents()
            self.assert_no_guard_error()
        finally:
            for dialog in dialogs:
                dialog.close()
                dialog.deleteLater()

    def test_plan_preview_cancel_is_read_only_then_accept_persists_tasks(self):
        goal_id = self.store.save_goal({"title": "가상 신규 학습 목표", "category": "learning", "kind": "deliverable",
                                       "due_date": (date.today()+timedelta(days=28)).isoformat(), "criteria": "결과물 확인"})
        before = self.store.tasks()
        with patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            self.window.plan()
        self.assertEqual(self.store.tasks(), before)
        with patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Accepted):
            self.window.plan()
        after = self.store.tasks()
        self.assertGreater(len(after), len(before))
        self.assertTrue(any(task["goal_id"] == goal_id for task in after))
        for original in before:
            self.assertEqual(next(task for task in after if task["id"] == original["id"]), original)
        self.assertTrue(any(item["summary"] == "로드맵 초안 적용" for item in self.store.history()))
        self.assert_no_guard_error()

    def test_theme_preference_and_selected_execution_date(self):
        old_style = self.app.styleSheet()
        self.window.set_light(True)
        self.assertTrue(self.window.preferences.value("light", False, type=bool))
        self.assertNotEqual(self.app.styleSheet(), old_style)
        self.window.set_light(False)
        self.window.navigate("today")
        previous = QDate.currentDate().addDays(-1)
        self.window.set_execution_date(previous)
        self.assertEqual(self.window.execution_date.isoformat(), previous.toString("yyyy-MM-dd"))
        self.assert_no_guard_error()

    def test_small_generated_task_and_long_actual_time_survive_edit_dialog(self):
        original = dict(next(task for task in self.store.tasks() if not task["done"]))
        original.update(minutes=1, actual_minutes=10000)
        dialog = TaskDialog(self.store.goals(), original, self.window)
        try:
            self.assertEqual(dialog.values()["minutes"], 1)
            self.assertEqual(dialog.values()["actual_minutes"], 10000)
            self.store.save_task(dialog.values())
            saved = next(task for task in self.store.tasks() if task["id"] == original["id"])
            self.assertEqual(saved["minutes"], 1)
            self.assertEqual(saved["actual_minutes"], 10000)
        finally:
            dialog.close()
            dialog.deleteLater()
        self.assert_no_guard_error()

    def test_demo_provenance_survives_backup_and_new_window_without_demo_flag(self):
        archive = Path(self.directory.name) / "demo-transfer.pgmbackup"
        self.store.export_backup(archive)
        destination = Store(Path(self.directory.name) / "other-pc")
        self.assertFalse(destination.is_demo())
        destination.restore_backup(archive)
        destination.close()
        reopened = Store(Path(self.directory.name) / "other-pc")
        window = MainWindow(reopened, demo=False)
        try:
            self.assertTrue(reopened.is_demo())
            self.assertTrue(window.demo)
            self.assertTrue(any("DEMO" in item.text() for item in window.scroll.widget().findChildren(QLabel)))
            self.assert_no_guard_error()
        finally:
            window.close()
            window.deleteLater()

    def test_duplicate_replan_preview_apply_is_atomic_and_reports_error(self):
        before = self.store.tasks()
        pending = dict(next(task for task in before if not task["done"]))
        pending["scheduled_date"] = (date.today()+timedelta(days=4)).isoformat()
        preview = {"tasks": [pending, dict(pending)], "warnings": [], "summary": "가상 중복 변경 검증"}
        with patch("pgm.app.engine.replan", return_value=preview), \
                patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Accepted):
            self.window.plan(True)
        self.assertEqual(self.store.tasks(), before)
        self.warning.assert_called_once()
        self.assertIn("중복", self.warning.call_args.args[2])

    def test_backup_roundtrip_refreshes_profile_and_restores_attachment(self):
        attachment = self.store.attachments_dir / "가상-result.txt"
        attachment.write_text("가상 결과물", encoding="utf-8")
        archive = Path(self.directory.name) / "transfer.pgmbackup"
        self.store.export_backup(archive)
        self.store.save_profile({**self.store.profile(), "name": "복원 전 가상 변경"})
        attachment.unlink()
        before = self.store.restore_backup(archive)
        self.window.navigate("profile")
        self.app.processEvents()
        self.assertTrue(before.is_file())
        self.assertEqual(self.window.profile_fields["name"].text(), "데모 사용자")
        self.assertEqual(attachment.read_text(encoding="utf-8"), "가상 결과물")
        self.assert_no_guard_error()


if __name__ == "__main__":
    unittest.main()
