import SwiftUI

struct CandleChart: View {
    let payload: ChartPayload?

    var body: some View {
        GeometryReader { geo in
            Canvas { context, size in
                guard let all = payload?.candles, !all.isEmpty else {
                    context.draw(
                        Text("차트 데이터 없음").font(.caption).foregroundColor(.secondary),
                        at: CGPoint(x: size.width / 2, y: size.height / 2)
                    )
                    return
                }

                let count = min(80, all.count)
                let start = all.count - count
                let candles = Array(all[start...])
                let highs = candles.map(\.high)
                let lows = candles.map(\.low)
                guard let high = highs.max(), let low = lows.min(), high > low else { return }

                let top: CGFloat = 10
                let bottom: CGFloat = 14
                let plotH = max(1, size.height - top - bottom)
                let step = size.width / CGFloat(max(count, 1))
                let bodyW = max(1, step * 0.55)

                func x(_ local: Int) -> CGFloat {
                    (CGFloat(local) + 0.5) * step
                }
                func y(_ price: Double) -> CGFloat {
                    top + CGFloat((high - price) / (high - low)) * plotH
                }

                for (i, candle) in candles.enumerated() {
                    let up = candle.close >= candle.open
                    let color: Color = up ? .red : .blue
                    let xx = x(i)
                    var wick = Path()
                    wick.move(to: CGPoint(x: xx, y: y(candle.high)))
                    wick.addLine(to: CGPoint(x: xx, y: y(candle.low)))
                    context.stroke(wick, with: .color(color), lineWidth: 1)

                    let y1 = y(candle.open)
                    let y2 = y(candle.close)
                    let rect = CGRect(
                        x: xx - bodyW / 2,
                        y: min(y1, y2),
                        width: bodyW,
                        height: max(1.2, abs(y2 - y1))
                    )
                    context.fill(Path(rect), with: .color(color))
                }

                drawLine(context: &context, size: size, values: payload?.ema112, start: start, count: count, color: .green, x: x, y: y)
                drawLine(context: &context, size: size, values: payload?.ema224, start: start, count: count, color: .orange, x: x, y: y)
                drawLine(context: &context, size: size, values: payload?.ema448, start: start, count: count, color: .gray, x: x, y: y)

                drawSignals(context: &context, candles: candles, globalStart: start, flags: payload?.signalPink, color: .pink, offset: 7, x: x, y: y)
                drawSignals(context: &context, candles: candles, globalStart: start, flags: payload?.signalBlue, color: .blue, offset: 13, x: x, y: y)
                drawSignals(context: &context, candles: candles, globalStart: start, flags: payload?.signalRed, color: .red, offset: 19, x: x, y: y)
                drawSignals(context: &context, candles: candles, globalStart: start, flags: payload?.signalBlack, color: .white, offset: 25, x: x, y: y)

                if let wm = payload?.watermelonDisplay {
                    for i in 0..<count {
                        let gi = start + i
                        guard gi < wm.count, wm[gi] else { continue }
                        context.draw(
                            Text("🍉").font(.system(size: 13)),
                            at: CGPoint(x: x(i), y: max(12, y(candles[i].low) + 16))
                        )
                    }
                }
            }
            .background(Color.black.opacity(0.35))
            .clipShape(RoundedRectangle(cornerRadius: 10))
        }
    }

    private func drawLine(
        context: inout GraphicsContext,
        size: CGSize,
        values: [Double?]?,
        start: Int,
        count: Int,
        color: Color,
        x: (Int) -> CGFloat,
        y: (Double) -> CGFloat
    ) {
        guard let values, !values.isEmpty else { return }
        var path = Path()
        var started = false
        for i in 0..<count {
            let gi = start + i
            guard gi < values.count, let value = values[gi] else { continue }
            let point = CGPoint(x: x(i), y: y(value))
            if started { path.addLine(to: point) }
            else { path.move(to: point); started = true }
        }
        if started {
            context.stroke(path, with: .color(color), lineWidth: 1.2)
        }
    }

    private func drawSignals(
        context: inout GraphicsContext,
        candles: [Candle],
        globalStart: Int,
        flags: [Bool]?,
        color: Color,
        offset: CGFloat,
        x: (Int) -> CGFloat,
        y: (Double) -> CGFloat
    ) {
        guard let flags else { return }
        for i in candles.indices {
            let gi = globalStart + i
            guard gi < flags.count, flags[gi] else { continue }
            let xx = x(i)
            let yy = y(candles[i].low) + offset
            var p = Path()
            p.move(to: CGPoint(x: xx, y: yy - 5))
            p.addLine(to: CGPoint(x: xx - 5, y: yy + 4))
            p.addLine(to: CGPoint(x: xx + 5, y: yy + 4))
            p.closeSubpath()
            context.fill(p, with: .color(color))
        }
    }
}
