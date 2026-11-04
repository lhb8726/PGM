"""Inspectable goal analysis, long-range milestones and actionable next steps."""
from __future__ import annotations

from datetime import date, timedelta
from html import escape
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QHeaderView, QMessageBox, QPushButton,
    QScrollArea, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .analysis import report_markdown
from .dialogs import _fit_to_screen
from .widgets import label, panel, pill


STATUS_LABELS = {"needs_input": "추가 정보 필요", "conditional": "조건부 계획", "at_risk": "조건 조정 필요", "completed": "완료 확인", "on_track": "입력 조건 검토"}


def _scroll():
    area = QScrollArea();area.setWidgetResizable(True)
    body = QWidget();layout = QVBoxLayout(body);layout.setContentsMargins(16,20,16,20);layout.setSpacing(16)
    area.setWidget(body)
    return area,layout


def wrapped_table(headers, rows, *, compact_columns=(), minimum_height_cap=470):
    table = QTableWidget(len(rows), len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setWordWrap(True)
    table.setTextElideMode(Qt.TextElideMode.ElideNone)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
    table.verticalHeader().setVisible(False)
    header = table.horizontalHeader()
    header.ensurePolished()
    header.setMinimumSectionSize(max((header.sectionSizeHint(column) for column in range(len(headers))), default=0))
    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    for column in compact_columns:
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
    for i,values in enumerate(rows):
        for j,value in enumerate(values):
            text = str(value)
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            item.setToolTip("<qt>" + escape(text).replace("\n", "<br>") + "</qt>")
            table.setItem(i, j, item)
    def fit_rows():
        table.resizeRowsToContents()
        height = header.height() + table.verticalHeader().length() + 10
        table.setMinimumHeight(min(minimum_height_cap, max(150, height)))

    # Resize after the layout assigns column widths and when the window changes.
    reflow = QTimer(table)
    reflow.setSingleShot(True)
    reflow.timeout.connect(fit_rows)
    header.sectionResized.connect(lambda *_: reflow.start(0))
    reflow.start(0)
    return table


class GoalAnalysisDialog(QDialog):
    """Accept=apply preview, 2=edit goal; calculations never modify records."""
    def __init__(self,report,plan,parent=None):
        super().__init__(parent)
        self.report=report;self.plan=plan
        self.setWindowTitle("목표 분석 · 상세 성장 로드맵")
        self.setMinimumSize(560,420);self.resize(1060,850)
        layout=QVBoxLayout(self);layout.setContentsMargins(25,24,25,20);layout.setSpacing(13)
        layout.addWidget(label(report["title"],"sectionTitle",True))
        tags=QHBoxLayout();tags.addWidget(pill(STATUS_LABELS.get(report.get("status"),"조건 확인")))
        tags.addWidget(pill("규칙 기반 분석 · 외부 AI 미연결","#82c5a3"));tags.addStretch()
        tags.addWidget(label(f"분석 기준 {report.get('generated_on','')}","muted"));layout.addLayout(tags)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        area,body=_scroll();self.tabs.addTab(area,"진단·시나리오")
        body.addWidget(label(report.get("summary",""),wrap=True))
        self._list(body,"입력된 사실·기록",report.get("facts",[]))
        if report.get("missing"):self._list(body,"먼저 확인할 정보",report["missing"],"#e5bd67")
        if report.get("warnings"):self._list(body,"제약·위험·조건 조정",report["warnings"],"#df9ab1")
        scenarios=report.get("scenarios",[])
        if scenarios:
            body.addWidget(label("조건을 바꾸면 달라지는 결과","sectionTitle"))
            body.addWidget(wrapped_table(["시나리오","조건상 결과","필요 조건","계산 가정·해석"],[[s.get("name",""),s.get("result",""),s.get("requirement",""),s.get("note","")] for s in scenarios]))
        finance=report.get("finance",{})
        comparison=finance.get("comparison",{})
        if comparison:
            body.addWidget(label("평가액 목표와 세후 현금 목표 비교","sectionTitle"))
            rows=[]
            for key,title in [("account_value","계좌 평가액 목표"),("after_tax_cash","세후 현금 목표")]:
                item=comparison.get(key) or {}
                def money(v):return "정보 부족" if v is None else f"{v:,.0f}원"
                value=item.get("required_return")
                rows.append([title,money(item.get("required_gross")),money(item.get("tax_at_target")),money(item.get("net_at_target")),"계산 불가·정보 부족" if value is None else f"{value:.2%}"])
            body.addWidget(wrapped_table(["목표 기준","필요 평가액","계산상 최종 세금","세후 현금","필요 연복리"],rows))
            body.addWidget(label("단일 과세 가정의 예시입니다. 세무 원가·과세 조건을 확인하지 않으면 세후 숫자를 만들지 않습니다. 세율은 미래의 확정 세법을 뜻하지 않습니다.","muted",True))
        self._list(body,"계산 가정·제안의 범위",report.get("assumptions",[]));body.addStretch()
        area,body=_scroll();self.tabs.addTab(area,"단계별 로드맵")
        anchor=date.fromisoformat(report.get("anchor_on") or report["generated_on"])
        body.addWidget(label("단계 기간은 목표 생성일 기준의 가이드입니다. 가까운 기간의 실행 과제는 현재 기록과 남은 시간으로 다시 배치합니다.","muted",True))
        for index,phase in enumerate(report.get("phases",[]),1):
            card,cl=panel();head=QHBoxLayout();head.addWidget(pill(f"{index:02d}"));head.addWidget(label(phase["title"],"sectionTitle",True));head.addStretch();cl.addLayout(head)
            start=anchor+timedelta(days=int(phase.get("start_day",0)));end=anchor+timedelta(days=int(phase.get("end_day",0)))
            cl.addWidget(label(f"{phase.get('period','')}  ·  {start:%Y.%m.%d} ~ {end:%Y.%m.%d}","muted",True))
            cl.addWidget(label(phase.get("objective",""),wrap=True))
            for action in phase.get("actions",[]):
                cl.addWidget(label("• "+action["title"],wrap=True))
                cl.addWidget(label(f"완료 기준  {action.get('done_when','')}\n이유  {action.get('why','')}\n초기 예상 작업량  {action['minutes']}분","muted",True))
            body.addWidget(card)
        self._list(body,"점검·계획 수정 기준",report.get("checkpoints",[]))
        milestones=finance.get("milestones",[])
        if milestones:
            body.addWidget(label("가정에 따른 자산 점검표","sectionTitle"))
            body.addWidget(label("실제 성과 예측이 아닌 고정 수익률·납입액 계산입니다. 각 시점의 세후 금액은 독립적인 전량 청산 비교이며 매번 매도·재투자하는 경로가 아닙니다.","muted",True))
            body.addWidget(wrapped_table(["기준일","경과 개월","평가액","세후 금액","연복리 가정"],[[m.get("date",""),m.get("month",""),f"{m['gross']:,.0f}원" if m.get("gross") is not None else "정보 부족",f"{m['net']:,.0f}원" if m.get("net") is not None else "정보 부족",f"{m['rate']:.0%}" if m.get("rate") is not None else "미입력"] for m in milestones]))
        body.addStretch()
        area,body=_scroll();self.tabs.addTab(area,"가까운 실행 계획")
        body.addWidget(label(plan.get("summary",""),"muted",True))
        self._list(body,"배치 조건·추가 확인",plan.get("warnings",[]),"#e5bd67")
        tasks=plan.get("tasks",[])
        if tasks:
            body.addWidget(wrapped_table(["예정 날짜","실행 과제","초기 예상","완료 기준"],[[t.get("scheduled_date") or "미배정",t["title"],f"{t['minutes']}분",t.get("done_when","")] for t in tasks],compact_columns=(0,2)))
        else:
            body.addWidget(label("추가할 실행 과제가 없습니다. 기존 미완료 과제, 단계 시작일, 기한과 가용 시간을 확인하세요.","muted",True))
        body.addWidget(label("적용하면 위 과제만 추가합니다. 완료 기록과 기존 과제는 보존합니다. 금액 시나리오가 계산됐다는 사실만으로 그 현금흐름이나 수익률이 확보된 것은 아닙니다.","muted",True));body.addStretch()
        area,body=_scroll();self.tabs.addTab(area,"근거·자료")
        body.addWidget(label("아래는 저장된 참고 자료입니다. 앱이 열릴 때마다 인터넷에서 최신 내용을 자동 검증하는 기능은 아직 연결되지 않았습니다.","muted",True))
        for source in report.get("sources",[]):
            url=source.get("url","")
            card,cl=panel();cl.addWidget(label(source.get("title","참고 자료"),"sectionTitle",True));cl.addWidget(label(url,"muted",True));cl.addWidget(label("자료 확인일: "+(source.get("checked_on") or "사용자 제공·미검증"),"muted"))
            if url.startswith(("https://","http://")):
                b=QPushButton("자료 열기 ↗");b.clicked.connect(lambda _=False,u=url:QDesktopServices.openUrl(QUrl(u)));cl.addWidget(b)
            body.addWidget(card)
        if not report.get("sources"):body.addWidget(label("등록된 근거 링크가 없습니다. 공식 기준이나 평가 자료를 목표에 추가해 주세요.","muted",True))
        body.addStretch()
        footer=QHBoxLayout()
        export=QPushButton("보고서 저장");export.clicked.connect(self.export);footer.addWidget(export)
        edit=QPushButton("목표·분석 조건 수정");edit.clicked.connect(lambda:self.done(2));footer.addWidget(edit);footer.addStretch()
        close=QPushButton("닫기");close.clicked.connect(self.reject);footer.addWidget(close)
        self.apply_button=QPushButton(f"실행 과제 {len(tasks)}개 추가");self.apply_button.setObjectName("primary");self.apply_button.setEnabled(bool(tasks));self.apply_button.clicked.connect(self.accept);footer.addWidget(self.apply_button)
        layout.addLayout(footer)

    def showEvent(self, event):
        _fit_to_screen(self)
        super().showEvent(event)

    @staticmethod
    def _list(layout,title,items,color=None):
        if not items:return
        card,cl=panel();heading=label(title,"sectionTitle")
        if color:heading.setStyleSheet(f"color:{color}")
        cl.addWidget(heading)
        for text in items:cl.addWidget(label("• "+str(text),"muted",True))
        layout.addWidget(card)

    def export(self):
        path,_=QFileDialog.getSaveFileName(self,"목표 분석 보고서 저장","PGM-목표분석.md","Markdown (*.md)")
        if not path:return
        try:
            Path(path).write_text(report_markdown(self.report),encoding="utf-8")
        except OSError as exc:QMessageBox.warning(self,"보고서를 저장하지 못했습니다",str(exc))
