"""Goal assumptions stay explicit when edited through the desktop forms."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest

from PySide6.QtWidgets import QApplication

from pgm.dialogs import GoalDialog, TaskDialog
from pgm.storage import Store


class PlanningDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_blank_optional_assumptions_are_not_fabricated_zeros(self):
        dialog = GoalDialog()
        try:
            planning = dialog.values()["planning"]
            self.assertIsNone(planning["estimated_hours"])
            self.assertIsNone(planning["weekly_hours"])
            self.assertIsNone(planning["monthly_contribution"])
            self.assertIsNone(planning["tax_cost_basis"])
            self.assertFalse(planning["contribution_confirmed"])
            self.assertFalse(planning["tax_assumptions_confirmed"])
            dialog.monthly_contribution_input.known.setChecked(True)
            self.assertEqual(dialog.values()["planning"]["monthly_contribution"], 0)
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_finance_inputs_are_absolute_won_and_survive_goal_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory))
            dialog = GoalDialog()
            try:
                dialog.title_input.setText("가상 자산 목표")
                dialog.criteria_input.setPlainText("가상 목표 금액과 확인 기준")
                dialog.category_input.setCurrentIndex(dialog.category_input.findData("finance"))
                dialog.kind_input.setCurrentIndex(dialog.kind_input.findData("numeric"))
                dialog.unit_input.setText("만원")
                dialog.current_input.setValue(135)
                dialog.target_input.setValue(900)
                dialog.monthly_contribution_input.known.setChecked(True)
                dialog.monthly_contribution_input.editor.setValue(75000)
                dialog.contribution_source_input.setText("가상 신규 수입")
                dialog.contribution_confirmed_input.setChecked(True)
                dialog.tax_cost_basis_input.known.setChecked(True)
                dialog.tax_cost_basis_input.editor.setValue(900000)
                dialog.tax_assumptions_confirmed_input.setChecked(True)
                dialog.target_basis_input.setCurrentIndex(dialog.target_basis_input.findData("after_tax_cash"))
                self.assertTrue(dialog.planning_tabs.isTabVisible(2))
                goal_id = store.save_goal(dialog.values())
                saved = next(g for g in store.goals() if g["id"] == goal_id)
                self.assertEqual(saved["current"], 135)
                self.assertEqual(saved["planning"]["tax_cost_basis"], 900000)
                self.assertEqual(saved["planning"]["monthly_contribution"], 75000)
                edited = GoalDialog(saved)
                try:
                    self.assertEqual(edited.values()["planning"], saved["planning"])
                finally:
                    edited.close()
                    edited.deleteLater()
            finally:
                dialog.close()
                dialog.deleteLater()
                store.close()

    def test_task_done_when_and_reason_survive_form_roundtrip(self):
        original = {"id": 11, "goal_id": 3, "title": "가상 확인 과제", "minutes": 15,
                    "done_when": "필수 항목 확인", "rationale": "현재 부족한 증빙 확인"}
        dialog = TaskDialog([{"id": 3, "title": "가상 상위 목표"}], original)
        try:
            self.assertEqual(dialog.values()["done_when"], original["done_when"])
            self.assertEqual(dialog.values()["rationale"], original["rationale"])
        finally:
            dialog.close()
            dialog.deleteLater()
