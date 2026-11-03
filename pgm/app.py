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

from PySide6.QtCore import QDate, QSettings, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSystemTrayIcon, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from . import __version__
from . import engine
from .constants import CATEGORIES, HORIZONS, KINDS, NAVIGATION, PRIORITIES
from .dialogs import GoalDialog, HabitDialog, MetricDialog, ReviewDialog, TaskDialog
from .storage import Store
from .theme import apply_theme
from .widgets import ActivityChart, Ring, label, panel, pill, stat_card


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
        self.notified_day=None
        self.setWindowTitle(f"PGM · Personal Growth Workspace {__version__}")
        self.setWindowIcon(QIcon(str(Path(__file__).parent/"assets"/"icon.svg")))
        self.setMinimumSize(1100,740)
        self.resize(1440,960)
        apply_theme(QApplication.instance(),self.preferences.value("light",False,type=bool))
        root=QWidget();root.setObjectName("appRoot");self.setCentralWidget(root)
        shell=QHBoxLayout(root);shell.setContentsMargins(0,0,0,0);shell.setSpacing(0)
        sidebar=QWidget();sidebar.setObjectName("sidebar");sidebar.setFixedWidth(230)
        side=QVBoxLayout(sidebar);side.setContentsMargins(19,27,18,20);side.setSpacing(6)
        brand=row(label("◈","brand"),label("PGM","brand"),None)
        side.addLayout(brand);side.addWidget(label("GROWTH WORKSPACE","eyebrow"));side.addSpacing(29)
        side.addWidget(label("나의 성장 공간","muted"));side.addSpacing(8)
        self.nav={}
        for key,icon,title in NAVIGATION:
            b=button(f"{icon}    {title}",lambda k=key:self.navigate(k))
            b.setObjectName("nav");b.setCheckable(True);side.addWidget(b);self.nav[key]=b
        side.addSpacing(23);side.addWidget(label("SIX AREAS OF GROWTH","eyebrow"));side.addSpacing(7)
        for key,c in CATEGORIES.items():
            item=label(f"●   {c['name']}");item.setStyleSheet(f"color:{c['color']}; padding:4px 11px; font-size:11px;")
            side.addWidget(item)
        side.addStretch()
        box,bl=panel();bl.setContentsMargins(12,12,12,12)
        bl.addWidget(label("내 PC에 저장되는 성장 기록",wrap=True))
        bl.addWidget(label("v0.1 · 데스크톱 프로토타입","muted"))
        side.addWidget(box);shell.addWidget(sidebar)
        right=QWidget();right_layout=QVBoxLayout(right);right_layout.setContentsMargins(0,0,0,0);right_layout.setSpacing(0)
        top=QWidget();top.setObjectName("topbar");top.setFixedHeight(75)
        tl=QHBoxLayout(top);tl.setContentsMargins(30,0,30,0)
        self.breadcrumb=label("WORKSPACE   /   대시보드","muted");tl.addWidget(self.breadcrumb);tl.addStretch()
        self.category_combo=QComboBox();self.category_combo.addItem("모든 분야","all")
        for key,c in CATEGORIES.items():self.category_combo.addItem(c["name"],key)
        self.category_combo.setMinimumWidth(160)
        self.category_combo.currentIndexChanged.connect(self.change_category)
        tl.addWidget(self.category_combo);tl.addWidget(button("＋ 목표 추가",self.edit_goal,True))
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
        self.breadcrumb.setText(f"WORKSPACE   /   {title}")
        for key,b in self.nav.items():b.setChecked(key==self.page_key)
        page=QWidget();page.setObjectName("page")
        layout=QVBoxLayout(page);layout.setContentsMargins(32,27,32,30);layout.setSpacing(22)
        if self.demo:
            hint=label("DEMO   ·   현재 표시된 이름·금액·성과는 모두 가상 예시입니다.")
            hint.setStyleSheet("color:#e5bd67; background:rgba(229,189,103,18); padding:9px 13px; border-radius:7px; font-size:11px;")
            layout.addWidget(hint)
        getattr(self,f"page_{self.page_key}")(layout)
        layout.addStretch()
        old=self.scroll.takeWidget()
        self.scroll.setWidget(page)
        if old is not None:old.deleteLater()
        self.statusBar().showMessage(f"로컬 저장 · 목표 {len(self.goals)}개 · 기록은 내 PC에 보관됩니다"+(" · 가상 예시" if self.demo else ""))

    def heading(self,layout,title,subtitle,eyebrow=None):
        box=QVBoxLayout();box.setSpacing(7)
        if eyebrow:box.addWidget(label(eyebrow,"eyebrow"))
        box.addWidget(label(title,"pageTitle"));box.addWidget(label(subtitle,"muted",True));layout.addLayout(box)

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

    def goal_card(self,g):
        c=CATEGORIES[g["category"]];p=engine.progress(g,self.tasks)
        w,l=panel();w.setMinimumWidth(300)
        l.addLayout(row(pill(c["name"],c["color"]),pill(HORIZONS.get(g["horizon"],"목표")),None,label("✓ 달성 확인" if g["status"]=="completed" else PRIORITIES.get(g["priority"],"보통"),"muted")))
        title=label(g["title"],"sectionTitle",True);l.addWidget(title)
        if g["kind"]=="numeric":detail=f"{number(g['current'])} / {number(g['target'])} {g['unit']}"
        else:detail=g.get("criteria","")
        l.addWidget(label(detail,"muted",True));l.addWidget(progress_bar(p,c["color"]))
        l.addLayout(row(label(f"{p:.0%} · 목표 진행도","muted"),None,label(date_text(g["due_date"]),"muted")))
        pending=[t for t in self.tasks if t["goal_id"]==g["id"] and not t["done"]]
        next_task=min(pending,key=lambda t:(t.get("scheduled_date") or "9999",t.get("position",0)),default=None)
        l.addWidget(label("다음  ·  "+(next_task["title"] if next_task else "다음 단계를 계획해 보세요"),wrap=True))
        l.addLayout(row(button("목표 수정",lambda:self.edit_goal(g),ghost=True),None,button("로드맵 보기",lambda:self.open_roadmap(g),ghost=True)))
        return w

    def goal_grid(self,layout,goals):
        grid=QGridLayout();grid.setSpacing(15)
        for i,g in enumerate(goals):grid.addWidget(self.goal_card(g),i//2,i%2)
        grid.setColumnStretch(0,1);grid.setColumnStretch(1,1);layout.addLayout(grid)

    def task_row(self,t):
        g=next((g for g in self.goals if g["id"]==t["goal_id"]),None)
        w,l=panel();l.setContentsMargins(15,12,15,12)
        h=QHBoxLayout();check=QCheckBox();check.setChecked(t["done"])
        check.setAccessibleName(f"{t['title']} 완료")
        check.toggled.connect(lambda done,i=t["id"]:self.toggle_task(i,done))
        h.addWidget(check)
        text=QVBoxLayout();text.setSpacing(5)
        title=label(t["title"],wrap=True)
        if t["done"]:title.setStyleSheet("color:#82938e;")
        text.addWidget(title)
        detail=f"{g['title'] if g else '연결 목표 없음'}  ·  {date_text(t.get('scheduled_date',''))}"
        if t["done"]:detail+=f" · 실제 {t['actual_minutes']}분" if t["actual_minutes"] else " · 실제 시간 미기록"
        text.addWidget(label(detail,"muted",True))
        h.addLayout(text,1);h.addWidget(pill(f"{t['minutes']}분",CATEGORIES[g["category"]]["color"] if g else "#b69af7"))
        h.addWidget(button("수정",lambda:self.edit_task(t),ghost=True));l.addLayout(h)
        return w

    def page_dashboard(self,layout):
        name=self.profile.get("name") or "당신"
        self.heading(layout,f"{name}의 다음 단계, 분명하게.","작은 실행을 쌓고, 실제 변화로 다음 경로를 조정하세요.",date.today().strftime("GROWTH OVERVIEW   /   %Y.%m.%d"))
        goals=self.filtered_goals();ids={g["id"] for g in goals}
        tasks=[t for t in self.tasks if t["goal_id"] in ids]
        active=[g for g in goals if g["status"]!="completed"]
        today=[t for t in tasks if t.get("scheduled_date")==date.today().isoformat()]
        done=sum(t["done"] for t in today)
        thisweek=[t for t in self.tasks if t.get("scheduled_date") and date.today()<=date.fromisoformat(t["scheduled_date"])<=date.today()+timedelta(days=6)]
        minutes=sum(t["minutes"] for t in thisweek)
        stats=QHBoxLayout();stats.setSpacing(14)
        for card in [stat_card("진행 중인 목표",str(len(active)),"각자의 속도로, 같은 방향으로","#b69af7","↗"),stat_card("오늘의 실행",f"{done} / {len(today)}","오늘 예정된 과제 기준","#82c5a3","✓"),stat_card("다음 7일 계획",f"{minutes/60:.1f}h",f"전체 분야 · 주당 가용 {self.profile['weekly_hours']:g}h","#70c4da","◷"),stat_card("이번 주 습관",str(sum(len([d for d in h['completions'] if date.today()-timedelta(days=6)<=date.fromisoformat(d)<=date.today()]) for h in self.habits)),"최근 7일의 수행 기록","#e5bd67","✦")]:stats.addWidget(card,1)
        layout.addLayout(stats)
        hero,hl=panel(True)
        avg=sum(engine.progress(g,self.tasks) for g in goals)/len(goals) if goals else 0
        inside=row();copy=QVBoxLayout();copy.setSpacing(9)
        copy.addWidget(label("YOUR NEXT MOVE","eyebrow"))
        overdue=[t for t in tasks if not t["done"] and t.get("scheduled_date") and t["scheduled_date"]<date.today().isoformat()]
        if overdue:headline=f"밀린 {len(overdue)}개의 과제, 다시 배치해 볼까요?";sub="완료한 기록을 보존하고 남은 시간에 맞춰 일정을 조정할 수 있습니다."
        elif not goals:headline="지금의 나를 적고, 첫 목표를 정해 보세요.";sub="프로필 → 목표 → 로드맵 → 실행 기록으로 시작합니다."
        else:headline="계획을 실행으로, 실행을 성장의 근거로.";sub="오늘의 과제와 결과를 기록하면 다음 계획의 기준이 됩니다."
        copy.addWidget(label(headline,"sectionTitle",True));copy.addWidget(label(sub,"muted",True))
        copy.addWidget(button("나의 성장 경로 확인  →",lambda:self.navigate("roadmap"),ghost=True),0,Qt.AlignmentFlag.AlignLeft)
        inside.addLayout(copy,1);inside.addWidget(Ring(avg,"목표 평균 진행도"));hl.addLayout(inside);layout.addWidget(hero)
        columns=QHBoxLayout();columns.setSpacing(22)
        left=QVBoxLayout();left.setSpacing(14);self.section(left,"집중하고 있는 목표",button("모두 보기 →",lambda:self.navigate("goals"),ghost=True))
        if goals:self.goal_grid(left,sorted(goals,key=lambda g:(g["status"]=="completed",-g["priority"],g["due_date"]))[:4])
        else:self.empty(left,"성장 방향을 정할 차례","첫 목표를 등록하면 분야별 진행 상황이 여기에 표시됩니다.",button("첫 목표 만들기",self.edit_goal,True))
        right=QVBoxLayout();right.setSpacing(14);self.section(right,"오늘의 실행",button("모두 보기 →",lambda:self.navigate("today"),ghost=True))
        if today:
            for t in sorted(today,key=lambda t:t["done"])[:3]:right.addWidget(self.task_row(t))
        else:self.empty(right,"오늘 예정된 과제가 없습니다","로드맵 초안을 생성하거나 직접 실행 과제를 추가하세요.",button("실행 과제 추가",self.edit_task,ghost=True))
        chart,cl=panel();cl.addWidget(label("최근 7일의 실행","sectionTitle"));cl.addWidget(label("연보라 완료  ·  회보라 계획  /  과제 수","muted"));cl.addWidget(ActivityChart(engine.activity_series(tasks)))
        right.addWidget(chart);right.addStretch();left.addStretch()
        columns.addLayout(left,3);columns.addLayout(right,2);layout.addLayout(columns)
        if not self.goals:
            layout.addWidget(button("가상 예시로 먼저 살펴보기",self.load_demo,ghost=True),0,Qt.AlignmentFlag.AlignLeft)

    def page_profile(self,layout):
        self.heading(layout,"지금의 나를 이해하는 것부터.","입력한 사실과 자기평가를 구분해, 목표의 출발점을 기록합니다.","PROFILE & BASELINE")
        w,l=panel();form=QGridLayout();form.setHorizontalSpacing(24);form.setVerticalSpacing(12);self.profile_fields={}
        fields=[("name","이름·닉네임","text"),("occupation","직업·현재 역할","text"),("age","나이 (선택)","text"),("experience","경력·경험","text"),("skills","현재 역량·보유 자격","text"),("weekly_hours","주당 순가용 시간 (시간)","hours"),("monthly_budget","월 목표용 가용 예산","money"),("assets","현재 자산 합계","money"),("liabilities","현재 부채 합계","money"),("monthly_income","월 수입","money"),("monthly_expenses","월 지출","money")]
        for i,(key,title,kind) in enumerate(fields):
            box=QVBoxLayout();box.setSpacing(6);box.addWidget(label(title,"muted"))
            if kind=="text":editor=QLineEdit(str(self.profile.get(key,"") or ""))
            else:
                editor=QDoubleSpinBox();editor.setRange(0,168 if kind=="hours" else 1e12);editor.setDecimals(1 if kind=="hours" else 0);editor.setGroupSeparatorShown(True);editor.setValue(float(self.profile.get(key,0)))
            self.profile_fields[key]=editor;box.addWidget(editor);form.addLayout(box,i//2,i%2)
        l.addLayout(form);l.addWidget(label("순가용 시간은 고정 일정·휴식을 제외하고 목표와 앱에 등록한 습관에 쓸 수 있는 시간입니다. 현재 계획기는 이 시간을 7일에 균등 배분합니다. 금액은 동일 통화 기준으로 직접 기록하며 계획의 예산 검증은 아직 지원하지 않습니다.","muted",True))
        l.addWidget(button("프로필 저장",self.save_profile,True),0,Qt.AlignmentFlag.AlignRight);layout.addWidget(w)
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
                card,cl=panel();cl.addWidget(label(f"{CATEGORIES[m['category']]['name']} · {m['label']}  {number(m['value'])}{m['unit']}"));cl.addWidget(label(f"{m['recorded_date']}  ·  { {'self':'자기평가','measured':'측정 기록','document':'문서·결과물'}[m['evidence_kind']] }  ·  {m['source']}","muted",True));layout.addWidget(card)

    def page_goals(self,layout):
        self.heading(layout,"원하는 미래를, 확인 가능한 목표로.","결과물·수치·반복 목표를 나누고, 달성 여부를 직접 확인합니다.","GOALS & MILESTONES")
        search=QLineEdit(self.goal_search);search.setPlaceholderText("목표 이름 또는 완료 기준 검색…")
        search.returnPressed.connect(lambda:self.filter_search(search.text()))
        layout.addLayout(row(search,button("검색",lambda:self.filter_search(search.text())),button("＋ 새로운 목표",self.edit_goal,True)))
        goals=[g for g in self.filtered_goals() if not self.goal_search or self.goal_search.casefold() in (g["title"]+g["criteria"]).casefold()]
        if goals:self.goal_grid(layout,sorted(goals,key=lambda g:(g["status"]=="completed",-g["priority"],g["due_date"])))
        else:self.empty(layout,"표시할 목표가 없습니다","검색·분야 필터를 조정하거나 첫 목표를 등록하세요.")
        layout.addWidget(label("진행도는 목표 기준의 변화 또는 준비 과제 완료 비율입니다. 과제를 모두 마친 뒤에도 최종 달성은 별도로 확인하세요.","muted",True))

    def page_roadmap(self,layout):
        self.heading(layout,"목표에서 오늘까지, 이어지는 경로.","모든 분야의 시간과 습관을 함께 반영한 규칙 기반 초안을 검토하고 적용하세요.","GROWTH ROADMAP")
        scale=QComboBox();scale.addItems(["월간","주간","일간"]);scale.setCurrentText(self.roadmap_scale)
        scale.currentTextChanged.connect(self.set_roadmap_scale)
        layout.addLayout(row(scale,None,button("미완료 일정 재배치",lambda:self.plan(True)),button("✦ 로드맵 초안 만들기",lambda:self.plan(False),True)))
        ids={g["id"] for g in self.filtered_goals()}
        tasks=[t for t in self.tasks if t["goal_id"] in ids]
        summary,sl=panel();sl.addWidget(label(f"주당 순가용 {self.profile['weekly_hours']:g}시간 · 현재 실행 과제 {len(tasks)}개 · 다음 28일 계획","sectionTitle",True));sl.addWidget(label("예상 시간은 수정 가능한 초안입니다. 장기 목표는 중간 성과부터 정하고 가까운 기간의 과제를 구체화합니다.","muted",True));layout.addWidget(summary)
        groups=defaultdict(list)
        for t in sorted(tasks,key=lambda t:t.get("scheduled_date") or "9999"):
            value=t.get("scheduled_date")
            if not value:key="일정 미배정"
            else:
                d=date.fromisoformat(value)
                if self.roadmap_scale=="월간":key=f"{d:%Y년 %m월}"
                elif self.roadmap_scale=="주간":key=f"{(d-timedelta(days=d.weekday())):%Y.%m.%d} 시작 주"
                else:key=f"{d:%Y.%m.%d}"
            groups[key].append(t)
        if not tasks:self.empty(layout,"목표를 실행 단계로 나눠 보세요","목표와 프로필을 입력한 뒤 로드맵 초안을 생성하세요. 생성 결과를 확인한 다음 적용할 수 있습니다.")
        for name,items in groups.items():
            self.section(layout,name)
            for t in sorted(items,key=lambda t:(t.get("scheduled_date") or "9999",t.get("position",0))):layout.addWidget(self.task_row(t))

    def page_today(self,layout):
        self.heading(layout,"오늘의 작은 실행이, 다음 변화를 만듭니다.","예정 과제와 반복 습관을 확인하고 실제 수행 시간을 기록하세요.","DAILY PRACTICE")
        editor=QDateEdit(QDate(self.execution_date.year,self.execution_date.month,self.execution_date.day));editor.setCalendarPopup(True);editor.setDisplayFormat("yyyy-MM-dd")
        editor.dateChanged.connect(self.set_execution_date)
        layout.addLayout(row(editor,button("오늘",lambda:self.set_execution_date(QDate.currentDate())),None,button("＋ 습관",self.edit_habit),button("＋ 실행 과제",self.edit_task,True)))
        ds=self.execution_date.isoformat();ids={g["id"] for g in self.filtered_goals()}
        items=[t for t in self.tasks if t["goal_id"] in ids and t.get("scheduled_date")==ds]
        self.section(layout,f"실행 과제  ·  {sum(t['done'] for t in items)} / {len(items)} 완료")
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
            checked=QCheckBox(h["title"]);checked.setChecked(ds in h["completions"]);checked.setEnabled(scheduled and self.execution_date<=date.today())
            checked.toggled.connect(lambda _done,i=h["id"],d=ds:self.toggle_habit(i,d))
            cl.addLayout(row(checked,None,pill(f"{engine.habit_streak(h)}회 연속","#e5bd67"),button("수정",lambda habit=h:self.edit_habit(habit),ghost=True)))
            days=" · ".join("월화수목금토일"[i] for i in h["weekdays"])
            cl.addWidget(label(f"{days}  /  {h['minutes']}분 · "+("수행 예정일" if scheduled else "쉬는 날"),"muted"));layout.addWidget(card)
        if not self.habits:self.empty(layout,"꾸준함을 위한 작은 약속","반복할 요일과 필요한 시간을 정해 습관을 등록하세요.")

    def page_analysis(self,layout):
        self.heading(layout,"기록을 돌아보고, 다음 방향을 조정하세요.","실행량과 목표 성과를 구분합니다. 이 화면의 수치는 저장된 기록을 기준으로 계산합니다.","REFLECTION & INSIGHTS")
        ids={g["id"] for g in self.filtered_goals()};tasks=[t for t in self.tasks if t["goal_id"] in ids]
        w,l=panel();l.addLayout(row(label("최근 7일 · 계획과 실행","sectionTitle"),None,label("과제 수 · 연보라 완료 / 회보라 계획","muted")));l.addWidget(ActivityChart(engine.activity_series(tasks)));layout.addWidget(w)
        self.section(layout,"분야별 목표 진행도")
        grid=QGridLayout();grid.setSpacing(14)
        for i,(key,c) in enumerate(CATEGORIES.items()):
            if self.category!="all" and key!=self.category:continue
            goals=[g for g in self.goals if g["category"]==key];p=sum(engine.progress(g,self.tasks) for g in goals)/len(goals) if goals else 0
            card,cl=panel();cl.addLayout(row(pill(c["name"],c["color"]),None,label(f"{p:.0%}" if goals else "목표 없음")));cl.addWidget(progress_bar(p,c["color"]));cl.addWidget(label(f"목표 {len(goals)}개 · 동일 가중 평균 · 역량 평가 점수 아님","muted",True));grid.addWidget(card,i//2,i%2)
        layout.addLayout(grid)
        self.section(layout,"나의 회고",button("＋ 회고 쓰기",self.add_review,ghost=True))
        reviews=self.store.reviews()
        for r in sorted(reviews,key=lambda r:r["date"],reverse=True)[:6]:
            card,cl=panel();cl.addWidget(label(r["date"],"eyebrow"))
            for title,key in [("잘한 점","good"),("어려웠던 점","challenge"),("다음 행동","next_action")]:
                if r.get(key):cl.addWidget(label(f"{title}  ·  {r[key]}",wrap=True))
            layout.addWidget(card)
        if not reviews:self.empty(layout,"이번 실행에서 무엇을 배웠나요?","잘한 점, 어려웠던 점, 다음에 바꿀 행동을 기록하세요.")
        history=self.store.history()
        if history:
            self.section(layout,"최근 계획 변경")
            for h in history[:5]:layout.addWidget(label(f"{h['created_at'][:16]}  ·  {h['summary']}","muted",True))

    def page_coach(self,layout):
        self.heading(layout,"기록에 근거한 제안, 선택은 당신에게.","현재 버전은 규칙 기반 코치입니다. 외부 생성형 AI와 자동 자료 검색은 연결하지 않았습니다.","COACHING ROOM")
        layout.addLayout(row(pill("규칙 기반 코치","#82c5a3"),pill("외부 AI 미연결","#e5bd67"),None))
        for insight in engine.insights(self.profile,self.goals,self.tasks,self.metrics,self.habits):
            card,cl=panel();cl.addWidget(label(insight["title"],"sectionTitle",True));cl.addWidget(label(insight["body"],"muted",True));layout.addWidget(card)
        actions,al=panel();al.addWidget(label("추천을 다음 계획으로 연결하기","sectionTitle"));al.addWidget(label("기존 완료 기록을 남기고, 현재 가용 시간 안에서 미완료 과제의 새 일정을 미리 확인합니다.","muted",True));al.addWidget(button("계획 수정안 보기",lambda:self.plan(True),True),0,Qt.AlignmentFlag.AlignLeft);layout.addWidget(actions)
        external,el=panel();el.addWidget(label("외부 상담과 자료 확인","sectionTitle"));el.addWidget(label("목표·실행 현황을 요약해 복사하거나 브라우저에서 자료를 직접 확인할 수 있습니다. 검색 결과를 검증된 근거로 자동 등록하지 않습니다.","muted",True))
        self.include_profile=QCheckBox("상담 요약에 프로필·자산 수치도 포함");el.addWidget(self.include_profile)
        search=QLineEdit();search.setPlaceholderText("직무·시험명 등 확인할 자료 입력")
        el.addLayout(row(button("상담용 요약 복사",self.copy_coaching),search,button("브라우저 검색 ↗",lambda:self.open_search(search.text()))));layout.addWidget(external)

    def page_settings(self,layout):
        self.heading(layout,"나의 데이터, 나의 작업 공간.","기록을 백업하고 다른 PC에서 복원하세요. 백업 복원은 현재 데이터를 교체합니다.","PREFERENCES")
        w,l=panel();l.addWidget(label("화면과 알림","sectionTitle"))
        light=QCheckBox("밝은 테마 사용");light.setChecked(self.preferences.value("light",False,type=bool));light.toggled.connect(self.set_light);l.addWidget(light)
        notifications=QCheckBox("앱 실행 중 오늘의 미완료 과제 알림");notifications.setChecked(self.preferences.value("notifications",False,type=bool));notifications.toggled.connect(lambda v:self.preferences.setValue("notifications",v));l.addWidget(notifications)
        l.addWidget(label("알림은 앱 실행 중에만 확인합니다. 완전 종료·절전 상태에서는 동작하지 않습니다.","muted",True));layout.addWidget(w)
        b,bl=panel();bl.addWidget(label("백업 · 다른 PC로 이동","sectionTitle"));bl.addWidget(label("DB와 첨부 파일을 .pgmbackup 파일로 내보냅니다. 백업은 암호화되지 않으므로 보관 위치를 직접 관리하세요. 복원 전 현재 데이터의 자동 백업을 생성합니다.","muted",True));bl.addLayout(row(button("백업 내보내기",self.export_backup,True),button("백업에서 복원",self.restore_backup),None));layout.addWidget(b)
        info,il=panel();il.addWidget(label("저장 위치와 프로토타입 범위","sectionTitle"));il.addWidget(label(str(self.store.data_dir),"muted",True));il.addWidget(label("SQLite 로컬 저장 · 별도 운영 서버 없음 · 외부 AI/API 키 미설정 · 기기 간 자동 병합 없음",wrap=True));il.addWidget(button("데이터 폴더 열기 ↗",lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.data_dir)))),0,Qt.AlignmentFlag.AlignLeft);layout.addWidget(info)
        if not self.goals:
            self.empty(layout,"실제 입력 전에 살펴보기","빈 작업 공간에만 가상 예시를 불러옵니다. 실제 사용은 별도 데이터 폴더에서 시작할 수 있습니다.",button("가상 예시 불러오기",self.load_demo))

    def edit_goal(self,goal=None):
        dialog=GoalDialog(goal,self)
        if goal:dialog.form.addRow(button("이 목표와 연결 과제 삭제",lambda:self.delete_record("goal",goal["id"],dialog)))
        if dialog.exec()==QDialog.DialogCode.Accepted:
            def action():
                self.store.save_goal(dialog.values());self.refresh()
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

    def set_roadmap_scale(self,value):
        self.roadmap_scale=value;self.refresh()

    def open_roadmap(self,goal):
        self.page_key="roadmap";self.category=goal["category"]
        self.category_combo.blockSignals(True);self.category_combo.setCurrentIndex(self.category_combo.findData(self.category));self.category_combo.blockSignals(False);self.refresh()

    def plan(self,replan=False):
        self.snapshot()
        if not self.goals:
            QMessageBox.information(self,"목표가 필요합니다","프로필과 첫 목표를 입력한 뒤 로드맵을 생성하세요.");return
        try:
            result=(engine.replan(self.tasks,self.goals,self.profile,self.habits) if replan else engine.build_plan(self.goals,self.tasks,self.profile,self.habits))
        except ValueError as exc:
            QMessageBox.warning(self,"계획 조건을 확인하세요",str(exc));return
        dialog=QDialog(self);dialog.setWindowTitle("계획 수정안" if replan else "로드맵 초안");dialog.resize(820,650)
        l=QVBoxLayout(dialog);l.setContentsMargins(24,24,24,24);l.setSpacing(14)
        l.addWidget(label("적용 전에 계획을 확인하세요","sectionTitle"));l.addWidget(label(result["summary"],"muted",True))
        if result["warnings"]:
            warnings=QTextEdit();warnings.setReadOnly(True);warnings.setPlainText("\n".join("• "+s for s in result["warnings"]));warnings.setMaximumHeight(135);l.addWidget(warnings)
        entries=result["tasks"]
        table=QTableWidget(len(entries),4);table.setHorizontalHeaderLabels(["실행 과제","일정","예상 시간","단계"])
        for i,t in enumerate(entries):
            for j,text in enumerate([t["title"],t.get("scheduled_date") or "배치 불가",f"{t['minutes']}분",t.get("stage","")]):table.setItem(i,j,QTableWidgetItem(str(text)))
        table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);table.verticalHeader().setVisible(False);l.addWidget(table,1)
        l.addWidget(label("규칙 기반 초안 · 예상 시간과 선행 학습은 목표에 맞춰 직접 수정할 수 있습니다. 완료 기록은 유지됩니다.","muted",True))
        cancel=button("취소",dialog.reject);apply=button(f"{len(entries)}개 변경 적용" if replan else f"{len(entries)}개 과제 추가",dialog.accept,True);apply.setEnabled(bool(entries));l.addLayout(row(None,cancel,apply))
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
        if self.include_profile.isChecked():data["profile"]=self.profile
        prompt="다음은 내가 직접 기록한 목표와 실행 현황이다. 사실·해석·정보 부족을 구분하고, 가용 시간 안에서 실행 가능한 개선안을 제안해줘. 근거 없는 실력 점수·성공 확률·투자수익을 만들지 말아줘.\n\n"+json.dumps(data,ensure_ascii=False,indent=2)
        QApplication.clipboard().setText(prompt);self.statusBar().showMessage("상담용 요약을 복사했습니다. 외부 서비스에 붙여넣을 내용을 확인하세요.",7000)

    def open_search(self,text):
        if text.strip():QDesktopServices.openUrl(QUrl("https://www.google.com/search?q="+quote(text.strip())))

    def set_light(self,value):
        self.preferences.setValue("light",value);apply_theme(QApplication.instance(),value)

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
    window=MainWindow(store,args.demo);window.show()
    if args.screenshot or args.smoke_test:
        def capture():
            try:
                if args.smoke_test:
                    for key,_,_ in NAVIGATION:window.navigate(key);app.processEvents()
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
