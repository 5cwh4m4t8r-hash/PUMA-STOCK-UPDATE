from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pkg = ROOT / "work" / "PUMA_STOCK_PRO_v2.3"
chart_path = pkg / "puma_trader" / "swing_chart.py"
signals_path = pkg / "puma_trader" / "signals.py"
ui_path = pkg / "puma_trader" / "ui.py"
updater_path = pkg / "puma_trader" / "updater.py"

chart = chart_path.read_text(encoding="utf-8")
signals = signals_path.read_text(encoding="utf-8")
ui = ui_path.read_text(encoding="utf-8")
updater = updater_path.read_text(encoding="utf-8")

def once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"target not found: {label}")
    return text.replace(old, new, 1)

# ---------- version ----------
ui = once(ui, 'self.setWindowTitle("PUMA STOCK PRO v2.3")', 'self.setWindowTitle("PUMA STOCK PRO v2.4")', "window version")
ui = once(ui, 'title = QLabel("🐆  PUMA STOCK PRO  v2.3")', 'title = QLabel("🐆  PUMA STOCK PRO  v2.4")', "header version")

# ---------- hide cluttered indicator labels at chart top ----------
old_top = '''        p.setPen(QColor('#d7e8f7')); p.setFont(QFont('Malgun Gothic',10,QFont.Bold))
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
            p.drawText(int(price_rect.left()+150), int(price_rect.top()+27), '● PUMA 수박확정: 복합조건 충족 구간만 표시')

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
'''
new_top = '''        # 차트 상단은 종목/봉 정보만 남긴다.
        # EMA/기준선/파란점선/일목/수박 등 지표 이름 범례는 차트 위를 가리지 않도록 숨김.
        p.setPen(QColor('#d7e8f7'))
        p.setFont(QFont('Malgun Gothic',10,QFont.Bold))
        if self.title:
            p.drawText(int(price_rect.left()), 19, self.title)

        p.setPen(QColor('#7991aa'))
        p.setFont(QFont('Malgun Gothic',8))
        p.drawText(
            int(price_rect.right()-410), 19, 400, 18, Qt.AlignRight,
            '휠: 확대/축소 · 드래그: 과거/최신 이동 · 더블클릭: 최신'
        )
'''
chart = once(chart, old_top, new_top, "hide indicator legends")

# Hide the left-side watermelon text too; only the watermelon shape remains.
chart = chart.replace(
'''            p.setFont(QFont('Malgun Gothic', 7, QFont.Bold))
            p.setPen(QColor('#83a1ba'))
            p.drawText(5, int(watermelon_rect.center().y()+3), 'PUMA수박확정')
''',
'''            # 수박 이름 텍스트는 숨기고 모양만 표시.
'''
)

# ---------- four arrow visibility ----------
old_sig = '''        # 사용자 영웅문 매수 화살표 3종.
        # 분홍: BBandsUp(40,2.2) 상향돌파 + EMA112/224/448 중 하나 상향돌파
        # 파랑: C>=SAR(0.066,0.016) + BBandsUp(40,2.2) 상향돌파 + EMA112 상향돌파
        # 빨강: C>=SAR(0.066,0.016) + EMA224 상향돌파
        sig_defs = [
            ('signal_pink', QColor('#ff33cc')),
            ('signal_blue', QColor('#1746ff')),
            ('signal_red', QColor('#ff2e2e')),
            # 검정 화살표는 별도 수식이 연결될 경우 사용.
            # 어두운 PUMA 배경에서는 흰 외곽선을 먼저 그려 영웅문 회색배경 수준의 대비를 확보한다.
            ('signal_black', QColor('#050505')),
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
                tri_outer = QPolygonF([
                    QPointF(xx, apex-2),
                    QPointF(xx - 7, apex + 9),
                    QPointF(xx + 7, apex + 9),
                ])
                p.setPen(QPen(QColor('#f4f7fb'), 2.2))
                p.setBrush(QColor('#f4f7fb'))
                p.drawPolygon(tri_outer)
                p.drawLine(QPointF(xx, base + 7), QPointF(xx, apex + 4))

                tri = QPolygonF([
                    QPointF(xx, apex),
                    QPointF(xx - 5, apex + 7),
                    QPointF(xx + 5, apex + 7),
                ])
                p.setPen(QPen(sig_color, 1.6))
                p.setBrush(sig_color)
                p.drawPolygon(tri)
                p.drawLine(QPointF(xx, base + 6), QPointF(xx, apex + 4))
                p.setBrush(Qt.NoBrush)
'''
new_sig = '''        # 사용자 영웅문 화살표 4종.
        # 같은 봉에 여러 신호가 겹쳐도 4개가 서로 가리지 않도록 전용 lane을 사용.
        # 검정 화살표는 PUMA의 검정 배경에서도 보이도록 흰 외곽선을 가장 강하게 적용.
        sig_defs = [
            ('signal_pink',  QColor('#ff2fcf'), 0),
            ('signal_blue',  QColor('#1e5bff'), 1),
            ('signal_red',   QColor('#ff3038'), 2),
            ('signal_black', QColor('#050505'), 3),
        ]
        for key, sig_color, lane in sig_defs:
            arr = self.series.get(key, [])
            if not isinstance(arr, list):
                continue
            visible = arr[start:end]
            for i, active in enumerate(visible):
                if not active:
                    continue

                xx = x(i)
                lane_gap = 13.0
                base = min(
                    price_rect.bottom() - 4,
                    y(cs[i]['low']) + 14 + lane * lane_gap
                )
                apex = base - 12

                # 밝은 halo: 배경/캔들/이평선 위에서도 신호 형태가 유지된다.
                halo = QColor('#ffffff')
                outer = QPolygonF([
                    QPointF(xx, apex - 3),
                    QPointF(xx - 9, apex + 10),
                    QPointF(xx + 9, apex + 10),
                ])
                p.setPen(QPen(halo, 2.8))
                p.setBrush(halo)
                p.drawPolygon(outer)
                p.drawLine(QPointF(xx, base + 9), QPointF(xx, apex + 4))

                inner = QPolygonF([
                    QPointF(xx, apex),
                    QPointF(xx - 6, apex + 8),
                    QPointF(xx + 6, apex + 8),
                ])
                p.setPen(QPen(sig_color, 2.0))
                p.setBrush(sig_color)
                p.drawPolygon(inner)
                p.drawLine(QPointF(xx, base + 7), QPointF(xx, apex + 4))

                # 검정색은 중앙에 얇은 흰 점을 한 번 더 넣어 검정 fill도 식별 가능하게 한다.
                if key == 'signal_black':
                    p.setPen(QPen(QColor('#ffffff'), 1.4))
                    p.setBrush(QColor('#ffffff'))
                    p.drawEllipse(QPointF(xx, apex + 5), 1.8, 1.8)

                p.setBrush(Qt.NoBrush)
'''
chart = once(chart, old_sig, new_sig, "four arrow visibility")

