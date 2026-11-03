"""Deterministic financial goal scenarios, not return forecasts or tax advice.

All amounts in the mathematical model are KRW. The tax model deliberately
requires an entered tax basis: a broker's displayed profit is never substituted
for tax records. Stored reference links are not a live tax-law lookup.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
import math
from typing import Any


RATES = (0.0, 0.03, 0.05, 0.07, 0.10)
MAX_MODEL_MONTHS = 1200
MAX_SEARCH_RETURN = 1.0
UNIT_MULTIPLIERS = {"원": 1, "krw": 1, "₩": 1, "만원": 10000, "억원": 100000000, "억": 100000000}
SOURCES = [
    {"title": "국세청 주식 양도소득세 안내 · 저장된 참고 자료", "url": "https://www.nts.go.kr/nts/na/ntt/selectNttInfo.do?nttSn=1350890", "checked_on": "2026-11-03"},
    {"title": "국회예산정책처 2026 대한민국 조세 · 저장된 참고 자료", "url": "https://korea.nabo.go.kr/board/file/down.do?fid=33319156", "checked_on": "2026-11-03"},
]


def _finite(value: Any, *, minimum: float = 0, maximum: float | None = None) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(value) or value < minimum or (maximum is not None and value > maximum):
        return None
    return value


def _day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _months(start: date, end: date) -> int:
    if end < start:
        return 0
    months = (end.year - start.year) * 12 + end.month - start.month
    return max(0, months - (_add_months(start, months) > end))


def _add_months(start: date, months: int) -> date:
    year, month_index = divmod(start.year * 12 + start.month - 1 + months, 12)
    return date(year, month_index + 1, min(start.day, monthrange(year, month_index + 1)[1]))


def _money(value: float | None) -> str:
    if value is None:
        return "정보 부족·계산 범위 밖"
    if abs(value) >= 100000000:
        return f"{value / 100000000:,.2f}억원"
    return f"{value:,.0f}원"


def future_value(pv: float, monthly: float, annual: float, months: int) -> float | None:
    """Month-end deposits; annual is an effective annual rate, not rate/12."""
    if months < 0 or min(pv, monthly, annual) < 0 or not all(math.isfinite(v) for v in (pv, monthly, annual)):
        return None
    try:
        if annual == 0:
            value = pv + monthly * months
        else:
            growth_log = math.log1p(annual)
            growth = math.exp(growth_log * months / 12)
            annuity = math.expm1(growth_log * months / 12) / math.expm1(growth_log / 12)
            value = pv * growth + monthly * annuity
    except (OverflowError, ZeroDivisionError, ValueError):
        return None
    return value if math.isfinite(value) else None


def liquidation(gross: float, basis: float, allowance: float, rate: float) -> tuple[float, float]:
    """Return (net, tax); all gains share the entered capital-gains regime."""
    tax = max(0.0, gross - basis - allowance) * rate
    return gross - tax, tax


def gross_for_net(target: float, basis: float, allowance: float, rate: float) -> float | None:
    if target <= basis + allowance or rate == 0:
        return target
    if rate >= 1:
        return None
    value = (target - rate * (basis + allowance)) / (1 - rate)
    return value if math.isfinite(value) else None


def required_monthly(pv: float, target: float, annual: float, months: int,
                     *, basis: float | None = None, allowance: float = 0,
                     tax_rate: float = 0, after_tax: bool = False) -> float | None:
    """Solve while increasing tax basis by months * the candidate deposit."""
    if months <= 0 or (after_tax and basis is None):
        return None

    def result(payment: float) -> float | None:
        gross = future_value(pv, payment, annual, months)
        if gross is None:
            return None
        if after_tax:
            return liquidation(gross, float(basis) + payment * months, allowance, tax_rate)[0]
        return gross

    initial = result(0)
    if initial is None:
        return None
    if initial >= target:
        return 0.0
    low, high = 0.0, max(1.0, target / months + pv / months)
    for _ in range(80):
        value = result(high)
        if value is not None and value >= target:
            break
        high *= 2
        if not math.isfinite(high) or high > 1e18:
            return None
    else:
        return None
    for _ in range(100):
        mid = (low + high) / 2
        value = result(mid)
        if value is None:
            return None
        if value >= target:
            high = mid
        else:
            low = mid
    return high


def required_return(pv: float, target: float, monthly: float, months: int,
                    *, basis: float | None = None, allowance: float = 0,
                    tax_rate: float = 0, after_tax: bool = False) -> float | None:
    if months <= 0 or (after_tax and basis is None):
        return None

    def result(annual: float) -> float | None:
        gross = future_value(pv, monthly, annual, months)
        if gross is None:
            return None
        return liquidation(gross, float(basis) + monthly * months, allowance, tax_rate)[0] if after_tax else gross

    zero, ceiling = result(0), result(MAX_SEARCH_RETURN)
    if zero is not None and zero >= target:
        return 0.0
    if ceiling is None or ceiling < target:
        return None
    low, high = 0.0, MAX_SEARCH_RETURN
    for _ in range(100):
        mid = (low + high) / 2
        value = result(mid)
        if value is None:
            return None
        if value >= target:
            high = mid
        else:
            low = mid
    return high


def _action(title: str, minutes: int, done_when: str, why: str) -> dict:
    return {"title": title, "minutes": minutes, "done_when": done_when, "why": why}


def _phases(title: str, days: int, pv: float | None, target: float | None,
            payment: float | None, required: float | None, basis: str) -> list[dict]:
    """Explicit offsets prevent multi-year phases becoming next-week tasks."""
    limit = max(0, days)
    gap = max(0, required - payment) if required is not None and payment is not None else None
    funding = (f"연 7% 가정에서 필요한 월 납입 {_money(required)}와 현재 {_money(payment)}를 비교하고 월 부족분 {_money(gap)}의 충당 가능성을 확인"
               if required is not None and payment is not None else "지속 가능한 신규 납입액과 목표에 필요한 금액을 먼저 확인")

    def phase(name, period, objective, start, end, actions):
        first = min(start, limit)
        return {"title": name, "period": period, "objective": objective,
                "start_day": first, "end_day": max(first, min(end, limit)), "actions": actions}

    return [
        phase("출발 자산·현금흐름 검증", "첫 2주", f"‘{title}’의 계산 출발점과 신규 자금을 증빙으로 확인", 0, 14, [
            _action(f"‘{title}’에 포함할 자산과 기준일 확인", 30, "자산 목록·중복 항목·기준일과 현재값을 기록", f"현재 {_money(pv)}와 목표 {_money(target)}가 같은 범위의 금액인지 확인합니다."),
            _action("월 신규 투자금의 출처·지속 기간 검증", 30, "생활비·세금 제외 후 신규 외부 유입액과 지속 기간을 기록", "매도대금·기존 예수금·재투자 수익을 신규 납입으로 중복 계산하지 않습니다."),
            _action("목표의 세전·세후 완료 기준 확정", 25, "평가액 또는 세후 현금 기준과 세금 모형 적용 범위를 확인", f"선택한 기준은 {basis}입니다. 세후 계산은 별도의 원화 취득원가와 과세 가정이 필요합니다."),
        ]),
        phase("손실 한도·지출 보호 계획", "2주~3개월", "목표에 사용할 자금과 생활 자금을 구분하고 위험 한도를 정함", 14, 89, [
            _action("비상 지출과 예정된 큰 지출 분리", 30, "예정 지출과 생활비 보호 금액을 따로 기록", "지출할 돈을 전액 장기 투자 가능 자금으로 보지 않습니다."),
            _action("종목·업종·통화별 집중도와 손실 한도 확인", 45, "보유 비중과 감당 가능한 손실액을 원 단위로 작성", "구체적인 보유 목록이 없으면 집중도를 추정하지 않습니다. 자산배분 변경 전 매도 세금을 확인합니다."),
        ]),
        phase("신규 납입 능력 검증·개선", "3개월~3년", funding, 90, 1095, [
            _action("목표 자금 부족분을 위한 현금흐름 실행안 작성", 45, "부족분·실행 후보·비용·확인할 소득 자료를 작성", "직업·기술·가용 시간이 없으면 특정 이직·부업·사업의 성공을 가정하지 않습니다."),
            _action("한 가지 소득 개선 후보를 검증 가능한 과제로 설정", 45, "다음 점검일, 실행 시간, 확인할 세후 순유입 기준을 정함", "기대 매출이 아니라 실제 생활비·세금 차감 후 납입 가능액을 검증합니다."),
        ]),
        phase("분기별 차이 분석·재계획", "첫 분기부터 반복 점검", "실제 자산·입금·세금과 필요한 조건의 차이를 재계산", 90, max(90, limit - 90), [
            _action("다음 분기 자산·납입·목표 차이 점검", 30, "기준일별 자산과 실제 신규 입금을 비교하고 변경 이유를 기록", "분기별 반복 점검을 제안합니다. 이 초안은 첫 점검 과제이며 자동 반복 일정은 별도로 설정해야 합니다."),
            _action("납입액·기한·목표 금액 대안 비교", 30, "충족 가능한 조건과 바꿀 조건을 구분해 확정", "시장 부진을 더 높은 예상 수익률로 덮지 않고 남은 필요 조건을 다시 계산합니다."),
        ]),
        phase("목표 자금 사용·현금화 준비", "마감 전 3개월", "사용 시점에 맞는 세금·유동성·필요 금액 확인", max(0, limit - 90), limit, [
            _action("사용 시점과 필요한 세후 금액 재확인", 30, "예정 사용일·잔여 공제·취득원가·예상 비용을 확인", "평가액과 실제 사용 가능한 현금을 구분하고 그 시점 세법을 다시 확인합니다."),
            _action("목표 달성 증빙과 현금화 범위 검토", 30, "완료 기준을 충족한 자금과 증빙을 직접 확인", "실제 현금화 여부와 무관하게 특정 거래를 자동 실행하지 않습니다."),
        ]),
    ]


def analyze_finance(goal: dict, profile: dict, today: Any = None) -> dict:
    """Return an explanation, bounded scenarios and a staged actionable roadmap."""
    now = _day(today) or date.today()
    settings = goal.get("planning") if isinstance(goal.get("planning"), dict) else {}
    title = str(goal.get("title") or "금융 목표")
    report = {"status": "needs_input", "summary": "계산에 필요한 조건을 먼저 확인하세요.",
              "facts": [], "assumptions": [], "missing": [], "warnings": [], "scenarios": [],
              "phases": [], "checkpoints": [], "sources": [dict(source) for source in SOURCES], "finance": {}}
    missing, warnings = report["missing"], report["warnings"]
    multiplier = UNIT_MULTIPLIERS.get(str(goal.get("unit", "")).strip().lower())
    pv_number, target_number = _finite(goal.get("current")), _finite(goal.get("target"))
    pv = pv_number * multiplier if pv_number is not None and multiplier is not None else None
    target = target_number * multiplier if target_number is not None and multiplier is not None else None
    if pv is not None and not math.isfinite(pv):
        pv = None
    if target is not None and not math.isfinite(target):
        target = None
    due = _day(goal.get("due_date"))
    anchor = _day(str(goal.get("created_at", ""))[:10]) or now
    if anchor > now:
        warnings.append("목표 생성일이 현재보다 뒤여서 단계 기준일을 현재로 보정했습니다. 생성 기록을 확인하세요.")
        anchor = now
    report["anchor_on"] = anchor.isoformat()
    months = _months(now, due) if due is not None else 0
    days = max(0, (due - now).days) if due is not None else 0
    payment = _finite(settings.get("monthly_contribution"))
    after_tax = settings.get("target_basis", "account_value") == "after_tax_cash"
    target_label = "세후 사용 가능한 현금" if after_tax else "계좌 평가액"
    cost_basis = _finite(settings.get("tax_cost_basis"))
    tax_percent = _finite(settings.get("tax_rate", 22), maximum=100)
    allowance = _finite(settings.get("annual_allowance", 2500000))
    tax_confirmed = settings.get("tax_assumptions_confirmed") is True
    tax_ready = cost_basis is not None and tax_percent is not None and allowance is not None and tax_confirmed
    tax_rate = tax_percent / 100 if tax_percent is not None else 0
    source = str(settings.get("contribution_source") or "").strip()
    contribution_confirmed = settings.get("contribution_confirmed") is True and bool(source)

    if goal.get("kind") != "numeric":
        missing.append("금액을 비교할 수 있는 수치형 목표와 현재값·목표값")
    if multiplier is None:
        missing.append("원화 금액 단위: 원·만원·억원·KRW 중 선택")
    if pv is None or target is None:
        missing.append("0 이상의 유효한 현재 금액과 목표 금액")
    if goal.get("direction", "increase") != "increase":
        missing.append("이 자산 축적 모형은 증가형 목표만 지원합니다. 감소형은 상환·지출 계획을 별도로 정의하세요.")
    if due is None:
        missing.append("유효한 목표 마감일")
    elif months <= 0:
        missing.append("월말 납입 모형에 필요한 최소 1개월 이상의 남은 기간")
    elif months > MAX_MODEL_MONTHS:
        missing.append("100년 이내의 계산 가능한 목표 기간")
    if payment is None:
        missing.append("매월 계좌 밖에서 새로 납입할 금액 (없으면 0 입력)")
    if not contribution_confirmed:
        missing.append("신규 납입금의 출처와 지속 가능성 확인")
    if after_tax and cost_basis is None:
        missing.append("세무 자료에 따른 현재 자산의 원화 취득원가·현금 합계")
    if after_tax and not tax_confirmed:
        missing.append("세후 모형의 과세 대상·세율·공제 적용 가정 확인")
    if after_tax and (tax_percent is None or allowance is None):
        missing.append("0~100% 세율과 0 이상 연간 잔여 공제액")

    if pv is not None:
        report["facts"].append(f"사용자 입력 현재 금액: {_money(pv)} · 프로필 전체 자산을 자동 대입하지 않음")
    if target is not None:
        report["facts"].append(f"사용자 입력 목표: {target_label} {_money(target)}")
    if due is not None:
        report["facts"].append(f"마감일 {due.isoformat()} · 현재부터 {months}회 월말 납입 가정 ({days}일)")
    if payment is not None:
        report["facts"].append(f"입력한 월 신규 납입: {_money(payment)} · 출처 {'확인 기록 있음: ' + source if contribution_confirmed else '미확인'}")
    if cost_basis is not None:
        report["facts"].append(f"사용자 입력 원화 취득원가·현금 합계: {_money(cost_basis)} · 세무 자료와의 일치는 자동 검증하지 않음")
    if settings.get("evidence"):
        report["facts"].append("사용자가 기재한 근거: " + str(settings["evidence"]))
    report["assumptions"] = [
        "원화 기준의 일정한 연복리 수익률과 매월 말 납입을 가정한 조건 계산입니다. 0·3·5·7·10%는 예상 수익률이나 확률이 아닙니다.",
        "월 납입액은 목표 단위와 관계없이 원화 금액입니다. 예수금 이동·보유 자산 매도·배당 재투자를 신규 외부 자금과 중복 계산하지 않습니다.",
        "중도 인출·수수료·환전 비용·배당 과세·중간 매매에 따른 세금 납부는 모형에 포함하지 않습니다. 실제 원화 수익에는 환율도 영향을 줍니다.",
        "장래 수익률·소득·세법을 확정하지 않습니다. 저장된 참고 자료의 확인일은 실제 사용 시점의 실시간 법령 확인을 뜻하지 않습니다.",
    ]
    if tax_ready:
        report["assumptions"].append(f"세후 계산은 전체 이익이 동일한 해외주식 양도차익 과세 방식에 해당한다고 단순화한 예시입니다. 세율 {tax_percent:g}%, 청산 연도 잔여 공제 {_money(allowance)}, 마지막 해 전량 청산을 가정합니다. 채권·예금 등은 실제 과세 방식이 다릅니다.")
        report["assumptions"].append("기본공제를 과거 연도에서 이월하지 않습니다. 월 납입액을 역산할 때도 취득원가에 새 납입 원금을 함께 더합니다.")
    else:
        warnings.append("세무 취득원가와 과세 가정이 확인되지 않아 세후 금액을 계산하지 않습니다. 계좌 평가손익으로 취득원가를 추정하지 않습니다.")

    income, expense = _finite(profile.get("monthly_income")), _finite(profile.get("monthly_expenses"))
    if payment is not None and income is not None and expense is not None and payment > income - expense:
        warnings.append(f"월 납입 {_money(payment)}가 프로필의 수입−지출 {_money(income - expense)}를 초과합니다. 소득 외 신규 재원의 금액·출처·지속 기간을 확인해야 하며, 별도 재원이 없다고 단정하지 않습니다.")
    if settings.get("constraints"):
        warnings.append("사용자 제약 조건을 계획에 확인: " + str(settings["constraints"]))
    if payment == 0:
        warnings.append("신규 납입을 0원으로 입력했습니다. 목표 부족분은 현재 자산의 가치 변화만으로 충족해야 합니다.")

    finance = report["finance"]
    finance.update({"months": months, "pv": pv, "target": target, "monthly_contribution": payment,
                    "target_basis": "after_tax_cash" if after_tax else "account_value", "tax_ready": tax_ready,
                    "cost_basis": cost_basis, "tax_rate": tax_percent, "annual_allowance": allowance,
                    "required_return": None, "required_gross": None, "comparison": {}, "rows": [], "milestones": []})
    if pv is not None and target is not None and goal.get("kind") == "numeric" and goal.get("direction", "increase") == "increase":
        current_net = liquidation(pv, cost_basis, allowance, tax_rate)[0] if tax_ready else None
        finance["current_net"] = current_net
        measured_current = current_net if after_tax else pv
        finance["goal_satisfied"] = measured_current >= target if measured_current is not None else None
        if finance["goal_satisfied"]:
            report["summary"] = "입력한 현재 금액은 선택한 목표 기준을 충족합니다. 실제 증빙·비용·현금화 여부를 확인하고 완료를 직접 확정하세요."
    core_ready = (goal.get("kind") == "numeric" and goal.get("direction", "increase") == "increase"
                  and pv is not None and target is not None and 0 < months <= MAX_MODEL_MONTHS)
    selected_ready = core_ready and (not after_tax or tax_ready)
    needed_seven = None
    if core_ready:
        for annual in RATES:
            gross = future_value(pv, payment, annual, months) if payment is not None else None
            net = (liquidation(gross, cost_basis + payment * months, allowance, tax_rate)[0]
                   if gross is not None and tax_ready and payment is not None else None)
            required = (required_monthly(pv, target, annual, months, basis=cost_basis, allowance=allowance or 0,
                                        tax_rate=tax_rate, after_tax=after_tax) if selected_ready else None)
            if annual == 0.07:
                needed_seven = required
            row = {"rate": annual, "gross": gross, "net": net, "required_monthly": required}
            finance["rows"].append(row)
            report["scenarios"].append({
                "name": f"年 {annual:.0%} 가정".replace("年", "연"),
                "result": f"평가액 {_money(gross)}" + (f" · 세후 {_money(net)}" if tax_ready else " · 세후 미산출"),
                "requirement": f"{target_label} 목표에 필요한 월 납입 {_money(required)}",
                "note": "매월 납입액을 변경하면 취득원가도 달라집니다. 세후 목표의 필요 평가액은 고정 비율이 아닙니다.",
            })
        if payment is not None:
            terminal_basis = cost_basis + payment * months if cost_basis is not None else None
            finance["terminal_cost_basis"] = terminal_basis
            account_net, account_tax = liquidation(target, terminal_basis, allowance, tax_rate) if tax_ready else (None, None)
            account_r = required_return(pv, target, payment, months)
            finance["comparison"]["account_value"] = {"required_gross": target, "tax_at_target": account_tax,
                                                        "net_at_target": account_net, "required_return": account_r}
            if tax_ready:
                net_gross = gross_for_net(target, terminal_basis, allowance, tax_rate)
                net_r = required_return(pv, target, payment, months, basis=cost_basis, allowance=allowance,
                                        tax_rate=tax_rate, after_tax=True)
                finance["comparison"]["after_tax_cash"] = {"required_gross": net_gross,
                                                            "tax_at_target": None if net_gross is None else net_gross - target,
                                                            "net_at_target": target, "required_return": net_r}
            comparison = finance["comparison"].get(finance["target_basis"], {})
            finance["required_return"] = comparison.get("required_return")
            finance["required_gross"] = comparison.get("required_gross")
            if selected_ready:
                current_net = liquidation(pv, cost_basis, allowance, tax_rate)[0] if after_tax else pv
                finance["goal_satisfied"] = current_net >= target
                rate = finance["required_return"]
                if current_net >= target:
                    report["summary"] = "입력한 현재 금액은 선택한 목표 기준을 충족합니다. 실제 증빙·비용·현금화 여부를 확인하고 완료를 직접 확정하세요."
                elif rate is None:
                    report["summary"] = "입력 조건에서 연 100% 이하 검색 범위 내의 필요 수익률을 산출할 수 없습니다. 납입액·목표 금액·기한을 재검토하세요."
                    warnings.append("필요 수익률은 연 0~100% 범위만 탐색합니다. 산출 불가는 달성이 수학적으로 불가능하다는 뜻과 다릅니다.")
                else:
                    report["summary"] = f"{months}개월 동안 월 {_money(payment)}을 유지하면, {target_label} {_money(target)}에 필요한 연복리 수익률은 약 {rate:.2%}입니다. 이는 달성 조건이며 수익 전망이 아닙니다."
                    if rate > 0.10:
                        warnings.append(f"필요 연복리 {rate:.2%}를 기본 계획으로 두는 것은 공격적이라는 제품상 판단입니다. 신규 납입 증가·기한 연장·목표 범위 변경을 함께 비교하세요.")
            for month in sorted({m for m in [1, 3, 6, 12, months // 2, months] if 0 < m <= months}):
                gross = future_value(pv, payment, 0.07, month)
                net = liquidation(gross, cost_basis + payment * month, allowance, tax_rate)[0] if tax_ready and gross is not None else None
                finance["milestones"].append({"month": month, "date": _add_months(now, month).isoformat(), "gross": gross, "net": net, "rate": 0.07})

    finance["required_monthly_7"] = needed_seven
    if goal.get("status") == "completed":
        report["status"] = "completed"
    elif missing:
        report["status"] = "needs_input"
        if report["summary"] == "계산에 필요한 조건을 먼저 확인하세요.":
            report["summary"] = f"‘{title}’의 현재 상태와 완료 기준은 기록했지만, 확정적인 경로를 제안하려면 누락된 조건을 먼저 확인해야 합니다."
        else:
            report["summary"] += " 신규 납입 등 미확인 조건이 있어 조건부 계산으로만 사용하세요."
    elif finance.get("goal_satisfied"):
        report["status"] = "on_track"
    elif finance["required_return"] is None or finance["required_return"] > 0.10:
        report["status"] = "at_risk"
    else:
        report["status"] = "conditional"
    report["phases"] = _phases(title, max(0, (due - anchor).days) if due is not None else 0,
                               pv, target, payment, needed_seven, target_label)
    report["checkpoints"] = [
        "매월: 실제 신규 납입액과 생활비·세금 차감 후 지속 가능성을 확인합니다.",
        "분기별: 자산 기준일·목표 범위·납입 내역·집중도·남은 기한을 갱신하고 필요 조건을 재계산합니다.",
        "소득·지출·목표·세법이 바뀌면 기존 계획의 가정을 수정합니다. 장기 단계를 첫 달에 완료한 것으로 취급하지 않습니다.",
        "목표에 근접하면 매도 비용과 실제 세무 원가를 확인하고, 평가액 달성과 세후 현금 확보를 구분해 완료합니다.",
    ]
    if payment is not None and selected_ready:
        reached = 0 if finance.get("goal_satisfied") else None
        if reached is None:
            for month in range(1, 721):
                gross = future_value(pv, payment, 0.07, month)
                if gross is None:
                    break
                value = liquidation(gross, cost_basis + payment * month, allowance, tax_rate)[0] if after_tax else gross
                if value >= target:
                    reached = month
                    break
        finance["months_at_7"] = reached
        if reached is not None:
            report["checkpoints"].append(f"기간 대안: 월 {_money(payment)}·연 7% 가정에서는 목표까지 약 {reached / 12:.1f}년입니다. 세금 적용 범위와 수익률은 위 가정과 동일하며 예측이 아닙니다.")
    report["missing"] = list(dict.fromkeys(missing))
    report["warnings"] = list(dict.fromkeys(warnings))
    return report
