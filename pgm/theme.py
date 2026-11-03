"""Application appearance kept separate from product logic."""

from PySide6.QtGui import QColor, QPalette


def apply_theme(app, light=False):
    c = ({"bg": "#f3f4f8", "sidebar": "#ffffff", "panel": "#ffffff", "input": "#f4f5fa", "line": "#dfe2ec", "text": "#202432", "muted": "#687386", "accent": "#7454ce", "selected": "#eee8fb"}
         if light else {"bg": "#11141c", "sidebar": "#171a24", "panel": "#1d2230", "input": "#171c28", "line": "#303747", "text": "#edf0f7", "muted": "#9ca7bb", "accent": "#b69af7", "selected": "#302744"})
    palette = QPalette()
    for role, color in [(QPalette.ColorRole.Window,c["bg"]),(QPalette.ColorRole.WindowText,c["text"]),(QPalette.ColorRole.Base,c["input"]),(QPalette.ColorRole.AlternateBase,c["panel"]),(QPalette.ColorRole.Text,c["text"]),(QPalette.ColorRole.Button,c["panel"]),(QPalette.ColorRole.ButtonText,c["text"]),(QPalette.ColorRole.Highlight,c["accent"]),(QPalette.ColorRole.HighlightedText,c["bg"])]:
        palette.setColor(role,QColor(color))
    app.setPalette(palette)
    css = """
    QWidget { color: TEXT; font-size: 13px; }
    QWidget#appRoot, QWidget#page { background: BG; }
    QWidget#sidebar { background: SIDE; border-right: 1px solid LINE; }
    QWidget#topbar { background: BG; border-bottom: 1px solid LINE; }
    QLabel { background: transparent; }
    QLabel#muted { color: MUTED; }
    QLabel#eyebrow { color: ACCENT; font-size: 10px; font-weight: 650; letter-spacing: 2px; }
    QLabel#pageTitle { font-size: 29px; font-weight: 750; }
    QLabel#sectionTitle { font-size: 17px; font-weight: 650; }
    QLabel#statValue { font-size: 29px; font-weight: 700; }
    QLabel#brand { font-size: 22px; font-weight: 750; }
    QFrame#card { background: PANEL; border: 1px solid LINE; border-radius: 15px; }
    QFrame#hero { background: PANEL; border: 1px solid #514461; border-radius: 18px; }
    QPushButton { background: PANEL; border: 1px solid LINE; border-radius: 8px; padding: 9px 15px; font-weight: 550; }
    QPushButton:hover { border-color: ACCENT; background: SELECTED; }
    QPushButton:focus { border: 1px solid ACCENT; }
    QPushButton:disabled { color: MUTED; }
    QPushButton#primary, QPushButton[primary="true"] { background: #b99cf7; color: #1b1429; border: 1px solid #b99cf7; font-weight: 700; }
    QPushButton#primary:hover { background: #ccb5ff; }
    QPushButton#nav { text-align: left; border: none; background: transparent; padding: 12px 15px; color: MUTED; font-size: 14px; }
    QPushButton#nav:checked { color: TEXT; background: SELECTED; border-left: 3px solid ACCENT; }
    QPushButton#nav:hover { background: SELECTED; color: TEXT; }
    QPushButton#ghost { border: none; background: transparent; color: ACCENT; padding: 4px; }
    QPushButton#danger { color: #f295a1; }
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox { background: INPUT; color: TEXT; border: 1px solid LINE; border-radius: 7px; padding: 8px; min-height: 20px; selection-background-color: ACCENT; }
    QLineEdit:focus, QTextEdit:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: ACCENT; }
    QComboBox QAbstractItemView { background: PANEL; color: TEXT; selection-background-color: SELECTED; padding: 4px; }
    QCheckBox { spacing: 10px; background: transparent; }
    QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #69758d; border-radius: 5px; background: INPUT; }
    QCheckBox::indicator:checked { background: #b99cf7; border: 1px solid #b99cf7; image: none; }
    QProgressBar { background: INPUT; border: none; border-radius: 3px; height: 6px; max-height: 6px; }
    QProgressBar::chunk { background: ACCENT; border-radius: 3px; }
    QScrollArea { border: none; background: transparent; }
    QScrollArea > QWidget > QWidget { background: BG; }
    QScrollBar:vertical { background: BG; width: 8px; margin: 0; }
    QScrollBar::handle:vertical { background: LINE; border-radius: 4px; min-height: 35px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
    QTableWidget { background: PANEL; alternate-background-color: INPUT; gridline-color: LINE; border: 1px solid LINE; border-radius: 8px; }
    QHeaderView::section { background: INPUT; color: MUTED; border: none; border-bottom: 1px solid LINE; padding: 9px; }
    QStatusBar { background: BG; color: MUTED; font-size: 11px; }
    QDialog { background: BG; }
    QTabWidget::pane { border: 1px solid LINE; border-radius: 6px; }
    QTabBar::tab { background: INPUT; color: MUTED; border: 1px solid LINE; padding: 9px 14px; }
    QTabBar::tab:selected { color: TEXT; background: SELECTED; border-bottom: 2px solid ACCENT; }
    QToolTip { background: PANEL; color: TEXT; border: 1px solid LINE; padding: 6px; }
    """
    for key,val in {"SELECTED":c["selected"],"ACCENT":c["accent"],"MUTED":c["muted"],"PANEL":c["panel"],"INPUT":c["input"],"TEXT":c["text"],"SIDE":c["sidebar"],"LINE":c["line"],"BG":c["bg"]}.items():
        css = css.replace(key,val)
    app.setStyleSheet(css)
