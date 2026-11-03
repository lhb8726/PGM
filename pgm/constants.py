"""Shared product labels. No external scoring norms are implied."""

CATEGORIES = {
    "finance": {"name": "금융·자산", "color": "#e5bd67", "icon": "₩", "description": "자산과 현금흐름"},
    "career": {"name": "커리어·전문성", "color": "#a08afa", "icon": "↗", "description": "경력과 결과물"},
    "learning": {"name": "학습·지식", "color": "#70c4da", "icon": "▤", "description": "배움과 지식"},
    "health": {"name": "건강·체력", "color": "#82c5a3", "icon": "♡", "description": "운동과 생활 기록"},
    "life": {"name": "경험·라이프", "color": "#df9ab1", "icon": "✧", "description": "경험과 새로운 시도"},
    "habits": {"name": "자기관리·습관", "color": "#e7a17b", "icon": "◷", "description": "꾸준함과 집중"},
}
HORIZONS = {"short": "단기", "medium": "중기", "long": "장기"}
KINDS = {"numeric": "수치 목표", "deliverable": "결과물 목표", "habit": "반복 목표"}
PRIORITIES = {1: "낮음", 2: "보통", 3: "높음"}
NAVIGATION = [
    ("dashboard", "◈", "대시보드"),
    ("profile", "◎", "나의 프로필·진단"),
    ("goals", "◉", "목표 관리"),
    ("roadmap", "⌁", "성장 로드맵"),
    ("today", "☑", "오늘의 실행"),
    ("analysis", "▥", "성장 분석·회고"),
    ("coach", "✦", "코치"),
    ("settings", "⚙", "설정"),
]
