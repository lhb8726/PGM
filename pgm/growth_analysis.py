"""Detailed, explainable growth-goal reports without an external AI service.

The module compares user-provided criteria, evidence and remaining resources.
It does not infer proficiency, medical outcomes or a probability of success.
Action durations below are editable planning estimates, not learning norms.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import math
import re
from urllib.parse import urlsplit


CATEGORY_NAMES = {
    "career": "커리어·전문성", "learning": "학습·지식", "health": "건강·체력",
    "life": "경험·라이프스타일", "habits": "자기관리·습관",
}
CAREER_PROFILE_FACT_PREFIX = "커리어 프로필 자기 보고 · "


def _text(value, limit=500):
    if not isinstance(value, str):
        return ""
    value = re.sub(r"</?[A-Za-z][^>]*>", "", value)
    value = "".join(ch for ch in value if ch.isprintable() or ch in "\n\t")
    return " ".join(value.split())[:limit]


def _career_profile_facts(profile):
    career = profile.get("career")
    if not isinstance(career, dict):
        career = {}
    facts = []
    for label, value in (
        ("현재 역할", profile.get("occupation")),
        ("경험 요약", profile.get("experience")),
        ("역량 요약", profile.get("skills")),
        ("희망 직무", career.get("desired_role")),
    ):
        if value := _text(value, 120):
            facts.append(f"{CAREER_PROFILE_FACT_PREFIX}{label}: {value}")

    for key, label, primary, fields in (
        ("skills", "기술", "name", ("level", "evidence")),
        ("employment", "업무 경력", "role", ("start_month", "end_month")),
        ("certificates", "자격 기록", "name", ("issuer", "issued_on")),
        ("portfolio", "포트폴리오", "title", ("role",)),
    ):
        entries = career.get(key)
        if not isinstance(entries, list):
            continue
        samples = []
        for row in entries:
            name = _text(row.get(primary), 80) if isinstance(row, dict) else ""
            if not name:
                continue
            parts = [name] + [_text(row.get(field), 80) for field in fields]
            samples.append(" · ".join(part for part in parts if part))
            if len(samples) == 3:
                break
        if samples:
            facts.append(f"{CAREER_PROFILE_FACT_PREFIX}{label} (최대 3건): {' / '.join(samples)}")
    return facts


def _number(value):
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    return None


def _created_date(value):
    parsed = _date(value)
    if parsed:
        return parsed
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    return None


def _fmt(value):
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"


def _action(title, minutes, done_when, why):
    return {"title": title, "minutes": minutes, "done_when": done_when, "why": why}


def _phases(category, title, criteria, requirements, evidence, constraints, days):
    """Keep the goal's later validation phases outside its first-week plan."""
    goal = f"‘{title}’"
    standard = requirements or criteria or "아직 입력하지 않은 완료 기준"
    proof = evidence or "아직 기록하지 않은 현재 결과물·측정값"
    limit = constraints or "시간·도구·활동·예산 제약의 유무"
    templates = {
        "career": [
            ("요구 기준과 현재 결과물 비교", "첫 1주", "지원·자격·업무 결과를 판단할 기준과 부족한 부분을 확인합니다.", [
                _action(f"{goal}의 요구 조건을 출처와 함께 정리", 30, f"{standard}에 대해 출처·확인일·필수/선택 조건을 기록", "직무명이나 자격명만으로 필요한 역량을 추측하지 않기 위해"),
                _action(f"{goal}에 사용할 현재 결과물 목록 작성", 30, f"{proof}를 기준별로 연결하고 없는 증빙을 표시", "자기평가와 확인 가능한 결과물을 구분하기 위해"),
            ]),
            ("우선 역량과 첫 작업 설계", "2주차부터 · 남은 기간 전반", "필수 조건의 차이를 작은 연습과 작업 단위로 바꿉니다.", [
                _action(f"{goal}의 첫 보완 역량 1개 선정", 30, "선정 이유·선행 지식·완료 증빙·확인 방법을 한 장에 정리", "전체 역량을 동시에 공부하는 대신 기준과 연결된 우선순위를 정하기 위해"),
                _action(f"{goal}의 작은 실습·작업 초안 작성", 45, "선정한 역량을 보여주는 첫 파일·문서 또는 작업 기록 생성", "학습 시간뿐 아니라 결과로 부족한 부분을 확인하기 위해"),
            ]),
            ("중간 성과 제작과 피드백", "남은 기간 중반", "작업 결과를 완료 기준과 연결해 반복 개선합니다.", [
                _action(f"{goal}의 첫 중간 결과물 제작", 60, "사용한 방법·실행/확인 절차·한계를 포함한 초안 보관", "완성 여부를 다른 사람이 재확인할 수 있게 하기 위해"),
                _action(f"{goal}의 기준별 검토와 보완 기록", 30, f"{standard}별 충족/부족/미확인 표시와 다음 보완 항목 기록", "완료 과제 수를 숙련도나 채용 가능성으로 오해하지 않기 위해"),
            ]),
            ("실전 조건에 맞춘 검증", "후반부 · 최종 제출 전", "목표의 실제 평가·제출 조건에서 결과물을 확인합니다.", [
                _action(f"{goal}의 제출·평가 방식 점검", 30, "실제 제출 형식·일정·평가 항목을 다시 확인하고 체크리스트 갱신", "이전 자료나 임의 기준으로 마감 준비를 끝내지 않기 위해"),
                _action(f"{goal}의 설명·검토 연습", 45, "결과 설명, 부족한 답변, 받은 피드백과 수정 내역 기록", "결과를 만들고 설명하는 능력을 함께 확인하기 위해"),
            ]),
            ("최종 증빙 확인과 다음 경로", "마감 직전 · 완료 확인", "지원·자격 취득·결과물 완성을 실제 증빙으로 구분합니다.", [
                _action(f"{goal}의 최종 증빙 확인", 30, f"{criteria or '최종 완료 기준'} 충족 여부와 확인일 기록", "준비 과제 완료만으로 취업·합격·최종 승인을 자동 확정하지 않기 위해"),
                _action(f"{goal}의 결과 회고와 다음 보완 선정", 20, "실제 결과·부족한 기준·다음 목표를 구분한 회고 저장", "실제 결과를 다음 성장 경로의 근거로 남기기 위해"),
            ]),
        ],
        "learning": [
            ("현재 수준과 목표 평가 기준 확인", "첫 1주", "학습 출발점을 같은 기준으로 비교할 수 있게 기록합니다.", [
                _action(f"{goal}의 평가 범위·자료 출처 확인", 30, f"{standard}에 해당하는 출처·확인일·시험/과제 조건 기록", "검증하지 않은 학습 범위나 시험 일정을 사실로 두지 않기 위해"),
                _action(f"{goal}의 출발점 기록", 30, f"{proof}의 측정일·문제/과제·오답 또는 결과를 보관", "느낌에 따른 수준 판단을 실제 결과와 구분하기 위해"),
            ]),
            ("첫 학습 단원과 실행 일정", "2주차부터 · 남은 기간 전반", "목표 기준과 연결되는 첫 주제를 골라 실행합니다.", [
                _action(f"{goal}의 첫 핵심 주제 선정", 20, "선행 개념·사용 자료·학습 후 풀 과제를 함께 기록", "자료를 모으는 활동과 실제 학습을 연결하기 위해"),
                _action(f"{goal}의 첫 주제 학습·요약", 45, "자신의 설명·예제·모르는 부분이 포함된 요약 작성", "읽은 시간만으로 이해 여부를 판단하지 않기 위해"),
            ]),
            ("적용 연습과 부족한 부분 보완", "남은 기간 중반", "배운 내용을 문제·발표·제작 등 목표 방식으로 적용합니다.", [
                _action(f"{goal}의 적용 과제 수행", 45, "풀이·말하기·작성·제작 결과와 사용 조건 보관", "기억한 내용이 실제 과제로 연결되는지 확인하기 위해"),
                _action(f"{goal}의 오류·부족한 개념 정리", 30, "오류 원인과 다시 시도할 항목을 기준별로 기록", "반복 횟수와 실제 개선을 구분하기 위해"),
            ]),
            ("동일 기준의 중간 평가", "후반부 · 시험/완료 전", "처음과 비교 가능한 조건에서 목표와의 차이를 확인합니다.", [
                _action(f"{goal}의 모의 과제·중간 평가", 60, "자료·시간·채점 기준을 적고 실제 결과를 저장", "서로 다른 평가 조건의 점수를 그대로 비교하지 않기 위해"),
                _action(f"{goal}의 남은 학습 범위 조정", 20, "평가에서 확인한 부족 항목과 남은 시간을 반영한 수정안 작성", "계획량을 채우기보다 확인한 차이에 시간을 배분하기 위해"),
            ]),
            ("최종 평가와 유지 계획", "마감 직전 · 완료 확인", "시험 결과나 결과물로 완료 기준을 확인합니다.", [
                _action(f"{goal}의 최종 결과 확인", 30, f"{criteria or '목표 완료 기준'}에 맞는 결과·증빙·기준일 기록", "공부 시간과 시험·결과물 성과를 따로 관리하기 위해"),
                _action(f"{goal}의 복습·다음 학습 계획", 20, "유지할 내용과 다음 학습 주제를 실제 결과에 따라 기록", "완료 후의 유지와 다음 목표를 연결하기 위해"),
            ]),
        ],
        "health": [
            ("생활·활동 기록과 제약 확인", "첫 1주", "측정값과 생활 조건을 기록하며 의학적 진단을 추정하지 않습니다.", [
                _action(f"{goal}의 활동·수면·측정 기준 기록", 20, f"{proof}의 측정일·측정 방법·현재 상태를 기록", "자기평가와 측정한 사실을 구분하기 위해"),
                _action(f"{goal}의 활동 제약 확인", 20, f"{limit}을 기록하고 확인이 필요한 내용을 별도 표시", "제약을 모르는 상태에서 운동 강도·식단을 임의 처방하지 않기 위해"),
            ]),
            ("생활 목표와 실행 조건 설정", "2주차부터 · 남은 기간 전반", "사용자가 정한 행동과 기록 가능한 기준을 연결합니다.", [
                _action(f"{goal}의 행동·측정 기준 정리", 20, f"{standard}를 확인할 기록 방식·수행 조건 작성", "체크한 횟수와 실제 상태 변화를 구분하기 위해"),
                _action(f"{goal}의 가능한 시간·환경 확인", 20, "일정·이용 가능한 장소·도구·중단 시 확인할 조건 기록", "현실적인 환경과 개인 제약에 맞는 계획을 세우기 위해"),
            ]),
            ("선택한 행동 실행과 기록", "남은 기간 중반", "사용자가 선택한 활동을 실행하고 실제 상태를 기록합니다.", [
                _action(f"{goal}의 실행 기록 양식 만들기", 15, "수행일·실제 시간·측정 조건·특이 사항을 기록할 양식 준비", "활동 내용과 결과를 같은 기준으로 비교하기 위해"),
                _action(f"{goal}의 기록을 주간 점검", 20, "실제 수행·계획 차이·불편 또는 제약 변화와 조정 필요사항 기록", "계획을 무조건 늘리지 않고 지속 가능성을 확인하기 위해"),
            ]),
            ("같은 측정 방법으로 변화 확인", "후반부 · 중간 점검", "측정 방법을 유지하며 변화와 미확인 원인을 구분합니다.", [
                _action(f"{goal}의 비교 가능한 재측정 기록", 20, "이전과 같은 방법·단위·기준일로 현재값 저장", "다른 조건에서 나온 숫자를 개선 효과로 단정하지 않기 위해"),
                _action(f"{goal}의 일정·행동 조정안 작성", 20, "기록과 제약 변화에 따른 유지·축소·확인 필요 항목 구분", "건강 효과나 필요한 활동량을 기록 없이 추측하지 않기 위해"),
            ]),
            ("목표 기준 확인과 유지", "마감 직전 · 완료 확인", "자기관리 목표의 완료 여부와 이후 기록 계획을 정합니다.", [
                _action(f"{goal}의 완료 기준 확인", 20, f"{criteria or '사용자가 설정한 기준'}의 충족 여부·측정 근거 기록", "앱의 기록을 임상 진단이나 검증된 처방으로 표현하지 않기 위해"),
                _action(f"{goal}의 유지·재점검 계획", 15, "유지할 기록과 다음 확인일, 추가 확인이 필요한 사항 기록", "목표 종료 후에도 상태와 제약을 확인하기 위해"),
            ]),
        ],
        "life": [
            ("원하는 경험과 조건 구체화", "첫 1주", "완료한 경험의 모습과 필요한 자원을 정합니다.", [
                _action(f"{goal}의 원하는 결과 정리", 20, f"{standard}를 일정·참여 조건·결과물로 구체화", "목표를 신청·준비·참여·완료 단계로 구분하기 위해"),
                _action(f"{goal}의 시간·비용·참여 제약 확인", 30, f"{limit}과 비용 상한·확인할 출처·불확실한 조건 기록", "예산이나 참여 가능성을 모른 채 예약·지출을 전제로 두지 않기 위해"),
            ]),
            ("준비 항목과 확인 순서", "2주차부터 · 남은 기간 전반", "일정과 비용이 확정되기 전에 필요한 조건을 확인합니다.", [
                _action(f"{goal}의 후보·준비 항목 비교", 30, "확인한 조건·비용·일정·취소 가능 여부를 표로 정리", "검색 결과와 실제 이용 조건을 구분하기 위해"),
                _action(f"{goal}의 첫 준비 행동 실행", 30, "필요 자료·문의 결과·신청 조건 중 첫 확인 결과 저장", "지출을 자동 권유하지 않고 필요한 근거부터 확보하기 위해"),
            ]),
            ("실행 준비와 자원 점검", "남은 기간 중반", "예산과 일정이 맞는 범위에서 실제 실행을 준비합니다.", [
                _action(f"{goal}의 준비 체크리스트 점검", 30, "확인 완료·준비 중·미확인 항목과 담당/확인일 표시", "준비 과제 누락과 불확실성을 드러내기 위해"),
                _action(f"{goal}의 실제 비용·일정 갱신", 20, "실제 확인 금액·날짜·예산 차이와 조정안 기록", "초기 추정 비용을 확정된 지출로 취급하지 않기 위해"),
            ]),
            ("경험 실행과 결과 기록", "후반부 · 실제 참여 시점", "사용자가 선택한 경험을 실행하고 결과를 보관합니다.", [
                _action(f"{goal}의 실행 조건 최종 확인", 20, "참여·이동·준비물·연락·취소 조건을 실제 시점에 재확인", "이전에 확인한 조건이 그대로라고 가정하지 않기 위해"),
                _action(f"{goal}의 경험·결과 기록", 30, "참여 여부·결과물·실제 시간·비용 기록", "준비 완료와 실제 경험 완료를 구분하기 위해"),
            ]),
            ("완료 확인과 회고", "완료 직후 · 다음 계획", "처음 원한 경험과 실제 결과를 비교합니다.", [
                _action(f"{goal}의 완료 기준과 결과 비교", 20, f"{criteria or '처음 정한 기준'}과 실제 결과의 차이 기록", "사용자가 원한 결과를 확인하기 위해"),
                _action(f"{goal}의 다음 경험 개선점 정리", 15, "잘된 점·부족한 준비·다음에 바꿀 한 가지 기록", "경험을 다음 계획의 근거로 남기기 위해"),
            ]),
        ],
        "habits": [
            ("현재 행동과 방해 조건 파악", "첫 1주", "반복 행동을 시작하기 어려운 상황을 기록합니다.", [
                _action(f"{goal}의 현재 행동·방해 요인 기록", 20, f"{proof}와 행동이 되는/안 되는 상황을 구분해 기록", "성격이나 의지 점수로 실패 원인을 단정하지 않기 위해"),
                _action(f"{goal}의 반복 기준 확인", 15, f"{standard}를 행동·요일·최소 기준·확인 방식으로 작성", "쉬는 날과 수행해야 할 날을 구분하기 위해"),
            ]),
            ("시작 조건과 환경 설계", "2주차부터 · 남은 기간 전반", "작은 행동과 반복 가능한 시작 조건을 정합니다.", [
                _action(f"{goal}의 시작 신호·준비 환경 설정", 20, "시작할 상황·위치·도구와 방해 요인 조정안을 기록", "추상적인 다짐을 관찰 가능한 실행 조건으로 바꾸기 위해"),
                _action(f"{goal}의 반복 일정과 예외 기준 등록", 20, "수행 요일·최소 시간·미수행·휴식 처리 기준을 앱에 기록", "연속 기록을 유지하려고 수행 사실을 임의 입력하지 않기 위해"),
            ]),
            ("실행 시범과 실제 기록", "남은 기간 중반", "정한 행동의 실행 가능성을 기록으로 확인합니다.", [
                _action(f"{goal}의 첫 수행 기록 확인", 15, "예정 여부·실제 수행·실제 시간·중단 사유 저장", "계획된 시간과 실제 수행을 구분하기 위해"),
                _action(f"{goal}의 실행 어려움 한 가지 조정", 20, "실제 중단 사유와 바꿀 환경/행동 한 가지 기록", "수행량을 자동으로 늘리기보다 방해 조건부터 점검하기 위해"),
            ]),
            ("기간 실행률과 기준 조정", "후반부 · 주기 점검", "연속 달성과 기간 실행률을 함께 확인합니다.", [
                _action(f"{goal}의 예정 대비 실제 수행 비교", 20, "예정 기회·수행 횟수·예외일·부족한 기록을 구분", "연속 횟수 하나로 꾸준함이나 개인 가치를 평가하지 않기 위해"),
                _action(f"{goal}의 반복 기준 수정안 검토", 15, "유지할 기준과 바꿀 요일·환경·최소 행동을 근거와 함께 기록", "실행 결과에 따라 다음 기간의 부담을 조절하기 위해"),
            ]),
            ("목표 기간 완료와 유지", "마감 직전 · 다음 반복 주기", "지정 기간의 실행 기준을 확인하고 다음 주기를 정합니다.", [
                _action(f"{goal}의 기간 완료 기준 확인", 20, f"{criteria or '정한 수행 기준'}의 기간·분모·실제 기록 확인", "준비 과제 완료를 반복 행동의 최종 성과로 바꾸지 않기 위해"),
                _action(f"{goal}의 유지 계획 작성", 15, "다음 주기의 수행 기준과 다시 점검할 날짜 기록", "일시적인 연속 달성과 지속 계획을 구분하기 위해"),
            ]),
        ],
    }
    span = max(0, days or 0)
    offsets = [
        (0, min(span, 7)),
        (min(span, 7), max(min(span, 7), int(span * .45))),
        (min(span, max(14, int(span * .20))), max(min(span, max(14, int(span * .20))), int(span * .70))),
        (int(span * .60), int(span * .90)),
        (int(span * .85), span),
    ]
    result = []
    for index, (name, period, objective, actions) in enumerate(templates[category]):
        start, end = offsets[index]
        result.append({"title": name, "period": period, "objective": objective,
                       "start_day": start, "end_day": end, "actions": actions})
    return result


