from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QPolygonF
from PySide6.QtWidgets import QWidget


class SwingChart(QWidget):
    """PUMA 공용 캔들 차트.

    v1.4: 마우스 휠 확대/축소, 좌우 드래그 과거 탐색, 선택 분석구간 강조,
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
        vol_h = 86
        watermelon_h = 34
        bottom = 42
        price_rect = QRectF(left, top, self.width()-left-right, self.height()-top-bottom-vol_h-watermelon_h)
        watermelon_rect = QRectF(left, price_rect.bottom()+3, price_rect.width(), watermelon_h)
        vol_rect = QRectF(left, watermelon_rect.bottom()+3, price_rect.width(), vol_h-10)

        total_candles = len(candles)
        future_count = int(self.series.get('future_count', 0) or 0) if end >= total_candles else 0
        display_n = max(1, n + future_count)

        vals = []
        for c in cs:
            vals += [c['high'], c['low']]
        line_keys = [k for k in self.series.keys() if k not in ('candles','acc_flags','acc_meta','box','watermelon','watermelon_stage','watermelon_score','watermelon_reason','cloud_a','cloud_b','signal_pink','signal_blue','signal_red','signal_sar','signal_bb40_22') and isinstance(self.series.get(k), list)]
        for key in line_keys:
            arr = self.series.get(key, [])
            vals += [v for v in arr[start:end] if isinstance(v, (int, float))]
        cloud_a = self.series.get('cloud_a', [])
        cloud_b = self.series.get('cloud_b', [])
        cloud_end = min(max(len(cloud_a), len(cloud_b)), end + future_count)
        if isinstance(cloud_a, list):
            vals += [v for v in cloud_a[start:cloud_end] if isinstance(v, (int, float))]
        if isinstance(cloud_b, list):
            vals += [v for v in cloud_b[start:cloud_end] if isinstance(v, (int, float))]
        lo, hi = min(vals), max(vals)
        pad = max((hi-lo)*0.08, hi*0.01, 1.0)
        lo -= pad; hi += pad

        def x(i): return price_rect.left() + (i + 0.5) * price_rect.width() / display_n
        def y(v): return price_rect.bottom() - (v-lo)/(hi-lo) * price_rect.height()

        # 선택 분석 구간 강조
        if self.analysis_range:
            a, b = self.analysis_range
            va = max(a, start); vb = min(b, end-1)
            if va <= vb:
                xs = x(va-start) - price_rect.width()/n/2
                xe = x(vb-start) + price_rect.width()/n/2
                p.fillRect(QRectF(xs, price_rect.top(), xe-xs, price_rect.height()+vol_h+watermelon_h), QColor(57,130,246,25))

        # 5분봉처럼 여러 거래일이 한 화면에 있을 때 날짜 경계를 명확히 분리.
        def day_key(raw):
            return ''.join(ch for ch in str(raw or '') if ch.isdigit())[:8]

        visible_days = [day_key(c.get('date', '')) for c in cs]
        unique_days = [d for i, d in enumerate(visible_days) if d and (i == 0 or d != visible_days[i-1])]
        # 일봉은 날짜 경계선을 그리지 않는다. 같은 거래일에 여러 봉이 존재하는 분봉에서만 표시.
        valid_days = [d for d in visible_days if d]
        is_intraday = len(valid_days) > len(set(valid_days))
        if is_intraday and len(unique_days) > 1:
            step_w = price_rect.width() / max(1, n)
            previous = visible_days[0] if visible_days else ''
            p.setFont(QFont('Malgun Gothic', 8, QFont.Bold))
            for i in range(1, n):
                current = visible_days[i]
                if current and current != previous:
                    xx = x(i) - step_w / 2
                    p.setPen(QPen(QColor('#5b7898'), 1, Qt.DashLine))
                    p.drawLine(QPointF(xx, price_rect.top()), QPointF(xx, vol_rect.bottom()))
                    label = f"{current[4:6]}/{current[6:8]}" if len(current) == 8 else current
                    p.setPen(QColor('#9bb8d1'))
                    p.drawText(int(xx + 4), int(price_rect.top() + 14), label)
                    previous = current

        # grid / y labels
        p.setPen(QPen(QColor('#17304a'), 1))
        for k in range(6):
            yy = price_rect.top() + k*price_rect.height()/5
            p.drawLine(QPointF(price_rect.left(), yy), QPointF(price_rect.right(), yy))
            value = hi - k*(hi-lo)/5
            p.setPen(QColor('#7f93a9')); p.drawText(5, int(yy+4), f'{value:,.0f}'); p.setPen(QPen(QColor('#17304a'),1))

        # 일목균형표 선행스팬 1·2: 사용자 영웅문 화면처럼 파란 구름대로 표시.
        # 최신 구간에서는 표준 +26 선행 구간까지 오른쪽에 예약해 구름이 앞쪽으로 이어진다.
        if isinstance(cloud_a, list) and isinstance(cloud_b, list):
            pts_a = []
            pts_b = []
            cloud_last = min(len(cloud_a), len(cloud_b), end + future_count)
            for gi in range(start, cloud_last):
                a = cloud_a[gi]
                b = cloud_b[gi]
                if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
                    continue
                xx = x(gi - start)
                pts_a.append(QPointF(xx, y(a)))
                pts_b.append(QPointF(xx, y(b)))
            if len(pts_a) >= 2 and len(pts_b) >= 2:
                poly = QPolygonF(pts_a + list(reversed(pts_b)))
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(40, 92, 255, 120))
                p.drawPolygon(poly)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor('#1f55ff'), 1.2))
                for pts in (pts_a, pts_b):
                    for j in range(1, len(pts)):
                        p.drawLine(pts[j-1], pts[j])

        # 공구리 박스
        box = self.series.get('box')
        if box and box.get('start',-1) < end and box.get('end',-1) >= start:
            bs = max(start, box['start']); be = min(end-1, box['end'])
            xs = x(bs-start)-4; xe = x(be-start)+4
            r = QRectF(xs, y(box['high']), xe-xs, y(box['low'])-y(box['high']))
            p.setPen(QPen(QColor('#f4ce48'),2,Qt.DashLine)); p.setBrush(QColor(244,206,72,28)); p.drawRect(r)
            p.setPen(QColor('#f4ce48')); p.drawText(int(xs+6), int(y(box['high'])-6), '공구리(박스권)')

        maxvol = max(c['volume'] for c in cs) or 1
        p.setPen(QColor('#91a8bd'))
        p.setFont(QFont('Malgun Gothic', 8, QFont.Bold))
        p.drawText(int(vol_rect.left()+4), int(vol_rect.top()+12), '거래량  ↑빨강 / ↓파랑')
        p.setPen(QPen(QColor('#263d58'), 1))
        p.drawLine(QPointF(vol_rect.left(), vol_rect.top()), QPointF(vol_rect.right(), vol_rect.top()))

        acc_full = self.series.get('acc_flags', [False]*len(candles))
        acc = acc_full[start:end] if len(acc_full) >= end else [False]*n
        cw = max(1.5, min(12.0, price_rect.width()/n*0.58))
        for i,c in enumerate(cs):
            xx=x(i)

            # 캔들 색: 가격 상승=빨강, 하락=파랑
            up=c['close']>=c['open']
            candle_col=QColor('#ef4747') if up else QColor('#2d77ff')

            if i < len(acc) and acc[i]:
                p.fillRect(QRectF(xx-cw*0.9, price_rect.top(), cw*1.8, price_rect.height()), QColor(255,190,35,25))
                if n <= 180:
                    p.setPen(QColor('#ffc13d')); p.drawText(int(xx-18), int(price_rect.top()+18), '매집')

            p.setPen(QPen(candle_col,1.1))
            p.drawLine(QPointF(xx,y(c['low'])),QPointF(xx,y(c['high'])))
            yo,yc=y(c['open']),y(c['close'])
            r=QRectF(xx-cw/2,min(yo,yc),cw,max(1.2,abs(yc-yo)))
            p.fillRect(r,candle_col)

            # 거래량 색은 캔들 등락과 무관하게 직전 봉 대비 거래량 증감 기준.
            # 증가=빨강 / 감소=파랑 / 동일=회색.
            global_i = start + i
            prev_vol = candles[global_i-1]['volume'] if global_i > 0 else c['volume']
            if c['volume'] > prev_vol:
                volume_col = QColor('#ef4747')
            elif c['volume'] < prev_vol:
                volume_col = QColor('#2d77ff')
            else:
                volume_col = QColor('#7f93a9')

            vh=vol_rect.height()*c['volume']/maxvol
            p.fillRect(
                QRectF(xx-cw/2,vol_rect.bottom()-vh,cw,vh),
                QColor(volume_col.red(),volume_col.green(),volume_col.blue(),185)
            )

        # PUMA 수박근사: 숫자 대신 수박 자체의 크기/속/씨앗으로 단계를 구분.
        # 1단=작은 수박, 2단=붉은 속+씨앗, 3단=큰 수박+강조 링.
        wm = self.series.get('watermelon_stage', [])
        if isinstance(wm, list) and wm:
            p.setFont(QFont('Malgun Gothic', 7, QFont.Bold))
            p.setPen(QColor('#83a1ba'))
            p.drawText(5, int(watermelon_rect.center().y()+3), 'PUMA수박')
            prev = 0
            for i, stage in enumerate(wm[start:end]):
                try:
                    stage = int(stage)
                except Exception:
                    stage = 0
                if stage <= 0 or stage == prev:
                    prev = stage
                    continue
                prev = stage
                xx = x(i)
                cy = watermelon_rect.center().y()
                radius = 8.5 if stage == 1 else (10.5 if stage == 2 else 13.0)

                if stage >= 3:
                    p.setPen(QPen(QColor('#ffd44a'), 2.2))
                    p.setBrush(Qt.NoBrush)
                    p.drawEllipse(QPointF(xx, cy), radius+3.2, radius+3.2)

                p.setPen(QPen(QColor('#08753a'), 2.0))
                p.setBrush(QColor('#35b85c'))
                p.drawEllipse(QPointF(xx, cy), radius, radius)

                inner = radius - 3.0
                p.setPen(Qt.NoPen)
                p.setBrush(QColor('#ff9aa0' if stage == 1 else '#ef4c5b'))
                p.drawEllipse(QPointF(xx, cy), inner, inner)

                seeds = [(-3,-2),(3,-2),(0,3)] if stage == 2 else [(-4,-3),(0,-4),(4,-3),(-2,3),(3,3)]
                if stage >= 2:
                    p.setBrush(QColor('#1c1515'))
                    for dx, dy in seeds:
                        p.drawEllipse(QPointF(xx+dx, cy+dy), 1.0, 1.6)

                p.setBrush(Qt.NoBrush)

        # 사용자 영웅문 매수 화살표 3종.
        # 분홍: BBandsUp(40,2.2) 상향돌파 + EMA112/224/448 중 하나 상향돌파
        # 파랑: C>=SAR(0.066,0.016) + BBandsUp(40,2.2) 상향돌파 + EMA112 상향돌파
        # 빨강: C>=SAR(0.066,0.016) + EMA224 상향돌파
        sig_defs = [
            ('signal_pink', QColor('#ff33cc')),
            ('signal_blue', QColor('#1746ff')),
            ('signal_red', QColor('#ff2e2e')),
        ]
        for key, sig_color in sig_defs:
            arr = self.series.get(key, [])
            if not isinstance(arr, list):
                continue
            visible = arr[start:end]
            for i, active in enumerate(visible):
                if not active:
                    continue
                xx = x(i)
                # 같은 봉에 복수 신호가 겹칠 수 있어 색상별 높이를 조금 다르게 둔다.
                order = 0 if key == 'signal_pink' else 1 if key == 'signal_blue' else 2
                base = min(price_rect.bottom() - 3, y(cs[i]['low']) + 12 + order * 10)
                apex = base - 9
                p.setPen(QPen(sig_color, 2))
                p.drawLine(QPointF(xx, base + 6), QPointF(xx, apex + 4))
                p.setBrush(sig_color)
                tri = QPolygonF([
                    QPointF(xx, apex),
                    QPointF(xx - 5, apex + 7),
                    QPointF(xx + 5, apex + 7),
                ])
                p.drawPolygon(tri)
                p.setBrush(Qt.NoBrush)

        colors={
            'ema5':'#ffd400','ema20':'#f2a900','ema60':'#27d36b','ema112':'#3d9cff',
            'ema224':'#c26cff','ema448':'#8f6b4b','blue':'#2e7cff','kijun':'#ffffff'
        }
        widths={'blue':3.0,'ema5':2.8,'kijun':5.0}
        styles={'blue':Qt.DotLine}
        if 'ema5' in line_keys:
            line_keys = [k for k in line_keys if k != 'ema5'] + ['ema5']
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
            p.drawText(int(x(j)-35), int(vol_rect.bottom()+7), 75, 18, Qt.AlignCenter, txt)

        p.setPen(QColor('#d7e8f7')); p.setFont(QFont('Malgun Gothic',10,QFont.Bold))
        legend = self.title or 'EMA / 파란점선'
        p.drawText(int(price_rect.left()), 19, legend)
        p.setPen(QColor('#7991aa')); p.setFont(QFont('Malgun Gothic',8))
        p.drawText(int(price_rect.right()-410), 19, 400, 18, Qt.AlignRight, '휠: 확대/축소 · 드래그: 과거/최신 이동 · 더블클릭: 최신')
        if isinstance(cloud_a, list) and isinstance(cloud_b, list) and cloud_a and cloud_b:
            p.setPen(QColor('#3972ff'))
            p.setFont(QFont('Malgun Gothic', 8, QFont.Bold))
            p.drawText(int(price_rect.left()), int(price_rect.top()+27), '■ 일목 선행스팬1·2')
        if isinstance(self.series.get('watermelon_stage'), list) and self.series.get('watermelon_stage'):
            p.setPen(QColor('#39b85f'))
            p.drawText(int(price_rect.left()+150), int(price_rect.top()+27), '● PUMA 수박근사(1~3단)')

        # 현재 차트에 실제 존재하는 선만 간단한 색상 범례로 표시.
        label_map = {
            'ema5':'EMA5(5선)', 'ema20':'EMA20', 'ema60':'EMA60', 'ema112':'EMA112',
            'ema224':'EMA224', 'ema448':'EMA448', 'blue':'파란점선', 'kijun':'기준선26'
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
