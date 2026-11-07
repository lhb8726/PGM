"""Native charts for recorded task counts and goal distribution."""
from __future__ import annotations

import math

from PySide6.QtCore import QByteArray, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from .theme import theme_colors


def _font(widget, pixels, bold=False):
    font = QFont(widget.font())
    font.setPixelSize(pixels)
    font.setBold(bold)
    return font


class TrendChart(QWidget):
    """Connect the last seven supplied daily counts without smoothing the data."""

    def __init__(self, series, parent=None):
        super().__init__(parent)
        self.series = [dict(item) for item in series[-7:]]
        self.setMinimumSize(220, 190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setAccessibleName("최근 7일의 예정일별 과제 수와 현재 완료 상태")
        summary = " / ".join(
            f"예정일 {item['date']} · 예정 {item['planned']}개 중 현재 완료 {item['completed']}개"
            for item in self.series
        )
        self.setAccessibleDescription(summary or "아직 실행 기록이 없습니다.")

    def sizeHint(self):
        return QSize(460, 220)

    def _plot(self):
        maximum = max([item[key] for item in self.series for key in ("planned", "completed")] + [0])
        left = max(34, self.fontMetrics().horizontalAdvance(str(maximum)) + 16)
        return QRectF(left, 38, self.width() - left - 14, self.height() - 70)

    def _x(self, index, plot):
        if len(self.series) == 1:
            return plot.center().x()
        return plot.left() + plot.width() * index / max(1, len(self.series) - 1)

    def paintEvent(self, event):
        colors = theme_colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(_font(self, 11))
        plot = self._plot()
        for x, key, caption, style in (
            (plot.left(), "chart_completed", "완료", Qt.PenStyle.SolidLine),
            (plot.left() + 82, "chart_planned", "예정", Qt.PenStyle.DashLine),
        ):
            painter.setPen(QPen(QColor(colors[key]), 2, style))
            painter.drawLine(QPointF(x, 14), QPointF(x + 20, 14))
            painter.setPen(QColor(colors["muted"]))
            painter.drawText(QRectF(x + 27, 5, 44, 18), Qt.AlignmentFlag.AlignVCenter, caption)

        maximum = max([item[key] for item in self.series for key in ("planned", "completed")] + [0])
        step = max(1, math.ceil(maximum / 3))
        ceiling = max(1, math.ceil(maximum / step) * step)
        for tick in range(0, ceiling + 1, step):
            y = plot.bottom() - plot.height() * tick / ceiling
            painter.setPen(QPen(QColor(colors["chart_grid"]), 1))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(colors["muted"]))
            painter.drawText(QRectF(0, y - 9, plot.left() - 10, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(tick))

        if not self.series:
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "아직 실행 기록이 없습니다")
            return

        for key, color_key, style in (
            ("planned", "chart_planned", Qt.PenStyle.DashLine),
            ("completed", "chart_completed", Qt.PenStyle.SolidLine),
        ):
            points = [QPointF(self._x(index, plot), plot.bottom() - plot.height() * item[key] / ceiling)
                      for index, item in enumerate(self.series)]
            line = QPainterPath(points[0])
            for point in points[1:]:
                line.lineTo(point)
            color = QColor(colors[color_key])
            if key == "completed":
                area = QPainterPath(line)
                area.lineTo(points[-1].x(), plot.bottom())
                area.lineTo(points[0].x(), plot.bottom())
                area.closeSubpath()
                gradient = QLinearGradient(plot.topLeft(), plot.bottomLeft())
                top_color, bottom_color = QColor(color), QColor(color)
                top_color.setAlpha(52)
                bottom_color.setAlpha(5)
                gradient.setColorAt(0, top_color)
                gradient.setColorAt(1, bottom_color)
                painter.fillPath(area, gradient)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(color, 2.3, style, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(line)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            radius = 3.5 if key == "completed" else 2.5
            for point in points:
                painter.drawEllipse(point, radius, radius)

        painter.setFont(_font(self, 11))
        painter.setPen(QColor(colors["muted"]))
        for index, item in enumerate(self.series):
            painter.drawText(QRectF(self._x(index, plot) - 16, plot.bottom() + 10, 32, 18),
                             Qt.AlignmentFlag.AlignCenter, str(item["label"]))

    def mouseMoveEvent(self, event):
        plot = self._plot()
        if self.series and plot.adjusted(-6, -6, 6, 6).contains(event.position()):
            index = min(range(len(self.series)), key=lambda i: abs(self._x(i, plot) - event.position().x()))
            item = self.series[index]
            QToolTip.showText(event.globalPosition().toPoint(),
                              f"예정일 {item['date']} ({item['label']})\n예정 {item['planned']}개 중 현재 완료 {item['completed']}개", self)
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)


