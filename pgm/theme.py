"""Shared colors and native Qt appearance for the growth workspace."""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


_LIGHT = {
    "bg": "#eef3fb", "sidebar": "#fbfcff", "panel": "#ffffff", "input": "#f7faff",
    "line": "#dbe5f0", "text": "#20314d", "muted": "#5c6f88", "accent": "#176c86",
    "accent_hover": "#125b73", "selected": "#e7f1fb", "primary": "#246fbb",
    "primary_hover": "#1b5fa5", "primary_text": "#ffffff", "soft": "#edf4fc",
    "hero_start": "#e3efff", "hero_end": "#f1eafb", "danger": "#aa3854",
    "warning_bg": "#fff7e9", "warning_line": "#e5cf9e",
    "danger_bg": "#fff1f4", "danger_line": "#e8bdc9",
    "chart_grid": "#dfe7f1", "chart_planned": "#6f8eaf", "chart_completed": "#277db4",
}
_DARK = {
    "bg": "#111c2a", "sidebar": "#162233", "panel": "#1b2a3d", "input": "#162335",
    "line": "#34475f", "text": "#edf4ff", "muted": "#aabdd4", "accent": "#82d3df",
    "accent_hover": "#a3e6ef", "selected": "#263e58", "primary": "#71b5ed",
    "primary_hover": "#91c8f4", "primary_text": "#102239", "soft": "#22364d",
    "hero_start": "#203d59", "hero_end": "#34304f", "danger": "#f0a7b7",
    "warning_bg": "#342e25", "warning_line": "#706047",
    "danger_bg": "#3d2936", "danger_line": "#7d4c62",
    "chart_grid": "#34475f", "chart_planned": "#7998bc", "chart_completed": "#79c7e8",
}


def theme_colors(light=None):
    """Return the active colors for stylesheets and custom chart painters."""
    if light is None:
        app = QApplication.instance()
        light = bool(app.property("lightTheme")) if app is not None else False
    return dict(_LIGHT if light else _DARK)