def analyze_growth(goal, profile, metrics, tasks, habits=None, today=None):
    """Return a conditional report grounded in inputs, with no hidden forecasts."""
    now = _date(today) or date.today()
    category = goal.get("category", "career")
    category = category if category in CATEGORY_NAMES else "career"
    title = _text(goal.get("title")) or "제목 미입력 목표"
    plan = goal.get("planning") if isinstance(goal.get("planning"), dict) else {}
    criteria = _text(goal.get("criteria"))
    requirements = _text(plan.get("requirements"))
    evidence = _text(plan.get("evidence"))
    context = _text(plan.get("context"))
    constraints = _text(plan.get("constraints"))
    due = _date(goal.get("due_date"))
    days = (due - now).days if due else None
    anchor = _created_date(goal.get("created_at")) or now
    phase_days = (due - anchor).days if due else 0
    missing, warnings, facts, scenarios = [], [], [], []
    risky = False
    facts.append(f"사용자 입력 목표: {title} · {CATEGORY_NAMES[category]}")
    facts.append(f"단계 일정 기준일 {anchor.isoformat()} · 목표 생성일 기준으로 고정")
    if due:
        facts.append(f"입력한 기한 {due.isoformat()} · 분석 기준일 {now.isoformat()} · 남은 {max(0, days)}일")
        if days < 0:
            warnings.append("목표 기한이 지났습니다. 기존 완료 기록을 보존하고 기한·범위·완료 여부를 먼저 확인하세요.")
            risky = True
    else:
        missing.append("유효한 목표 기한")
    if criteria:
        facts.append(f"사용자 입력 완료 기준: {criteria}")
    else:
        missing.append("목표 달성을 확인할 구체적인 완료 기준")
    if requirements:
        facts.append(f"사용자 입력 요구 조건: {requirements}")
    else:
        missing.append("목표의 필수 요구 조건·평가 범위")
    if context:
        facts.append(f"사용자 입력 배경: {context}")
    if constraints:
        facts.append(f"사용자 입력 제약: {constraints}")
    elif category in {"health", "life"}:
        missing.append("활동·일정·참여 제약의 유무(없으면 '없음' 명시)")

    recorded = [m for m in (metrics or []) if m.get("category") == category]
    recorded.sort(key=lambda m: str(m.get("recorded_date", "")), reverse=True)
    if evidence:
        facts.append(f"사용자 입력 현재 상태·증빙 설명: {evidence}")
    for metric in recorded[:3]:
        kind = {"self": "자기 보고", "measured": "측정 기록으로 분류", "document": "문서·결과물로 분류"}.get(metric.get("evidence_kind"), "사용자 분류 미확인")
        value = _number(metric.get("value"))
        amount = _fmt(value) if value is not None else "값 미확인"
        facts.append(f"저장된 사용자 기록: {_text(metric.get('label'), 100)} {amount}{_text(metric.get('unit'), 30)} · {kind} · {_text(metric.get('recorded_date'), 20)} · {_text(metric.get('source'), 180) or '출처 미입력'}")
    if not evidence and not recorded:
        missing.append("현재 수준을 확인할 결과물·측정값·수행 기록")
    elif recorded and not evidence and all(m.get("evidence_kind") == "self" for m in recorded):
        missing.append("자기평가를 확인할 측정 방법 또는 결과물")

    related = [t for t in (tasks or []) if t.get("goal_id") == goal.get("id")]
    facts.append(f"연결된 준비 과제 {len(related)}개 중 {sum(bool(t.get('done')) for t in related)}개 완료 · 최종 성과는 별도 확인")
    if goal.get("kind") == "numeric":
        current, target = _number(goal.get("current")), _number(goal.get("target"))
        unit = _text(goal.get("unit"), 30)
        if current is None or target is None or not unit:
            missing.append("현재값·목표값·단위")
        else:
            change = current - target if goal.get("direction") == "decrease" else target - current
            facts.append(f"입력한 현재값 {_fmt(current)}{unit} → 목표값 {_fmt(target)}{unit} · 목표 방향 기준 남은 변화량 {_fmt(max(0, change))}{unit}")
            if change <= 0 and goal.get("status") != "completed":
                warnings.append("입력한 수치가 이미 목표 기준을 충족합니다. 실제 증빙과 완료 기준을 직접 확인하세요.")
    if category == "health":
        warnings.append("이 보고서는 생활·운동 기록의 계획 비교입니다. 의학적 진단·적정 체중·운동 강도·식단을 산출하지 않습니다.")
    if category == "career":
        facts.extend(_career_profile_facts(profile))
        warnings.append("준비 과제·결과물 충족 여부와 실제 채용·합격·최종 승인은 서로 다른 결과입니다.")

    hours = _number(plan.get("estimated_hours"))
    weekly = _number(plan.get("weekly_hours"))
    shared = _number(profile.get("weekly_hours"))
    if hours is None or hours < 0:
        hours = None
        missing.append("앞으로 남은 작업의 예상 총시간(사용자 추정)")
    else:
        facts.append(f"사용자 추정 남은 작업 {_fmt(hours)}시간")
    if weekly is None or not 0 <= weekly <= 168:
        weekly = None
        missing.append("이 목표에 배정할 주당 순가용 시간")
    else:
        facts.append(f"사용자 배정 시간 주 {_fmt(weekly)}시간")
    if shared is not None and shared >= 0:
        facts.append(f"설정의 전체 목표용 주간 순가용 시간 {_fmt(shared)}시간 · 다른 목표와 공유")
        if weekly is not None and weekly > shared:
            warnings.append(f"이 목표의 주간 배정 {_fmt(weekly)}시간이 전체 가용 {_fmt(shared)}시간을 초과합니다.")
            risky = True
    cost = _number(plan.get("monthly_cost"))
    budget = _number(profile.get("monthly_budget"))
    if cost is not None and cost >= 0:
        facts.append(f"사용자 예상 월 필요 비용 {_fmt(cost)} · 프로필과 동일 통화 기준")
        if budget is not None and budget >= 0 and cost > budget:
            warnings.append(f"이 목표의 예상 월 비용 {_fmt(cost)}이 전체 목표용 월 가용 예산 {_fmt(budget)}을 초과합니다.")
            risky = True
    elif category == "life":
        missing.append("예상 월 비용 또는 비용이 없다는 확인값 0")

    if hours is None or weekly is None or days is None:
        scenarios.append({"name": "현재 조건 유지", "result": "완료 시점·시간 충족 여부: 정보 부족", "requirement": "남은 예상 작업 시간·주간 배정 시간·기한 입력", "note": "학습 기간이나 숙련 속도를 임의 추정하지 않았습니다."})
    else:
        capacity = weekly * max(0, days) / 7
        feasible = hours <= capacity
        if hours > 0 and days <= 0:
            feasible = False
            warnings.append("남은 작업이 있으나 미래 계획을 배치할 기간이 없습니다.")
        if not feasible:
            risky = True
            warnings.append(f"현재 조건의 시간 총량이 약 {_fmt(max(0, hours-capacity))}시간 부족합니다. 기한·범위·배정 시간을 조정하세요.")
        scenarios.append({"name": "현재 조건 유지", "result": f"시간 총량 {'충족' if feasible else '부족'} · 약 {_fmt(capacity)}시간 배정 가능", "requirement": f"남은 사용자 예상 작업 {_fmt(hours)}시간", "note": "예상시간의 정확성·세부 일정·실력·최종 성공을 검증한 결과가 아닙니다."})
        if hours == 0:
            scenarios.append({"name": "완료 기준 재확인", "result": "입력한 남은 작업 시간 0시간", "requirement": "증빙과 실제 완료 기준을 직접 확인", "note": "0시간 입력만으로 목표 상태를 완료로 바꾸지 않습니다."})
        else:
            if weekly > 0:
                needed_days = hours / weekly * 7
                extra_days = math.ceil(needed_days) if math.isfinite(needed_days) else 36526
                if extra_days <= 36525 and now.toordinal()+extra_days <= date.max.toordinal():
                    end = now + timedelta(days=extra_days)
                    result = f"주 {_fmt(weekly)}시간 기준 약 {extra_days}일 · {end.isoformat()}"
                else:
                    result = "예상 완료일이 계산 범위(약 100년)를 초과합니다."
                scenarios.append({"name": "기한 재설정", "result": result, "requirement": "현재 배정 시간을 유지할 수 있는지 확인", "note": "매주 같은 시간을 쓰고 추가 작업·휴식 변동이 없다는 단순 시간 모형입니다."})
            else:
                scenarios.append({"name": "기한 재설정", "result": "주간 배정 시간이 0이어서 완료일 계산 불가", "requirement": "주간 시간을 확보하거나 목표 범위를 다시 정의", "note": "가용 시간을 임의로 배정하지 않습니다."})
            if days > 0:
                required = hours / (days / 7)
                scenarios.append({"name": "주간 시간 조정", "result": f"입력한 기한을 유지하려면 주 약 {_fmt(required)}시간 필요", "requirement": "다른 목표·휴식·고정 일정과 함께 배정 가능 여부 확인", "note": "전체 가용 시간을 늘릴 수 있다는 소득·생활 전망이 아닙니다."})

    sources = []
    reference = _text(plan.get("reference_url"), 2000)
    if reference:
        try:
            parsed = urlsplit(reference)
            valid = parsed.scheme in {"http", "https"} and bool(parsed.hostname) and parsed.username is None and not any(ch.isspace() for ch in reference)
        except ValueError:
            valid = False
        if valid:
            sources.append({"title": "사용자 제공 참고자료 · 내용 미검증", "url": reference, "checked_on": ""})
        else:
            warnings.append("참고자료 URL 형식이 올바르지 않아 출처 링크에 포함하지 않았습니다.")
    elif requirements:
        missing.append("요구 조건을 재확인할 출처 또는 직접 정한 기준이라는 설명")

    missing = list(dict.fromkeys(missing))
    status = "completed" if goal.get("status") == "completed" else "at_risk" if risky else "needs_input" if missing else "conditional"
    if status == "completed":
        summary = f"‘{title}’는 사용자가 완료 확인한 목표입니다. 최종 증빙과 다음 유지 계획을 검토하세요."
    elif risky:
        summary = f"‘{title}’의 입력 조건에서 기한·시간·예산 중 조정이 필요한 항목을 발견했습니다. {len(missing)}개 정보가 추가로 필요합니다."
    elif missing:
        summary = f"‘{title}’의 세부 경로 초안을 만들었습니다. {len(missing)}개 확인 항목이 남아 있어 실현 가능성을 확정하지 않았습니다."
    else:
        summary = f"‘{title}’의 입력한 기준과 시간 조건을 비교했습니다. 조건부 실행 초안이며 실제 기록으로 재검토해야 합니다."
    return {
        "status": status, "summary": summary, "facts": facts, "anchor_on": anchor.isoformat(),
        "assumptions": [
            "남은 작업 시간과 배정 시간은 사용자 입력값이며 실제 숙련 속도를 검증한 값이 아닙니다.",
            "주간 배정 시간을 동일하게 유지하는 시간 총량 비교입니다. 다른 목표와의 합계·세부 일정은 공통 계획에서 확인합니다.",
            "각 실행 과제의 분 단위 시간은 첫 행동을 위한 수정 가능한 초안입니다. 단계 전체의 소요시간이나 성공 가능성을 뜻하지 않습니다.",
            "저장된 자기 보고·측정·문서 분류는 자료의 진위나 공인된 역량을 자동 검증하지 않습니다.",
        ],
        "missing": missing, "warnings": list(dict.fromkeys(warnings)), "scenarios": scenarios,
        "phases": _phases(category, title, criteria, requirements, evidence, constraints, phase_days),
        "checkpoints": [
            "매주: 예정·실제 수행 시간, 만들어진 결과물, 막힌 원인을 기록하고 다음 주 과제량을 조정합니다.",
            "매월: 같은 기준의 현재 상태와 완료 조건을 비교하고 남은 작업 시간·필요 비용을 다시 추정합니다.",
            "매 분기 또는 기한·제약 변경 시: 목표 범위·마감일·다른 목표의 자원 배분을 함께 재검토합니다.",
            "필수 기준·출처가 바뀌거나 실행 기록이 예상과 다르면 기존 완료 기록을 보존하고 변경안을 확인한 뒤 적용합니다.",
        ],
        "sources": sources,
    }
