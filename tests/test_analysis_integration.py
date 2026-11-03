"""Cross-module goal analysis checks using only fictional goal data."""
from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest

from pgm.analysis import analyze_goal, report_markdown
from pgm.engine import build_plan, replan
from pgm.storage import Store


TODAY = date(2029, 5, 16)


def fictional_goal(goal_id=1, category="career", **updates):
    result = {
        "id": goal_id,
        "title": "가상 결과물 제작" if category == "career" else "가상 지식 평가 준비",
        "category": category, "kind": "deliverable", "horizon": "medium",
        "due_date": (TODAY+timedelta(days=84)).isoformat(), "priority": 2,
        "baseline": 0, "current": 0, "target": 1, "unit": "개",
        "direction": "increase", "criteria": "가상 결과물과 검토 체크리스트 완성",
        "status": "active", "created_at": TODAY.isoformat()+"T09:00:00+00:00",
        "planning": {
            "context": "통합 검증용 가상 목표", "requirements": "가상 필수 조건과 확인 방법",
            "evidence": "가상 기존 초안", "constraints": "추가 제약 없음",
            "estimated_hours": 24, "weekly_hours": 4, "monthly_cost": 60000,
            "reference_url": "https://example.org/fictional-criteria",
        },
    }
    result.update(updates)
    return result


def fictional_profile(**updates):
    result = {"name": "가상 통합 검증", "weekly_hours": 14, "monthly_budget": 300000}
    result.update(updates)
    return result


def custom_report(actions=None, future=True):
    early_actions = actions or [{"title": "가상 기준과 현재 증빙 비교", "minutes": 30,
                                 "done_when": "기준별 현재 증빙과 부족 항목 기록",
                                 "why": "가상 목표의 출발점을 확인하기 위해"}]
    phases = [{"title": "초기 확인", "period": "첫 주", "objective": "가상 조건 확인",
               "start_day": 0, "end_day": 6, "actions": early_actions}]
    if future:
        phases.append({"title": "후반 최종 확인", "period": "60일 이후", "objective": "가상 최종 결과 확인",
                       "start_day": 60, "end_day": 84,
                       "actions": [{"title": "가상 최종 결과 검토", "minutes": 30,
                                    "done_when": "최종 기준표와 결과 대조", "why": "실제 결과 확인"}]})
    return {"anchor_on": TODAY.isoformat(), "warnings": [], "missing": [], "phases": phases}