def apply_theme(app, light=False):
    colors = theme_colors(light)
    app.setProperty("lightTheme", bool(light))
    app.setProperty("themeColors", colors)
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: "bg",
        QPalette.ColorRole.WindowText: "text",
        QPalette.ColorRole.Base: "input",
        QPalette.ColorRole.AlternateBase: "panel",
        QPalette.ColorRole.Text: "text",
        QPalette.ColorRole.Button: "panel",
        QPalette.ColorRole.ButtonText: "text",
        QPalette.ColorRole.Highlight: "primary",
        QPalette.ColorRole.HighlightedText: "primary_text",
        QPalette.ColorRole.PlaceholderText: "muted",
        QPalette.ColorRole.Mid: "chart_grid",
        QPalette.ColorRole.Midlight: "chart_planned",
        QPalette.ColorRole.Link: "accent",
        QPalette.ColorRole.ToolTipBase: "panel",
        QPalette.ColorRole.ToolTipText: "text",
    }
    for role, key in roles.items():
        palette.setColor(role, QColor(colors[key]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors["muted"]))
    app.setPalette(palette)
    css = """
    QWidget { color: @text@; font-size: 13px; }
    QWidget#appRoot, QWidget#page {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 @bg@, stop:1 @hero_end@);
    }
    QWidget#sidebar { background: @sidebar@; border-right: 1px solid @line@; }
    QWidget#topbar { background: @sidebar@; border-bottom: 1px solid @line@; }
    QLabel { background: transparent; }
    QLabel#muted, QLabel#dialogSubtitle { color: @muted@; }
    QLabel#eyebrow { color: @accent@; font-size: 11px; font-weight: 650; letter-spacing: 1px; }
    QLabel#pageTitle { font-size: 26px; font-weight: 750; }
    QLabel#dialogTitle { font-size: 23px; font-weight: 700; }
    QLabel#sectionTitle { font-size: 17px; font-weight: 650; }
    QLabel#summaryTitle { font-size: 20px; font-weight: 700; }
    QLabel#recordTitle { font-size: 15px; font-weight: 650; }
    QLabel#fieldLabel { color: @muted@; font-size: 13px; font-weight: 550; }
    QLabel#statValue, QLabel#metricValue { font-size: 29px; font-weight: 750; }
    QLabel#brand { font-size: 23px; font-weight: 750; letter-spacing: 1px; }
    QLabel#brandMark { background: @primary@; color: @primary_text@; border-radius: 11px; font-size: 23px; font-weight: 750; padding: 0; }
    QLabel#demoNotice { color: @text@; background: @warning_bg@; border: 1px solid @warning_line@; border-radius: 10px; padding: 9px 12px; font-size: 12px; }
    QLabel#sectionIndex { color: @accent@; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
    QLabel#countBadge {
        color: @accent@; background: @selected@; border-radius: 9px;
        padding: 3px 7px; font-size: 11px; font-weight: 650;
    }
    QFrame#card, QFrame#goalCard, QFrame#timelineCard, QFrame#settingsSection,
    QFrame#careerMenu, QFrame#careerRecord {
        background: @panel@; border: 1px solid @line@; border-radius: 18px;
    }
    QFrame#careerRecord { background: @input@; border-radius: 13px; }
    QFrame#taskCard { background: @panel@; border: 1px solid @line@; border-radius: 14px; }
    QFrame#statCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 @panel@, stop:1 @soft@);
        border: 1px solid @line@; border-radius: 18px;
    }
    QFrame#hero, QFrame#profileBanner {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 @hero_start@, stop:1 @hero_end@);
        border: 1px solid @line@; border-radius: 20px;
    }
    QFrame[tone="warning"], QFrame#card[tone="warning"], QFrame#timelineCard[tone="warning"] { background: @warning_bg@; border: 1px solid @warning_line@; }
    QFrame[tone="danger"], QFrame#card[tone="danger"], QFrame#timelineCard[tone="danger"] { background: @danger_bg@; border: 1px solid @danger_line@; }
    QPushButton, QToolButton {
        background: @panel@; border: 1px solid @line@; border-radius: 9px;
        padding: 8px 13px; font-weight: 550;
    }
    QPushButton:hover, QToolButton:hover { border-color: @accent@; background: @selected@; }
    QPushButton:focus, QToolButton:focus { border: 1px solid @accent@; }
    QPushButton:disabled, QToolButton:disabled { color: @muted@; background: @input@; }
    QPushButton#primary, QPushButton[primary="true"] {
        background: @primary@; color: @primary_text@; border: 1px solid @primary@; font-weight: 650;
    }
    QPushButton#primary:hover, QPushButton[primary="true"]:hover {
        background: @primary_hover@; border-color: @primary_hover@;
    }
    QPushButton#primary:disabled, QPushButton[primary="true"]:disabled {
        background: @soft@; color: @muted@; border-color: @line@;
    }
    QPushButton#nav {
        text-align: left; border: none; background: transparent; padding: 10px 12px;
        border-radius: 10px; color: @muted@; font-size: 13px;
    }
    QPushButton#categoryLink { text-align: left; color: @muted@; background: transparent; border: none; padding: 4px 8px; font-size: 12px; }
    QPushButton#categoryLink:hover { color: @accent@; background: @soft@; }
    QPushButton#nav:checked { color: @accent@; background: @selected@; font-weight: 700; }
    QPushButton#nav:hover { background: @soft@; color: @text@; }
    QPushButton#ghost, QPushButton#subtle {
        border: 1px solid transparent; background: transparent; color: @accent@; padding: 5px 7px;
    }
    QPushButton#ghost:hover, QPushButton#subtle:hover { background: @selected@; }
    QPushButton#softButton { color: @accent@; background: @soft@; border-color: @line@; }
    QPushButton#softButton:hover { background: @selected@; border-color: @accent@; }
    QPushButton#danger { color: @danger@; background: transparent; }
    QPushButton#danger:hover { background: @danger_bg@; border-color: @danger_line@; }
    QPushButton#careerSection {
        text-align: left; color: @muted@; background: transparent; border: none;
        border-radius: 8px; padding: 7px 9px;
    }
    QPushButton#careerSection:hover { background: @soft@; color: @text@; }
    QPushButton#careerSection[available="false"] { color: @muted@; }
    QPushButton#careerSection[selected="true"] { color: @accent@; background: @selected@; font-weight: 650; }
    QPushButton#sectionToggle {
        color: @accent@; background: @soft@; border: none; border-radius: 8px; padding: 5px 7px;
    }
    QPushButton#sectionToggle[selected="true"] { background: @selected@; }
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox {
        background: @input@; color: @text@; border: 1px solid @line@; border-radius: 9px;
        padding: 8px; min-height: 20px; selection-background-color: @primary@; selection-color: @primary_text@;
    }
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QDoubleSpinBox:focus,
    QSpinBox:focus, QDateEdit:focus, QComboBox:focus { border-color: @accent@; }
    QLineEdit:disabled, QTextEdit:disabled, QDoubleSpinBox:disabled { color: @muted@; }
    QComboBox { padding-right: 26px; }
    QComboBox::drop-down { width: 22px; border: none; }
    QComboBox QAbstractItemView {
        background: @panel@; color: @text@; selection-background-color: @selected@;
        selection-color: @text@; padding: 4px; border: 1px solid @line@;
    }
    QCheckBox { spacing: 8px; background: transparent; }
    QCheckBox::indicator {
        width: 17px; height: 17px; border: 1px solid @muted@; border-radius: 5px; background: @input@;
    }
    QCheckBox::indicator:checked { background: @primary@; border-color: @primary@; }
    QCheckBox::indicator:disabled { border-color: @line@; background: @input@; }
    QProgressBar { background: @soft@; border: none; border-radius: 4px; height: 7px; max-height: 7px; }
    QProgressBar::chunk { background: @primary@; border-radius: 4px; }
    QScrollArea { border: none; background: transparent; }
    QScrollArea > QWidget > QWidget { background: @bg@; }
    QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
    QScrollBar::handle:vertical { background: @line@; border-radius: 4px; min-height: 35px; }
    QScrollBar::handle:vertical:hover { background: @muted@; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
    QTableWidget {
        background: @panel@; alternate-background-color: @input@; gridline-color: @line@;
        border: 1px solid @line@; border-radius: 10px;
        selection-background-color: @selected@; selection-color: @text@;
    }
    QHeaderView::section {
        background: @input@; color: @muted@; border: none; border-bottom: 1px solid @line@;
        padding: 9px; font-size: 12px; font-weight: 600;
    }
    QStatusBar { background: @sidebar@; color: @muted@; font-size: 11px; }
    QDialog { background: @bg@; }
    QWidget#dialogHeader { background: @panel@; border-bottom: 1px solid @line@; }
    QWidget#reportBody { background: @bg@; }
    QWidget#formBody { background: @bg@; }
    QWidget#dialogFooter { background: @panel@; border-top: 1px solid @line@; }
    QTabWidget::pane { background: @panel@; border: 1px solid @line@; border-radius: 14px; }
    QTabBar::tab {
        background: @soft@; color: @muted@; border: 1px solid @line@;
        border-radius: 8px; padding: 8px 13px; margin-right: 4px;
    }
    QTabBar::tab:hover { color: @text@; background: @selected@; }
    QTabBar::tab:selected {
        color: @accent@; background: @panel@; border-bottom: 2px solid @primary@; font-weight: 650;
    }
    QToolTip { background: @panel@; color: @text@; border: 1px solid @line@; padding: 7px; border-radius: 5px; }
    """
    for key, value in colors.items():
        css = css.replace(f"@{key}@", value)
    app.setStyleSheet(css)
