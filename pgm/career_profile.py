"""Career profile editor with repeatable records for each section."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .dialogs import _FormDialog, _text
from .profile_schema import CAREER_SECTIONS, normalize_career
from .widgets import label, panel


_PLACEHOLDERS = {
    "start_month": "YYYY-MM",
    "end_month": "YYYY-MM · 진행 중이면 비워 두세요",
    "issued_on": "YYYY-MM-DD",
    "url": "https://example.com/portfolio",
}


class _CareerEntryDialog(_FormDialog):
    def __init__(self, section: str, records: list[dict[str, str]], row: int | None, parent: QWidget):
        name, fields = CAREER_SECTIONS[section]
        action = "수정" if row is not None else "추가"
        super().__init__(f"{name} {action}", "별표가 표시된 항목은 필수입니다.", parent)
        self.section = section
        self.records = list(records)
        self.row = row
        self.fields: dict[str, QLineEdit | QTextEdit] = {}
        self.save_button.setText("기록 반영")
        self.resize(600, min(650, 200 + len(fields) * 63))

        entry = records[row] if row is not None else {}
        for index, (key, title) in enumerate(fields):
            value = entry.get(key, "")
            if key in {"details", "evidence"}:
                editor = _text(value, height=78)
            else:
                editor = QLineEdit(value)
                editor.setPlaceholderText(_PLACEHOLDERS.get(key, ""))
            self.fields[key] = editor
            self.form.addRow(title + (" *" if index == 0 else ""), editor)

    def accept(self) -> None:
        values = {
            key: (editor.text() if isinstance(editor, QLineEdit) else editor.toPlainText()).strip()
            for key, editor in self.fields.items()
        }
        draft = list(self.records)
        if self.row is None:
            draft.append(values)
        else:
            draft[self.row] = values
        try:
            self.records = normalize_career({self.section: draft})[self.section]
        except ValueError as exc:
            first_key = CAREER_SECTIONS[self.section][1][0][0]
            self._required(self.fields[first_key], str(exc))
            return
        super().accept()


class CareerProfile(QWidget):
    """Edit structured career information alongside earlier profile memos."""

    def __init__(self, profile: dict, parent: QWidget | None = None):
        super().__init__(parent)
        career = profile.get("career") or {}
        self._records = {
            key: [dict(entry) for entry in career.get(key, [])]
            for key in CAREER_SECTIONS
        }

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        card, content = panel()
        layout.addWidget(card)
        content.addWidget(label("커리어 프로필", "sectionTitle"))
        content.addWidget(label("직무에 필요한 근거와 경험을 항목별로 기록하세요. 변경 내용은 프로필 저장으로 반영됩니다.", "muted", True))

        self.occupation = QLineEdit(profile.get("occupation") or "")
        self.occupation.setPlaceholderText("현재 직업 또는 역할")
        self.desired_role = QLineEdit(career.get("desired_role", ""))
        self.desired_role.setPlaceholderText("희망 직무")
        roles = QFormLayout()
        roles.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        roles.addRow("현재 직업·역할", self.occupation)
        roles.addRow("희망 직무", self.desired_role)
        content.addLayout(roles)

        section_row = QHBoxLayout()
        self.section_selector = QComboBox()
        self.section_selector.setAccessibleName("커리어 기록 분류")
        for key, (title, _fields) in CAREER_SECTIONS.items():
            self.section_selector.addItem(title, key)
        section_row.addWidget(self.section_selector, 1)
        self.record_count = label("", "muted")
        section_row.addWidget(self.record_count)
        content.addLayout(section_row)

        self.entries = QListWidget()
        self.entries.setAccessibleName("선택한 분류의 기록")
        self.entries.setAlternatingRowColors(True)
        self.entries.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.entries.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.empty_state = label("아직 기록이 없습니다. 항목을 추가해 보세요.", "muted", True)
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.record_view = QStackedWidget()
        self.record_view.setMinimumHeight(110)
        self.record_view.setMaximumHeight(160)
        self.record_view.addWidget(self.entries)
        self.record_view.addWidget(self.empty_state)
        content.addWidget(self.record_view)

        actions = QHBoxLayout()
        actions.addStretch()
        self.add_button = QPushButton("＋ 기록 추가")
        self.add_button.clicked.connect(lambda: self._open_entry())
        self.edit_button = QPushButton("선택 수정")
        self.edit_button.clicked.connect(self._edit_selected)
        self.delete_button = QPushButton("선택 삭제")
        self.delete_button.clicked.connect(self._delete_selected)
        for button in (self.add_button, self.edit_button, self.delete_button):
            actions.addWidget(button)
        content.addLayout(actions)

        self.introduction = _text(career.get("introduction", ""), "경험과 강점을 짧게 소개하세요.", 78)
        introduction_form = QFormLayout()
        introduction_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        introduction_form.addRow("자기소개", self.introduction)
        content.addLayout(introduction_form)

        memo_button = QPushButton("경력·역량 메모 편집")
        memo_button.setCheckable(True)
        memo_button.setObjectName("ghost")
        content.addWidget(memo_button, 0, Qt.AlignmentFlag.AlignLeft)
        memo_panel = QWidget()
        memos = QFormLayout(memo_panel)
        memos.setContentsMargins(0, 0, 0, 0)
        memos.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.experience = _text(profile.get("experience", ""), height=70)
        self.skills = _text(profile.get("skills", ""), height=70)
        memos.addRow("경력·경험 메모", self.experience)
        memos.addRow("역량·자격 메모", self.skills)
        memo_panel.hide()
        content.addWidget(memo_panel)
        memo_button.toggled.connect(memo_panel.setVisible)

        self.section_selector.currentIndexChanged.connect(lambda: self._refresh_records())
        self.entries.currentRowChanged.connect(self._update_actions)
        self.entries.itemDoubleClicked.connect(lambda: self._edit_selected())
        self._refresh_records()

    def values(self) -> dict:
        career = normalize_career({
            **self._records,
            "desired_role": self.desired_role.text(),
            "introduction": self.introduction.toPlainText(),
        })
        return {
            "occupation": self.occupation.text().strip(),
            "experience": self.experience.toPlainText().strip(),
            "skills": self.skills.toPlainText().strip(),
            "career": career,
        }

    def _refresh_records(self, select_row: int = -1) -> None:
        section = self.section_selector.currentData()
        records = self._records[section]
        self.entries.clear()
        fields = CAREER_SECTIONS[section][1]
        for entry in records:
            parts = [entry[key] for key, _title in fields if entry.get(key) and key not in {"details", "evidence"}]
            self.entries.addItem("  ·  ".join(parts))
        self.record_count.setText(f"{len(records)}개 기록")
        self.record_view.setCurrentWidget(self.entries if records else self.empty_state)
        if 0 <= select_row < len(records):
            self.entries.setCurrentRow(select_row)
        self._update_actions(self.entries.currentRow())

    def _update_actions(self, row: int) -> None:
        self.edit_button.setEnabled(row >= 0)
        self.delete_button.setEnabled(row >= 0)

    def _open_entry(self, row: int | None = None) -> None:
        section = self.section_selector.currentData()
        dialog = _CareerEntryDialog(section, self._records[section], row, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._records[section] = dialog.records
        self._refresh_records(len(dialog.records) - 1 if row is None else row)

    def _edit_selected(self) -> None:
        row = self.entries.currentRow()
        if row >= 0:
            self._open_entry(row)

    def _delete_selected(self) -> None:
        row = self.entries.currentRow()
        if row < 0:
            return
        answer = QMessageBox.question(
            self,
            "커리어 기록 삭제",
            "선택한 기록을 삭제할까요? 프로필을 저장하면 삭제가 반영됩니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            records = self._records[self.section_selector.currentData()]
            del records[row]
            self._refresh_records(min(row, len(records) - 1))