class AnalysisIntegrationTests(unittest.TestCase):
    def test_report_combines_goal_inputs_with_shared_time_and_budget_warnings(self):
        goals = [fictional_goal(), fictional_goal(2, "learning")]
        report = analyze_goal(goals[0], fictional_profile(weekly_hours=6, monthly_budget=100000),
                              all_goals=goals, today=TODAY)
        self.assertEqual(report["goal_id"], goals[0]["id"])
        self.assertEqual(report["title"], goals[0]["title"])
        self.assertEqual(report["generated_on"], TODAY.isoformat())
        self.assertTrue(any("합계 8시간/주" in x for x in report["warnings"]))
        self.assertTrue(any("120,000원/월" in x for x in report["warnings"]))
        self.assertTrue(any(goals[0]["criteria"] in x for x in report["facts"]))

    def test_completed_goal_is_excluded_from_shared_resource_sum(self):
        active = fictional_goal()
        completed = fictional_goal(2, "learning", status="completed")
        report = analyze_goal(active, fictional_profile(weekly_hours=5, monthly_budget=70000),
                              all_goals=[active, completed], today=TODAY)
        self.assertFalse(any("목표별 배정 시간 합계" in x for x in report["warnings"]))
        self.assertFalse(any("목표 비용 합계" in x for x in report["warnings"]))

    def test_first_28_days_exclude_future_phases(self):
        g = fictional_goal()
        result = build_plan([g], [], fictional_profile(), today=TODAY,
                            reports={g["id"]: custom_report()})
        self.assertTrue(result["tasks"])
        self.assertEqual({t["stage"] for t in result["tasks"]}, {"초기 확인"})
        self.assertFalse(any("최종" in t["title"] for t in result["tasks"]))
        self.assertTrue(all(TODAY <= date.fromisoformat(t["scheduled_date"]) < TODAY+timedelta(days=28)
                            for t in result["tasks"]))

    def test_goal_and_shared_daily_time_limits_are_both_respected(self):
        goals = [fictional_goal(), fictional_goal(2, "learning")]
        for g in goals:
            g["planning"]["weekly_hours"] = 1
        action = [{"title": "가상 큰 작업의 실행 초안", "minutes": 300,
                   "done_when": "가상 작업 결과 기록", "why": "분할 검증"}]
        reports = {g["id"]: custom_report(action, future=False) for g in goals}
        result = build_plan(goals, [], fictional_profile(weekly_hours=7), today=TODAY,
                            horizon_days=7, reports=reports)
        by_goal_day = defaultdict(int)
        by_day = defaultdict(int)
        for task in result["tasks"]:
            by_goal_day[(task["goal_id"], task["scheduled_date"])]+=task["minutes"]
            by_day[task["scheduled_date"]]+=task["minutes"]
        self.assertEqual({key[0] for key in by_goal_day}, {1, 2})
        self.assertTrue(all(minutes <= 8 for minutes in by_goal_day.values()))
        self.assertTrue(all(minutes <= 60 for minutes in by_day.values()))
        self.assertTrue(any("배치하지 못했습니다" in x for x in result["warnings"]))

    def test_analysis_action_criteria_and_reason_survive_storage_reopen(self):
        with tempfile.TemporaryDirectory(prefix="pgm-analysis-roundtrip-") as temporary:
            path = Path(temporary)/"workspace"
            store = Store(path)
            try:
                g = fictional_goal();g.pop("id")
                gid = store.save_goal(g)
                saved = store.goals()[0]
                result = build_plan([saved], [], fictional_profile(), today=TODAY,
                                    reports={gid: custom_report(future=False)})
                store.add_tasks(result["tasks"])
                expected = store.tasks()[0]
            finally:
                store.close()
            reopened = Store(path)
            try:
                task = reopened.tasks()[0]
                for key in ["done_when", "rationale", "analysis_key", "not_before"]:
                    self.assertTrue(task[key])
                    self.assertEqual(task[key], expected[key])
                self.assertEqual(reopened.goals()[0]["planning"]["requirements"], "가상 필수 조건과 확인 방법")
            finally:
                reopened.close()

    def test_completed_analysis_action_is_not_generated_again(self):
        g = fictional_goal();report = custom_report(future=False)
        first = build_plan([g], [], fictional_profile(), today=TODAY, reports={g["id"]: report})
        completed = [{**t, "id": i+1, "done": True,
                      "completed_at": TODAY.isoformat()+"T12:00:00+00:00"}
                     for i,t in enumerate(first["tasks"])]
        again = build_plan([g], completed, fictional_profile(), today=TODAY,
                          reports={g["id"]: report})
        self.assertEqual(again["tasks"], [])

    def test_partial_completed_action_resumes_remaining_minutes_only(self):
        g = fictional_goal();g["planning"]["weekly_hours"] = 7
        report = custom_report([{"title": "가상 분할 작업", "minutes": 120,
                                 "done_when": "작업의 필수 부분 모두 완료", "why": "남은 분량 추적"}], future=False)
        first = build_plan([g], [], fictional_profile(weekly_hours=7), today=TODAY,
                           horizon_days=1, reports={g["id"]:report})
        self.assertEqual(sum(t["minutes"] for t in first["tasks"]), 60)
        completed = [{**first["tasks"][0], "id": 1, "done": True,
                      "completed_at": TODAY.isoformat()+"T12:00:00+00:00"}]
        resumed = build_plan([g], completed, fictional_profile(weekly_hours=7),
                             today=TODAY+timedelta(days=1), horizon_days=1,
                             reports={g["id"]:report})
        self.assertEqual(sum(t["minutes"] for t in resumed["tasks"]), 60)
        self.assertEqual(resumed["tasks"][0]["analysis_key"], completed[0]["analysis_key"])

    def test_existing_unfinished_action_prevents_duplicate_proposals(self):
        g = fictional_goal();report = custom_report(future=False)
        initial = build_plan([g], [], fictional_profile(), today=TODAY, reports={g["id"]:report})
        unfinished = [{**t,"id":i+1} for i,t in enumerate(initial["tasks"])]
        repeat = build_plan([g], unfinished, fictional_profile(), today=TODAY, reports={g["id"]:report})
        self.assertEqual(repeat["tasks"], [])
        self.assertTrue(any("중복" in x for x in repeat["warnings"]))

    def test_replan_preserves_future_start_constraint_and_completed_records(self):
        g = fictional_goal();g["planning"]["weekly_hours"] = 7
        future = TODAY+timedelta(days=10)
        tasks = [
            {"id":1,"goal_id":g["id"],"title":"가상 미래 확인","minutes":30,"actual_minutes":0,
             "done":False,"scheduled_date":TODAY.isoformat(),"stage":"미래 단계","position":1,
             "not_before":future.isoformat(),"done_when":"필요 조건 확인","rationale":"미래 조건","analysis_key":"synthetic-key"},
            {"id":2,"goal_id":g["id"],"title":"가상 완료 기록","minutes":20,"actual_minutes":18,
             "done":True,"completed_at":TODAY.isoformat()+"T08:00:00+00:00", "scheduled_date":TODAY.isoformat(),
             "stage":"완료 단계","position":0},
        ]
        before=deepcopy(tasks)
        short=replan(tasks,[g],fictional_profile(weekly_hours=7),today=TODAY,horizon_days=7)
        self.assertEqual(short["tasks"][0]["scheduled_date"], "")
        self.assertEqual(short["tasks"][0]["not_before"], future.isoformat())
        enough=replan(tasks,[g],fictional_profile(weekly_hours=7),today=TODAY,horizon_days=28)
        self.assertGreaterEqual(date.fromisoformat(enough["tasks"][0]["scheduled_date"]), future)
        self.assertEqual({t["id"] for t in enough["tasks"]},{1})
        self.assertEqual(tasks,before)

    def test_export_keeps_missing_information_and_unverified_user_source_visible(self):
        g=fictional_goal(2,"learning")
        g["planning"]["estimated_hours"]=None
        report=analyze_goal(g,fictional_profile(),today=TODAY)
        markdown=report_markdown(report)
        self.assertIn(g["title"], markdown)
        self.assertIn(g["criteria"], markdown)
        self.assertIn("정보 부족", markdown)
        self.assertIn("예상 총시간",markdown)
        self.assertIn("https://example.org/fictional-criteria",markdown)
        self.assertIn("사용자 제공·미검증",markdown)
        self.assertIn("완료 기준:",markdown)
        self.assertIn("이유:",markdown)

    def test_report_reopen_keeps_phase_anchor_and_stable_action_identifiers(self):
        g=fictional_goal()
        first_report=analyze_goal(g,fictional_profile(),today=TODAY)
        later_day=TODAY+timedelta(days=2)
        later_report=analyze_goal(g,fictional_profile(),today=later_day)
        self.assertEqual(first_report["anchor_on"],later_report["anchor_on"])
        self.assertEqual(first_report["phases"],later_report["phases"])
        first=build_plan([g],[],fictional_profile(),today=TODAY,reports={g["id"]:first_report})
        later=build_plan([g],[],fictional_profile(),today=later_day,reports={g["id"]:later_report})
        self.assertEqual({t["analysis_key"] for t in first["tasks"]}, {t["analysis_key"] for t in later["tasks"]})
        self.assertTrue(all(t["not_before"]>=TODAY.isoformat() for t in later["tasks"]))


if __name__ == "__main__":
    unittest.main()
