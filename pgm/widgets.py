"""Small native Qt visual components; all charts display stored records."""

import re

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPalette
from PySide6.QtWidgets import QBoxLayout, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .theme import theme_colors


_SOFT_BREAK = "\u200b"
_LONG_TOKEN = re.compile(r"[^\s\u200b]{17,}")


def _break_token(match):
    token = match.group()
    return _SOFT_BREAK.join(token[index:index + 16] for index in range(0, len(token), 16))


class WrappingLabel(QLabel):
    """Give unusually long tokens break points while keeping the original text."""

    def __init__(self, text):
        super().__init__()
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setText(text)

    def setText(self, text):
        self._original_text = text
        display = _LONG_TOKEN.sub(_break_token, text)
        super().setText(display)
        self.setAccessibleName(text if display != text else "")

    def text(self):
        return self._original_text


def label(text, name=None, wrap=False):
    w = WrappingLabel(str(text)) if wrap else QLabel(str(text))
    w.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        w.setObjectName(name)
    return w


def panel(hero=False):
    w = QFrame()
    w.setObjectName("hero" if hero else "card")
    layout = QVBoxLayout(w)
    layout.setContentsMargins(21,19,21,19)
    layout.setSpacing(12)
    return w,layout


class ResponsiveColumns(QWidget):
    def __init__(self, left, right, *, spacing=22, stretch=(3, 2)):
        super().__init__()
        self.columns = left, right
        self.column_stretch = stretch
        self.arrangement = QBoxLayout(QBoxLayout.Direction.TopToBottom, self)
        self.arrangement.setContentsMargins(0, 0, 0, 0)
        self.arrangement.setSpacing(spacing)
        self.arrangement.addLayout(left)
        self.arrangement.addLayout(right)

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        hint.setWidth(max(column.minimumSize().width() for column in self.columns))
        return hint

    def resizeEvent(self, event):
        super().resizeEvent(event)
        required = sum(column.minimumSize().width() for column in self.columns) + self.arrangement.spacing()
        wide = event.size().width() >= required
        direction = QBoxLayout.Direction.LeftToRight if wide else QBoxLayout.Direction.TopToBottom
        if direction != self.arrangement.direction():
            self.arrangement.setDirection(direction)
            for index, stretch in enumerate(self.column_stretch):
                self.arrangement.setStretch(index, stretch if wide else 0)


class CheckBoxLabel(WrappingLabel):
    def __init__(self, text, checkbox):
        super().__init__(text)
        self.checkbox = checkbox
        if checkbox.isEnabled():
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.checkbox.isEnabled():
            self.checkbox.click()
            event.accept()
        else:
            super().mouseReleaseEvent(event)


def pill(text,color="#b69af7"):
    w = label(text)
    w.setProperty("accentColor", color)
    _style_accent(w)
    w.setFixedHeight(27)
    return w


def _style_accent(widget):
    foreground, background = _accent_colors(widget.property("accentColor"))
    decoration = ("border-radius:11px; font-size:16px; font-weight:650; padding:0;"
                  if widget.objectName() == "statIcon"
                  else "border-radius:8px; padding:4px 9px; font-size:11px; font-weight:600;")
    widget.setStyleSheet(f"color:{foreground}; background:{background}; border:none; {decoration}")


def refresh_accents(root):
    for widget in root.findChildren(QLabel):
        if widget.property("accentColor"):
            _style_accent(widget)


def _accent_colors(value):
    color = QColor(value)
    light = QColor(theme_colors()["bg"]).lightness() > 128
    foreground = color.darker(180) if light else color.lighter(160)
    red, green, blue, _ = color.getRgb()
    background = f"rgba({red},{green},{blue},{28 if light else 42})"
    return foreground.name(), background


class Ring(QWidget):
    def __init__(self,value=0,caption="목표 진행도",color="#b69af7",parent=None):
        super().__init__(parent)
        self.value=max(0,min(1,value))
        self.caption=caption
        self.color=color
        self.setFixedSize(112,126)
        self.setAccessibleName(f"{caption} {self.value:.0%}")

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(13,5,86,86)
        p.setPen(QPen(self.palette().color(QPalette.ColorRole.Midlight),7))
        p.drawArc(rect,0,360*16)
        accent = self.palette().color(QPalette.ColorRole.Highlight)
        if self.color != "#b69af7":
            accent = QColor(_accent_colors(self.color)[0])
        pen=QPen(accent,7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(rect,90*16,-round(360*16*self.value))
        p.setPen(self.palette().windowText().color())
        font=QFont(self.font());font.setPixelSize(25);font.setBold(True)
        p.setFont(font)
        p.drawText(rect,Qt.AlignmentFlag.AlignCenter,f"{self.value:.0%}")
        font.setPixelSize(11);font.setBold(False);p.setFont(font)
        p.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
        p.drawText(QRectF(0,99,112,24),Qt.AlignmentFlag.AlignCenter,self.caption)


class ActivityChart(QWidget):
    def __init__(self,series,parent=None):
        super().__init__(parent)
        self.series=series
        self.setMinimumHeight(170)
        self.setMinimumWidth(220)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w=self.width();h=self.height();top=20;bottom=h-30
        maxval=max([x.get("planned",0) for x in self.series]+[x.get("completed",0) for x in self.series]+[1])
        font = QFont(self.font())
        font.setPixelSize(11)
        p.setFont(font)
        left=max(29,p.fontMetrics().horizontalAdvance(str(maxval))+12)
        grid = self.palette().color(QPalette.ColorRole.Mid)
        muted = self.palette().color(QPalette.ColorRole.PlaceholderText)
        planned = self.palette().color(QPalette.ColorRole.Midlight)
        completed = self.palette().color(QPalette.ColorRole.Highlight)
        for tick in sorted({0, round(maxval / 2), maxval}):
            y=bottom-(bottom-top)*tick/maxval
            p.setPen(QPen(grid,.8))
            p.drawLine(left,int(y),w-8,int(y))
            p.setPen(muted)
            p.drawText(0,int(y)-8,left-8,16,Qt.AlignmentFlag.AlignRight,str(tick))
        n=max(1,len(self.series));slot=(w-left-12)/n;bar=min(19,slot*.28)
        for i,item in enumerate(self.series):
            x=left+slot*(i+.5)
            for off,key,color in [(-bar-2,"planned",planned),(2,"completed",completed)]:
                height=(bottom-top)*item.get(key,0)/maxval
                if height > 0:
                    p.setPen(Qt.PenStyle.NoPen);p.setBrush(color)
                    p.drawRoundedRect(QRectF(x+off,bottom-height,bar,max(2,height)),3,3)
            p.setPen(muted)
            p.drawText(QRectF(x-slot/2,bottom+7,slot,20),Qt.AlignmentFlag.AlignCenter,str(item.get("label","")))


def stat_card(title,value,detail,color="#b69af7",icon="◈"):
    w,layout=panel()
    w.setObjectName("statCard")
    layout.setContentsMargins(18,17,18,17)
    layout.setSpacing(10)
    badge = label(icon, "statIcon")
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setFixedSize(34,34)
    badge.setProperty("accentColor", color)
    _style_accent(badge)
    top=QHBoxLayout()
    top.setSpacing(10)
    top.addWidget(label(title,"muted",True),1)
    top.addWidget(badge)
    layout.addLayout(top)
    layout.addWidget(label(value,"statValue",True))
    layout.addWidget(label(detail,"muted",True))
    return w
