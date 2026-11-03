"""Goal reports built from explicit user inputs and inspectable product rules."""
from __future__ import annotations

from datetime import date


def analyze_goal(goal, profile, metrics=None, tasks=None, habits=None, all_goals=None, today=None):
    from .finance_analysis import analyze_finance
    from .growth_analysis import analyze_growth

    current = today or date.today()
    if isinstance(current, str):
        current = date.fromisoformat(current)
    if goal.get("category") == "finance":
        report = analyze_finance(goal, profile, today=current)
    else:
        report = analyze_growth(goal, profile, metrics or [], tasks or [], habits or [], today=current)
    report = dict(report)
    for key in ("facts", "assumptions", "missing", "warnings", "scenarios", "phases", "checkpoints", "sources"):
        report[key] = list(report.get(key) or [])
    report.update(goal_id=goal.get("id"), title=goal.get("title", "목표"), category=goal.get("category"), generated_on=current.isoformat())
    active = [g for g in (all_goals or [goal]) if g.get("status", "active") == "active"]
    allocated = sum(float(g.get("planning", {}).get("weekly_hours") or 0) for g in active)
    available = float(profile.get("weekly_hours") or 0)
    if allocated > available:
        report["warnings"].append(f"목표별 배정 시간 합계 {allocated:g}시간/주가 전체 순가용 {available:g}시간/주를 초과합니다. 다른 목표와 함께 조정하세요.")
    costs = sum(float(g.get("planning", {}).get("monthly_cost") or 0) for g in active)
    budget = float(profile.get("monthly_budget") or 0)
    if costs > budget:
        report["warnings"].append(f"선언한 목표 비용 합계 {costs:,.0f}원/월이 프로필의 목표용 예산 {budget:,.0f}원/월을 초과합니다. 기본값·미입력 여부와 비용 배분을 확인하세요.")
    report["assumptions"].append("단계와 과제는 입력 정보에 따른 규칙 기반 제안입니다. 실행 과제의 예상 분량은 수정 가능한 초기 추정이며 목표 전체의 달성을 보장하지 않습니다.")
    if report.get("finance", {}).get("milestones"):
        report["assumptions"].append("시점별 세후 금액은 각 시점에 독립적으로 전량 청산하는 비교입니다. 매번 매도·납부한 뒤 재투자하는 경로나 기본공제를 누적 적용한 경로가 아닙니다.")
    for key in ("facts", "assumptions", "missing", "warnings", "checkpoints"):
        report[key] = list(dict.fromkeys(str(item) for item in report[key] if item))
    if goal.get("status") != "completed":
        if report["missing"]:
            report["status"] = "needs_input"
        elif report["warnings"] and report.get("status") not in ("at_risk",):
            report["status"] = "conditional"
    return report


def report_markdown(report):
    """Format a user-requested local export; never write a report automatically."""
    def money(v):
        return "정보 부족" if v is None else f"{v:,.0f}원"

    lines = [f"# {report['title']} — 목표 분석", "", f"분석 기준일: {report.get('generated_on', '')}", "", report.get("summary", ""), ""]
    for key, title in [("facts", "입력된 사실·기록"), ("assumptions", "계산 가정·해석"), ("missing", "추가로 확인할 정보"), ("warnings", "제약·위험")]:
        lines += [f"## {title}", ""]
        lines += [f"- {text}" for text in report.get(key, [])] or ["- 없음"]
        lines.append("")
    lines += ["## 조건·시나리오 비교", ""]
    for scenario in report.get("scenarios", []):
        lines += [f"### {scenario.get('name', '')}", "", f"결과: {scenario.get('result', '')}", f"필요 조건: {scenario.get('requirement', '')}", f"가정: {scenario.get('note', '')}", ""]
    finance = report.get("finance", {})
    comparison = finance.get("comparison", {})
    if comparison:
        lines += ["## 평가액·세후 현금 목표 비교", "", "| 목표 기준 | 필요 평가액 | 계산상 최종 세금 | 세후 현금 | 필요 연복리 |", "|---|---:|---:|---:|---:|"]
        for key, title in [("account_value", "계좌 평가액"), ("after_tax_cash", "세후 현금")]:
            item = comparison.get(key) or {}
            rate = item.get("required_return")
            lines.append(f"| {title} | {money(item.get('required_gross'))} | {money(item.get('tax_at_target'))} | {money(item.get('net_at_target'))} | {rate:.2%} |" if rate is not None else f"| {title} | {money(item.get('required_gross'))} | {money(item.get('tax_at_target'))} | {money(item.get('net_at_target'))} | 정보 부족·계산 범위 밖 |")
        lines.append("")
    if finance.get("milestones"):
        lines += ["## 가정에 따른 자산 점검표", "", "각 행은 해당 시점의 독립적인 청산 비교입니다.", "", "| 기준일 | 경과 개월 | 평가액 | 세후 금액 | 연복리 가정 |", "|---|---:|---:|---:|---:|"]
        for item in finance["milestones"]:
            rate = item.get("rate")
            rate_text = "미입력" if rate is None else f"{rate:.0%}"
            lines.append(f"| {item.get('date', '')} | {item.get('month', '')} | {money(item.get('gross'))} | {money(item.get('net'))} | {rate_text} |")
        lines.append("")
    lines += ["## 단계별 로드맵", ""]
    for phase in report.get("phases", []):
        lines += [f"### {phase['title']} · {phase.get('period', '')}", "", phase.get("objective", ""), ""]
        for action in phase.get("actions", []):
            lines += [f"- {action['title']} (초기 예상 {action['minutes']}분)", f"  - 완료 기준: {action.get('done_when', '')}", f"  - 이유: {action.get('why', '')}"]
        lines.append("")
    lines += ["## 점검·수정 기준", ""] + [f"- {x}" for x in report.get("checkpoints", [])] + ["", "## 근거 자료", ""]
    for source in report.get("sources", []):
        lines += [f"- {source.get('title', '')}: {source.get('url', '')} (확인일: {source.get('checked_on') or '사용자 제공·미검증'})"]
    return "\n".join(lines).rstrip() + "\n"
