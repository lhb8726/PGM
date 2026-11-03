from collections import defaultdict
from datetime import date, timedelta
import math
import unittest

from pgm.engine import activity_series, build_plan, diagnose, habit_streak, insights, progress, replan


TODAY = date(2026, 11, 3)


def goal(id=1, category="career", **overrides):
    value = {"id": id, "title": f"목표 {id}", "category": category, "kind": "deliverable", "status": "active", "priority": 2, "due_date": "2026-12-01", "criteria": "결과물 확인"}
    value.update(overrides)
    return value


def task(id=1, goal_id=1, **overrides):
    value = {"id": id, "goal_id": goal_id, "title": "실행", "minutes": 30, "actual_minutes": 0, "done": False, "scheduled_date": TODAY.isoformat(), "position": id, "stage": "단계"}
    value.update(overrides)
    return value


class ProgressTests(unittest.TestCase):
    def test_numeric_increase_decrease_and_bounds(self):
        self.assertEqual(progress(goal(kind="numeric", baseline=0, current=40, target=100), []), .4)
        self.assertEqual(progress(goal(kind="numeric", baseline=100, current=80, target=60, direction="decrease"), []), .5)
        self.assertEqual(progress(goal(kind="numeric", baseline=0, current=-10, target=100), []), 0)
        self.assertEqual(progress(goal(kind="numeric", baseline=0, current=150, target=100), []), 1)

    def test_equal_start_and_target_checked_directly(self):
        self.assertEqual(progress(goal(kind="numeric", baseline=10, current=10, target=10), []), 1)
        self.assertEqual(progress(goal(kind="numeric", baseline=10, current=9, target=10), []), 0)
        self.assertEqual(progress(goal(kind="numeric", baseline=10, current=11, target=10, direction="decrease"), []), 0)

    def test_missing_or_nonfinite_number_does_not_invent_progress(self):
        for current in [None, "", "abc", math.nan, math.inf]:
            self.assertEqual(progress(goal(kind="numeric", baseline=0, current=current, target=10), []), 0)

    def test_related_tasks_only_and_no_state_mutation(self):
        value = goal()
        tasks = [task(done=True), task(id=2), task(id=3, goal_id=2, done=True)]
        self.assertEqual(progress(value, tasks), .5)
        self.assertEqual(value["status"], "active")
        self.assertEqual(progress(goal(status="completed"), []), 1)


class PlanTests(unittest.TestCase):
    def test_shared_capacity_across_six_categories_and_dependencies(self):
        categories = ["finance", "career", "learning", "health", "life", "habits"]
        goals = [goal(index+1, category) for index, category in enumerate(categories)]
        plan = build_plan(goals, [], {"weekly_hours": 7}, today=TODAY)
        used = defaultdict(int)
        by_goal = defaultdict(list)
        for item in plan["tasks"]:
            used[item["scheduled_date"]] += item["minutes"]
            by_goal[item["goal_id"]].append(item["scheduled_date"])
        self.assertTrue(plan["tasks"])
        self.assertTrue(all(minutes <= 60 for minutes in used.values()))
        self.assertTrue(all(days == sorted(days) for days in by_goal.values()))
        self.assertLessEqual(plan["total_minutes"], plan["available_minutes"])
        self.assertEqual(len(by_goal), 6)

    def test_existing_task_and_habit_minutes_are_reserved(self):
        existing = [task(goal_id=99, minutes=20)]
        habits = [{"weekdays": [TODAY.weekday()], "minutes": 15}]
        plan = build_plan([goal()], existing, {"weekly_hours": 7}, habits, TODAY)
        today_minutes = sum(item["minutes"] for item in plan["tasks"] if item["scheduled_date"] == TODAY.isoformat())
        self.assertLessEqual(today_minutes, 25)

    def test_actual_completed_time_uses_execution_day(self):
        completed = [task(goal_id=99, done=True, minutes=10, actual_minutes=55,
                          scheduled_date=(TODAY-timedelta(days=2)).isoformat(), completed_at=TODAY.isoformat()+"T10:00:00")]
        plan = build_plan([goal()], completed, {"weekly_hours": 7}, today=TODAY)
        self.assertLessEqual(sum(item["minutes"] for item in plan["tasks"] if item["scheduled_date"] == TODAY.isoformat()), 5)

    def test_deadline_never_exceeded_when_insufficient(self):
        plan = build_plan([goal(due_date=TODAY.isoformat())], [], {"weekly_hours": 7}, today=TODAY)
        self.assertTrue(plan["warnings"])
        self.assertTrue(all(item["scheduled_date"] == TODAY.isoformat() for item in plan["tasks"]))
        self.assertLessEqual(plan["total_minutes"], 60)

    def test_zero_capacity_and_past_deadline(self):
        plan = build_plan([goal()], [], {"weekly_hours": 0}, today=TODAY)
        self.assertEqual(plan["tasks"], [])
        self.assertTrue(plan["warnings"])
        plan = build_plan([goal(due_date="2026-11-02")], [], {"weekly_hours": 10}, today=TODAY)
        self.assertEqual(plan["tasks"], [])
        self.assertTrue(any("기한이 지났" in item for item in plan["warnings"]))

    def test_existing_roadmap_does_not_duplicate(self):
        plan = build_plan([goal()], [task()], {"weekly_hours": 10}, today=TODAY)
        self.assertEqual(plan["tasks"], [])
        self.assertTrue(any("중복" in item for item in plan["warnings"]))

    def test_priority_processed_before_lower_priority(self):
        plan = build_plan([goal(1, priority=1), goal(2, priority=3)], [], {"weekly_hours": 7}, today=TODAY, horizon_days=1)
        self.assertTrue(plan["tasks"])
        self.assertTrue(all(item["goal_id"] == 2 for item in plan["tasks"]))

    def test_invalid_deadline_and_empty_horizon_reported(self):
        plan = build_plan([goal(due_date="bad")], [], {"weekly_hours": 7}, today=TODAY)
        self.assertTrue(plan["tasks"])
        self.assertTrue(any("기한이 없어" in item for item in plan["warnings"]))
        self.assertEqual(build_plan([goal()], [], {"weekly_hours": 7}, today=TODAY, horizon_days=0)["tasks"], [])

    def test_replan_preserves_completed_record_and_reserves_actual_minutes(self):
        completed = task(done=True, actual_minutes=50, completed_at=TODAY.isoformat())
        pending = task(id=2, minutes=30, scheduled_date="2026-11-01")
        records = [completed.copy(), pending.copy()]
        result = replan(records, [goal()], {"weekly_hours": 7}, today=TODAY)
        self.assertEqual(records[0], completed)
        self.assertEqual(records[1], pending)
        self.assertEqual(len(result["tasks"]), 1)
        self.assertEqual(result["tasks"][0]["id"], 2)
        self.assertEqual(result["tasks"][0]["scheduled_date"], "2026-11-04")

    def test_replan_impossible_keeps_id_and_marks_unscheduled(self):
        result = replan([task(minutes=120)], [goal()], {"weekly_hours": 7}, today=TODAY)
        self.assertEqual(result["tasks"][0]["id"], 1)
        self.assertEqual(result["tasks"][0]["scheduled_date"], "")
        self.assertTrue(result["warnings"])


