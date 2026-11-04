"""Shared field definitions and validation for the category profile."""

from datetime import date
from urllib.parse import urlsplit


FINANCE_AMOUNTS = {
    "assets": "총자산",
    "liabilities": "총부채",
    "monthly_income": "월 실수령 수입",
    "monthly_expenses": "월 생활 지출",
}

CAREER_SECTIONS = {
    "skills": ("스킬", (("name", "기술·도구"), ("level", "활용 수준"), ("evidence", "활용 사례·근거"))),
    "education": ("학력", (("school", "학교"), ("major", "전공"), ("degree", "학위"), ("status", "재학·졸업 상태"),
                         ("start_month", "입학월"), ("end_month", "졸업월"))),
    "employment": ("경력", (("company", "회사"), ("role", "직무·직급"), ("start_month", "입사월"),
                           ("end_month", "퇴사월"), ("details", "주요 업무·성과"))),
    "activities": ("인턴/대외활동", (("name", "활동명"), ("organization", "기관"), ("role", "담당 역할"),
                                  ("start_month", "시작월"), ("end_month", "종료월"), ("details", "활동·성과"))),
    "training": ("교육이수", (("name", "과정명"), ("organization", "교육기관"), ("start_month", "시작월"),
                           ("end_month", "수료월"), ("details", "이수 내용"))),
    "certificates": ("자격증", (("name", "자격증명"), ("issuer", "발급기관"), ("issued_on", "취득일"))),
    "awards": ("수상", (("name", "수상명"), ("issuer", "주최기관"), ("issued_on", "수상일"), ("details", "수상 내용"))),
    "overseas": ("해외경험", (("country", "국가"), ("purpose", "목적"), ("start_month", "시작월"),
                           ("end_month", "종료월"), ("details", "경험·성과"))),
    "languages": ("어학", (("language", "언어"), ("test", "시험명"), ("score", "점수·등급"), ("issued_on", "취득일"))),
    "portfolio": ("포트폴리오", (("title", "프로젝트·작업명"), ("role", "담당 역할"), ("url", "결과물 링크"),
                             ("details", "문제·기여·성과"))),
    "preferences": ("취업우대/병역", (("kind", "구분"), ("status", "해당 상태"), ("details", "비고"))),
}
OPTIONAL_CAREER_SECTIONS = tuple(key for key in CAREER_SECTIONS if key != "skills") + ("introduction",)


def _career_text(value, label, limit=300):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"{label}은(는) {limit:,}자 이내로 입력하세요.")
    return value.strip()


def _career_date(value, label, month_only):
    date_text = value + "-01" if month_only else value
    try:
        if date.fromisoformat(date_text).isoformat() == date_text:
            return
    except ValueError:
        pass
    format_text = "YYYY-MM" if month_only else "YYYY-MM-DD"
    raise ValueError(f"{label}은(는) {format_text} 형식으로 입력하세요.")


def _career_link(value):
    try:
        url = urlsplit(value)
        if (url.scheme in {"http", "https"} and url.hostname and not url.username
                and not url.password and not any(character.isspace() for character in value)):
            return
    except ValueError:
        pass
    raise ValueError("결과물 링크는 로그인 정보가 없는 http 또는 https 주소를 입력하세요.")


def normalize_career(data: dict) -> dict:
    if not isinstance(data, dict) or data.keys() - (CAREER_SECTIONS.keys() | {"desired_role", "introduction", "visible_sections"}):
        raise ValueError("커리어 프로필에 지원하지 않는 항목이 있습니다.")

    result = {}
    for key, title, limit in (("desired_role", "희망직무", 300), ("introduction", "자기소개", 20000)):
        value = _career_text(data.get(key, ""), title, limit)
        if value:
            result[key] = value

    for key, (title, fields) in CAREER_SECTIONS.items():
        entries = data.get(key, [])
        if not isinstance(entries, list) or len(entries) > 100:
            raise ValueError(f"{title}은(는) 최대 100개까지 기록할 수 있습니다.")
        normalized = []
        field_names = dict(fields)
        for entry in entries:
            if not isinstance(entry, dict) or entry.keys() - field_names.keys():
                raise ValueError(f"{title}의 입력 항목을 확인하세요.")
            values = {}
            for field, label in fields:
                limit = {"details": 20000, "evidence": 20000, "url": 2000}.get(field, 300)
                value = _career_text(entry.get(field, ""), label, limit)
                if not value:
                    continue
                if field.endswith("_month") or field == "issued_on":
                    _career_date(value, label, field.endswith("_month"))
                if field == "url":
                    _career_link(value)
                values[field] = value
            first_field, first_label = fields[0]
            if first_field not in values:
                raise ValueError(f"{title}의 {first_label}을(를) 입력하세요.")
            if values.get("end_month") and values.get("start_month", "") > values["end_month"]:
                raise ValueError(f"{title}의 종료월은 시작월과 같거나 이후여야 합니다.")
            normalized.append(values)
        if normalized:
            result[key] = normalized

    if "visible_sections" in data:
        sections = data["visible_sections"]
        if not isinstance(sections, list) or any(section not in OPTIONAL_CAREER_SECTIONS for section in sections):
            raise ValueError("표시할 커리어 항목을 확인하세요.")
        selected = [key for key in OPTIONAL_CAREER_SECTIONS if key in sections]
        if selected != [key for key in OPTIONAL_CAREER_SECTIONS if key in result]:
            result["visible_sections"] = selected
    return result
