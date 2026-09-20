from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import QWidget


class SwingChart(QWidget):
    """PUMA 공용 캔들 차트.

    v0.6: 마우스 휠 확대/축소, 좌우 드래그 과거 탐색, 선택 분석구간 강조,
    일봉/분봉 공용 표시를 지원한다.
    """

    viewportChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.series = None
        self.analysis = None
        self.title = ''
        self.view_bars = 130
        self.view_end: int | None = None  # exclusive index
        self.analysis_range: tuple[int, int] | None = None
        self._drag_x = None
        self._drag_end = None
        self.setMinimumHeight(430)
        self.setMouseTracking(True)

    def set_data(self, analysis, series, title: str = '', preserve_view: bool = False):
        old_end = self.view_end
        self.analysis = analysis
        self.series = series
        self.title = title or self.title
        n = len(series.get('candles', [])) if series else 0
        if not preserve_view or old_end is None:
            self.view_end = n
        else:
            self.view_end = min(max(1, old_end), n)
        self.view_bars = min(max(25, self.view_bars), max(25, n)) if n else 130
        self.update()
        self._emit_viewport()

    def set_basic_data(self, candles: list[dict], lines: dict | None = None, title: str = '', preserve_view: bool = False):
        lines = lines or {}
        series = {
            'candles': candles,
            'acc_flags': [False] * len(candles),
            'box': None,
            **lines,
        }
        self.set_data(None, series, title=title, preserve_view=preserve_view)

    def set_analysis_range(self, start_idx: int | None, end_idx: int | None):
        if start_idx is None or end_idx is None:
            self.analysis_range = None
        else:
            a, b = sorted((int(start_idx), int(end_idx)))
            self.analysis_range = (a, b)
        self.update()

    def clear_analysis_range(self):
        self.analysis_range = None
        self.update()

    def show_latest(self):
        if self.series:
            self.view_end = len(self.series.get('candles', []))
            self.update(); self._emit_viewport()

    def show_all(self):
        if self.series:
            n = len(self.series.get('candles', []))
            self.view_bars = max(25, n)
            self.view_end = n
            self.update(); self._emit_viewport()

    def pan_bars(self, bars: int):
        if not self.series:
            return
        total = len(self.series.get('candles', []))
        if total <= 0:
            return
        end = self.view_end if self.view_end is not None else total
        min_end = min(total, max(1, min(self.view_bars, total)))
        self.view_end = max(min_end, min(total, end + int(bars)))
        self.update(); self._emit_viewport()

    def zoom_by(self, factor: float):
        if not self.series:
            return
        total = len(self.series.get('candles', []))
        if total <= 0:
            return
        new_n = int(round(self.view_bars * factor))
        self.view_bars = max(25, min(total, new_n))
        if self.view_end is None:
            self.view_end = total
        self.view_end = max(min(self.view_bars, total), min(total, self.view_end))
        self.update(); self._emit_viewport()

    def visible_index_range(self) -> tuple[int, int]:
        if not self.series:
            return (0, 0)
        total = len(self.series.get('candles', []))
        end = self.view_end if self.view_end is not None else total
        end = max(1, min(total, end))
        start = max(0, end - min(self.view_bars, total))
        return start, end

    def visible_range_text(self) -> str:
        if not self.series or not self.series.get('candles'):
            return '-'
        start, end = self.visible_index_range()
        cs = self.series['candles']
        if end <= start:
            return '-'
        return f"{self._date_label(cs[start].get('date',''))} ~ {self._date_label(cs[end-1].get('date',''))} · {end-start}봉 / 전체 {len(cs)}봉"

    def _emit_viewport(self):
        self.viewportChanged.emit(self.visible_range_text())

    @staticmethod
    def _date_label(raw) -> str:
        s = ''.join(ch for ch in str(raw or '') if ch.isdigit())
        try:
            if len(s) >= 14:
                return datetime.strptime(s[:14], '%Y%m%d%H%M%S').strftime('%y/%m/%d %H:%M')
            if len(s) >= 8:
                return datetime.strptime(s[:8], '%Y%m%d').strftime('%y/%m/%d')
        except Exception:
            pass
        return str(raw or '-')[:10]

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            self.zoom_by(0.80)
        else:
            self.zoom_by(1.25)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_x = event.position().x()
            self._drag_end = self.view_end
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_x is not None and self.series:
            total = len(self.series.get('candles', []))
            width = max(1.0, self.width() - 80.0)
            px_per_bar = width / max(1, min(self.view_bars, total))
            delta = event.position().x() - self._drag_x
            shift = int(round(delta / max(1.0, px_per_bar)))
            # 오른쪽으로 끌면 과거, 왼쪽으로 끌면 최신 방향.
            end0 = self._drag_end if self._drag_end is not None else total
            min_end = min(total, max(1, min(self.view_bars, total)))
            self.view_end = max(min_end, min(total, end0 - shift))
            self.update(); self._emit_viewport()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_x = None
            self._drag_end = None
            self.unsetCursor()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.show_latest()
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor('#091524'))
        if not self.series or not self.series.get('candles'):
            p.setPen(QColor('#8aa0b8'))
            p.drawText(self.rect(), Qt.AlignCenter, '데이터를 불러오면 차트가 표시됩니다.')
            return

        candles = self.series['candles']
        start, end = self.visible_index_range()
        cs = candles[start:end]
        n = len(cs)
        if n <= 0:
            return

        left, right, top = 60, 25, 28
        vol_h = 82
        bottom = 42
        price_rect = QRectF(left, top, self.width()-left-right, self.height()-top-bottom-vol_h)
        vol_rect = QRectF(left, price_rect.bottom()+8, price_rect.width(), vol_h-8)

        vals = []
        for c in cs:
            vals += [c['high'], c['low']]
        line_keys = [k for k in self.series.keys() if k not in ('candles','acc_flags','acc_meta','box') and isinstance(self.series.get(k), list)]
        for key in line_keys:
            arr = self.series.get(key, [])
            vals += [v for v in arr[start:end] if isinstance(v, (int, float))]
        lo, hi = min(vals), max(vals)
        pad = max((hi-lo)*0.08, hi*0.01, 1.0)
        lo -= pad; hi += pad

        def x(i): return price_rect.left() + (i + 0.5) * price_rect.width() / n
        def y(v): return price_rect.bottom() - (v-lo)/(hi-lo) * price_rect.height()

        # 선택 분석 구간 강조
        if self.analysis_range:
            a, b = self.analysis_range
            va = max(a, start); vb = min(b, end-1)
            if va <= vb:
                xs = x(va-start) - price_rect.width()/n/2
                xe = x(vb-start) + price_rect.width()/n/2
                p.fillRect(QRectF(xs, price_rect.top(), xe-xs, price_rect.height()+vol_h), QColor(57,130,246,25))

        # grid / y labels
        p.setPen(QPen(QColor('#17304a'), 1))
        for k in range(6):
            yy = price_rect.top() + k*price_rect.height()/5
            p.drawLine(QPointF(price_rect.left(), yy), QPointF(price_rect.right(), yy))
            value = hi - k*(hi-lo)/5
            p.setPen(QColor('#7f93a9')); p.drawText(5, int(yy+4), f'{value:,.0f}'); p.setPen(QPen(QColor('#17304a'),1))

        # 공구리 박스
        box = self.series.get('box')
        if box and box.get('start',-1) < end and box.get('end',-1) >= start:
            bs = max(start, box['start']); be = min(end-1, box['end'])
            xs = x(bs-start)-4; xe = x(be-start)+4
            r = QRectF(xs, y(box['high']), xe-xs, y(box['low'])-y(box['high']))
            p.setPen(QPen(QColor('#f4ce48'),2,Qt.DashLine)); p.setBrush(QColor(244,206,72,28)); p.drawRect(r)
            p.setPen(QColor('#f4ce48')); p.drawText(int(xs+6), int(y(box['high'])-6), '공구리(박스권)')

        maxvol = max(c['volume'] for c in cs) or 1
        acc_full = self.series.get('acc_flags', [False]*len(candles))
        acc = acc_full[start:end] if len(acc_full) >= end else [False]*n
        cw = max(1.5, min(12.0, price_rect.width()/n*0.58))
        for i,c in enumerate(cs):
            xx=x(i); up=c['close']>=c['open']; col=QColor('#ef4747') if up else QColor('#2d77ff')
            if i < len(acc) and acc[i]:
                p.fillRect(QRectF(xx-cw*0.9, price_rect.top(), cw*1.8, price_rect.height()), QColor(255,190,35,25))
                if n <= 180:
                    p.setPen(QColor('#ffc13d')); p.drawText(int(xx-18), int(price_rect.top()+18), '매집')
            p.setPen(QPen(col,1.1)); p.drawLine(QPointF(xx,y(c['low'])),QPointF(xx,y(c['high'])))
            yo,yc=y(c['open']),y(c['close']); r=QRectF(xx-cw/2,min(yo,yc),cw,max(1.2,abs(yc-yo)))
            p.fillRect(r,col)
            vh=vol_rect.height()*c['volume']/maxvol; p.fillRect(QRectF(xx-cw/2,vol_rect.bottom()-vh,cw,vh),QColor(col.red(),col.green(),col.blue(),170))

        colors={
            'ema5':'#f5e145','ema20':'#f2d33c','ema60':'#27d36b','ema112':'#3d9cff',
            'ema224':'#c26cff','ema448':'#8f6b4b','blue':'#2e7cff','kijun':'#f2f2f2'
        }
        widths={'blue':3.0,'ema5':1.2,'kijun':2.0}
        styles={'blue':Qt.DotLine}
        for key in line_keys:
            col = QColor(colors.get(key, '#9bb8d1'))
            self._draw_series(p, self.series[key], start, end, x, y, col, widths.get(key,1.5), styles.get(key,Qt.SolidLine))

        # breakout marker
        bi = getattr(self.analysis, 'breakout_index', -1) if self.analysis is not None else -1
        if start <= bi < end:
            xx=x(bi-start); p.setPen(QPen(QColor('#61ff8f'),2)); p.drawLine(QPointF(xx,price_rect.top()+18),QPointF(xx,price_rect.bottom()))
            p.setPen(QColor('#61ff8f')); p.setFont(QFont('Malgun Gothic',9,QFont.Bold)); p.drawText(int(xx+5), int(price_rect.top()+34), '박스 상단 돌파')

        # x-axis 날짜 라벨
        p.setPen(QColor('#8298af')); p.setFont(QFont('Malgun Gothic',8))
        ticks = min(6, n)
        for k in range(ticks):
            j = int(round(k*(n-1)/max(1,ticks-1)))
            txt = self._date_label(cs[j].get('date',''))
            p.drawText(int(x(j)-35), int(vol_rect.bottom()+22), 75, 18, Qt.AlignCenter, txt)

        p.setPen(QColor('#d7e8f7')); p.setFont(QFont('Malgun Gothic',10,QFont.Bold))
        legend = self.title or 'EMA / 파란점선'
        p.drawText(int(price_rect.left()), 19, legend)
        p.setPen(QColor('#7991aa')); p.setFont(QFont('Malgun Gothic',8))
        p.drawText(int(price_rect.right()-410), 19, 400, 18, Qt.AlignRight, '휠: 확대/축소 · 드래그: 과거/최신 이동 · 더블클릭: 최신')

        # 현재 차트에 실제 존재하는 선만 간단한 색상 범례로 표시.
        label_map = {
            'ema5':'EMA5', 'ema20':'EMA20', 'ema60':'EMA60', 'ema112':'EMA112',
            'ema224':'EMA224', 'ema448':'EMA448', 'blue':'파란점선', 'kijun':'PUMA기준선'
        }
        lx = price_rect.left()
        ly = price_rect.top() + 13
        p.setFont(QFont('Malgun Gothic', 7, QFont.Bold))
        for key in line_keys:
            name = label_map.get(key)
            if not name:
                continue
            p.setPen(QColor(colors.get(key, '#9bb8d1')))
            p.drawText(int(lx), int(ly), name)
            lx += 12 + max(35, len(name) * 8)
            if lx > price_rect.right() - 80:
                break

    def _draw_series(self,p,arr,start,end,x,y,color,width,style):
        p.setPen(QPen(color,width,style)); prev=None
        for idx in range(start, end):
            if idx<0 or idx>=len(arr) or arr[idx] is None:
                prev=None; continue
            pt=QPointF(x(idx-start),y(arr[idx]))
            if prev is not None: p.drawLine(prev,pt)
            prev=pt