class DiagnosisTests(unittest.TestCase):
    def test_all_categories_missing_without_fabricated_score(self):
        result = diagnose({}, [], [])
        self.assertEqual(len(result), 6)
        self.assertTrue(all(item["level"] == "정보 부족" for item in result))
        self.assertTrue(all(item["missing"] for item in result))
        self.assertTrue(all("score" not in item for item in result))

    def test_evidence_and_self_report_distinction(self):
        metrics = [{"category": "learning", "label": "시험", "value": 50, "unit": "점", "evidence_kind": "measured", "source": "모의 시험", "recorded_date": TODAY.isoformat()}]
        result = {item["category"]: item for item in diagnose({}, metrics, [goal(category="learning")])}
        self.assertEqual(result["learning"]["level"], "근거 기록 있음")
        self.assertIn("모의 시험", result["learning"]["evidence"])
        self.assertNotEqual(result["finance"]["level"], "근거 기록 있음")

    def test_zero_income_is_not_divided(self):
        result = diagnose({"assets": 100, "monthly_income": 0}, [], [])[0]
        self.assertIn("계산하지", result["evidence"])


class HabitAndActivityTests(unittest.TestCase):
    def test_weekdays_skip_rest_days_and_today_is_open(self):
        # Tuesday today is not completed; Monday and previous Friday continue.
        habit = {"weekdays": [0, 1, 2, 3, 4], "completions": ["2026-11-02", "2026-10-30"]}
        self.assertEqual(habit_streak(habit, TODAY), 2)
        habit["completions"].append(TODAY.isoformat())
        self.assertEqual(habit_streak(habit, TODAY), 3)

    def test_missing_scheduled_day_breaks_streak(self):
        self.assertEqual(habit_streak({"weekdays": list(range(7)), "completions": ["2026-11-01"]}, TODAY), 0)
        self.assertEqual(habit_streak({"weekdays": [], "completions": [TODAY.isoformat()]}, TODAY), 0)

    def test_series_uses_scheduled_dates_and_zero_fills(self):
        records = [task(done=True), task(id=2), task(id=3, scheduled_date="2026-10-01", done=True)]
        result = activity_series(records, 7, TODAY)
        self.assertEqual(len(result), 7)
        self.assertEqual(result[-1]["planned"], 2)
        self.assertEqual(result[-1]["completed"], 1)
        self.assertEqual(result[0]["planned"], 0)

    def test_insights_are_local_and_show_unplanned_work(self):
        result = insights({"weekly_hours": 0}, [], [task(scheduled_date="")], [], today=TODAY)
        self.assertTrue(any("날짜가 없는" in item["title"] for item in result))
        self.assertTrue(any("규칙 기반" in item["body"] for item in result))


if __name__ == "__main__":
    unittest.main()
