import Foundation
import SwiftUI

enum ConnectionMode: String, CaseIterable, Identifiable {
    case relay = "Relay"
    case direct = "Direct / Tailscale"
    var id: String { rawValue }
}

@MainActor
final class PumaClient: ObservableObject {
    @Published var state: PumaState?
    @Published var pcOnline = false
    @Published var connected = false
    @Published var errorMessage = ""
    @Published var lastCommandMessage = ""

    @Published var connectionMode: ConnectionMode
    @Published var serverURL: String
    @Published var deviceID: String
    @Published var pairToken: String

    private var pollTask: Task<Void, Never>?
    private let defaults = UserDefaults.standard
    private let session: URLSession

    init() {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = 8
        cfg.timeoutIntervalForResource = 12
        cfg.waitsForConnectivity = true
        self.session = URLSession(configuration: cfg)

        let modeRaw = defaults.string(forKey: "connectionMode") ?? ConnectionMode.relay.rawValue
        self.connectionMode = ConnectionMode(rawValue: modeRaw) ?? .relay
        self.serverURL = defaults.string(forKey: "serverURL") ?? ""
        self.deviceID = defaults.string(forKey: "deviceID") ?? ""
        self.pairToken = KeychainStore.loadToken()
    }

    var isConfigured: Bool {
        let urlOK = URL(string: normalizedBaseURL()) != nil
        let tokenOK = pairToken.count == 6 && pairToken.allSatisfy(\.isNumber)
        let deviceOK = connectionMode == .direct || deviceID.count == 12
        return urlOK && tokenOK && deviceOK
    }

    func saveConnection(mode: ConnectionMode, serverURL: String, deviceID: String, token: String) {
        self.connectionMode = mode
        self.serverURL = serverURL.trimmingCharacters(in: .whitespacesAndNewlines)
        self.deviceID = deviceID.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        self.pairToken = token.trimmingCharacters(in: .whitespacesAndNewlines)

        defaults.set(mode.rawValue, forKey: "connectionMode")
        defaults.set(self.serverURL, forKey: "serverURL")
        defaults.set(self.deviceID, forKey: "deviceID")
        KeychainStore.saveToken(self.pairToken)
        errorMessage = ""
    }

    func clearConnection() {
        stopPolling()
        defaults.removeObject(forKey: "serverURL")
        defaults.removeObject(forKey: "deviceID")
        KeychainStore.clearToken()
        serverURL = ""
        deviceID = ""
        pairToken = ""
        state = nil
        connected = false
        pcOnline = false
    }

