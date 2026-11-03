"""After-tax funding progress uses wholly fictional financial inputs."""
from copy import deepcopy
import unittest

from pgm.engine import progress, progress_state


def synthetic_goal():
    return {
        "id": 73, "title": "가상 세후 자금 목표", "category": "finance",
        "kind": "numeric", "unit": "원", "direction": "increase",
        "baseline": 50000000, "current": 260000000, "target": 250000000,
        "due_date": "2035-07-31", "created_at": "2025-07-31T00:00:00+00:00",
        "status": "active", "planning": {
            "target_basis": "after_tax_cash", "tax_cost_basis": 50000000,
            "tax_rate": 22, "annual_allowance": 2500000,
            "tax_assumptions_confirmed": True, "monthly_contribution": 700000,
            "contribution_source": "가상 추가 재원", "contribution_confirmed": True,
        },
    }


class AfterTaxProgressTests(unittest.TestCase):
    def test_gross_above_target_does_not_complete_net_target(self):
        goal = synthetic_goal()
        # (260m - 50m - 2.5m) * .22 = 45.65m tax; cash=214.35m.
        state = progress_state(goal, [])
        self.assertAlmostEqual(state["value"], 214350000 / 250000000)
        self.assertLess(state["value"], 1)
        self.assertIn("세후", state["label"])
        self.assertIn("214,350,000", state["detail"])
        self.assertEqual(goal["status"], "active")

    def test_missing_basis_is_unknown_not_zero_percent(self):
        goal = synthetic_goal()
        goal["planning"]["tax_cost_basis"] = None
        state = progress_state(goal, [])
        self.assertIsNone(state["value"])
        self.assertIn("정보 부족", state["label"])
        self.assertEqual(progress(goal, []), 0.0)  # compatibility-only API

    def test_unconfirmed_tax_regime_is_unknown(self):
        goal = synthetic_goal()
        goal["planning"]["tax_assumptions_confirmed"] = False
        self.assertIsNone(progress_state(goal, [])["value"])

    def test_funding_ratio_does_not_guess_a_historical_net_baseline(self):
        goal = synthetic_goal()
        other = deepcopy(goal)
        other["baseline"] = 255000000
        self.assertEqual(progress_state(goal, [])["value"], progress_state(other, [])["value"])
        self.assertAlmostEqual(progress_state(other, [])["value"], .8574)

    def test_explicit_completion_is_the_users_record(self):
        goal = synthetic_goal()
        goal["planning"]["tax_cost_basis"] = None
        goal["status"] = "completed"
        state = progress_state(goal, [])
        self.assertEqual(state["value"], 1.0)
        self.assertIn("직접 확인", state["label"])

    def test_goal_units_convert_but_tax_basis_stays_in_won(self):
        goal = synthetic_goal()
        converted = deepcopy(goal)
        converted.update(unit="만원", baseline=5000, current=26000, target=25000)
        self.assertEqual(progress_state(goal, []), progress_state(converted, []))

    def test_zero_basis_is_a_known_value(self):
        goal = synthetic_goal()
        goal.update(current=100000000, target=200000000)
        goal["planning"]["tax_cost_basis"] = 0
        state = progress_state(goal, [])
        self.assertIsNotNone(state["value"])
        self.assertAlmostEqual(state["value"], 78550000 / 200000000)

    def test_zero_assets_and_zero_tax_basis_show_real_zero(self):
        goal = synthetic_goal()
        goal.update(current=0, baseline=0)
        goal["planning"]["tax_cost_basis"] = 0
        state = progress_state(goal, [])
        self.assertEqual(state["value"], 0.0)
        self.assertNotIn("정보 부족", state["label"])

    def test_zero_tax_rate_has_no_tax_deduction(self):
        goal = synthetic_goal()
        goal["planning"]["tax_rate"] = 0
        state = progress_state(goal, [])
        self.assertEqual(state["value"], 1.0)
        self.assertEqual(goal["status"], "active")

    def test_invalid_unit_and_debt_direction_remain_unknown(self):
        for key, value in [("unit", "USD"), ("direction", "decrease")]:
            goal = synthetic_goal()
            goal[key] = value
            with self.subTest(field=key):
                self.assertIsNone(progress_state(goal, [])["value"])


if __name__ == "__main__":
    unittest.main()