# Ensure the fourth series always exists in signal payload; do not invent its formula.
signals = once(
    signals,
'''        return {
            "signal_pink": [], "signal_blue": [], "signal_red": [],
            "signal_sar": [], "signal_bb40_22": [],
        }
''',
'''        return {
            "signal_pink": [], "signal_blue": [], "signal_red": [], "signal_black": [],
            "signal_sar": [], "signal_bb40_22": [],
        }
''',
    "empty black signal",
)
signals = once(
    signals,
'''    return {
        "signal_pink": pink,
        "signal_blue": blue,
        "signal_red": red,
        "signal_sar": sar,
        "signal_bb40_22": bb,
    }
''',
'''    # 검정 화살표는 아직 사용자 원본 수식이 제공되지 않았으므로 임의 조건을 만들지 않는다.
    # 배열은 항상 제공해 렌더러/외부 신호 연결 시 즉시 표시할 수 있게 한다.
    black = [False] * n
    return {
        "signal_pink": pink,
        "signal_blue": blue,
        "signal_red": red,
        "signal_black": black,
        "signal_sar": sar,
        "signal_bb40_22": bb,
    }
''',
    "black placeholder payload",
)

# ---------- update note ----------
ui = ui.replace(
    "v2.3: 공개 단테 강의의 박스돌파→저거래량 눌림 원칙을 재반영. 박스권 돌파는 전봉 또는 20봉평균 대비 거래량강도 300%로 확인하고, 눌림은 돌파선 지지와 뚜렷한 거래량 감소를 확인해 최초 1회 표시. 지나친 필터를 완화해 유효 돌파/눌림 누락을 줄이고 공통경로 품질점수를 확률판단에 사용.",
    "v2.4: 차트 상단의 EMA/기준선/파란점선/일목/수박 지표명 범례를 숨겨 차트를 정리. 분홍·파랑·빨강·검정 4종 화살표를 큰 화살표+흰 외곽선+개별 lane으로 그려 겹침과 검정배경 묻힘을 개선. 검정 화살표 발생식은 사용자 수식 전까지 임의 생성하지 않음."
)

# ---------- updater ----------
updater = once(updater, 'CURRENT_VERSION = "2.3.0"', 'CURRENT_VERSION = "2.4.0"', "updater version")
updater = updater.replace("PUMA-STOCK-UPDATER/2.3", "PUMA-STOCK-UPDATER/2.4")

chart_path.write_text(chart, encoding="utf-8")
signals_path.write_text(signals, encoding="utf-8")
ui_path.write_text(ui, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
(pkg / "puma_trader" / "__init__.py").write_text('__version__ = "2.4.0"\n', encoding="utf-8")
print("PUMA v2.4 clean chart + 4-arrow visibility patch applied")
