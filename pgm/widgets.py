"""Small native Qt visual components; all charts display stored records."""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


def label(text, name=None, wrap=False):
    w = QLabel(str(text))
    w.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        w.setObjectName(name)
    w.setWordWrap(wrap)
    return w


def panel(hero=False):
    w = QFrame()
    w.setObjectName("hero" if hero else "card")
    layout = QVBoxLayout(w)
    layout.setContentsMargins(21,19,21,19)
    layout.setSpacing(12)
    return w,layout


def pill(text,color="#b69af7"):
    w = label(text)
    r,g,b,_=QColor(color).getRgb()
    w.setStyleSheet(f"color:{color}; background:rgba({r},{g},{b},20); border:1px solid rgba({r},{g},{b},48); border-radius:8px; padding:4px 8px; font-size:10px;")
    w.setFixedHeight(25)
    return w


class Ring(QWidget):
    def __init__(self,value=0,caption="목표 진행도",color="#b69af7",parent=None):
        super().__init__(parent)
        self.value=max(0,min(1,value))
        self.caption=caption
        self.color=color
        self.setFixedSize(112,126)

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(13,5,86,86)
        p.setPen(QPen(QColor("#343a4c"),7))
        p.drawArc(rect,0,360*16)
        pen=QPen(QColor(self.color),7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(rect,90*16,-round(360*16*self.value))
        p.setPen(self.palette().windowText().color())
        font=QFont(self.font());font.setPixelSize(23);font.setBold(True)
        p.setFont(font)
        p.drawText(rect,Qt.AlignmentFlag.AlignCenter,f"{self.value:.0%}")
        font.setPixelSize(10);font.setBold(False);p.setFont(font)
        p.setPen(QColor("#9ca7bb"))
        p.drawText(QRectF(0,99,112,24),Qt.AlignmentFlag.AlignCenter,self.caption)


class ActivityChart(QWidget):
    def __init__(self,series,parent=None):
        super().__init__(parent)
        self.series=series
        self.setMinimumHeight(170)
        self.setMinimumWidth(220)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w=self.width();h=self.height();left=29;top=20;bottom=h-30
        maxval=max([x.get("planned",0) for x in self.series]+[x.get("completed",0) for x in self.series]+[1])
        p.setFont(QFont(self.font().family(),9))
        for frac in [0,.5,1]:
            y=bottom-(bottom-top)*frac
            p.setPen(QPen(QColor("#343b4b"),.6))
            p.drawLine(left,int(y),w-8,int(y))
            p.setPen(QColor("#9ca7bb"));p.drawText(0,int(y)-7,25,15,Qt.AlignmentFlag.AlignRight,str(round(maxval*frac)))
        n=max(1,len(self.series));slot=(w-left-12)/n;bar=min(19,slot*.28)
        for i,item in enumerate(self.series):
            x=left+slot*(i+.5)
            for off,key,color in [(-bar-2,"planned","#42415e"),(2,"completed","#b69af7")]:
                height=(bottom-top)*item.get(key,0)/maxval
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(color))
                p.drawRoundedRect(QRectF(x+off,bottom-height,bar,max(2,height)),3,3)
            p.setPen(QColor("#9ca7bb"))
            p.drawText(QRectF(x-slot/2,bottom+7,slot,20),Qt.AlignmentFlag.AlignCenter,str(item.get("label","")))


def stat_card(title,value,detail,color="#b69af7",icon="◈"):
    w,layout=panel()
    top=QHBoxLayout();top.addWidget(label(title,"muted"));top.addStretch();top.addWidget(pill(icon,color))
    layout.addLayout(top);layout.addWidget(label(value,"statValue"));layout.addWidget(label(detail,"muted",True))
    return w
