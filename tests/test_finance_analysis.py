"""Financial model checks using wholly fictional assets and targets."""
from datetime import date
import json
import math
import unittest

from pgm.finance_analysis import (
    analyze_finance, future_value, gross_for_net, liquidation,
    required_monthly, required_return,
)


NOW = date(2030, 1, 31)


def goal(**overrides):
    value = {
        "id": 7, "title": "가상 자금 목표", "category": "finance", "kind": "numeric",
        "direction": "increase", "unit": "원", "current": 80000000, "baseline": 60000000,
        "target": 250000000, "due_date": "2040-01-31", "status": "active",
        "created_at": "2030-01-31T09:00:00+00:00",
        "planning": {"monthly_contribution": 700000, "contribution_source": "가상 외부 소득 확인",
                     "contribution_confirmed": True, "target_basis": "account_value",
                     "tax_cost_basis": 40000000, "tax_rate": 22,
                     "annual_allowance": 2500000, "tax_assumptions_confirmed": True},
    }
    value.update(overrides)
    return value


PROFILE = {"monthly_income": 3000000, "monthly_expenses": 1500000, "weekly_hours": 8}


class FinancialAnalysisTests(unittest.TestCase):
    def test_zero_return_is_only_principal_and_new_deposits(self):
        self.assertEqual(future_value(80000000, 700000, 0, 120), 164000000)
        self.assertEqual(future_value(80000000, 700000, 0, 0), 80000000)

    def test_effective_annual_growth_and_month_end_deposits(self):
        self.assertAlmostEqual(future_value(1000, 0, .05, 12), 1050)
        self.assertAlmostEqual(future_value(0, 100, .12, 1), 100)
        self.assertAlmostEqual(future_value(1000, 100, .12, 1), 1000 * 1.12 ** (1 / 12) + 100)

    def test_only_profit_above_allowance_is_taxed(self):
        net, tax = liquidation(250000000, 150000000, 2500000, .22)
        self.assertEqual(tax, 21450000)
        self.assertEqual(net, 228550000)
        self.assertEqual(liquidation(80000000, 90000000, 2500000, .22), (80000000, 0))

    def test_net_target_inverse_does_not_tax_principal(self):
        gross = gross_for_net(250000000, 150000000, 2500000, .22)
        self.assertAlmostEqual(liquidation(gross, 150000000, 2500000, .22)[0], 250000000)
        self.assertLess(gross, 250000000 / .78)

    def test_required_payment_also_increases_tax_basis(self):
        # At zero return, the embedded initial gain stays 40m regardless of new
        # deposits. Only (40m - 2.5m)*22%=8.25m is taxed, not the contributions.
        expected = (250000000 - 80000000 + 8250000) / 120
        monthly = required_monthly(80000000, 250000000, 0, 120, basis=40000000,
                                   allowance=2500000, tax_rate=.22, after_tax=True)
        self.assertAlmostEqual(monthly, expected)

    def test_required_payment_handles_initial_unrealized_loss(self):
        payment = required_monthly(100, 200, 0, 10, basis=1000,
                                   allowance=0, tax_rate=.22, after_tax=True)
        self.assertAlmostEqual(payment, 10)

    def test_required_payment_and_return_round_trip(self):
        for rate in (0, .03, .07, .10):
            payment = required_monthly(80000000, 250000000, rate, 120, basis=40000000,
                                       allowance=2500000, tax_rate=.22, after_tax=True)
            gross = future_value(80000000, payment, rate, 120)
            net, _ = liquidation(gross, 40000000 + payment * 120, 2500000, .22)
            self.assertAlmostEqual(net, 250000000, places=4)
            recovered = required_return(80000000, 250000000, payment, 120, basis=40000000,
                                        allowance=2500000, tax_rate=.22, after_tax=True)
            self.assertAlmostEqual(recovered, rate, places=10)

    def test_zero_balance_and_zero_deposits_cannot_create_money(self):
        self.assertIsNone(required_return(0, 250000000, 0, 120))
        g = goal(current=0)
        g["planning"]["monthly_contribution"] = 0
        report = analyze_finance(g, PROFILE, NOW)
        self.assertIsNone(report["finance"]["required_return"])
        self.assertEqual(report["status"], "at_risk")

    def test_report_provides_different_account_and_net_targets(self):
        report = analyze_finance(goal(), PROFILE, NOW)
        comparison = report["finance"]["comparison"]
        self.assertEqual(comparison["account_value"]["required_gross"], 250000000)
        self.assertLess(comparison["account_value"]["net_at_target"], 250000000)
        self.assertGreater(comparison["after_tax_cash"]["required_gross"], 250000000)
        self.assertGreater(comparison["after_tax_cash"]["required_return"], comparison["account_value"]["required_return"])
        self.assertEqual(len(report["scenarios"]), 5)

    def test_net_goal_requires_entered_tax_basis_and_confirmed_model(self):
        g = goal()
        g["planning"].update(target_basis="after_tax_cash", tax_cost_basis=None,
                              tax_assumptions_confirmed=False)
        report = analyze_finance(g, PROFILE, NOW)
        self.assertEqual(report["status"], "needs_input")
        self.assertFalse(report["finance"]["tax_ready"])
        self.assertIsNone(report["finance"]["required_return"])
        self.assertTrue(all(row["net"] is None and row["required_monthly"] is None for row in report["finance"]["rows"]))
        self.assertTrue(any("취득원가" in x for x in report["missing"]))

    def test_current_gross_meeting_target_does_not_mean_net_goal_met(self):
        g = goal(current=260000000)
        g["planning"].update(target_basis="after_tax_cash", tax_cost_basis=50000000)
        report = analyze_finance(g, PROFILE, NOW)
        self.assertFalse(report["finance"]["goal_satisfied"])
        self.assertLess(report["finance"]["current_net"], 250000000)

    def test_unknown_tax_basis_does_not_invent_current_net(self):
        g = goal(current=260000000)
        g["planning"].update(target_basis="after_tax_cash", tax_cost_basis=None)
        report = analyze_finance(g, PROFILE, NOW)
        self.assertIsNone(report["finance"]["current_net"])
        self.assertIsNone(report["finance"]["goal_satisfied"])

    def test_already_satisfied_goal_has_no_extra_waiting_period(self):
        report = analyze_finance(goal(current=300000000), PROFILE, NOW)
        self.assertTrue(report["finance"]["goal_satisfied"])
        self.assertEqual(report["finance"]["required_return"], 0)
        self.assertEqual(report["finance"]["months_at_7"], 0)

    def test_unknown_monthly_deposit_does_not_become_zero(self):
        g = goal()
        g["planning"]["monthly_contribution"] = None
        report = analyze_finance(g, PROFILE, NOW)
        self.assertEqual(report["status"], "needs_input")
        self.assertTrue(all(row["gross"] is None for row in report["finance"]["rows"]))
        self.assertTrue(all(row["required_monthly"] is not None for row in report["finance"]["rows"]))

    def test_unknown_deposit_source_is_explicitly_conditional(self):
        g = goal()
        g["planning"].update(contribution_confirmed=False, contribution_source="")
        report = analyze_finance(g, PROFILE, NOW)
        self.assertEqual(report["status"], "needs_input")
        self.assertTrue(any("출처" in x for x in report["missing"]))

    def test_cashflow_mismatch_is_flagged_without_denying_external_money(self):
        g = goal()
        g["planning"]["monthly_contribution"] = 2000000
        report = analyze_finance(g, PROFILE, NOW)
        self.assertTrue(any("수입−지출" in x and "단정하지" in x for x in report["warnings"]))

    def test_units_convert_goal_amounts_but_not_monthly_deposits(self):
        original = analyze_finance(goal(), PROFILE, NOW)
        converted = analyze_finance(goal(unit="만원", current=8000, target=25000), PROFILE, NOW)
        self.assertEqual(original["finance"]["rows"], converted["finance"]["rows"])
        self.assertEqual(converted["finance"]["monthly_contribution"], 700000)

    def test_foreign_currency_and_decreasing_goals_do_not_use_wrong_model(self):
        for g in [goal(unit="USD"), goal(direction="decrease"), goal(kind="deliverable"), goal(current=-1)]:
            with self.subTest(goal=g):
                report = analyze_finance(g, PROFILE, NOW)
                self.assertEqual(report["status"], "needs_input")
                self.assertEqual(report["finance"]["rows"], [])

    def test_partial_month_end_of_month_and_past_dates(self):
        self.assertEqual(analyze_finance(goal(due_date="2030-02-28"), PROFILE, NOW)["finance"]["months"], 1)
        self.assertEqual(analyze_finance(goal(due_date="2030-02-20"), PROFILE, NOW)["finance"]["months"], 0)
        report = analyze_finance(goal(current=300000000, due_date="2029-12-31"), PROFILE, NOW)
        self.assertTrue(report["finance"]["goal_satisfied"])
        self.assertIsNone(report["finance"]["required_return"])

    def test_long_horizon_is_bounded_and_json_has_no_nonfinite_numbers(self):
        for g in [goal(due_date="2200-01-01"), goal(target=1e300), goal(current=float("inf"))]:
            report = analyze_finance(g, PROFILE, NOW)
            json.dumps(report, allow_nan=False)
        self.assertIn("100년", " ".join(analyze_finance(goal(due_date="2200-01-01"), PROFILE, NOW)["missing"]))

    def test_stage_offsets_remain_anchored_on_goal_creation(self):
        early = analyze_finance(goal(), PROFILE, NOW)
        later = analyze_finance(goal(), PROFILE, date(2030, 5, 31))
        self.assertEqual(early["anchor_on"], "2030-01-31")
        self.assertEqual(later["anchor_on"], early["anchor_on"])
        self.assertEqual([(p["start_day"], p["end_day"]) for p in early["phases"]],
                         [(p["start_day"], p["end_day"]) for p in later["phases"]])
        self.assertGreaterEqual(early["phases"][2]["start_day"], 90)
        self.assertGreaterEqual(early["phases"][-1]["start_day"], 3000)
        self.assertTrue(all(a["done_when"] and a["why"] for p in early["phases"] for a in p["actions"]))

    def test_tax_exemption_is_only_one_liquidation_year(self):
        report = analyze_finance(goal(), PROFILE, NOW)
        comparison = report["finance"]["comparison"]["account_value"]
        expected_basis = 40000000 + 120 * 700000
        self.assertEqual(comparison["tax_at_target"], (250000000 - expected_basis - 2500000) * .22)

    def test_report_does_not_substitute_profile_assets_or_claim_live_sources(self):
        report = analyze_finance(goal(), {**PROFILE, "assets": 999999999999}, NOW)
        self.assertEqual(report["finance"]["pv"], 80000000)
        self.assertTrue(all("저장된" in source["title"] for source in report["sources"]))
        self.assertTrue(any("실시간" in a for a in report["assumptions"]))


if __name__ == "__main__":
    unittest.main()
