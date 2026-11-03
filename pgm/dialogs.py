"""Editable Qt forms. Dialogs return plain dictionaries and never access storage."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .constants import CATEGORIES, HORIZONS, KINDS


def _select(combo: QComboBox, value: Any) -> None:
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)


def _choices(items: dict[str, Any], value: Any = None) -> QComboBox:
    combo = QComboBox()
    for key, item in items.items():
        combo.addItem(item["name"] if isinstance(item, dict) else str(item), key)
    _select(combo, value)
    return combo


def _date(value: str | None = None, offset: int = 0) -> QDateEdit:
    parsed = QDate.fromString(str(value or ""), "yyyy-MM-dd")
    editor = QDateEdit(parsed if parsed.isValid() else QDate.currentDate().addDays(offset))
    editor.setCalendarPopup(True)
    editor.setDisplayFormat("yyyy-MM-dd")
    editor.setMinimumDate(QDate(1900, 1, 1))
    editor.setMaximumDate(QDate(2200, 12, 31))
    return editor


def _text(value: str = "", placeholder: str = "", height: int = 88) -> QTextEdit:
    editor = QTextEdit()
    editor.setPlainText(str(value or ""))
    editor.setPlaceholderText(placeholder)
    editor.setMinimumHeight(height)
    editor.setMaximumHeight(height + 22)
    editor.setAcceptRichText(False)
    return editor


def _number(value: float = 0) -> QDoubleSpinBox:
    editor = QDoubleSpinBox()
    editor.setRange(-1_000_000_000_000, 1_000_000_000_000)
    editor.setDecimals(2)
    editor.setGroupSeparatorShown(True)
    editor.setValue(float(value or 0))
    return editor


class _FormDialog(QDialog):
    """A scrollable form with consistent layout and validation feedback."""

    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(540)
        self.resize(600, 720)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 20)
        outer.setSpacing(16)
        heading = QLabel(title)
        heading.setObjectName("dialogTitle")
        heading.setStyleSheet("font-size: 21px; font-weight: 700;")
        outer.addWidget(heading)
        description = QLabel(subtitle)
        description.setWordWrap(True)
        description.setObjectName("muted")
        outer.addWidget(description)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self.form = QFormLayout(body)
        self.form.setContentsMargins(0, 4, 12, 4)
        self.form.setHorizontalSpacing(20)
        self.form.setVerticalSpacing(14)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("취소")
        cancel.setMinimumWidth(84)
        cancel.clicked.connect(self.reject)
        self.save_button = QPushButton("저장")
        self.save_button.setObjectName("primary")
        self.save_button.setProperty("primary", True)
        self.save_button.setMinimumWidth(100)
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(self.save_button)
        outer.addLayout(buttons)

    def _required(self, field: QWidget, message: str) -> bool:
        QMessageBox.warning(self, "입력 내용을 확인해 주세요", message)
        field.setFocus()
        return False


class GoalDialog(_FormDialog):
    def __init__(self, goal: dict | None = None, parent: QWidget | None = None):
        self.original = dict(goal or {})
        super().__init__(
            "목표 수정" if goal else "새로운 목표",
            "이루고 싶은 결과와 완료 기준을 정하세요. 계획 과제를 끝내도 최종 목표는 별도로 확인합니다.",
            parent,
        )
        g = self.original
        self.title_input = QLineEdit(str(g.get("title", "")))
        self.title_input.setPlaceholderText("예: 데이터 분석 포트폴리오 완성")
        self.category_input = _choices(CATEGORIES, g.get("category", "career"))
        self.kind_input = _choices(KINDS, g.get("kind", "deliverable"))
        self.horizon_input = _choices(HORIZONS, g.get("horizon", "short"))
        self.due_input = _date(g.get("due_date"), 30)
        self.priority_input = _choices({"3": "높음", "2": "보통", "1": "낮음"}, str(g.get("priority", 2)))
        self.criteria_input = _text(
            g.get("criteria", ""), "예: 프로젝트 2개, 설명 문서, 실행 방법을 포함해 최종 검토 완료", 90
        )
        self.status_input = _choices({"active": "진행 중", "completed": "목표 달성 확인"}, g.get("status", "active"))
        self.form.addRow("목표 이름 *", self.title_input)
        self.form.addRow("분야", self.category_input)
        self.form.addRow("목표 유형", self.kind_input)
        self.form.addRow("기간 구분", self.horizon_input)
        self.form.addRow("목표 기한", self.due_input)
        self.form.addRow("우선순위", self.priority_input)
        self.form.addRow("완료 기준 *", self.criteria_input)
        self.numeric_box = QWidget()
        numeric = QFormLayout(self.numeric_box)
        numeric.setContentsMargins(0, 8, 0, 8)
        numeric.setSpacing(12)
        self.baseline_input = _number(g.get("baseline", 0))
        self.current_input = _number(g.get("current", g.get("baseline", 0)))
        self.target_input = _number(g.get("target", 100))
        self.unit_input = QLineEdit(str(g.get("unit", "")))
        self.unit_input.setPlaceholderText("원, 점, kg, 개 등")
        self.direction_input = _choices({"increase": "증가할수록 목표에 가까움", "decrease": "감소할수록 목표에 가까움"}, g.get("direction", "increase"))
        for label, widget in [
            ("시작값", self.baseline_input), ("현재값", self.current_input),
            ("목표값", self.target_input), ("단위 *", self.unit_input), ("목표 방향", self.direction_input),
        ]:
            numeric.addRow(label, widget)
        self.numeric_notice = QLabel()
        self.numeric_notice.setWordWrap(True)
        self.numeric_notice.setObjectName("muted")
        numeric.addRow(self.numeric_notice)
        self.form.addRow(self.numeric_box)
        self.form.addRow("목표 상태", self.status_input)
        note = QLabel("‘목표 달성 확인’은 결과나 증빙을 직접 확인한 기록입니다. AI나 과제 완료만으로 자동 확정하지 않습니다.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        self.form.addRow(note)
        self.kind_input.currentIndexChanged.connect(self._numeric_visibility)
        self.direction_input.currentIndexChanged.connect(self._update_notice)
        self.baseline_input.valueChanged.connect(self._update_notice)
        self.target_input.valueChanged.connect(self._update_notice)
        self._numeric_visibility()

    def _numeric_visibility(self, *_args) -> None:
        self.numeric_box.setVisible(self.kind_input.currentData() == "numeric")
        self._update_notice()

    def _update_notice(self, *_args) -> None:
        start, target = self.baseline_input.value(), self.target_input.value()
        direction = self.direction_input.currentData()
        reached_at_start = start >= target if direction == "increase" else start <= target
        self.numeric_notice.setText(
            "시작값이 이미 목표 기준을 충족합니다. 진행률 계산 대신 현재값의 목표 충족 여부를 확인합니다."
            if reached_at_start else "시작값 대비 현재값의 변화를 표시합니다. 최종 목표 완료는 직접 확인해 주세요."
        )

    def values(self) -> dict:
        return {
            **self.original,
            "title": self.title_input.text().strip(), "category": self.category_input.currentData(),
            "kind": self.kind_input.currentData(), "horizon": self.horizon_input.currentData(),
            "due_date": self.due_input.date().toString("yyyy-MM-dd"),
            "priority": int(self.priority_input.currentData()),
            "baseline": self.baseline_input.value(), "current": self.current_input.value(),
            "target": self.target_input.value(), "unit": self.unit_input.text().strip(),
            "direction": self.direction_input.currentData(), "criteria": self.criteria_input.toPlainText().strip(),
            "status": self.status_input.currentData(),
        }

    def accept(self) -> None:
        values = self.values()
        if not values["title"]:
            self._required(self.title_input, "목표 이름을 입력해 주세요.")
            return
        if not values["criteria"]:
            self._required(self.criteria_input, "달성 여부를 확인할 수 있는 완료 기준을 입력해 주세요.")
            return
        if not self.original.get("id") and self.due_input.date() < QDate.currentDate():
            self._required(self.due_input, "새 목표의 기한은 오늘 이후로 지정해 주세요.")
            return
        if values["kind"] == "numeric" and not values["unit"]:
            self._required(self.unit_input, "수치 목표의 단위를 입력해 주세요.")
            return
        if values["status"] == "completed" and self.original.get("status") != "completed":
            result = QMessageBox.question(
                self, "목표 달성 확인", "설정한 완료 기준과 결과를 직접 확인했나요?\n확인한 경우에만 목표를 완료 처리합니다.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
            )
            if result != QMessageBox.StandardButton.Yes:
                return
        super().accept()


class TaskDialog(_FormDialog):
    def __init__(self, goals: list[dict], task: dict | None = None, parent: QWidget | None = None):
        self.original = dict(task or {})
        super().__init__("과제 수정" if task else "실행 과제 추가", "과제를 목표에 연결하고 날짜와 예상 시간을 정하세요.", parent)
        t = self.original
        self.goal_input = QComboBox()
        for goal in goals:
            self.goal_input.addItem(goal["title"], goal["id"])
        _select(self.goal_input, t.get("goal_id"))
        self.title_input = QLineEdit(str(t.get("title", "")))
        self.title_input.setPlaceholderText("예: 프로젝트 주제와 데이터셋 선정")
        self.scheduled_input = QCheckBox("날짜 지정")
        self.scheduled_input.setChecked(bool(t.get("scheduled_date")) if task else True)
        self.date_input = _date(t.get("scheduled_date"))
        self.date_input.setEnabled(self.scheduled_input.isChecked())
        self.scheduled_input.toggled.connect(self.date_input.setEnabled)
        schedule = QWidget()
        row = QHBoxLayout(schedule)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.scheduled_input)
        row.addWidget(self.date_input, 1)
        self.minutes_input = QSpinBox()
        self.minutes_input.setRange(1, 1440)
        self.minutes_input.setSingleStep(5)
        self.minutes_input.setSuffix(" 분")
        self.minutes_input.setValue(int(t.get("minutes", 30)))
        self.actual_input = QSpinBox()
        self.actual_input.setRange(0, 10080)
        self.actual_input.setSuffix(" 분")
        self.actual_input.setValue(int(t.get("actual_minutes", 0)))
        self.stage_input = QLineEdit(str(t.get("stage", "직접 작성")))
        self.done_input = QCheckBox("이 과제를 완료했습니다")
        self.done_input.setChecked(bool(t.get("done", False)))
        for label, widget in [
            ("연결 목표 *", self.goal_input), ("과제 이름 *", self.title_input),
            ("실행 날짜", schedule), ("예상 시간", self.minutes_input),
            ("실제 시간", self.actual_input), ("단계 / 중간 성과", self.stage_input), ("실행 상태", self.done_input),
        ]:
            self.form.addRow(label, widget)
        note = QLabel("실제 시간은 한 번만 기록됩니다. 과제 완료와 최종 목표 달성은 별도입니다.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        self.form.addRow(note)
        self.resize(580, 600)

    def values(self) -> dict:
        return {
            **self.original,
            "goal_id": self.goal_input.currentData(), "title": self.title_input.text().strip(),
            "scheduled_date": self.date_input.date().toString("yyyy-MM-dd") if self.scheduled_input.isChecked() else "",
            "minutes": self.minutes_input.value(), "actual_minutes": self.actual_input.value(),
            "stage": self.stage_input.text().strip() or "직접 작성", "done": self.done_input.isChecked(),
            "position": self.original.get("position", 0),
        }

    def accept(self) -> None:
        if self.goal_input.currentData() is None:
            self._required(self.goal_input, "먼저 목표를 등록한 뒤 과제를 연결해 주세요.")
            return
        if not self.title_input.text().strip():
            self._required(self.title_input, "실행할 과제 이름을 입력해 주세요.")
            return
        super().accept()


class MetricDialog(_FormDialog):
    def __init__(self, category: str | None = None, parent: QWidget | None = None):
        super().__init__("현재 상태 기록", "측정한 값과 근거를 남기세요. 자기평가와 실제 측정 자료는 구분해서 표시합니다.", parent)
        self.category_input = _choices(CATEGORIES, category or "learning")
        self.label_input = QLineEdit()
        self.label_input.setPlaceholderText("예: 영어 모의시험 점수, 주간 운동 횟수")
        self.value_input = _number()
        self.unit_input = QLineEdit()
        self.unit_input.setPlaceholderText("점, 회, 시간, 원 등")
        self.evidence_input = _choices({"self": "자기평가", "measured": "직접 측정", "document": "시험 / 결과물 / 문서"}, "self")
        self.source_input = QLineEdit("사용자 자기평가")
        self.source_input.setPlaceholderText("측정 방법, 시험명, 결과물 이름 또는 URL")
        self.date_input = _date()
        for label, widget in [
            ("분야", self.category_input), ("지표 이름 *", self.label_input),
            ("현재 값", self.value_input), ("단위 *", self.unit_input), ("근거 유형", self.evidence_input),
            ("출처 / 측정 방법 *", self.source_input), ("측정 기준일", self.date_input),
        ]:
            self.form.addRow(label, widget)
        self.evidence_input.currentIndexChanged.connect(self._evidence_changed)
        self.resize(580, 580)

    def _evidence_changed(self, *_args) -> None:
        if self.evidence_input.currentData() != "self" and self.source_input.text() == "사용자 자기평가":
            self.source_input.clear()
        elif self.evidence_input.currentData() == "self" and not self.source_input.text():
            self.source_input.setText("사용자 자기평가")

    def values(self) -> dict:
        return {
            "category": self.category_input.currentData(), "label": self.label_input.text().strip(),
            "value": self.value_input.value(), "unit": self.unit_input.text().strip(),
            "evidence_kind": self.evidence_input.currentData(), "source": self.source_input.text().strip(),
            "recorded_date": self.date_input.date().toString("yyyy-MM-dd"),
        }

    def accept(self) -> None:
        for field, message in [
            (self.label_input, "기록할 지표 이름을 입력해 주세요."),
            (self.unit_input, "측정값의 단위를 입력해 주세요."),
            (self.source_input, "자료의 출처나 측정 방법을 입력해 주세요."),
        ]:
            if not field.text().strip():
                self._required(field, message)
                return
        if self.date_input.date() > QDate.currentDate():
            self._required(self.date_input, "현재 상태의 측정 기준일은 미래 날짜로 기록할 수 없습니다.")
            return
        super().accept()


class HabitDialog(_FormDialog):
    def __init__(self, habit: dict | None = None, parent: QWidget | None = None):
        self.original = dict(habit or {})
        super().__init__("습관 수정" if habit else "반복 습관 만들기", "수행할 요일을 정하세요. 쉬는 날은 연속 달성 계산에서 제외됩니다.", parent)
        h = self.original
        self.title_input = QLineEdit(str(h.get("title", "")))
        self.title_input.setPlaceholderText("예: 하루 20분 독서")
        self.category_input = _choices(CATEGORIES, h.get("category", "habits"))
        self.minutes_input = QSpinBox()
        self.minutes_input.setRange(5, 120)
        self.minutes_input.setSingleStep(5)
        self.minutes_input.setSuffix(" 분")
        self.minutes_input.setValue(int(h.get("minutes", 10)))
        days = QWidget()
        row = QHBoxLayout(days)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.weekday_inputs = []
        selected = h.get("weekdays", [0, 1, 2, 3, 4])
        for index, label in enumerate(["월", "화", "수", "목", "금", "토", "일"]):
            checkbox = QCheckBox(label)
            checkbox.setChecked(index in selected)
            self.weekday_inputs.append(checkbox)
            row.addWidget(checkbox)
        self.form.addRow("습관 이름 *", self.title_input)
        self.form.addRow("분야", self.category_input)
        self.form.addRow("한 번에 쓸 시간", self.minutes_input)
        self.form.addRow("수행 요일 *", days)
        note = QLabel("이 시간은 로드맵의 가용 시간에서 예약됩니다. 같은 행동을 별도 과제로도 등록하면 중복이 될 수 있으니 한쪽에서 관리해 주세요.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        self.form.addRow(note)
        self.resize(580, 420)

    def values(self) -> dict:
        return {
            **self.original,
            "title": self.title_input.text().strip(), "category": self.category_input.currentData(),
            "minutes": self.minutes_input.value(),
            "weekdays": [i for i, checkbox in enumerate(self.weekday_inputs) if checkbox.isChecked()],
            "completions": list(self.original.get("completions", [])),
        }

    def accept(self) -> None:
        if not self.title_input.text().strip():
            self._required(self.title_input, "반복할 습관의 이름을 입력해 주세요.")
            return
        if not any(checkbox.isChecked() for checkbox in self.weekday_inputs):
            self._required(self.weekday_inputs[0], "수행할 요일을 하나 이상 선택해 주세요.")
            return
        super().accept()


class ReviewDialog(_FormDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("성장 회고 남기기", "실행 결과를 돌아보고 다음 계획에 반영할 행동을 적어 주세요.", parent)
        self.date_input = _date()
        self.good_input = _text(placeholder="계속 유지하고 싶은 행동이나 성과")
        self.challenge_input = _text(placeholder="막혔던 부분과 실제 원인")
        self.next_input = _text(placeholder="다음 주에 바꿀 구체적인 행동")
        self.form.addRow("회고 날짜", self.date_input)
        self.form.addRow("잘한 점", self.good_input)
        self.form.addRow("어려웠던 점", self.challenge_input)
        self.form.addRow("다음 개선 행동", self.next_input)
        self.resize(600, 610)

    def values(self) -> dict:
        return {
            "date": self.date_input.date().toString("yyyy-MM-dd"),
            "good": self.good_input.toPlainText().strip(), "challenge": self.challenge_input.toPlainText().strip(),
            "next_action": self.next_input.toPlainText().strip(),
        }

    def accept(self) -> None:
        values = self.values()
        if not any(values[key] for key in ("good", "challenge", "next_action")):
            self._required(self.good_input, "회고 내용을 한 가지 이상 입력해 주세요.")
            return
        super().accept()