    func startPolling() {
        guard isConfigured else { return }
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                try? await Task.sleep(for: .milliseconds(900))
            }
        }
    }

    func stopPolling() {
        pollTask?.cancel()
        pollTask = nil
    }

    func refresh() async {
        guard isConfigured else {
            connected = false
            pcOnline = false
            return
        }
        do {
            let data = try await perform(path: statePath, method: "GET")
            let decoder = JSONDecoder()
            if connectionMode == .relay {
                let env = try decoder.decode(RelayStateEnvelope.self, from: data)
                self.state = env.state
                self.pcOnline = env.pcOnline ?? false
            } else {
                self.state = try decoder.decode(PumaState.self, from: data)
                self.pcOnline = true
            }
            self.connected = true
            self.errorMessage = ""
        } catch {
            self.connected = false
            self.pcOnline = false
            self.errorMessage = error.localizedDescription
        }
    }

    func sendCommand(_ payload: [String: Any]) async throws -> CommandStatus {
        let body = try JSONSerialization.data(withJSONObject: payload, options: [])
        let acceptedData = try await perform(path: commandPath, method: "POST", body: body)
        let accepted = try JSONDecoder().decode(CommandAccepted.self, from: acceptedData)
        guard let requestID = accepted.requestId, !requestID.isEmpty else {
            throw ClientError.message("명령 ID를 받지 못했습니다.")
        }

        for _ in 0..<32 {
            try await Task.sleep(for: .milliseconds(250))
            let statusData = try await perform(path: "\(commandPath)/\(requestID)", method: "GET")
            let status = try JSONDecoder().decode(CommandStatus.self, from: statusData)
            if status.status == "done" {
                lastCommandMessage = status.result?["message"]?.description ?? "완료"
                await refresh()
                return status
            }
            if status.status == "error" {
                throw ClientError.message(status.error ?? "명령 처리 실패")
            }
        }
        throw ClientError.message("PC 응답 시간이 초과되었습니다.")
    }

    func selectStock(code: String, name: String) async throws {
        _ = try await sendCommand([
            "type": "select_stock",
            "code": code,
            "name": name,
        ])
    }

    func setChartMode(_ mode: String) async throws {
        _ = try await sendCommand([
            "type": "set_chart_mode",
            "mode": mode,
        ])
    }

    func unlockLive() async throws {
        _ = try await sendCommand([
            "type": "unlock_live",
            "phrase": "PUMA LIVE",
        ])
    }

    func lockLive() async throws {
        _ = try await sendCommand(["type": "lock_live"])
    }

    func stopAuto() async throws {
        _ = try await sendCommand(["type": "auto_stop"])
    }

    func startAuto(scope: String = "ALL") async throws {
        let settings = state?.auto?.settings
        let selected = state?.selected
        _ = try await sendCommand([
            "type": "auto_start",
            "scope": scope,
            "code": selected?.code ?? "",
            "name": selected?.name ?? "",
            "candidate_source": settings?.candidateSource ?? "HERO4",
            "order_budget": settings?.orderBudget ?? 500_000,
            "max_positions": settings?.maxPositions ?? 3,
            "max_daily_orders": settings?.maxDailyOrders ?? 20,
            "take_profit_pct": settings?.takeProfitPct ?? 4.0,
            "stop_loss_pct": settings?.stopLossPct ?? -3.0,
            "trailing_enabled": settings?.trailingEnabled ?? false,
            "trailing_start_pct": settings?.trailingStartPct ?? 3.0,
            "trailing_gap_pct": settings?.trailingGapPct ?? 1.0,
        ])
    }

    func placeOrder(
        code: String,
        side: String,
        orderType: String,
        qty: Int,
        price: Int,
        condPrice: Int
    ) async throws {
        _ = try await sendCommand([
            "type": "order",
            "code": code,
            "side": side,
            "order_type": orderType,
            "qty": qty,
            "price": price,
            "cond_price": condPrice,
        ])
    }

    private var statePath: String {
        connectionMode == .relay ? "/v1/mobile/state" : "/api/state"
    }

    private var commandPath: String {
        connectionMode == .relay ? "/v1/mobile/command" : "/api/command"
    }

    private func normalizedBaseURL() -> String {
        var value = serverURL.trimmingCharacters(in: .whitespacesAndNewlines)
        while value.hasSuffix("/") { value.removeLast() }
        return value
    }

    private func perform(path: String, method: String, body: Data? = nil) async throws -> Data {
        let base = normalizedBaseURL()
        guard let url = URL(string: base + path) else {
            throw ClientError.message("서버 주소가 올바르지 않습니다.")
        }
        if url.scheme?.lowercased() != "https" {
            throw ClientError.message("iPhone 외부망 연결은 HTTPS 주소를 사용하세요.")
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 8
        request.setValue(pairToken, forHTTPHeaderField: "X-Puma-Token")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if connectionMode == .relay {
            request.setValue(deviceID, forHTTPHeaderField: "X-Puma-Device")
        }
        request.httpBody = body

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw ClientError.message("서버 응답이 올바르지 않습니다.")
        }
        guard (200..<300).contains(http.statusCode) else {
            var message = "HTTP \(http.statusCode)"
            if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let text = obj["error"] as? String {
                message = text
            }
            throw ClientError.message(message)
        }
        return data
    }
}

enum ClientError: LocalizedError {
    case message(String)
    var errorDescription: String? {
        switch self {
        case .message(let text): return text
        }
    }
}
