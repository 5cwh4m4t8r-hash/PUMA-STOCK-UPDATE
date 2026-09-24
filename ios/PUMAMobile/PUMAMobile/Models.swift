import Foundation

struct RelayStateEnvelope: Codable {
    let ok: Bool?
    let pcOnline: Bool?
    let lastPcSeen: Double?
    let state: PumaState

    enum CodingKeys: String, CodingKey {
        case ok
        case pcOnline = "pc_online"
        case lastPcSeen = "last_pc_seen"
        case state
    }
}

struct PumaState: Codable {
    let version: String?
    let updatedAt: String?
    let connected: Bool?
    let live: Bool?
    let realArmed: Bool?
    let mobileLiveUnlocked: Bool?
    let status: String?
    let mode: String?
    let auto: PumaAuto?
    let candidates: [Candidate]?
    let positions: [PositionRow]?
    let logs: [LogRow]?
    let selected: SelectedState?

    enum CodingKeys: String, CodingKey {
        case version
        case updatedAt = "updated_at"
        case connected
        case live
        case realArmed = "real_armed"
        case mobileLiveUnlocked = "mobile_live_unlocked"
        case status
        case mode
        case auto
        case candidates
        case positions
        case logs
        case selected
    }
}

struct PumaAuto: Codable {
    let enabled: Bool?
    let scope: String?
    let scopeLabel: String?
    let focusOnlyCode: String?
    let settings: AutoSettings?

    enum CodingKeys: String, CodingKey {
        case enabled, scope
        case scopeLabel = "scope_label"
        case focusOnlyCode = "focus_only_code"
        case settings
    }
}

struct AutoSettings: Codable {
    let candidateSource: String?
    let orderBudget: Int?
    let maxPositions: Int?
    let maxDailyOrders: Int?
    let takeProfitPct: Double?
    let stopLossPct: Double?
    let trailingEnabled: Bool?
    let trailingStartPct: Double?
    let trailingGapPct: Double?

    enum CodingKeys: String, CodingKey {
        case candidateSource = "candidate_source"
        case orderBudget = "order_budget"
        case maxPositions = "max_positions"
        case maxDailyOrders = "max_daily_orders"
        case takeProfitPct = "take_profit_pct"
        case stopLossPct = "stop_loss_pct"
        case trailingEnabled = "trailing_enabled"
        case trailingStartPct = "trailing_start_pct"
        case trailingGapPct = "trailing_gap_pct"
    }
}

struct Candidate: Codable, Identifiable {
    var id: String { code }
    let code: String
    let name: String?
    let active: Bool?
    let classification: String?
    let detail: String?
    let enteredAt: String?
    let scores: ScoreSet?

    enum CodingKeys: String, CodingKey {
        case code, name, active, classification, detail, scores
        case enteredAt = "entered_at"
    }
}

struct ScoreSet: Codable {
    let danta: Int?
    let swing: Int?
    let bowl: Int?
}

struct PositionRow: Codable, Identifiable {
    var id: String { code }
    let code: String
    let name: String?
    let qty: Int?
    let avgPrice: Double?
    let currentPrice: Double?
    let pnlPct: Double?

    enum CodingKeys: String, CodingKey {
        case code, name, qty
        case avgPrice = "avg_price"
        case currentPrice = "current_price"
        case pnlPct = "pnl_pct"
    }
}

struct LogRow: Codable, Identifiable {
    var id: String { "\(time ?? "")-\(stock ?? "")-\(kind ?? "")-\(text ?? "")" }
    let time: String?
    let stock: String?
    let kind: String?
    let price: String?
    let text: String?
}

struct SelectedState: Codable {
    let code: String?
    let name: String?
    let price: Double?
    let chartMode: String?
    let stage: String?
    let analysis: AnalysisText?
    let chart: ChartPayload?

    enum CodingKeys: String, CodingKey {
        case code, name, price, stage, analysis, chart
        case chartMode = "chart_mode"
    }
}

struct AnalysisText: Codable {
    let danta: String?
    let swing: String?
    let bowl: String?
}

struct ChartPayload: Codable {
    let candles: [Candle]?
    let ema112: [Double?]?
    let ema224: [Double?]?
    let ema448: [Double?]?
    let signalPink: [Bool]?
    let signalBlue: [Bool]?
    let signalRed: [Bool]?
    let signalBlack: [Bool]?
    let watermelonDisplay: [Bool]?

    enum CodingKeys: String, CodingKey {
        case candles, ema112, ema224, ema448
        case signalPink = "signal_pink"
        case signalBlue = "signal_blue"
        case signalRed = "signal_red"
        case signalBlack = "signal_black"
        case watermelonDisplay = "watermelon_display"
    }
}

struct Candle: Codable, Identifiable {
    var id: String { date + "-\(open)-\(close)" }
    let date: String
    let open: Double
    let high: Double
    let low: Double
    let close: Double
    let volume: Double
}

struct CommandAccepted: Codable {
    let accepted: Bool?
    let requestId: String?

    enum CodingKeys: String, CodingKey {
        case accepted
        case requestId = "request_id"
    }
}

struct CommandStatus: Codable {
    let status: String?
    let result: [String: JSONValue]?
    let error: String?
}

enum JSONValue: Codable, CustomStringConvertible {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let v = try? c.decode(Bool.self) { self = .bool(v) }
        else if let v = try? c.decode(Double.self) { self = .number(v) }
        else if let v = try? c.decode(String.self) { self = .string(v) }
        else if let v = try? c.decode([String: JSONValue].self) { self = .object(v) }
        else if let v = try? c.decode([JSONValue].self) { self = .array(v) }
        else { throw DecodingError.dataCorruptedError(in: c, debugDescription: "Unsupported JSON value") }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .string(let v): try c.encode(v)
        case .number(let v): try c.encode(v)
        case .bool(let v): try c.encode(v)
        case .object(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .null: try c.encodeNil()
        }
    }

    var description: String {
        switch self {
        case .string(let v): return v
        case .number(let v): return String(v)
        case .bool(let v): return v ? "true" : "false"
        case .object: return "[object]"
        case .array: return "[array]"
        case .null: return ""
        }
    }
}
