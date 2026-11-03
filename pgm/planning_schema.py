"""Validated, optional evidence and assumptions used by goal analysis.

Missing numerical inputs stay ``None``. Zero is a recorded value, not missing
information. Monetary planning inputs use absolute KRW, independent of the
display unit selected on a numeric goal.
"""
from __future__ import annotations

import math
from urllib.parse import urlsplit


DEFAULT_PLANNING = {
    "context": "", "requirements": "", "evidence": "", "constraints": "",
    "reference_url": "", "estimated_hours": None, "weekly_hours": None,
    "monthly_cost": None, "monthly_contribution": None,
    "contribution_source": "", "contribution_confirmed": False,
    "target_basis": "account_value", "tax_cost_basis": None,
    "tax_rate": 22.0, "annual_allowance": 2_500_000.0,
    "tax_assumptions_confirmed": False,
}


def normalize_planning(data: dict | None = None) -> dict:
    if data is None:
        data = {}
    if not isinstance(data, dict) or set(data) - set(DEFAULT_PLANNING):
        raise ValueError("목표 분석 설정에 지원하지 않는 항목이 있습니다.")
    result = {**DEFAULT_PLANNING, **data}
    for key in ("context", "requirements", "evidence", "constraints", "contribution_source", "reference_url"):
        value = result[key]
        if not isinstance(value, str) or len(value) > (2000 if key == "reference_url" else 20000):
            raise ValueError("목표 분석 설명과 출처를 확인하세요.")
        result[key] = value.strip()
    if result["reference_url"]:
        try:
            url = urlsplit(result["reference_url"])
        except ValueError as exc:
            raise ValueError("출처는 http 또는 https 주소를 입력하세요.") from exc
        if (url.scheme.lower() not in {"http", "https"} or not url.hostname
                or url.username or url.password or any(character.isspace() for character in result["reference_url"])):
            raise ValueError("출처는 로그인 정보가 없는 http 또는 https 주소를 입력하세요.")
    for key in ("contribution_confirmed", "tax_assumptions_confirmed"):
        if not isinstance(result[key], bool):
            raise ValueError("목표 분석의 확인 항목은 참 또는 거짓이어야 합니다.")
    if not isinstance(result["target_basis"], str) or result["target_basis"] not in {"account_value", "after_tax_cash"}:
        raise ValueError("자산 목표의 완료 기준을 확인하세요.")
    optional = ("estimated_hours", "weekly_hours", "monthly_cost", "monthly_contribution", "tax_cost_basis")
    for key in (*optional, "tax_rate", "annual_allowance"):
        value = result[key]
        if key in optional and value is None:
            continue
        if isinstance(value, bool):
            raise ValueError("목표 분석 수치는 숫자로 입력하세요.")
        try:
            value = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("목표 분석 수치를 확인하세요.") from exc
        maximum = 168 if key == "weekly_hours" else 1e15
        if not math.isfinite(value) or value < 0 or value > maximum or (key == "tax_rate" and value >= 100):
            raise ValueError("목표 분석 수치의 범위를 확인하세요.")
        result[key] = value
    return result
