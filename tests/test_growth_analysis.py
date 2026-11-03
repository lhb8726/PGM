"""Synthetic scenario checks for evidence-based nonfinancial planning reports."""
from datetime import date, timedelta
import unittest

from pgm.growth_analysis import analyze_growth


TODAY = date(2028, 4, 12)


def goal(category="career", **updates):
    result = {
        "id": 11, "title": "가상 학습 결과물", "category": category,
        "kind": "deliverable", "status": "active", "due_date": (TODAY+timedelta(days=70)).isoformat(),
        "criteria": "가상 결과물과 검토 기록 완성", "current": 2, "target": 9, "unit": "개", "direction": "increase",
        "planning": {"requirements": "가상 필수 항목과 검토 기준", "evidence": "가상 기존 결과물", "constraints": "추가 제약 없음", "estimated_hours": 40, "weekly_hours": 5, "monthly_cost": 0, "reference_url": "https://example.org/synthetic"},
    }
    result.update(updates)
    return result


def profile(**updates):
    result = {"weekly_hours": 12, "monthly_budget": 300000, "skills": "가상 기술", "occupation": "가상 직업"}
    result.update(updates)
    return result


class GrowthAnalysisTests(unittest.TestCase):
    def report(self, g=None, p=None, metrics=None, tasks=None):
        return analyze_growth(g or goal(), p or profile(), metrics or [], tasks or [], today=TODAY)

    def test_complete_inputs_produce_conditional_detailed_report(self):
        report = self.report()
        self.assertEqual(report["status"], "conditional")
        self.assertEqual(report["missing"], [])
        self.assertEqual(len(report["phases"]), 5)
        self.assertGreaterEqual(sum(len(p["actions"]) for p in report["phases"]), 10)
        self.assertGreaterEqual(len(report["scenarios"]), 3)
        self.assertIn("시간 총량 충족", report["scenarios"][0]["result"])
        for phase in report["phases"]:
            self.assertGreaterEqual(phase["start_day"], 0)
            self.assertLessEqual(phase["start_day"], phase["end_day"])
            for action in phase["actions"]:
                self.assertTrue(action["done_when"])
                self.assertTrue(action["why"])
                self.assertIn("가상 학습 결과물", action["title"])
                self.assertGreater(action["minutes"], 0)

    def test_missing_hours_does_not_invent_completion_duration(self):
        g = goal();g["planning"]["estimated_hours"] = None
        report = self.report(g)
        self.assertEqual(report["status"], "needs_input")
        self.assertIn("정보 부족", report["scenarios"][0]["result"])
        self.assertFalse(any(s["name"] == "기한 재설정" for s in report["scenarios"]))
        self.assertTrue(any("예상 총시간" in m for m in report["missing"]))

    def test_profile_hours_are_not_silently_allocated_to_one_goal(self):
        g = goal();g["planning"]["weekly_hours"] = None
        report = self.report(g)
        self.assertEqual(report["status"], "needs_input")
        self.assertIn("정보 부족", report["scenarios"][0]["result"])

    def test_shortfall_is_computed_from_remaining_work_and_time(self):
        g = goal();g["planning"].update(estimated_hours=120, weekly_hours=5)
        report = self.report(g)
        self.assertEqual(report["status"], "at_risk")
        self.assertTrue(any("70시간 부족" in w for w in report["warnings"]))
        self.assertTrue(any("주 약 12시간 필요" in s["result"] for s in report["scenarios"]))
        self.assertTrue(any("168일" in s["result"] for s in report["scenarios"]))

    def test_weekly_allocation_cannot_exceed_shared_profile_capacity(self):
        g = goal();g["planning"]["weekly_hours"] = 15
        report = self.report(g)
        self.assertEqual(report["status"], "at_risk")
        self.assertTrue(any("전체 가용" in w for w in report["warnings"]))

    def test_zero_weekly_hours_has_no_false_completion_date(self):
        g = goal();g["planning"]["weekly_hours"] = 0
        report = self.report(g)
        self.assertEqual(report["status"], "at_risk")
        self.assertTrue(any("완료일 계산 불가" in s["result"] for s in report["scenarios"]))

    def test_zero_remaining_work_does_not_automatically_complete_goal(self):
        g = goal();g["planning"].update(estimated_hours=0, weekly_hours=0)
        report = self.report(g)
        self.assertEqual(report["status"], "conditional")
        self.assertTrue(any("직접 확인" in s["requirement"] for s in report["scenarios"]))
        self.assertEqual(g["status"], "active")

    def test_past_or_invalid_deadline_does_not_divide_by_zero(self):
        past = self.report(goal(due_date=(TODAY-timedelta(days=1)).isoformat()))
        self.assertEqual(past["status"], "at_risk")
        self.assertTrue(any("기한이 지났" in w for w in past["warnings"]))
        invalid = self.report(goal(due_date="not-a-date"))
        self.assertEqual(invalid["status"], "needs_input")
        self.assertTrue(any("기한" in m for m in invalid["missing"]))

    def test_domain_specific_phases_and_medical_boundaries(self):
        first_titles = set()
        for category in ["career", "learning", "health", "life", "habits"]:
            with self.subTest(category=category):
                report = self.report(goal(category))
                first_titles.add(report["phases"][0]["title"])
                self.assertEqual(len(report["phases"]), 5)
        self.assertEqual(len(first_titles), 5)
        health = self.report(goal("health",kind="numeric",direction="decrease",current=12,target=9))
        self.assertTrue(any("남은 변화량 3개" in f for f in health["facts"]))
        self.assertTrue(any("의학적 진단" in w for w in health["warnings"]))

    def test_source_is_user_provided_and_never_claimed_verified(self):
        report = self.report()
        self.assertIn("미검증", report["sources"][0]["title"])
        self.assertEqual(report["sources"][0]["checked_on"], "")
        g = goal();g["planning"]["reference_url"] = "javascript:alert(1)"
        report = self.report(g)
        self.assertEqual(report["sources"], [])
        self.assertTrue(any("URL" in w for w in report["warnings"]))

    def test_metric_type_is_a_saved_classification_not_a_certification(self):
        g = goal();g["planning"]["evidence"] = ""
        metric = {"category":"career","label":"가상 점검","value":4,"unit":"개","evidence_kind":"document","source":"가상 작성 기록","recorded_date":TODAY.isoformat()}
        report = self.report(g,metrics=[metric])
        self.assertTrue(any("문서·결과물로 분류" in f for f in report["facts"]))
        self.assertTrue(any("진위" in s for s in report["assumptions"]))

    def test_monthly_cost_over_budget_is_flagged(self):
        g = goal("life");g["planning"]["monthly_cost"] = 400000
        report = self.report(g)
        self.assertEqual(report["status"], "at_risk")
        self.assertTrue(any("월 가용 예산" in w for w in report["warnings"]))

    def test_far_future_validation_stages_are_not_assigned_to_first_week(self):
        report = self.report(goal(due_date=(TODAY+timedelta(days=700)).isoformat()))
        self.assertGreater(report["phases"][-1]["start_day"], 28)
        short = self.report(goal(due_date=(TODAY+timedelta(days=2)).isoformat()))
        self.assertTrue(all(0 <= p["start_day"] <= p["end_day"] <= 2 for p in short["phases"]))

    def test_phase_windows_are_anchored_to_creation_instead_of_report_reopen(self):
        created = TODAY - timedelta(days=20)
        g = goal(created_at=created.isoformat()+"T09:00:00+00:00")
        first = self.report(g)
        later = analyze_growth(g, profile(), [], [], today=TODAY+timedelta(days=15))
        self.assertEqual(first["anchor_on"], created.isoformat())
        self.assertEqual(first["phases"], later["phases"])
        self.assertNotEqual(first["scenarios"][0]["result"], later["scenarios"][0]["result"])

    def test_excessive_work_estimate_does_not_overflow_completion_date(self):
        g = goal();g["planning"].update(estimated_hours=1e308, weekly_hours=1e-308)
        report = self.report(g)
        self.assertTrue(any("계산 범위" in s["result"] for s in report["scenarios"]))

    def test_user_completion_is_preserved_and_markup_not_rendered(self):
        report = self.report(goal(title="<b>가상 목표</b>\x00",status="completed"))
        self.assertEqual(report["status"], "completed")
        self.assertNotIn("<b>", repr(report))
        self.assertNotIn("\x00", repr(report))


if __name__ == "__main__":
    unittest.main()