class CategoryChart(QWidget):
    """Show goal counts by category, with the original entry names in its legend."""

    def __init__(self, entries, parent=None):
        super().__init__(parent)
        self.entries = [dict(entry) for entry in entries]
        self.total = sum(entry["value"] for entry in self.entries)
        self.setMinimumWidth(160)
        self.setMinimumHeight(174 + 25 * len(self.entries))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setAccessibleName("분야별 목표 개수")
        self.setAccessibleDescription(
            f"합계 {self.total}개. " + " / ".join(f"{entry['name']} {entry['value']}개" for entry in self.entries)
        )

    def sizeHint(self):
        return QSize(240, self.minimumHeight())

    def paintEvent(self, event):
        colors = theme_colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        diameter = min(self.width() - 40, 140)
        ring = QRectF((self.width() - diameter) / 2, 14, diameter, diameter)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(colors["chart_grid"]), 14))
        painter.drawEllipse(ring)
        if self.total:
            start = 90 * 16
            for entry in self.entries:
                span = round(360 * 16 * entry["value"] / self.total)
                painter.setPen(QPen(QColor(entry["color"]), 14, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
                painter.drawArc(ring, start, -span)
                start -= span
        painter.setPen(QColor(colors["text"]))
        painter.setFont(_font(self, 29, True))
        painter.drawText(ring.adjusted(0, -12, 0, -12), Qt.AlignmentFlag.AlignCenter, str(self.total))
        painter.setFont(_font(self, 11))
        painter.setPen(QColor(colors["muted"]))
        painter.drawText(ring.adjusted(0, 28, 0, 0), Qt.AlignmentFlag.AlignCenter, "등록한 목표")
        painter.setFont(_font(self, 12))
        for index, entry in enumerate(self.entries):
            y = 174 + index * 25
            painter.setBrush(QColor(entry["color"]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(8, y + 6, 7, 7))
            painter.setPen(QColor(colors["muted"]))
            count = f"{entry['value']}개"
            count_width = painter.fontMetrics().horizontalAdvance(count) + 8
            label_width = max(0, self.width() - count_width - 36)
            name = painter.fontMetrics().elidedText(str(entry["name"]), Qt.TextElideMode.ElideRight, label_width)
            painter.drawText(QRectF(24, y, label_width, 20), Qt.AlignmentFlag.AlignVCenter, name)
            painter.setPen(QColor(colors["text"]))
            painter.drawText(QRectF(self.width() - count_width - 8, y, count_width, 20),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, count)


def ui_icon(name, color, size=20):
    """Small shared outline icons rendered locally at high density."""
    paths = {
        "dashboard": "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
        "profile": "M16 7a4 4 0 1 1-8 0a4 4 0 1 1 8 0 M4 21v-2a8 8 0 0 1 16 0v2",
        "goals": "M21 12a9 9 0 1 1-9-9 M17 12a5 5 0 1 1-5-5 M12 12l9-9 M16 3h5v5",
        "roadmap": "M6 3v18 M18 3v18 M6 5h12 M6 12h12 M6 19h12",
        "today": "M5 5h14v16H5z M9 3h6v4H9z M8 13l3 3 5-6",
        "analysis": "M4 3v18h17 M8 16l4-5 4 2 5-7",
        "coach": "M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-8l-6 4v-4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2 M7 9h10 M7 13h6",
        "settings": "M9 3h6l1 4 4 1v8l-4 1-1 4H9l-1-4-4-1V8l4-1z M15 12a3 3 0 1 1-6 0a3 3 0 1 1 6 0",
    }
    if name not in paths:
        return QIcon()
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
           f'<path d="{paths[name]}" fill="none" stroke="{QColor(color).name()}" '
           'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter, QRectF(0, 0, size, size))
    painter.end()
    return QIcon(pixmap)
