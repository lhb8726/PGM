"""Career profile editor with repeatable records for each section."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .dialogs import _FormDialog, _text
from .profile_schema import CAREER_SECTIONS, OPTIONAL_CAREER_SECTIONS, normalize_career
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
    """Edit the visible career sections from a separate section menu."""

    def __init__(self, profile: dict, parent: QWidget | None = None):
        super().__init__(parent)
        career = profile.get("career") or {}
        self._records = {key: [dict(entry) for entry in career.get(key, [])] for key in CAREER_SECTIONS}
        inferred_sections = [key for key in OPTIONAL_CAREER_SECTIONS if key in career]
        self._visible_sections = set(career.get("visible_sections", inferred_sections))
        self._cards = {}
        self._record_lists = {}
        self._section_links = {}
        self._section_counts = {}
        self._active_section = "desired_role"
        self.section_toggles = {}
        self.record_add_buttons = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 16, 14, 16)
        layout.setSpacing(18)

        self.editor_scroll = QScrollArea()
        self.editor_scroll.setWidgetResizable(True)
        self.editor_scroll.setMinimumHeight(400)
        self.editor_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.editor_scroll.setAccessibleName("커리어 항목 편집")
        self._editor = QWidget()
        self.editor_scroll.setWidget(self._editor)
        layout.addWidget(self.editor_scroll, 1)
        self._content = QVBoxLayout(self._editor)
        self._content.setContentsMargins(0, 0, 8, 0)
        self._content.setSpacing(16)

        roles = self._section("desired_role", "희망직무")
        self.occupation = QLineEdit(profile.get("occupation") or "")
        self.occupation.setPlaceholderText("현재 직업 또는 역할")
        self.desired_role = QLineEdit(career.get("desired_role", ""))
        self.desired_role.setPlaceholderText("예  ·  데이터 분석가")
        for title, field in (("현재 직업·역할", self.occupation), ("희망직무", self.desired_role)):
            field.setAccessibleName(title)
            roles.addWidget(label(title, "muted", True))
            roles.addWidget(field)

        for key, (title, _fields) in CAREER_SECTIONS.items():
            add = QPushButton("＋ 기록 추가")
            add.setObjectName("subtle")
            add.setMinimumHeight(34)
            add.setAccessibleName(f"{title} 기록 추가")
            add.clicked.connect(lambda _checked=False, section=key: self._open_entry(section))
            self.record_add_buttons[key] = add
            content = self._section(key, title, add)
            self._record_lists[key] = QVBoxLayout()
            content.addLayout(self._record_lists[key])

        introduction = self._section("introduction", "자기소개")
        self.introduction = _text(career.get("introduction", ""), "경험과 강점을 소개하세요.", 110)
        self.introduction.setAccessibleName("자기소개")
        introduction.addWidget(self.introduction)
        self._add_legacy_memos(profile)
        self._content.addStretch()

        menu, items = panel()
        menu.setObjectName("careerMenu")
        items.setContentsMargins(14, 18, 14, 16)
        items.setSpacing(8)
        items.addWidget(label("커리어 항목", "sectionTitle"))
        items.addWidget(label("필요한 항목을 선택하세요.", "muted", True))
        items.addSpacing(6)
        names = {
            "desired_role": "희망직무",
            **{key: title for key, (title, _) in CAREER_SECTIONS.items()},
            "introduction": "자기소개",
        }
        for key, title in names.items():
            entry = QHBoxLayout()
            entry.setSpacing(6)
            link = QPushButton(title)
            link.setObjectName("careerSection")
            link.setCheckable(True)
            link.setMinimumHeight(36)
            link.clicked.connect(lambda _checked=False, section=key: self._jump_to(section))
            self._section_links[key] = link
            entry.addWidget(link, 1)
            if key in CAREER_SECTIONS:
                count = label("0", "countBadge")
                count.setAlignment(Qt.AlignmentFlag.AlignCenter)
                count.setMinimumWidth(24)
                self._section_counts[key] = count
                entry.addWidget(count)
            if key in OPTIONAL_CAREER_SECTIONS:
                toggle = QPushButton()
                toggle.setObjectName("sectionToggle")
                toggle.setCheckable(True)
                toggle.setMinimumSize(36, 36)
                toggle.clicked.connect(lambda _checked=False, section=key: self._toggle_section(section))
                self.section_toggles[key] = toggle
                entry.addWidget(toggle)
            items.addLayout(entry)
            self._sync_section(key)
        items.addSpacing(10)
        items.addWidget(label("＋ 항목 표시  ·  − 항목 숨김\n숨긴 기록도 프로필에 보관됩니다.", "muted", True))
        items.addStretch()
        self.section_menu_scroll = QScrollArea()
        self.section_menu_scroll.setWidgetResizable(True)
        self.section_menu_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.section_menu_scroll.setAccessibleName("커리어 항목 메뉴")
        self.section_menu_scroll.setMinimumWidth(218)
        self.section_menu_scroll.setMaximumWidth(240)
        self.section_menu_scroll.setMinimumHeight(400)
        self.section_menu_scroll.setWidget(menu)
        layout.addWidget(self.section_menu_scroll)

    def _section(self, key: str, title: str, action: QPushButton | None = None) -> QVBoxLayout:
        card, content = panel()
        content.setContentsMargins(18, 18, 18, 18)
        content.setSpacing(12)
        heading = label(title, "sectionTitle", True)
        if action is None:
            content.addWidget(heading)
        else:
            header = QHBoxLayout()
            header.addWidget(heading, 1)
            header.addWidget(action)
            content.addLayout(header)
        self._cards[key] = card
        self._content.addWidget(card)
        return content

    def _add_legacy_memos(self, profile: dict) -> None:
        card, content = panel()
        toggle = QPushButton("경력·역량 메모 편집")
        toggle.setCheckable(True)
        toggle.setObjectName("subtle")
        content.addWidget(toggle, 0, Qt.AlignmentFlag.AlignLeft)
        memo_panel = QWidget()
        memos = QVBoxLayout(memo_panel)
        memos.setContentsMargins(0, 0, 0, 0)
        self.experience = _text(profile.get("experience", ""), height=70)
        self.skills = _text(profile.get("skills", ""), height=70)
        for title, field in (("경력·경험 메모", self.experience), ("역량·자격 메모", self.skills)):
            field.setAccessibleName(title)
            memos.addWidget(label(title, "muted"))
            memos.addWidget(field)
        content.addWidget(memo_panel)
        memo_panel.hide()
        toggle.toggled.connect(memo_panel.setVisible)
        self._content.addWidget(card)

    def values(self) -> dict:
        career = normalize_career({
            **self._records,
            "desired_role": self.desired_role.text(),
            "introduction": self.introduction.toPlainText(),
            "visible_sections": [key for key in OPTIONAL_CAREER_SECTIONS if key in self._visible_sections],
        })
        return {
            "occupation": self.occupation.text().strip(),
            "experience": self.experience.toPlainText().strip(),
            "skills": self.skills.toPlainText().strip(),
            "career": career,
        }

    def _sync_section(self, section: str) -> None:
        visible = section not in OPTIONAL_CAREER_SECTIONS or section in self._visible_sections
        self._cards[section].setVisible(visible)
        link = self._section_links[section]
        link.setEnabled(visible)
        selected = visible and section == self._active_section
        link.setChecked(selected)
        link.setProperty("selected", selected)
        link.setProperty("available", visible)
        link.style().unpolish(link)
        link.style().polish(link)
        count = self._section_counts.get(section)
        if count is not None:
            count.setText(str(len(self._records[section])))
            count.setAccessibleName(f"{link.text()} 기록 {len(self._records[section])}개")
        if toggle := self.section_toggles.get(section):
            action = "숨기기" if visible else "추가"
            toggle.setText("−" if visible else "＋")
            toggle.setChecked(visible)
            toggle.setProperty("selected", visible)
            toggle.style().unpolish(toggle)
            toggle.style().polish(toggle)
            toggle.setAccessibleName(f"{link.text()} {action}")
            toggle.setToolTip(toggle.accessibleName())
        if visible and section in self._record_lists:
            self._refresh_records(section)

    def _toggle_section(self, section: str) -> None:
        if section in self._visible_sections:
            self._visible_sections.remove(section)
            if section == self._active_section:
                self._active_section = "desired_role"
                self._sync_section("desired_role")
            self._sync_section(section)
        else:
            self._visible_sections.add(section)
            self._sync_section(section)
            self._jump_to(section)

    def _jump_to(self, section: str) -> None:
        card = self._cards[section]
        self._active_section = section
        for key, link in self._section_links.items():
            selected = key == section and link.isEnabled()
            link.setChecked(selected)
            link.setProperty("selected", selected)
            link.style().unpolish(link)
            link.style().polish(link)

        def scroll_to_card():
            if not card.isHidden():
                top = card.mapTo(self._editor, QPoint()).y()
                self.editor_scroll.verticalScrollBar().setValue(top)

        QTimer.singleShot(0, self, scroll_to_card)

    def _refresh_records(self, section: str) -> None:
        listing = self._record_lists[section]
        while listing.count():
            previous = listing.takeAt(0).widget()
            previous.hide()
            previous.deleteLater()
        records = self._records[section]
        count = self._section_counts.get(section)
        if count is not None:
            count.setText(str(len(records)))
            count.setAccessibleName(f"{CAREER_SECTIONS[section][0]} 기록 {len(records)}개")
        if not records:
            listing.addWidget(label("기록을 추가해 주세요.", "muted", True))
            return

        _title, fields = CAREER_SECTIONS[section]
        first = fields[0][0]
        for index, entry in enumerate(records):
            card, content = panel()
            card.setObjectName("careerRecord")
            content.setContentsMargins(14, 14, 14, 14)
            summary = QVBoxLayout()
            summary.setSpacing(4)
            summary.addWidget(label(entry[first], "recordTitle", True))
            details = [f"{title}  {entry[key]}" for key, title in fields[1:]
                       if entry.get(key) and key not in {"details", "evidence", "url"}]
            if details:
                summary.addWidget(label("  ·  ".join(details), "muted", True))
            actions = QHBoxLayout()
            actions.addLayout(summary, 1)
            for title, callback in (("수정", self._open_entry), ("삭제", self._delete_record)):
                action = QPushButton(title)
                action.setObjectName("danger" if title == "삭제" else "subtle")
                action.setMinimumHeight(34)
                action.setAccessibleName(f"{entry[first]} {title}")
                action.clicked.connect(lambda _checked=False, cb=callback, i=index: cb(section, i))
                actions.addWidget(action, 0, Qt.AlignmentFlag.AlignTop)
            content.addLayout(actions)
            listing.addWidget(card)

    def _open_entry(self, section: str, row: int | None = None) -> None:
        dialog = _CareerEntryDialog(section, self._records[section], row, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._records[section] = dialog.records
            self._refresh_records(section)
        dialog.deleteLater()

    def _delete_record(self, section: str, row: int) -> None:
        answer = QMessageBox.question(
            self,
            "커리어 기록 삭제",
            "선택한 기록을 삭제할까요? 프로필을 저장하면 삭제가 반영됩니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            del self._records[section][row]
            self._refresh_records(section)
