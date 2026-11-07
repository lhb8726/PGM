"""Native desktop prototype for the personal growth workspace."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QDate, QSize, QSettings, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QDoubleSpinBox,
    QFileDialog, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSystemTrayIcon, QTabBar, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget,
)

from . import __version__
from . import engine
from .analysis import analyze_goal
from .analysis_view import GoalAnalysisDialog, wrapped_table
from .career_profile import CareerProfile
from .constants import CATEGORIES, HORIZONS, KINDS, NAVIGATION, PRIORITIES
from .dialogs import GoalDialog, HabitDialog, MetricDialog, OptionalNumber, ReviewDialog, TaskDialog, _fit_to_screen, goal_selector
from .profile_schema import FINANCE_AMOUNTS
from .storage import Store
from .theme import apply_theme, theme_colors
from .visuals import CategoryChart, TrendChart, ui_icon
from .widgets import CheckBoxLabel, ResponsiveColumns, Ring, label, panel, pill, refresh_accents, stat_card


def button(text, callback, primary=False, ghost=False):
    w = QPushButton(text)
    if primary:
        w.setObjectName("primary")
    elif ghost:
        w.setObjectName("ghost")
    w.setCursor(Qt.CursorShape.PointingHandCursor)
    w.clicked.connect(lambda _checked=False: callback())
    return w


def row(*items):
    layout = QHBoxLayout()
    layout.setSpacing(12)
    for item in items:
        if item is None:
            layout.addStretch()
        elif isinstance(item, QWidget):
            layout.addWidget(item)
        else:
            layout.addLayout(item)
    return layout


def progress_bar(value, color="#b69af7"):
    w=QProgressBar();w.setRange(0,100);w.setValue(round(value*100));w.setTextVisible(False)
    w.setStyleSheet(f"QProgressBar::chunk {{ background:{color}; border-radius:3px; }}")
    return w


def date_text(value):
    if not value:
        return "일정 미배정"
    try:
        d=date.fromisoformat(value);delta=(d-date.today()).days
        tag="오늘" if delta==0 else (f"D−{delta}" if delta>0 else f"{abs(delta)}일 지연")
        return f"{d:%m.%d}  ·  {tag}"
    except ValueError:
        return str(value)


def number(value):
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"


class ProfileTabs(QTabWidget):
    def sizeHint(self):
        hint = super().sizeHint()
        page = self.currentWidget()
        if page is not None:
            # Inactive pages are ignored for the minimum size by select_profile_tab.
            chrome = self.minimumSizeHint().height() - page.minimumSizeHint().height()
            hint.setHeight(chrome + page.sizeHint().height())
        return hint

    def heightForWidth(self, width):
        page = self.currentWidget()
        preferred = self.sizeHint().height()
        if page is not None and (height := page.heightForWidth(width)) >= 0:
            return preferred - page.sizeHint().height() + height
        return preferred


class MainWindow(QMainWindow):
    def __init__(self, store:Store, demo=False):
        super().__init__()
        self.store=store
        self.preferences=QSettings(str(store.data_dir/"preferences.ini"),QSettings.Format.IniFormat)
        self.demo=store.is_demo() if hasattr(store,"is_demo") else demo
        if demo:
            self.preferences.setValue("demo",True)
        self.page_key="dashboard"
        self.category="all"
        self.goal_search=""
        self.execution_date=date.today()
        self.roadmap_scale="주간"
        self.profile_tab = 0
        self.notified_day=None
        self.setWindowTitle(f"PGM · Personal Growth Workspace {__version__}")
        self.setWindowIcon(QIcon(str(Path(__file__).parent/"assets"/"icon.svg")))
        self.setMinimumSize(960,600)
        self.resize(1440,960)
        apply_theme(QApplication.instance(),self.preferences.value("light",True,type=bool))
        root=QWidget();root.setObjectName("appRoot");self.setCentralWidget(root)
        shell=QHBoxLayout(root);shell.setContentsMargins(0,0,0,0);shell.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 24, 16, 16)
        side.setSpacing(5)
        mark = label("P", "brandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(36, 36)
        brand_copy = QVBoxLayout()
        brand_copy.setSpacing(1)
        brand_copy.addWidget(label("PGM", "brand"))
        brand_copy.addWidget(label("PERSONAL GROWTH", "eyebrow"))
        side.addLayout(row(mark, brand_copy, None))
        side.addSpacing(24)
        side.addWidget(label("WORKSPACE", "eyebrow"))
        self.nav = {}
        for key, _icon, title in NAVIGATION:
            item = button(title, lambda k=key: self.navigate(k))
            item.setObjectName("nav")
            item.setCheckable(True)
            item.setIcon(ui_icon(key, theme_colors()["muted"]))
            item.setIconSize(QSize(19, 19))
            side.addWidget(item)
            self.nav[key] = item
        side.addSpacing(22)
        side.addWidget(label("성장 분야", "eyebrow"))
        for key, category in CATEGORIES.items():
            item = button(category["name"], lambda k=key: self.select_category(k), ghost=True)
            item.setObjectName("categoryLink")
            item.setAccessibleName(category["name"] + " 목표 보기")
            side.addWidget(item)
        side.addStretch()
        box, footer = panel()
        footer.setContentsMargins(12, 12, 12, 12)
        footer.addWidget(label("나만의 성장 기록", "summaryTitle"))
        footer.addWidget(label("이 PC에 보관되는 기록", "muted", True))
        footer.addWidget(label(f"PGM  {__version__}", "muted"))
        side.addWidget(box)
        sidebar_scroll = QScrollArea()
        sidebar_scroll.setFixedWidth(218)
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sidebar_scroll.setWidget(sidebar)
        shell.addWidget(sidebar_scroll)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        top = QWidget()
        top.setObjectName("topbar")
        top.setFixedHeight(70)
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(28, 0, 28, 0)
        self.breadcrumb = label("나의 성장 공간  /  대시보드", "muted")
        top_layout.addWidget(self.breadcrumb)
        top_layout.addStretch()
        self.category_combo = QComboBox()
        self.category_combo.addItem("모든 분야", "all")
        for key, category in CATEGORIES.items():
            self.category_combo.addItem(category["name"], key)
        self.category_combo.setMinimumWidth(150)
        self.category_combo.currentIndexChanged.connect(self.change_category)
        top_layout.addWidget(self.category_combo)
        top_layout.addWidget(button("＋ 목표 추가", self.edit_goal, True))
        right_layout.addWidget(top)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);right_layout.addWidget(self.scroll,1)
        shell.addWidget(right,1)
        self.statusBar().showMessage("로컬 저장 · 외부 AI 미연결"+ (" · 가상 예시 데이터" if self.demo else ""))
        self.tray=QSystemTrayIcon(self.windowIcon(),self)
        self.notification_timer=QTimer(self);self.notification_timer.setInterval(60000)
        self.notification_timer.timeout.connect(self.check_notifications);self.notification_timer.start()
        self.refresh()

    def snapshot(self):
        self.profile=self.store.profile();self.goals=self.store.goals();self.tasks=self.store.tasks()
        self.metrics=self.store.metrics();self.habits=self.store.habits()

    def filtered_goals(self):
        return [g for g in self.goals if (self.category=="all" or g["category"]==self.category)]

    def navigate(self,key):
        self.page_key=key
        self.refresh()

    def change_category(self):
        self.category=self.category_combo.currentData();self.refresh()

    def refresh(self):
        self.snapshot()
        title=next(x[2] for x in NAVIGATION if x[0]==self.page_key)
        self.breadcrumb.setText(f"나의 성장 공간  /  {title}")
        for key, item in self.nav.items():
            item.setChecked(key == self.page_key)
            color = theme_colors()["accent"] if key == self.page_key else theme_colors()["muted"]
            item.setIcon(ui_icon(key, color))
        page=QWidget();page.setObjectName("page")
        layout=QVBoxLayout(page);layout.setContentsMargins(32,27,32,30);layout.setSpacing(22)
        if self.demo:
            hint=label("DEMO · 가상 예시로 둘러보는 중입니다. 이름·금액·성과는 모두 예시입니다.", "demoNotice", True)
            layout.addWidget(hint)
        getattr(self,f"page_{self.page_key}")(layout)
        layout.addStretch()
        old=self.scroll.takeWidget()
        self.scroll.setWidget(page)
        if old is not None:old.deleteLater()
        self.statusBar().showMessage(f"로컬 저장 · 목표 {len(self.goals)}개 · 기록은 내 PC에 보관됩니다"+(" · 가상 예시" if self.demo else ""))

    def select_category(self, category):
        self.category_combo.setCurrentIndex(self.category_combo.findData(category))
        if self.page_key in {"profile", "settings"}:
            self.navigate("goals")

    def heading(self, layout, title, subtitle, eyebrow=None, action=None):
        copy = QVBoxLayout()
        copy.setSpacing(7)
        if eyebrow:
            copy.addWidget(label(eyebrow, "eyebrow"))
        copy.addWidget(label(title, "pageTitle", True))
        copy.addWidget(label(subtitle, "muted", True))
        header = QHBoxLayout()
        header.addLayout(copy, 1)
        if action is not None:
            action.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            header.addWidget(action, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

    def stat_row(self, layout, cards):
        first, second = QHBoxLayout(), QHBoxLayout()
        midpoint = (len(cards) + 1) // 2
        for group, entries in ((first, cards[:midpoint]), (second, cards[midpoint:])):
            group.setSpacing(14)
            for card in entries:
                group.addWidget(card, 1)
        layout.addWidget(ResponsiveColumns(first, second, spacing=14, stretch=(1, 1)))

    def section(self,layout,title,action=None):
        r=row(label(title,"sectionTitle"),None)
        if action:r.addWidget(action)
        layout.addLayout(r)

    def empty(self,layout,title,body,action=None):
        w,l=panel();l.setContentsMargins(24,25,24,25)
        l.addWidget(label(title,"sectionTitle"));l.addWidget(label(body,"muted",True))
        if action:l.addWidget(action,0,Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(w)

    def guard(self,callback):
        try:return callback()
        except (ValueError,OSError,RuntimeError,KeyError,sqlite3.Error) as exc:
            QMessageBox.warning(self,"작업을 완료하지 못했습니다",str(exc))
            return None

    def goal_card(self, goal):
        category = CATEGORIES[goal["category"]]
        state = engine.progress_state(goal, self.tasks)
        progress = state["value"]
        card, content = panel()
        card.setObjectName("goalCard")
        card.setMinimumWidth(286)
        content.addLayout(row(
            pill(category["name"], category["color"]),
            None,
            label("달성 완료" if goal["status"] == "completed" else HORIZONS[goal["horizon"]], "muted"),
        ))
        content.addWidget(label(goal["title"], "sectionTitle", True))
        content.addWidget(label(goal.get("criteria") or "완료 기준을 추가해 주세요.", "muted", True))
        if goal["kind"] == "numeric":
            amount = f"{number(goal['current'])} / {number(goal['target'])} {goal['unit']}"
            if goal["category"] == "finance" and (goal.get("planning") or {}).get("target_basis") == "after_tax_cash":
                amount = "현재 평가액 / 세후 목표  ·  " + amount
            content.addWidget(label(amount, "summaryTitle", True))
        value = "정보 부족" if progress is None else f"{progress:.0%}"
        progress_text = label(value, "metricValue")
        progress_text.setToolTip(state["detail"])
        content.addLayout(row(label(state["label"], "muted", True), None, progress_text))
        content.addWidget(progress_bar(progress or 0, category["color"]))
        pending = [task for task in self.tasks if task["goal_id"] == goal["id"] and not task["done"]]
        next_task = min(pending, key=lambda task: (task.get("scheduled_date") or "9999", task.get("position", 0)), default=None)
        content.addWidget(label("다음 실행  ·  " + (next_task["title"] if next_task else "목표의 다음 단계를 정해 보세요."), "muted", True))
        content.addLayout(row(pill(PRIORITIES[goal["priority"]]), None, label(date_text(goal["due_date"]), "muted")))
        content.addLayout(row(
            button("상세 분석", lambda: self.show_goal_analysis(goal)),
            button("수정", lambda: self.edit_goal(goal), ghost=True),
            None,
            button("로드맵 →", lambda: self.open_roadmap(goal), ghost=True),
        ))
        return card

    def goal_grid(self,layout,goals):
        grid=QGridLayout();grid.setSpacing(15)
        for i,g in enumerate(goals):grid.addWidget(self.goal_card(g),i//2,i%2)
        grid.setColumnStretch(0,1);grid.setColumnStretch(1,1);layout.addLayout(grid)

    def task_row(self,t):
        g=next((g for g in self.goals if g["id"]==t["goal_id"]),None)
        w,l=panel();w.setObjectName("taskCard");l.setContentsMargins(16,14,16,14)
        h=QHBoxLayout();check=QCheckBox();check.setChecked(t["done"])
        check.setAccessibleName(f"{t['title']} 완료")
        check.toggled.connect(lambda done,i=t["id"]:self.toggle_task(i,done))
        h.addWidget(check)
        text=QVBoxLayout();text.setSpacing(5)
        title=label(t["title"],wrap=True)
        if t["done"]:title.setObjectName("muted")
        text.addWidget(title)
        detail=f"{g['title'] if g else '연결 목표 없음'}  ·  {date_text(t.get('scheduled_date',''))}"
        if t["done"]:detail+=f" · 실제 {t['actual_minutes']}분" if t["actual_minutes"] else " · 실제 시간 미기록"
        text.addWidget(label(detail,"muted",True))
        if t.get("done_when"):
            criterion=label("완료 기준  ·  "+t["done_when"],"muted",True);criterion.setToolTip(t.get("rationale", ""));text.addWidget(criterion)
        h.addLayout(text,1);h.addWidget(pill(f"{t['minutes']}분",CATEGORIES[g["category"]]["color"] if g else "#b69af7"))
        h.addWidget(button("수정",lambda:self.edit_task(t),ghost=True));l.addLayout(h)
        return w

    def page_dashboard(self, layout):
        name = self.profile.get("name") or "나"
        self.heading(layout, f"{name}의 성장 대시보드", "오늘의 실행과 목표의 흐름을 한눈에 확인하세요.", date.today().strftime("%Y.%m.%d  /  OVERVIEW"))
        goals = self.filtered_goals()
        goal_ids = {goal["id"] for goal in goals}
        tasks = [task for task in self.tasks if task["goal_id"] in goal_ids]
        active = [goal for goal in goals if goal["status"] != "completed"]
        today = [task for task in tasks if task.get("scheduled_date") == date.today().isoformat()]
        done = sum(task["done"] for task in today)
        next_week = [task for task in self.tasks if task.get("scheduled_date") and date.today() <= date.fromisoformat(task["scheduled_date"]) <= date.today() + timedelta(days=6)]
        minutes = sum(task["minutes"] for task in next_week)
        self.stat_row(layout, [
            stat_card("진행 중인 목표", str(len(active)), "선택한 분야의 목표", "#4f7ff3", "↗"),
            stat_card("오늘의 실행", f"{done} / {len(today)}", "오늘 예정된 과제 중 완료", "#159f90", "✓"),
            stat_card("다음 7일 계획", f"{minutes/60:.1f}h", f"전체 분야 · 주당 가용 {self.profile['weekly_hours']:g}h", "#8b6ae8", "◷"),
            stat_card("달성한 목표", str(sum(goal["status"] == "completed" for goal in goals)), "직접 달성을 확인한 기록", "#d38b39", "✦"),
        ])
        chart, chart_content = panel()
        chart_content.addLayout(row(label("최근 7일의 실행 흐름", "sectionTitle"), None,
                                    button("성장 분석 ↗", lambda: self.navigate("analysis"), ghost=True)))
        chart_content.addWidget(label("예정일별 과제 수와 그중 완료한 과제 수", "muted", True))
        chart_content.addWidget(TrendChart(engine.activity_series(tasks)))
        pace, pace_content = panel(True)
        pace_content.addWidget(label("오늘의 페이스", "sectionTitle"))
        if today:
            pace_content.addWidget(Ring(done / len(today), "오늘의 완료율", "#159f90"), 0, Qt.AlignmentFlag.AlignHCenter)
            pace_content.addWidget(label(f"{len(today) - done}개 과제가 남아 있어요.", "summaryTitle", True))
        else:
            pace_content.addWidget(label("새로운 실행을 계획해 보세요.", "metricValue", True))
            pace_content.addWidget(label("오늘 예정된 과제가 없습니다.", "muted", True))
        overdue = [task for task in tasks if not task["done"] and task.get("scheduled_date") and task["scheduled_date"] < date.today().isoformat()]
        pace_content.addWidget(label(f"지연 과제 {len(overdue)}개  ·  진행 중 목표 {len(active)}개", "muted", True))
        pace_content.addStretch()
        pace_content.addWidget(button("오늘의 실행 보기 →", lambda: self.navigate("today"), True))
        left, right = QVBoxLayout(), QVBoxLayout()
        left.addWidget(chart)
        right.addWidget(pace)
        layout.addWidget(ResponsiveColumns(left, right, stretch=(3, 1)))
        self.section(layout, "집중하고 있는 목표", button("모든 목표 보기 →", lambda: self.navigate("goals"), ghost=True))
        if goals:
            self.goal_grid(layout, sorted(goals, key=lambda goal: (goal["status"] == "completed", -goal["priority"], goal["due_date"]))[:4])
        else:
            self.empty(layout, "첫 목표를 만들어 보세요", "현재 상태와 원하는 결과를 입력하면 성장 경로를 설계할 수 있습니다.", button("목표 만들기", self.edit_goal, True))
        self.section(layout, "오늘의 실행", button("일정 전체 보기 →", lambda: self.navigate("today"), ghost=True))
        if today:
            for task in sorted(today, key=lambda task: task["done"])[:3]:
                layout.addWidget(self.task_row(task))
        else:
            self.empty(layout, "오늘을 위한 작은 한 걸음", "계획한 목표에 실행 과제를 추가해 보세요.", button("실행 과제 추가", self.edit_task))
        if not self.goals:
            layout.addWidget(button("가상 예시로 먼저 살펴보기", self.load_demo, ghost=True), 0, Qt.AlignmentFlag.AlignLeft)

    def page_profile(self,layout):
        self.heading(layout, "나의 프로필", "현재의 역량과 자원을 기록하고 성장의 출발점을 정하세요.", "PROFILE", button("프로필 저장", self.save_profile, True))
        self.profile_fields = {}
        tabs = self.profile_tabs = ProfileTabs()
        tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        tabs.addTab(self.profile_common_tab(), "공통")
        tabs.addTab(self.profile_finance_tab(), "금융·자산")
        self.career_profile = CareerProfile(self.profile)
        tabs.addTab(self.career_profile, "커리어")
        tabs.setCurrentIndex(self.profile_tab)
        self.select_profile_tab(tabs.currentIndex())
        tabs.currentChanged.connect(self.select_profile_tab)
        layout.addWidget(tabs)
        self.section(layout,"분야별 현재 상태",button("＋ 근거·측정값 기록",self.add_metric,ghost=True))
        grid=QGridLayout();grid.setSpacing(15)
        for i,d in enumerate(engine.diagnose(self.profile,self.metrics,self.goals)):
            c=CATEGORIES[d["category"]];card,cl=panel();cl.addLayout(row(pill(c["name"],c["color"]),None,label(d["level"],"muted")))
            cl.addWidget(label(d["summary"],wrap=True));cl.addWidget(label(str(d.get("evidence","")),"muted",True))
            cl.addWidget(label("다음 확인  ·  "+d["next_step"],"muted",True))
            cl.addWidget(button("현재 상태 기록",lambda k=d["category"]:self.add_metric(k),ghost=True),0,Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(card,i//2,i%2)
        layout.addLayout(grid)
        if self.metrics:
            self.section(layout,"최근 진단 근거")
            for m in sorted(self.metrics,key=lambda m:m["recorded_date"],reverse=True)[:8]:
                card,cl=panel();cl.addWidget(label(f"{CATEGORIES[m['category']]['name']} · {m['label']}  {number(m['value'])}{m['unit']}",wrap=True));cl.addWidget(label(f"{m['recorded_date']}  ·  { {'self':'자기평가','measured':'측정 기록','document':'문서·결과물'}[m['evidence_kind']] }  ·  {m['source']}","muted",True));layout.addWidget(card)

    def select_profile_tab(self, index):
        self.profile_tab = index
        for i in range(self.profile_tabs.count()):
            page = self.profile_tabs.widget(i)
            if i == index:
                page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            else:
                page.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.profile_tabs.updateGeometry()

    def profile_card(self, title, fields, hint=""):
        card, layout = panel()
        layout.addWidget(label(title, "sectionTitle", True))
        for key, caption, editor in fields:
            self.profile_fields[key] = editor
            caption_label = label(caption, "fieldLabel", True)
            if isinstance(editor, OptionalNumber):
                caption_label.setBuddy(editor.known)
                editor.known.setAccessibleName(f"{caption} 입력")
                editor.editor.setAccessibleName(caption)
            else:
                caption_label.setBuddy(editor)
            field = QVBoxLayout()
            field.setSpacing(5)
            field.addWidget(caption_label)
            field.addWidget(editor)
            layout.addLayout(field)
        if hint:
            layout.addWidget(label(hint, "muted", True))
        layout.addStretch()
        return card

    def profile_cards_tab(self, left, right, extra=None):
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)
        first, second = QVBoxLayout(), QVBoxLayout()
        first.addWidget(left)
        second.addWidget(right)
        layout.addWidget(ResponsiveColumns(first, second, spacing=14, stretch=(1, 1)))
        if extra is not None:
            layout.addWidget(extra)
        layout.addStretch()
        return body

    def profile_common_tab(self):
        hours = QDoubleSpinBox()
        hours.setRange(0, 168)
        hours.setDecimals(1)
        hours.setValue(self.profile["weekly_hours"])
        budget = QDoubleSpinBox()
        budget.setRange(0, 10**16)
        budget.setDecimals(0)
        budget.setGroupSeparatorShown(True)
        budget.setValue(self.profile["monthly_budget"])
        identity = self.profile_card("기본 정보", (
            ("name", "이름·닉네임", QLineEdit(self.profile["name"])),
            ("age", "나이 (선택)", QLineEdit(self.profile["age"])),
        ))
        resources = self.profile_card("목표에 쓸 시간과 예산", (
            ("weekly_hours", "주당 순가용 시간 (시간)", hours),
            ("monthly_budget", "월 목표용 가용 예산 (원)", budget),
        ), "고정 일정과 휴식을 제외한 시간을 입력하세요. 계획기는 이 시간을 7일에 균등 배분합니다.")
        return self.profile_cards_tab(identity, resources)

    def profile_finance_tab(self):
        amounts = {
            key: (key, f"{title} (원)", OptionalNumber(self.profile[key], maximum=10**16, decimals=0))
            for key, title in FINANCE_AMOUNTS.items()
        }
        valuation_date = QLineEdit(self.profile["valuation_date"])
        valuation_date.setPlaceholderText("YYYY-MM-DD")
        expenses = QLineEdit(self.profile["planned_expenses"])
        expenses.setPlaceholderText("예  ·  내년 이사비 300만 원")
        balances = self.profile_card("자산·부채 현황", (
            amounts["assets"], amounts["liabilities"], ("valuation_date", "자산·부채 기준일", valuation_date),
        ), "원화로 환산한 금액을 기록하세요. 부채가 없다면 ‘입력’을 켜고 0원을 기록하세요.")
        cashflow = self.profile_card("월 현금흐름", (
            amounts["monthly_income"], amounts["monthly_expenses"],
        ), "이전에 기록한 수입의 통화와 실수령 기준을 확인해 주세요. 목표별 투자 시작금과 월 납입금은 목표에서 설정합니다.")
        planned = self.profile_card("예정 지출", (("planned_expenses", "예정된 큰 지출", expenses),))
        return self.profile_cards_tab(balances, cashflow, planned)

    def page_goals(self,layout):
        self.heading(layout, "목표 관리", "완료 기준을 정하고 다음 실행으로 연결하세요.", "GOALS & MILESTONES")
        search=QLineEdit(self.goal_search);search.setPlaceholderText("목표 이름 또는 완료 기준 검색…")
        search.returnPressed.connect(lambda:self.filter_search(search.text()))
        layout.addLayout(row(search,button("검색",lambda:self.filter_search(search.text())),button("＋ 새로운 목표",self.edit_goal,True)))
        goals=[g for g in self.filtered_goals() if not self.goal_search or self.goal_search.casefold() in (g["title"]+g["criteria"]).casefold()]
        if goals:self.goal_grid(layout,sorted(goals,key=lambda g:(g["status"]=="completed",-g["priority"],g["due_date"])))
        else:self.empty(layout,"표시할 목표가 없습니다","검색·분야 필터를 조정하거나 첫 목표를 등록하세요.")
        layout.addWidget(label("진행도는 목표 기준의 변화 또는 준비 과제 완료 비율입니다. 과제를 모두 마친 뒤에도 최종 달성은 별도로 확인하세요.","muted",True))

    def page_roadmap(self,layout):
        self.heading(layout, "성장 로드맵", "단계별 계획을 살펴보고 나에게 맞는 실행 속도를 정하세요.", "GROWTH ROADMAP")
        selected=goal_selector(self.filtered_goals())
        selected.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        selected.setMinimumWidth(250)
        detail=button("목표 상세 분석·단계 보기",lambda:self.show_goal_analysis(next((g for g in self.goals if g["id"]==selected.currentData()),None)),True)
        detail.setEnabled(bool(selected.count()))
        layout.addLayout(row(selected,detail))
        periods = ("일간", "주간", "월간")
        period_tabs = QTabBar()
        period_tabs.setObjectName("roadmapPeriods")
        period_tabs.setAccessibleName("로드맵 보기 단위")
        period_tabs.setExpanding(False)
        period_tabs.setElideMode(Qt.TextElideMode.ElideNone)
        period_tabs.setUsesScrollButtons(False)
        for period in periods:
            period_tabs.addTab(period)
        period_tabs.setCurrentIndex(periods.index(self.roadmap_scale))
        layout.addLayout(row(period_tabs, None, button("미완료 일정 재배치", lambda: self.plan(True)),
                             button("✦ 로드맵 초안 만들기", lambda: self.plan(False), True)))
        ids={g["id"] for g in self.filtered_goals()}
        tasks=[t for t in self.tasks if t["goal_id"] in ids]
        summary,sl=panel();sl.addWidget(label(f"주당 순가용 {self.profile['weekly_hours']:g}시간 · 현재 실행 과제 {len(tasks)}개 · 다음 28일 계획","sectionTitle",True));sl.addWidget(label("예상 시간은 수정 가능한 초안입니다. 장기 목표는 중간 성과부터 정하고 가까운 기간의 과제를 구체화합니다.","muted",True));layout.addWidget(summary)
        task_area = QVBoxLayout()
        task_area.setSpacing(0)
        layout.addLayout(task_area)

        def show_period(index):
            self.roadmap_scale = periods[index]
            previous = task_area.takeAt(0)
            if previous is not None:
                previous.widget().hide()
                previous.widget().deleteLater()
            content = QWidget()
            sections = QVBoxLayout(content)
            sections.setContentsMargins(0, 0, 0, 0)
            sections.setSpacing(layout.spacing())
            self.roadmap_tasks(sections, tasks)
            task_area.addWidget(content)

        period_tabs.currentChanged.connect(show_period)
        show_period(period_tabs.currentIndex())

    def roadmap_tasks(self, layout, tasks):
        groups = defaultdict(list)
        for task in sorted(tasks, key=lambda item: item.get("scheduled_date") or "9999"):
            value = task.get("scheduled_date")
            if not value:
                key = "일정 미배정"
            else:
                day = date.fromisoformat(value)
                if self.roadmap_scale == "월간":
                    key = f"{day:%Y년 %m월}"
                elif self.roadmap_scale == "주간":
                    key = f"{(day - timedelta(days=day.weekday())):%Y.%m.%d} 시작 주"
                else:
                    key = f"{day:%Y.%m.%d}"
            groups[key].append(task)
        if not tasks:
            self.empty(layout, "목표를 실행 단계로 나눠 보세요", "프로필과 목표를 입력한 뒤 실행할 로드맵을 설계할 수 있습니다.")
        for index, (title, entries) in enumerate(groups.items(), 1):
            card, content = panel()
            card.setObjectName("timelineCard")
            number_label = label(f"{index:02d}", "sectionIndex")
            number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            content.addLayout(row(number_label, label(title, "sectionTitle", True), None,
                                  pill(f"{sum(task['done'] for task in entries)} / {len(entries)} 완료")))
            for task in sorted(entries, key=lambda item: (item.get("scheduled_date") or "9999", item.get("position", 0))):
                content.addWidget(self.task_row(task))
            layout.addWidget(card)

    def page_today(self,layout):
        self.heading(layout, "오늘의 실행", "예정된 과제와 반복 습관을 확인하고 실행을 기록하세요.", "DAILY PRACTICE")
        editor=QDateEdit(QDate(self.execution_date.year,self.execution_date.month,self.execution_date.day));editor.setCalendarPopup(True);editor.setDisplayFormat("yyyy-MM-dd");editor.setMinimumWidth(148)
        editor.dateChanged.connect(self.set_execution_date)
        layout.addLayout(row(editor,button("오늘",lambda:self.set_execution_date(QDate.currentDate())),None,button("＋ 습관",self.edit_habit),button("＋ 실행 과제",self.edit_task,True)))
        ds=self.execution_date.isoformat();ids={g["id"] for g in self.filtered_goals()}
        items=[t for t in self.tasks if t["goal_id"] in ids and t.get("scheduled_date")==ds]
        summary, summary_content = panel(True)
        completed = sum(task["done"] for task in items)
        summary_content.addLayout(row(label("선택한 날짜의 실행", "sectionTitle"), None,
                                      pill(f"{completed} / {len(items)} 완료", "#159f90")))
        summary_content.addWidget(progress_bar(completed / len(items) if items else 0, theme_colors()["accent"]))
        summary_content.addWidget(label(f"예상 작업 시간 {sum(task['minutes'] for task in items) / 60:g}시간 · 남은 과제 {len(items) - completed}개", "muted", True))
        layout.addWidget(summary)
        self.section(layout, "실행 과제")
        for t in sorted(items,key=lambda t:(t["done"],t.get("position",0))):layout.addWidget(self.task_row(t))
        if not items:self.empty(layout,"이 날짜에 예정된 과제가 없습니다","로드맵에서 일정을 배치하거나 직접 과제를 추가할 수 있습니다.")
        if self.execution_date==date.today():
            overdue=[t for t in self.tasks if t["goal_id"] in ids and not t["done"] and (not t.get("scheduled_date") or t["scheduled_date"]<ds)]
            if overdue:
                self.section(layout,f"다시 계획할 과제  ·  {len(overdue)}개",button("일정 재배치",lambda:self.plan(True),ghost=True))
                for t in overdue[:8]:layout.addWidget(self.task_row(t))
        self.section(layout,"반복 습관")
        for h in self.habits:
            if self.category!="all" and h["category"]!=self.category:continue
            card,cl=panel();scheduled=self.execution_date.weekday() in h["weekdays"]
            checked=QCheckBox();checked.setAccessibleName(h["title"])
            checked.setChecked(ds in h["completions"]);checked.setEnabled(scheduled and self.execution_date<=date.today())
            checked.toggled.connect(lambda _done,i=h["id"],d=ds:self.toggle_habit(i,d))
            header=row(checked);header.addWidget(CheckBoxLabel(h["title"],checked),1)
            header.addWidget(pill(f"{engine.habit_streak(h)}회 연속","#e5bd67"))
            header.addWidget(button("수정",lambda habit=h:self.edit_habit(habit),ghost=True))
            cl.addLayout(header)
            days=" · ".join("월화수목금토일"[i] for i in h["weekdays"])
            cl.addWidget(label(f"{days}  /  {h['minutes']}분 · "+("수행 예정일" if scheduled else "쉬는 날"),"muted"));layout.addWidget(card)
        if not self.habits:self.empty(layout,"꾸준함을 위한 작은 약속","반복할 요일과 필요한 시간을 정해 습관을 등록하세요.")

    def page_analysis(self, layout):
        self.heading(layout, "성장 분석과 회고", "실행 기록을 돌아보고 다음 계획의 기준을 찾으세요.", "INSIGHTS & REFLECTION")
        goals = self.filtered_goals()
        goal_ids = {goal["id"] for goal in goals}
        tasks = [task for task in self.tasks if task["goal_id"] in goal_ids]
        series = engine.activity_series(tasks)
        reviews = self.store.reviews()
        known = [state["value"] for goal in goals if (state := engine.progress_state(goal, tasks))["value"] is not None]
        self.stat_row(layout, [
            stat_card("최근 7일 예정", str(sum(day["planned"] for day in series)), "예정일이 최근 7일인 과제", "#4f7ff3", "◷"),
            stat_card("그중 완료한 과제", str(sum(day["completed"] for day in series)), "현재 완료 상태를 기준으로 집계", "#159f90", "✓"),
            stat_card("분석 가능한 목표", f"{len(known)} / {len(goals)}", "진행도를 계산할 수 있는 목표", "#8b6ae8", "↗"),
            stat_card("남긴 회고", str(len(reviews)), "분야 전체의 회고 기록", "#d38b39", "▤"),
        ])
        activity, activity_content = panel()
        activity_content.addWidget(label("계획과 실행의 흐름", "sectionTitle"))
        activity_content.addWidget(label("예정일별 과제 수와 그중 완료한 과제 수 · 최근 7일", "muted", True))
        activity_content.addWidget(TrendChart(series))
        categories, category_content = panel()
        category_content.addWidget(label("분야별 목표 분포", "sectionTitle"))
        category_content.addWidget(label("선택한 분야에 등록된 목표 개수", "muted", True))
        category_content.addWidget(CategoryChart([
            {"name": category["name"], "color": category["color"],
             "value": sum(goal["category"] == key for goal in goals)}
            for key, category in CATEGORIES.items() if self.category in {"all", key}
        ]))
        chart_column, category_column = QVBoxLayout(), QVBoxLayout()
        chart_column.addWidget(activity)
        category_column.addWidget(categories)
        layout.addWidget(ResponsiveColumns(chart_column, category_column, stretch=(3, 1)))
        self.section(layout, "목표 진행도")
        grid = QGridLayout()
        grid.setSpacing(14)
        index = 0
        for key, category in CATEGORIES.items():
            if self.category not in {"all", key}:
                continue
            related = [goal for goal in goals if goal["category"] == key]
            values = [state["value"] for goal in related if (state := engine.progress_state(goal, tasks))["value"] is not None]
            average = sum(values) / len(values) if values else None
            card, content = panel()
            content.addLayout(row(pill(category["name"], category["color"]), None,
                                  label(f"{average:.0%}" if average is not None else "정보 부족", "metricValue")))
            content.addWidget(progress_bar(average or 0, category["color"]))
            content.addWidget(label(f"목표 {len(related)}개 · 계산 가능 {len(values)}개 기준의 평균 진행도", "muted", True))
            grid.addWidget(card, index // 2, index % 2)
            index += 1
        layout.addLayout(grid)
        self.section(layout, "회고 노트", button("＋ 회고 쓰기", self.add_review))
        for review in sorted(reviews, key=lambda item: item["date"], reverse=True)[:6]:
            card, content = panel()
            card.setObjectName("timelineCard")
            content.addLayout(row(pill(review["date"]), None, label("나의 성장 기록", "muted")))
            for title, key in (("잘한 점", "good"), ("어려웠던 점", "challenge"), ("다음 행동", "next_action")):
                if review.get(key):
                    content.addWidget(label(title, "summaryTitle"))
                    content.addWidget(label(review[key], "muted", True))
            layout.addWidget(card)
        if not reviews:
            self.empty(layout, "이번 실행에서 무엇을 배웠나요?", "잘한 점, 어려움, 다음에 바꿀 행동을 기록해 보세요.", button("첫 회고 작성", self.add_review))
        history = self.store.history()
        if history:
            self.section(layout, "최근 계획 변경")
            for item in history[:5]:
                card, content = panel()
                content.setContentsMargins(16, 12, 16, 12)
                content.addLayout(row(pill(item["created_at"][:10]), label(item["summary"], "muted", True), None))
                layout.addWidget(card)

    def page_coach(self, layout):
        self.heading(layout, "나의 성장 코치", "저장된 기록을 바탕으로 다음 행동을 점검하세요.", "COACHING ROOM")
        intro, intro_content = panel(True)
        intro_content.addLayout(row(pill("규칙 기반 코치", "#159f90"), None, label("외부 AI 미연결", "muted")))
        intro_content.addWidget(label("지금 막힌 곳부터, 다음 한 걸음으로.", "summaryTitle", True))
        intro_content.addWidget(label("목표의 부족한 정보와 실행 조건을 확인하고, 일정 변경안을 직접 검토할 수 있습니다.", "muted", True))
        intro_content.addWidget(button("계획 수정안 살펴보기 →", lambda: self.plan(True), True), 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(intro)
        self.section(layout, "목표별 점검")
        grid = QGridLayout()
        grid.setSpacing(14)
        goals = self.filtered_goals()[:3]
        for index, goal in enumerate(goals):
            report = analyze_goal(goal, self.profile, self.metrics, self.tasks, self.habits, self.goals)
            card, content = panel()
            category = CATEGORIES[goal["category"]]
            content.addLayout(row(pill(category["name"], category["color"]), None,
                                  label(f"확인할 정보 {len(report['missing'])}건", "muted")))
            content.addWidget(label(goal["title"], "sectionTitle", True))
            content.addWidget(label(report["summary"], "muted", True))
            content.addWidget(label(f"조건과 위험 점검 {len(report['warnings'])}건", "muted", True))
            content.addWidget(button("상세 진단 보기 →", lambda item=goal: self.show_goal_analysis(item)))
            grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(grid)
        self.section(layout, "기록에서 찾은 점검 노트")
        for index, insight in enumerate(engine.insights(self.profile, self.goals, self.tasks, self.metrics, self.habits), 1):
            card, content = panel()
            heading = row(pill(f"{index:02d}", "#d38b39" if insight["kind"] == "warning" else "#4f7ff3"),
                          label(insight["title"], "sectionTitle", True), None)
            content.addLayout(heading)
            content.addWidget(label(insight["body"], "muted", True))
            layout.addWidget(card)
        external, external_content = panel()
        external_content.addWidget(label("상담과 자료 확인", "sectionTitle"))
        external_content.addWidget(label("현재 기록을 상담용으로 복사하거나, 브라우저에서 목표에 필요한 자료를 찾아보세요.", "muted", True))
        self.include_profile = QCheckBox("프로필도 포함 (금융·자산 및 커리어 상세 정보)")
        external_content.addWidget(self.include_profile)
        external_content.addWidget(button("상담용 요약 복사", self.copy_coaching), 0, Qt.AlignmentFlag.AlignLeft)
        search = QLineEdit()
        search.setPlaceholderText("확인할 직무·시험·학습 자료")
        external_content.addLayout(row(search, button("브라우저 검색 ↗", lambda: self.open_search(search.text()))))
        layout.addWidget(external)

    def page_settings(self, layout):
        self.heading(layout, "작업 공간 설정", "화면, 알림, 백업을 내 사용 방식에 맞게 관리하세요.", "PREFERENCES")
        appearance, appearance_content = panel()
        appearance.setObjectName("settingsSection")
        appearance_content.addWidget(label("화면과 알림", "sectionTitle"))
        appearance_content.addWidget(label("매일 쓰기 편한 작업 공간을 만들어 보세요.", "muted", True))
        light = QCheckBox("밝은 테마 사용")
        light.setChecked(self.preferences.value("light", True, type=bool))
        light.toggled.connect(self.set_light)
        appearance_content.addWidget(light)
        notifications = QCheckBox("앱 실행 중 오늘의 미완료 과제 알림")
        notifications.setChecked(self.preferences.value("notifications", False, type=bool))
        notifications.toggled.connect(lambda value: self.preferences.setValue("notifications", value))
        appearance_content.addWidget(notifications)
        appearance_content.addWidget(label("완전 종료·절전 중에는 알림이 표시되지 않습니다.", "muted", True))
        backups, backup_content = panel()
        backups.setObjectName("settingsSection")
        backup_content.addWidget(label("백업과 데이터 이동", "sectionTitle"))
        backup_content.addWidget(label("기록과 첨부 파일을 묶어 다른 PC로 옮기세요. 복원 시 현재 데이터를 교체하고, 교체 전 기록을 자동 백업합니다.", "muted", True))
        backup_content.addWidget(pill("백업 파일은 암호화되지 않습니다.", "#d38b39"), 0, Qt.AlignmentFlag.AlignLeft)
        backup_content.addWidget(button("백업 내보내기", self.export_backup, True))
        backup_content.addWidget(button("백업에서 복원", self.restore_backup))
        left, right = QVBoxLayout(), QVBoxLayout()
        left.addWidget(appearance)
        right.addWidget(backups)
        layout.addWidget(ResponsiveColumns(left, right, stretch=(1, 1)))
        storage, storage_content = panel()
        storage_content.addWidget(label("내 데이터 보관 위치", "sectionTitle"))
        storage_content.addWidget(label(str(self.store.data_dir), "muted", True))
        storage_content.addWidget(button("데이터 폴더 열기 ↗", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.data_dir)))), 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(storage)
        if not self.goals:
            self.empty(layout, "실제 입력 전에 살펴보기", "빈 작업 공간에 가상 예시를 불러와 화면을 살펴볼 수 있습니다.", button("가상 예시 불러오기", self.load_demo))

    def edit_goal(self,goal=None):
        dialog=GoalDialog(goal,self)
        if goal:dialog.form.addRow(button("이 목표와 연결 과제 삭제",lambda:self.delete_record("goal",goal["id"],dialog)))
        if dialog.exec()==QDialog.DialogCode.Accepted:
            def action():
                goal_id=self.store.save_goal(dialog.values());self.refresh()
                saved=next(g for g in self.goals if g["id"]==goal_id)
                self.show_goal_analysis(saved)
            self.guard(action)

    def show_goal_analysis(self,goal=None):
        if not goal:return
        def action():
            self.snapshot()
            current=next((g for g in self.goals if g["id"]==goal["id"]),None)
            if current is None:return
            report=analyze_goal(current,self.profile,self.metrics,self.tasks,self.habits,self.goals)
            plan=engine.build_plan([current],self.tasks,self.profile,self.habits,reports={current["id"]:report},metrics=self.metrics)
            dialog=GoalAnalysisDialog(report,plan,self)
            result=dialog.exec()
            if result==QDialog.DialogCode.Accepted:
                self.store.add_tasks(plan["tasks"])
                self.store.log_change(f"‘{current['title']}’ 상세 분석 기반 실행 과제 추가",plan["summary"])
                self.refresh()
            elif result==2:
                self.edit_goal(current)
        self.guard(action)

    def edit_task(self,task=None):
        if not self.goals:
            QMessageBox.information(self,"먼저 목표를 등록하세요","실행 과제를 연결할 목표가 필요합니다.");return
        dialog=TaskDialog(self.goals,task,self)
        if task:dialog.form.addRow(button("이 실행 과제 삭제",lambda:self.delete_record("task",task["id"],dialog)))
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.guard(lambda:self.store.save_task(dialog.values()));self.refresh()

    def edit_habit(self,habit=None):
        dialog=HabitDialog(habit,self)
        if habit:dialog.form.addRow(button("이 습관과 수행 기록 삭제",lambda:self.delete_record("habit",habit["id"],dialog)))
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.guard(lambda:self.store.save_habit(dialog.values()));self.refresh()

    def add_metric(self,category=None):
        dialog=MetricDialog(category,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.guard(lambda:self.store.add_metric(dialog.values()));self.refresh()

    def delete_record(self,kind,record_id,dialog):
        if QMessageBox.warning(self,"기록 삭제","선택한 항목과 연결된 기록을 삭제할까요? 삭제 전 필요하면 설정에서 백업하세요.",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes:return
        def action():
            getattr(self.store,f"delete_{kind}")(record_id);dialog.reject();self.refresh()
        self.guard(action)

    def add_review(self):
        dialog=ReviewDialog(self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.guard(lambda:self.store.add_review(dialog.values()));self.refresh()

    def save_profile(self):
        def action():
            data={key:(editor.text().strip() if isinstance(editor,QLineEdit) else editor.value()) for key,editor in self.profile_fields.items()}
            data.update(self.career_profile.values())
            self.store.save_profile(data);self.refresh();self.statusBar().showMessage("프로필을 저장했습니다.",5000)
        self.guard(action)

    def toggle_task(self,task_id,done):
        self.guard(lambda:self.store.set_task_done(task_id,done));self.refresh()

    def toggle_habit(self,habit_id,ds):
        self.guard(lambda:self.store.toggle_habit(habit_id,ds));self.refresh()

    def filter_search(self,text):
        self.goal_search=text.strip();self.refresh()

    def set_execution_date(self,d):
        self.execution_date=date(d.year(),d.month(),d.day());self.refresh()

    def open_roadmap(self,goal):
        self.page_key="roadmap";self.category=goal["category"]
        self.category_combo.blockSignals(True);self.category_combo.setCurrentIndex(self.category_combo.findData(self.category));self.category_combo.blockSignals(False);self.refresh()

    def plan(self,replan=False):
        self.snapshot()
        if not self.goals:
            QMessageBox.information(self,"목표가 필요합니다","프로필과 첫 목표를 입력한 뒤 로드맵을 생성하세요.");return
        try:
            result=(engine.replan(self.tasks,self.goals,self.profile,self.habits) if replan else engine.build_plan(self.goals,self.tasks,self.profile,self.habits,metrics=self.metrics))
        except ValueError as exc:
            QMessageBox.warning(self,"계획 조건을 확인하세요",str(exc));return
        dialog=QDialog(self);dialog.setWindowTitle("계획 수정안" if replan else "로드맵 초안");dialog.resize(820,650)
        l=QVBoxLayout(dialog);l.setContentsMargins(24,24,24,24);l.setSpacing(14)
        l.addWidget(label("적용 전에 계획을 확인하세요","sectionTitle"));l.addWidget(label(result["summary"],"muted",True))
        if result["warnings"]:
            warnings=QTextEdit();warnings.setReadOnly(True);warnings.setPlainText("\n".join("• "+s for s in result["warnings"]));warnings.setMaximumHeight(135);l.addWidget(warnings)
        entries=result["tasks"]
        rows = [
            (task["title"], task.get("scheduled_date") or "배치 불가", f"{task['minutes']}분",
             task.get("stage", ""), task.get("done_when", ""))
            for task in entries
        ]
        table = wrapped_table(["실행 과제", "일정", "예상 시간", "단계", "완료 기준"], rows,
                              compact_columns=(1, 2), minimum_height_cap=220)
        l.addWidget(table, 1)
        l.addWidget(label("규칙 기반 초안 · 예상 시간과 선행 학습은 목표에 맞춰 직접 수정할 수 있습니다. 완료 기록은 유지됩니다.","muted",True))
        cancel=button("취소",dialog.reject);apply=button(f"{len(entries)}개 변경 적용" if replan else f"{len(entries)}개 과제 추가",dialog.accept,True);apply.setEnabled(bool(entries));l.addLayout(row(None,cancel,apply))
        _fit_to_screen(dialog)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            def action():
                if replan:
                    self.store.apply_task_updates(entries)
                else:self.store.add_tasks(entries)
                self.store.log_change("미완료 일정 재배치" if replan else "로드맵 초안 적용",result["summary"])
                self.refresh()
            self.guard(action)

    def copy_coaching(self):
        data={"goals":self.goals,"tasks":self.tasks,"weekly_hours":self.profile["weekly_hours"]}
        include_profile = self.include_profile.isChecked()
        report_profile = self.profile if include_profile else {"weekly_hours": self.profile["weekly_hours"]}
        data["goal_analysis"]=[analyze_goal(g,report_profile,self.metrics,self.tasks,self.habits,self.goals) for g in self.goals if g["status"]=="active"]
        if include_profile:data["profile"]=self.profile
        prompt="다음은 내가 직접 기록한 목표와 실행 현황이다. 사실·해석·정보 부족을 구분하고, 가용 시간 안에서 실행 가능한 개선안을 제안해줘. 근거 없는 실력 점수·성공 확률·투자수익을 만들지 말아줘.\n\n"+json.dumps(data,ensure_ascii=False,indent=2)
        QApplication.clipboard().setText(prompt);self.statusBar().showMessage("상담용 요약을 복사했습니다. 외부 서비스에 붙여넣을 내용을 확인하세요.",7000)

    def open_search(self,text):
        if text.strip():QDesktopServices.openUrl(QUrl("https://www.google.com/search?q="+quote(text.strip())))

    def set_light(self,value):
        self.preferences.setValue("light", value)
        apply_theme(QApplication.instance(), value)
        refresh_accents(self)
        for key, item in self.nav.items():
            color = theme_colors()["accent"] if key == self.page_key else theme_colors()["muted"]
            item.setIcon(ui_icon(key, color))

    def load_demo(self):
        if QMessageBox.question(self,"가상 예시 불러오기","모든 이름·금액·성과가 가상인 예시를 빈 작업 공간에 추가할까요?")!=QMessageBox.StandardButton.Yes:return
        def action():
            if not self.store.seed_demo():
                QMessageBox.information(self,"비어 있는 작업 공간이 필요합니다","이미 입력한 데이터가 있어 예시를 불러오지 않았습니다. 별도 데모 모드를 사용하세요.")
                return
            self.demo=True;self.preferences.setValue("demo",True);self.refresh()
        self.guard(action)

    def export_backup(self):
        path,_=QFileDialog.getSaveFileName(self,"백업 저장",f"PGM-{date.today().isoformat()}.pgmbackup","PGM 백업 (*.pgmbackup)")
        if path:
            def action():
                self.store.export_backup(path);QMessageBox.information(self,"백업 완료",f"백업 파일을 저장했습니다.\n{path}\n\n이 파일은 암호화되지 않았습니다.")
            self.guard(action)

    def restore_backup(self):
        path,_=QFileDialog.getOpenFileName(self,"백업 선택","","PGM 백업 (*.pgmbackup)")
        if not path:return
        if QMessageBox.warning(self,"현재 데이터 교체","선택한 백업으로 현재 데이터 전체를 교체합니다. 먼저 현재 상태를 자동 백업합니다. 두 기기의 변경 내용은 병합하지 않습니다.",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes:return
        def action():
            previous=self.store.restore_backup(path);self.demo=self.store.is_demo();self.preferences.setValue("demo",self.demo);self.refresh();QMessageBox.information(self,"복원 완료",f"백업을 복원했습니다.\n복원 전 자동 백업: {previous}")
        self.guard(action)

    def check_notifications(self):
        if not self.preferences.value("notifications",False,type=bool) or self.notified_day==date.today():return
        pending=[t for t in self.store.tasks() if not t["done"] and t.get("scheduled_date")==date.today().isoformat()]
        if not pending:return
        self.notified_day=date.today();message=f"오늘 예정된 미완료 과제가 {len(pending)}개 있습니다."
        if QSystemTrayIcon.isSystemTrayAvailable() and QSystemTrayIcon.supportsMessages():
            self.tray.show();self.tray.showMessage("PGM · 오늘의 실행",message,QSystemTrayIcon.MessageIcon.Information,8000)
        self.statusBar().showMessage(message,15000)

    def closeEvent(self,event):
        self.notification_timer.stop();self.tray.hide();self.preferences.sync();self.store.close();super().closeEvent(event)


def main(argv=None):
    parser=argparse.ArgumentParser(description="PGM personal growth desktop prototype")
    parser.add_argument("--data-dir",type=Path,help="Use a separate local data folder")
    parser.add_argument("--demo",action="store_true",help="Use clearly fictional example data in a separate demo workspace")
    parser.add_argument("--screenshot",type=Path,help="Save dashboard screenshot and exit")
    parser.add_argument("--smoke-test",action="store_true",help="Open all navigation pages and exit")
    args=parser.parse_args(argv)
    app=QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("PGM");app.setOrganizationName("PGM")
    if sys.platform=="darwin":app.setFont(QFont("Apple SD Gothic Neo",12))
    elif sys.platform=="win32":app.setFont(QFont("Malgun Gothic",10))
    folder=args.data_dir or Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    if args.demo and args.data_dir is None:folder=folder/"demo"
    store=Store(folder)
    if args.demo:
        store.seed_demo()
        if not store.is_demo():
            store.close();parser.error("지정한 폴더에 개인 데이터가 있습니다. 데모용 새 폴더를 선택하세요.")
    window=MainWindow(store,args.demo)
    _fit_to_screen(window)
    window.show()
    if args.screenshot or args.smoke_test:
        def capture():
            try:
                if args.smoke_test:
                    for key,_,_ in NAVIGATION:
                        window.navigate(key)
                        app.processEvents()
                        if key == "profile":
                            for tab in range(window.profile_tabs.count()):
                                window.profile_tabs.setCurrentIndex(tab)
                                app.processEvents()
                            window.profile_tabs.setCurrentIndex(0)
                    for goal in window.goals:
                        report=analyze_goal(goal,window.profile,window.metrics,window.tasks,window.habits,window.goals)
                        preview=engine.build_plan([goal],window.tasks,window.profile,window.habits,reports={goal['id']:report},metrics=window.metrics)
                        probe=GoalAnalysisDialog(report,preview,window);probe.show();app.processEvents()
                        for tab in range(probe.tabs.count()):probe.tabs.setCurrentIndex(tab);app.processEvents()
                        probe.close();probe.deleteLater()
                    window.navigate("dashboard");app.processEvents()
                if args.screenshot:
                    args.screenshot.parent.mkdir(parents=True,exist_ok=True)
                    if not window.grab().save(str(args.screenshot)):raise OSError("Screenshot save failed")
                print("PGM_SMOKE_OK" if args.smoke_test else "PGM_SCREENSHOT_OK")
                window.close();app.quit()
            except Exception:
                import traceback
                traceback.print_exc();window.close();app.exit(1)
        QTimer.singleShot(500,capture)
    return app.exec()
