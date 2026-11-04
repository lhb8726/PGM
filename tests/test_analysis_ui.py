"""Integration coverage for inspectable goal reports and explicit plan changes."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox, QTableWidget

from pgm.analysis import analyze_goal
from pgm.analysis_view import GoalAnalysisDialog
from pgm.app import MainWindow
from pgm.dialogs import GoalDialog
from pgm.engine import build_plan
from pgm.storage import Store


class GoalAnalysisIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="pgm-analysis-ui-")
        self.root = Path(self.directory.name)
        self.store = Store(self.root / "workspace")
        self.store.save_profile({"name": "가상 분석 사용자", "weekly_hours": 8, "monthly_budget": 100000})
        self.warning_patch = patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Ok)
        self.warning = self.warning_patch.start()
        self.window = MainWindow(self.store)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.warning_patch.stop()
        self.directory.cleanup()

    def learning_goal(self):
        identifier = self.store.save_goal({
            "title": "가상 분석 과제 완성", "category": "learning", "kind": "deliverable",
            "due_date": (date.today() + timedelta(days=120)).isoformat(), "criteria": "문제 풀이와 설명 문서 확인",
            "planning": {"context": "가상 프로젝트 학습", "requirements": "필수 문제 풀이와 설명 문서",
                         "evidence": "가상 사전 평가 기록", "estimated_hours": 18, "weekly_hours": 3,
                         "monthly_cost": 0, "reference_url": "https://example.com/synthetic-learning"},
        })
        return next(goal for goal in self.store.goals() if goal["id"] == identifier)

    def report_and_plan(self, goal):
        report = analyze_goal(goal, self.store.profile(), self.store.metrics(), self.store.tasks(),
                              self.store.habits(), self.store.goals())
        plan = build_plan([goal], self.store.tasks(), self.store.profile(), self.store.habits(),
                          reports={goal["id"]: report}, metrics=self.store.metrics())
        return report, plan

    def test_report_renders_four_tabs_with_evidence_and_completion_criteria(self):
        goal = self.learning_goal()
        report, plan = self.report_and_plan(goal)
        dialog = GoalAnalysisDialog(report, plan, self.window)
        try:
            dialog.show()
            for index in range(dialog.tabs.count()):
                dialog.tabs.setCurrentIndex(index)
                self.app.processEvents()
            self.assertEqual([dialog.tabs.tabText(i) for i in range(dialog.tabs.count())],
                             ["진단·시나리오", "단계별 로드맵", "가까운 실행 계획", "근거·자료"])
            self.assertTrue(dialog.apply_button.isEnabled())
            texts = "\n".join(item.text() for item in dialog.findChildren(QLabel))
            self.assertIn("가상 분석 과제 완성", texts)
            self.assertIn("완료 기준", texts)
            self.assertIn("규칙 기반 분석", texts)
            self.assertIn("자동 검증", texts)
            self.assertTrue(all(task["done_when"] and task["rationale"] for task in plan["tasks"]))
            self.warning.assert_not_called()
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_narrow_report_reflows_long_cells_and_keeps_source_links_readable(self):
        long_note = "가상 완료 기준을 점검하고 필요한 증빙을 항목별로 확인합니다. " * 20
        report = {
            "title": "가상 좁은 창 분석",
            "generated_on": date.today().isoformat(),
            "scenarios": [{"name": "가상 조건", "note": long_note}],
            "sources": [{"title": "가상 링크", "url": "https://example.com/" + "a" * 1600}],
        }
        dialog = GoalAnalysisDialog(report, {"tasks": []}, self.window)
        try:
            dialog.show()
            dialog.resize(560, 420)
            QTest.qWait(20)
            self.assertEqual(dialog.width(), 560)
            overview = dialog.tabs.currentWidget()
            table = overview.findChild(QTableWidget)
            automatic_height = table.rowHeight(0)
            table.resizeRowsToContents()
            self.assertGreaterEqual(automatic_height, table.rowHeight(0))
            self.assertGreater(table.rowHeight(0), table.viewport().height())
            self.assertEqual(table.verticalScrollMode(), QTableWidget.ScrollMode.ScrollPerPixel)
            self.assertGreater(table.verticalScrollBar().maximum(), 0)
            header = table.horizontalHeader()
            for column in range(table.columnCount()):
                self.assertGreaterEqual(header.sectionSize(column), header.sectionSizeHint(column))

            dialog.tabs.setCurrentIndex(3)
            QTest.qWait(20)
            self.assertEqual(dialog.tabs.currentWidget().horizontalScrollBar().maximum(), 0)
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_after_tax_report_displays_unknown_without_fabricating_tax_basis(self):
        identifier = self.store.save_goal({
            "title": "가상 세후 자금 목표", "category": "finance", "kind": "numeric", "unit": "원",
            "baseline": 1200000, "current": 1200000, "target": 4500000,
            "due_date": (date.today() + timedelta(days=730)).isoformat(), "criteria": "가상 세후 현금 기준 확인",
            "planning": {"monthly_contribution": 120000, "contribution_source": "가상 신규 자금",
                         "contribution_confirmed": True, "target_basis": "after_tax_cash"},
        })
        goal = next(g for g in self.store.goals() if g["id"] == identifier)
        report, plan = self.report_and_plan(goal)
        self.assertIsNone(report["finance"]["cost_basis"])
        self.assertFalse(report["finance"]["tax_ready"])
        self.assertEqual(report["status"], "needs_input")
        self.assertNotIn("after_tax_cash", report["finance"]["comparison"])
        dialog = GoalAnalysisDialog(report, plan, self.window)
        try:
            tables = dialog.findChildren(QTableWidget)
            values = [table.item(i, j).text() for table in tables for i in range(table.rowCount())
                      for j in range(table.columnCount()) if table.item(i, j) is not None]
            self.assertIn("정보 부족", values)
            text = "\n".join(item.text() for item in dialog.findChildren(QLabel))
            self.assertIn("원화 취득원가", text)
            self.assertIn("세후 금액을 계산하지 않습니다", text)
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_saving_a_goal_automatically_opens_its_detailed_analysis(self):
        values = {"title": "가상 신규 저장 목표", "category": "career", "kind": "deliverable",
                  "due_date": (date.today() + timedelta(days=90)).isoformat(), "criteria": "필수 결과물 확인",
                  "planning": {"requirements": "가상 필수 기능", "evidence": "가상 기존 결과물"}}
        with patch.object(GoalDialog, "exec", return_value=QDialog.DialogCode.Accepted), \
             patch.object(GoalDialog, "values", return_value=values), \
             patch.object(self.window, "show_goal_analysis") as show:
            self.window.edit_goal()
        show.assert_called_once()
        self.assertEqual(show.call_args.args[0]["title"], values["title"])
        self.assertIn("planning", show.call_args.args[0])
        self.warning.assert_not_called()

    def test_accept_adds_only_previewed_tasks_and_keeps_explanations(self):
        goal = self.learning_goal()
        _report, plan = self.report_and_plan(goal)
        self.assertTrue(plan["tasks"])
        with patch.object(GoalAnalysisDialog, "exec", return_value=QDialog.DialogCode.Accepted):
            self.window.show_goal_analysis(goal)
        tasks = self.store.tasks()
        self.assertEqual(len(tasks), len(plan["tasks"]))
        self.assertTrue(all(task["done_when"] and task["rationale"] and task["analysis_key"] for task in tasks))
        self.assertTrue(all(task["not_before"] for task in tasks))
        self.assertTrue(self.store.history())
        self.warning.assert_not_called()

    def test_reject_leaves_goal_tasks_and_history_unchanged(self):
        goal = self.learning_goal()
        before = (self.store.goals(), self.store.tasks(), self.store.history())
        with patch.object(GoalAnalysisDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            self.window.show_goal_analysis(goal)
        self.assertEqual((self.store.goals(), self.store.tasks(), self.store.history()), before)
        self.warning.assert_not_called()

    def test_edit_result_returns_to_goal_conditions_without_applying_tasks(self):
        goal = self.learning_goal()
        with patch.object(GoalAnalysisDialog, "exec", return_value=2), \
             patch.object(self.window, "edit_goal") as edit:
            self.window.show_goal_analysis(goal)
        edit.assert_called_once()
        self.assertEqual(edit.call_args.args[0]["id"], goal["id"])
        self.assertEqual(self.store.tasks(), [])
        self.warning.assert_not_called()

    def test_local_markdown_export_is_user_initiated_and_has_analysis_sections(self):
        goal = self.learning_goal()
        report, plan = self.report_and_plan(goal)
        dialog = GoalAnalysisDialog(report, plan, self.window)
        destination = self.root / "synthetic-analysis.md"
        try:
            self.assertFalse(destination.exists())
            with patch("pgm.analysis_view.QFileDialog.getSaveFileName", return_value=(str(destination), "Markdown (*.md)")):
                dialog.export()
            text = destination.read_text(encoding="utf-8")
            for section in ["입력된 사실·기록", "계산 가정·해석", "추가로 확인할 정보", "단계별 로드맵", "완료 기준", "근거 자료"]:
                self.assertIn(section, text)
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_legacy_goal_edit_leaves_new_unknown_assumptions_empty(self):
        legacy = {"id": 77, "title": "가상 이전 버전 목표", "category": "career", "kind": "deliverable",
                  "due_date": (date.today() + timedelta(days=90)).isoformat(), "criteria": "기존 완료 기준"}
        dialog = GoalDialog(legacy, self.window)
        try:
            planning = dialog.values()["planning"]
            self.assertIsNone(planning["monthly_contribution"])
            self.assertIsNone(planning["tax_cost_basis"])
            self.assertIsNone(planning["estimated_hours"])
            self.assertIsNone(planning["weekly_hours"])
            self.assertFalse(planning["tax_assumptions_confirmed"])
        finally:
            dialog.close()
            dialog.deleteLater()
