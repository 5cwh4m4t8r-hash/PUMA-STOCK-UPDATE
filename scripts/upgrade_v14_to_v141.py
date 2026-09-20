from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pkg = ROOT / "work" / "PUMA_STOCK_PRO_v1.4"
chart_path = pkg / "puma_trader" / "swing_chart.py"
updater_path = pkg / "puma_trader" / "updater.py"
ui_path = pkg / "puma_trader" / "ui.py"

chart = chart_path.read_text(encoding="utf-8")
updater = updater_path.read_text(encoding="utf-8")
ui = ui_path.read_text(encoding="utf-8")

old = """        for i,c in enumerate(cs):
            xx=x(i); up=c['close']>=c['open']; col=QColor('#ef4747') if up else QColor('#2d77ff')
            if i < len(acc) and acc[i]:
                p.fillRect(QRectF(xx-cw*0.9, price_rect.top(), cw*1.8, price_rect.height()), QColor(255,190,35,25))
                if n <= 180:
                    p.setPen(QColor('#ffc13d')); p.drawText(int(xx-18), int(price_rect.top()+18), '매집')
            p.setPen(QPen(col,1.1)); p.drawLine(QPointF(xx,y(c['low'])),QPointF(xx,y(c['high'])))
            yo,yc=y(c['open']),y(c['close']); r=QRectF(xx-cw/2,min(yo,yc),cw,max(1.2,abs(yc-yo)))
            p.fillRect(r,col)
            vh=vol_rect.height()*c['volume']/maxvol; p.fillRect(QRectF(xx-cw/2,vol_rect.bottom()-vh,cw,vh),QColor(col.red(),col.green(),col.blue(),170))
"""
new = """        for i,c in enumerate(cs):
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
"""
if old not in chart:
    raise RuntimeError("volume paint block not found")
chart = chart.replace(old, new, 1)

ui = ui.replace("PUMA STOCK PRO v1.4", "PUMA STOCK PRO v1.4.1")
ui = ui.replace("PUMA STOCK PRO  v1.4", "PUMA STOCK PRO  v1.4.1")
ui = ui.replace(
    "v1.4: 직접 주문 명칭 변경, 분석 카드에 간단 이유 표시, 기존 임시 수박바 제거, 일봉/5분봉에 일목균형표 선행스팬1·2 파란 구름대 반영.",
    "v1.4.1: 거래량 막대 색상을 직전 봉 대비 거래량 증감 기준으로 수정. 증가=빨강, 감소=파랑, 동일=회색."
)

updater = updater.replace('CURRENT_VERSION = "1.4.0"', 'CURRENT_VERSION = "1.4.1"')
updater = updater.replace("PUMA-STOCK-UPDATER/1.4", "PUMA-STOCK-UPDATER/1.4.1")

chart_path.write_text(chart, encoding="utf-8")
ui_path.write_text(ui, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
(pkg / "puma_trader" / "__init__.py").write_text('__version__ = "1.4.1"\n', encoding="utf-8")
print("PUMA v1.4.1 volume color fix applied")
