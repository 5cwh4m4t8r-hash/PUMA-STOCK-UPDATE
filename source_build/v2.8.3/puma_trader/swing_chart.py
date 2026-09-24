from __future__ import annotations

from datetime import datetime
import time
from bisect import bisect_left, bisect_right

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QPolygonF
from PySide6.QtWidgets import QWidget

from .performance import DEVICE_PROFILE


class SwingChart(QWidget):
    """PUMA 공용 캔들 차트.

    v1.4: 마우스 휠 확대/축소, 좌우 드래그 과거 탐색, 선택 분석구간 강조,
    일봉/분봉 공용 표시를 지원한다.
    """

    viewportChanged = Signal(str)
    paintMeasured = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.series = None
        self.analysis = None
        self.title = ''
        self.view_bars = 80 if DEVICE_PROFILE.very_low_power else 90 if DEVICE_PROFILE.low_power else 130
        self.view_end: int | None = None  # exclusive index
        self.analysis_range: tuple[int, int] | None = None
        self._drag_x = None
        self._drag_end = None
        self._low_power = DEVICE_PROFILE.low_power
        self._line_keys = ()
        self._day_keys = ()
        self._last_paint_ms = 0.0
        self.setMinimumHeight(430)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setMouseTracking(True)

    def set_data(self, analysis, series, title: str = '', preserve_view: bool = False):
        old_end = self.view_end
        old_candles = (self.series or {}).get('candles', [])
        was_latest = old_end is None or old_end >= len(old_candles)
        anchor = str(old_candles[min(old_end, len(old_candles))-1].get('date', '')) if old_candles and old_end else ''
        range_dates = None
        if self.analysis_range and old_candles:
            a, b = self.analysis_range
            if 0 <= a <= b < len(old_candles):
                range_dates = (str(old_candles[a].get('date', '')), str(old_candles[b].get('date', '')))
        self.analysis = analysis
        self.series = series
        self._prepare_render_cache()
        self.title = title or self.title
        n = len(series.get('candles', [])) if series else 0
        new_candles = (series or {}).get('candles', [])
        date_key = lambda c: str(c.get('date', ''))
        if not preserve_view or was_latest:
            self.view_end = n
        else:
            # Older pages are prepended. Preserve the visible date, not its old index.
            self.view_end = min(n, max(1, bisect_right(new_candles, anchor, key=date_key)))
        if preserve_view and range_dates and n:
            a = bisect_left(new_candles, range_dates[0], key=date_key)
            b = bisect_right(new_candles, range_dates[1], key=date_key) - 1
            self.analysis_range = (a, b) if a <= b < n else None
        self.view_bars = min(max(15, self.view_bars), max(15, n)) if n else 130
        self.update()
        self._emit_viewport()

    def _prepare_render_cache(self):
        series = self.series or {}
        # Only actual PRICE overlays may participate in price-axis scaling/drawing.
        # Never auto-discover every list in series: diagnostic arrays such as
        # volume EMA, booleans or disparity values can be orders of magnitude
        # away from price and make candles look vertically flat.
        price_line_order = (
            'ema5', 'ema20', 'ema60', 'ema112', 'ema224', 'ema448',
            'blue', 'kijun',
        )
        self._line_keys = tuple(
            k for k in price_line_order
            if isinstance(series.get(k), list)
        )
        candles = series.get('candles', [])
        self._day_keys = tuple(
            ''.join(ch for ch in str(c.get('date', '') or '') if ch.isdigit())[:8]
            for c in candles
        )

    def _emit_paint_timing(self, started: float):
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        self._last_paint_ms = elapsed
        self.paintMeasured.emit(elapsed)

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
            self.view_bars = max(15, n)
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
        self.view_bars = max(15, min(total, new_n))
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
        paint_started = time.perf_counter()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, not self._low_power)
        p.fillRect(self.rect(), QColor('#343a40'))
        if not self.series or not self.series.get('candles'):
            p.setPen(QColor('#c7ced6'))
            p.drawText(self.rect(), Qt.AlignCenter, '데이터를 불러오면 차트가 표시됩니다.')
            self._emit_paint_timing(paint_started)
            return

        candles = self.series['candles']
        start, end = self.visible_index_range()
        cs = candles[start:end]
        n = len(cs)
        if n <= 0:
            self._emit_paint_timing(paint_started)
            return

        left, right, top = 60, 25, 28
        vol_h = 86
        watermelon_h = 4
        bottom = 42
        price_rect = QRectF(left, top, self.width()-left-right, self.height()-top-bottom-vol_h-watermelon_h)
        watermelon_rect = QRectF(left, price_rect.bottom()+3, price_rect.width(), watermelon_h)
        vol_rect = QRectF(left, watermelon_rect.bottom()+3, price_rect.width(), vol_h-10)

        total_candles = len(candles)
        future_count = int(self.series.get('future_count', 0) or 0) if end >= total_candles else 0
        display_n = max(1, n + future_count)

        # Vertical auto-scale is based on the VISIBLE candles first.
        # This makes wheel zoom reveal actual price curvature instead of keeping
        # a huge global range. Nearby price overlays are included; very distant
        # long MAs/cloud values are clipped rather than flattening the candles.
        candle_lo = min(float(c['low']) for c in cs)
        candle_hi = max(float(c['high']) for c in cs)
        candle_span = max(candle_hi - candle_lo, candle_hi * 0.002, 1.0)
        candle_mid = (candle_hi + candle_lo) / 2.0

        # The more the user zooms in, the tighter the vertical padding.
        pad_ratio = 0.035 if n <= 30 else 0.045 if n <= 60 else 0.060
        base_pad = max(candle_span * pad_ratio, candle_mid * 0.0025, 1.0)
        lo = candle_lo - base_pad
        hi = candle_hi + base_pad

        # Include nearby overlays only. This keeps EMA112/224 etc visible when
        # relevant, but a remote EMA448 or cloud cannot crush the price action.
        proximity = max(candle_span * 1.25, candle_mid * 0.06, 2.0)
        nearby_lo = candle_lo - proximity
        nearby_hi = candle_hi + proximity

        def include_near_price(v):
            nonlocal lo, hi
            if not isinstance(v, (int, float)):
                return
            value = float(v)
            if nearby_lo <= value <= nearby_hi:
                lo = min(lo, value)
                hi = max(hi, value)

        overlay_suppressed = bool(
            self.series.get('overlay_suppressed_long_trend')
            or self.series.get('long_trend_suppressed_now')
        )
        # In an already extended 112>224>448 bullish trend, keep only price,
        # volume and EMA lines. Bottom/reversal indicators are intentionally unused.
        line_keys = tuple(
            k for k in self._line_keys
            if not overlay_suppressed or str(k).startswith('ema')
        )
        for key in line_keys:
            arr = self.series.get(key, [])
            for v in arr[start:end]:
                include_near_price(v)

        cloud_a = self.series.get('cloud_a', [])
        cloud_b = self.series.get('cloud_b', [])
        cloud_end = min(max(len(cloud_a), len(cloud_b)), end + future_count)
        if isinstance(cloud_a, list):
            for v in cloud_a[start:cloud_end]:
                include_near_price(v)
        if isinstance(cloud_b, list):
            for v in cloud_b[start:cloud_end]:
                include_near_price(v)

        # Final small padding after nearby overlays are included.
        final_span = max(hi - lo, 1.0)
        final_pad = max(final_span * (0.025 if n <= 60 else 0.04), 1.0)
        lo -= final_pad
        hi += final_pad

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
        visible_days = self._day_keys[start:end]
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
                    p.setPen(QPen(QColor('#646d77'), 1, Qt.DashLine))
                    p.drawLine(QPointF(xx, price_rect.top()), QPointF(xx, vol_rect.bottom()))
                    label = f"{current[4:6]}/{current[6:8]}" if len(current) == 8 else current
                    p.setPen(QColor('#c4ccd4'))
                    p.drawText(int(xx + 4), int(price_rect.top() + 14), label)
                    previous = current

        # grid / y labels
        p.setPen(QPen(QColor('#4f5760'), 1))
        for k in range(6):
            yy = price_rect.top() + k*price_rect.height()/5
            p.drawLine(QPointF(price_rect.left(), yy), QPointF(price_rect.right(), yy))
            value = hi - k*(hi-lo)/5
            p.setPen(QColor('#c9d0d7')); p.drawText(5, int(yy+4), f'{value:,.0f}'); p.setPen(QPen(QColor('#4f5760'),1))

        # 일목균형표 선행스팬 1·2: 사용자 영웅문 화면처럼 파란 구름대로 표시.
        # 최신 구간에서는 표준 +26 선행 구간까지 오른쪽에 예약해 구름이 앞쪽으로 이어진다.
        if not overlay_suppressed and isinstance(cloud_a, list) and isinstance(cloud_b, list):
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
                # 구름대 내부는 반투명 대신 완전 채움.
                p.setBrush(QColor('#4f6598'))
                p.drawPolygon(poly)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor('#7f9be0'), 1.2))
                for pts in (pts_a, pts_b):
                    for j in range(1, len(pts)):
                        p.drawLine(pts[j-1], pts[j])

        # 공구리: 최근 박스만 덮어쓰지 말고 확정된 과거 박스까지 누적 표시.
        # 과거는 얇고 투명하게, 가장 최근 박스는 굵고 선명하게 표시한다.
        one_box = self.series.get('box')
        boxes = self.series.get('boxes')
        if not isinstance(boxes, list):
            boxes = [one_box] if isinstance(one_box, dict) else []
        elif isinstance(one_box, dict) and one_box.get('structure_type') != '공구리':
            # 전고점언덕은 공구리 목록과 별도로 유지한다.
            boxes = list(boxes) + [one_box]

        visible_boxes = [] if overlay_suppressed else [
            b for b in boxes
            if isinstance(b, dict)
            and b.get('start', -1) < end
            and b.get('end', -1) >= start
        ]
        latest_concrete = None
        concrete_only = [b for b in boxes if isinstance(b, dict) and b.get('structure_type') == '공구리']
        if concrete_only:
            latest_concrete = max(concrete_only, key=lambda b: int(b.get('end', -1)))

        for box in visible_boxes:
            bs = max(start, int(box.get('start', start)))
            be = min(end - 1, int(box.get('end', end - 1)))
            xs = x(bs-start)-4; xe = x(be-start)+4
            structure_type = str(box.get('structure_type') or '공구리')

            if structure_type == '공구리':
                is_latest = bool(
                    latest_concrete
                    and int(box.get('start', -1)) == int(latest_concrete.get('start', -2))
                    and int(box.get('end', -1)) == int(latest_concrete.get('end', -2))
                )
                # 공구리는 노란 네모 테두리만 표시한다.
                # 내부를 채우지 않아 캔들/이평선/구름/화살표를 가리지 않고,
                # 이 레이어가 먼저 그려지므로 뒤에 그리는 봉/지표에도 영향을 주지 않는다.
                border = QColor('#ffe04b')
                pen_w = 2.5 if is_latest else 1.8
                r = QRectF(xs, y(box['high']), xe-xs, y(box['low'])-y(box['high']))
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(border, pen_w, Qt.SolidLine))
                p.drawRect(r)
            else:
                p.setPen(QPen(QColor('#f4ce48'),2,Qt.DashLine))
                p.drawLine(QPointF(xs, y(box['high'])), QPointF(xe, y(box['high'])))
                p.drawText(int(xs+6), int(y(box['high'])-6), '전고점언덕 저항')

        maxvol = max(c['volume'] for c in cs) or 1
        p.setPen(QColor('#c8d0d8'))
        p.setFont(QFont('Malgun Gothic', 8, QFont.Bold))
        p.drawText(int(vol_rect.left()+4), int(vol_rect.top()+12), '거래량  ↑빨강 / ↓파랑')
        p.setPen(QPen(QColor('#59616a'), 1))
        p.drawLine(QPointF(vol_rect.left(), vol_rect.top()), QPointF(vol_rect.right(), vol_rect.top()))

        raw_acc_full = self.series.get('raw_acc_flags', [False]*len(candles))
        raw_acc = raw_acc_full[start:end] if len(raw_acc_full) >= end else [False]*n
        acc_full = self.series.get('acc_flags', [False]*len(candles))
        acc = acc_full[start:end] if len(acc_full) >= end else [False]*n
        path_break = self.series.get('path_breakout', [])
        path_pull = self.series.get('path_pullback', [])
        path_rebreak = self.series.get('path_rebreakout', [])
        path_break_ma = self.series.get('path_breakout_ma', [])
        path_pull_ma = self.series.get('path_pullback_ma', [])
        cw = max(1.5, min(12.0, price_rect.width()/n*0.58))
        for i,c in enumerate(cs):
            xx=x(i)

            # 캔들 색: 가격 상승=빨강, 하락=파랑
            up=c['close']>=c['open']
            candle_col=QColor('#ef4747') if up else QColor('#2d77ff')

            if not overlay_suppressed:
                is_candidate = i < len(raw_acc) and raw_acc[i]
                is_confirmed = i < len(acc) and acc[i]
                if is_candidate and not is_confirmed:
                    # Single suspicious volume/price bar: visible, but do not
                    # paint a full-height band or call it confirmed.
                    p.setPen(QPen(QColor('#e0a72f'), 1.6))
                    marker_y = max(price_rect.top()+8, y(c['high'])-8)
                    p.drawEllipse(QPointF(xx, marker_y), 3.2, 3.2)
                    if n <= 120:
                        p.drawText(int(xx-15), int(marker_y-6), '매집')
                if is_confirmed:
                    p.fillRect(QRectF(xx-cw*0.9, price_rect.top(), cw*1.8, price_rect.height()), QColor(255,190,35,25))
                    if n <= 180:
                        p.setPen(QColor('#ffc13d')); p.drawText(int(xx-26), int(price_rect.top()+18), '매집확정')

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
                volume_col = QColor('#8d98a3')

            vh=vol_rect.height()*c['volume']/maxvol
            p.fillRect(
                QRectF(xx-cw/2,vol_rect.bottom()-vh,cw,vh),
                QColor(volume_col.red(),volume_col.green(),volume_col.blue(),185)
            )

            gi = start + i
            label = ''
            label_color = QColor('#ffffff')
            if not overlay_suppressed and isinstance(path_rebreak, list) and gi < len(path_rebreak) and path_rebreak[gi]:
                label = '✓재돌파'; label_color = QColor('#ffcf3d')
            elif not overlay_suppressed and isinstance(path_pull, list) and gi < len(path_pull) and path_pull[gi]:
                ma = path_pull_ma[gi] if isinstance(path_pull_ma, list) and gi < len(path_pull_ma) else 0
                label = f'✓눌림{ma}' if ma else '✓눌림'; label_color = QColor('#62d98b')
            elif not overlay_suppressed and isinstance(path_break, list) and gi < len(path_break) and path_break[gi]:
                ma = path_break_ma[gi] if isinstance(path_break_ma, list) and gi < len(path_break_ma) else 0
                label = f'✓돌파{ma}' if ma else '✓돌파'; label_color = QColor('#ff6a6a')
            if label:
                p.setPen(label_color)
                p.setFont(QFont('Malgun Gothic', 8, QFont.Bold))
                p.drawText(int(xx-16), int(max(price_rect.top()+32, y(c['high'])-8)), label)

        # 밥그릇3번 자리: 분석기가 판정한 실제 일봉 위치에 단계별 태그를 표시.
        bowl3_markers = self.series.get('bowl3_markers', [])
        if not overlay_suppressed and isinstance(bowl3_markers, list) and bowl3_markers:
            marker_colors = {
                'prebreak': QColor('#7a5d00'),
                'breakout': QColor('#b33a24'),
                'accepted': QColor('#176b39'),
                'historical_core': QColor('#8b55b7'),
                'core': QColor('#6f2da8'),
            }
            for marker_info in bowl3_markers:
                if not isinstance(marker_info, dict):
                    continue
                gi = int(marker_info.get('index', -1))
                if not (start <= gi < end):
                    continue
                i = gi - start
                xx = x(i)
                candle = cs[i]
                yy = max(price_rect.top() + 22.0, y(candle['high']) - 28.0)
                label = str(marker_info.get('label') or '밥3')
                kind = str(marker_info.get('kind') or 'core')
                col = marker_colors.get(kind, QColor('#6f2da8'))

                # 봉과 태그를 연결하고, 어두운 회색 차트에서 읽히도록 짙은 판을 깐다.
                p.setPen(QPen(col, 1.6))
                p.drawLine(QPointF(xx, y(candle['high']) - 2), QPointF(xx, yy + 14))
                text_w = max(54, min(86, 10 + len(label) * 13))
                rect = QRectF(xx - text_w / 2, yy - 2, text_w, 22)
                p.setPen(QPen(col, 1.4))
                p.setBrush(QColor(38, 43, 48, 235))
                p.drawRoundedRect(rect, 5, 5)
                p.setPen(col)
                p.setFont(QFont('Malgun Gothic', 8, QFont.Bold))
                p.drawText(rect, Qt.AlignCenter, label)
                p.setBrush(Qt.NoBrush)

        # PUMA 수박근사: 신호가 발생한 실제 봉에 붙여 표시.
        # 별도 하단 띠에 몰아넣지 않고, 봉 저가 아래(공간 부족 시 고가 위)에 앵커링한다.
        wm = self.series.get('watermelon_display', [])
        if not overlay_suppressed and isinstance(wm, list) and wm:
            for i, stage in enumerate(wm[start:end]):
                if not stage:
                    continue
                xx = x(i)
                low_y = y(cs[i]['low'])
                high_y = y(cs[i]['high'])
                below_cy = low_y + 20.0
                if below_cy + 14.0 <= price_rect.bottom():
                    cy = below_cy
                    p.setPen(QPen(QColor('#ffd44a'), 1.4))
                    p.drawLine(QPointF(xx, low_y + 2), QPointF(xx, cy - 13))
                else:
                    cy = max(price_rect.top() + 14.0, high_y - 20.0)
                    p.setPen(QPen(QColor('#ffd44a'), 1.4))
                    p.drawLine(QPointF(xx, high_y - 2), QPointF(xx, cy + 13))

                radius = 11.0
                p.setPen(QPen(QColor('#fff3a8'), 3.0))
                p.setBrush(QColor('#35b85c'))
                p.drawEllipse(QPointF(xx, cy), radius + 2.0, radius + 2.0)

                p.setPen(QPen(QColor('#08753a'), 2.0))
                p.setBrush(QColor('#ef4c5b'))
                p.drawEllipse(QPointF(xx, cy), radius - 2.0, radius - 2.0)

                p.setPen(Qt.NoPen)
                p.setBrush(QColor('#1c1515'))
                for dx, dy in ((-4,-3),(0,-4),(4,-3),(-2,3),(3,3)):
                    p.drawEllipse(QPointF(xx+dx, cy+dy), 1.0, 1.6)
                p.setBrush(Qt.NoBrush)

        # 화살표 4종: 영웅문처럼 신호가 발생한 '정확한 봉의 x좌표'에 세로 적층.
        # 같은 봉 신호를 좌우로 펼치면 다른 날짜처럼 보이므로 수평 오프셋은 사용하지 않는다.
        # 시인성은 흰 halo / 검정은 금색 halo로 확보한다.
        sig_defs = [
            ('signal_pink',  QColor('#ff2fcf'), '분'),
            ('signal_blue',  QColor('#2774ff'), '파'),
            ('signal_red',   QColor('#ff343f'), '빨'),
            ('signal_black', QColor('#050505'), '검'),
        ]
        for i, candle in enumerate(cs):
            if overlay_suppressed:
                break
            gi = start + i
            active = []
            for key, sig_color, sig_label in sig_defs:
                arr = self.series.get(key, [])
                if isinstance(arr, list) and gi < len(arr) and arr[gi]:
                    active.append((key, sig_color, sig_label))
            if not active:
                continue

            xx = x(i)  # 절대 다른 봉으로 보이지 않게 모든 신호가 동일 x좌표 사용
            low_y = y(candle['low'])
            high_y = y(candle['high'])
            spacing = 21.0
            stack_h = 30.0 + spacing * max(0, len(active) - 1)

            # 기본은 캔들 아래. 아래 공간이 부족하면 캔들 위에 같은 x로 세로 적층.
            place_below = low_y + stack_h <= price_rect.bottom()
            if place_below:
                first_apex = low_y + 10.0
            else:
                first_apex = high_y - 10.0

            for idx, (key, sig_color, sig_label) in enumerate(active):
                if place_below:
                    apex = first_apex + idx * spacing
                    tail_y = apex + 16.0
                    outer = QPolygonF([
                        QPointF(xx, apex),
                        QPointF(xx - 8.5, apex + 11.0),
                        QPointF(xx + 8.5, apex + 11.0),
                    ])
                    inner = QPolygonF([
                        QPointF(xx, apex + 2.0),
                        QPointF(xx - 5.8, apex + 9.0),
                        QPointF(xx + 5.8, apex + 9.0),
                    ])
                    text_rect_y = tail_y + 3.0
                    stem_end = apex + 6.0
                else:
                    # 위에 놓더라도 화살표 자체는 '매수 상향' 모양을 유지.
                    apex = first_apex - idx * spacing
                    tail_y = apex + 16.0
                    outer = QPolygonF([
                        QPointF(xx, apex),
                        QPointF(xx - 8.5, apex + 11.0),
                        QPointF(xx + 8.5, apex + 11.0),
                    ])
                    inner = QPolygonF([
                        QPointF(xx, apex + 2.0),
                        QPointF(xx - 5.8, apex + 9.0),
                        QPointF(xx + 5.8, apex + 9.0),
                    ])
                    text_rect_y = tail_y + 3.0
                    stem_end = apex + 6.0

                halo = QColor('#ffd84a') if key == 'signal_black' else QColor('#ffffff')
                p.setPen(QPen(halo, 3.2))
                p.setBrush(halo)
                p.drawPolygon(outer)
                p.drawLine(QPointF(xx, tail_y), QPointF(xx, stem_end))

                p.setPen(QPen(QColor('#ffffff'), 1.6))
                p.setBrush(sig_color)
                p.drawPolygon(inner)
                p.drawLine(QPointF(xx, tail_y - 1.5), QPointF(xx, stem_end))

                if key == 'signal_black':
                    p.setPen(QPen(QColor('#ffd84a'), 1.2))
                    p.setBrush(QColor('#050505'))
                    p.drawEllipse(QPointF(xx, apex + 6.0), 2.0, 2.0)

                # 라벨도 같은 봉의 x좌표를 유지하되 우측으로 아주 조금만 붙여 식별성 확보.
                p.setFont(QFont('Malgun Gothic', 8, QFont.Bold))
                p.setPen(QColor('#ffd84a') if key == 'signal_black' else sig_color)
                p.drawText(int(xx + 7), int(text_rect_y - 8), 18, 13, Qt.AlignLeft, sig_label)
                p.setBrush(Qt.NoBrush)

        # 사용자 영웅문 화면의 시각 체계를 밝은 회색 배경에 맞게 재현.
        # 5=노랑, 20=빨강, 60=초록, 112=갈색/주황, 224=검정 굵게, 448=회색 점선.
        colors={
            'ema5':'#ffd21f',
            'ema20':'#ff3434',
            'ema60':'#00b85a',
            'ema112':'#b85a18',
            'ema224':'#050505',
            'ema448':'#9aa0a6',
            'blue':'#1f49ff',
            'kijun':'#f2e7a3'
        }
        widths={
            'ema5':2.3,'ema20':2.1,'ema60':2.1,'ema112':2.5,
            'ema224':3.2,'ema448':1.8,'blue':3.2,'kijun':5.0
        }
        styles={'blue':Qt.DotLine,'ema448':Qt.DashLine}
        priority = ['ema448','ema224','ema112','ema60','ema20','ema5','blue','kijun']
        ordered = [k for k in priority if k in line_keys] + [k for k in line_keys if k not in priority]
        for key in ordered:
            col = QColor(colors.get(key, '#c0c8d0'))
            if key == 'ema224':
                # 회색 배경에서도 224EMA는 거의 검정색 코어로 또렷하게 표시한다.
                pass
            if key == 'kijun':
                self._draw_series(p, self.series[key], start, end, x, y, QColor('#b71c1c'), 1.0, Qt.SolidLine)
            self._draw_series(p, self.series[key], start, end, x, y, col, widths.get(key,1.5), styles.get(key,Qt.SolidLine))

        # breakout marker
        bi = getattr(self.analysis, 'breakout_index', -1) if self.analysis is not None else -1
        if not overlay_suppressed and start <= bi < end:
            xx=x(bi-start); p.setPen(QPen(QColor('#61ff8f'),2)); p.drawLine(QPointF(xx,price_rect.top()+18),QPointF(xx,price_rect.bottom()))
            cp = self.series.get('core_path', {}) or {}
            ma = int(cp.get('breakout_ma_period',0) or 0)
            p.setPen(QColor('#61ff8f')); p.setFont(QFont('Malgun Gothic',9,QFont.Bold))
            p.drawText(int(xx+5), int(price_rect.top()+34), f'확정 돌파 {ma}EMA' if ma else '확정 돌파')

        # x-axis 날짜 라벨
        p.setPen(QColor('#c2cad2')); p.setFont(QFont('Malgun Gothic',8))
        ticks = min(6, n)
        for k in range(ticks):
            j = int(round(k*(n-1)/max(1,ticks-1)))
            txt = self._date_label(cs[j].get('date',''))
            p.drawText(int(x(j)-35), int(vol_rect.bottom()+7), 75, 18, Qt.AlignCenter, txt)

        # 차트 상단은 종목/봉 정보만 남긴다.
        # EMA/기준선/파란점선/일목/수박 등 지표 이름 범례는 차트 위를 가리지 않도록 숨김.
        p.setPen(QColor('#f0f3f5'))
        p.setFont(QFont('Malgun Gothic',10,QFont.Bold))
        if self.title:
            p.drawText(int(price_rect.left()), 19, self.title)

        p.setPen(QColor('#b8c1c9'))
        p.setFont(QFont('Malgun Gothic',8))
        p.drawText(
            int(price_rect.right()-410), 19, 400, 18, Qt.AlignRight,
            '휠: 확대/축소 · 드래그: 과거/최신 이동 · 더블클릭: 최신'
        )
        self._emit_paint_timing(paint_started)

    def _draw_series(self,p,arr,start,end,x,y,color,width,style):
        p.setPen(QPen(color,width,style)); prev=None
        for idx in range(start, end):
            if idx<0 or idx>=len(arr) or arr[idx] is None:
                prev=None; continue
            pt=QPointF(x(idx-start),y(arr[idx]))
            if prev is not None: p.drawLine(prev,pt)
            prev=pt
