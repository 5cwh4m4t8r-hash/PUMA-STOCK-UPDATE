import SwiftUI

struct RootView: View {
    @EnvironmentObject var client: PumaClient

    var body: some View {
        Group {
            if client.isConfigured {
                MainTabs()
            } else {
                SetupView()
            }
        }
        .tint(.blue)
    }
}

struct SetupView: View {
    @EnvironmentObject var client: PumaClient
    @State private var mode: ConnectionMode = .relay
    @State private var serverURL = ""
    @State private var deviceID = ""
    @State private var token = ""
    @State private var working = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Picker("연결 방식", selection: $mode) {
                        ForEach(ConnectionMode.allCases) { item in
                            Text(item.rawValue).tag(item)
                        }
                    }
                    TextField(
                        mode == .relay ? "https://relay.example.com" : "https://pc-name.tailnet.ts.net",
                        text: $serverURL
                    )
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)

                    if mode == .relay {
                        TextField("PUMA 기기 ID 12자리", text: $deviceID)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                    }

                    TextField("연결코드 6자리", text: $token)
                        .keyboardType(.numberPad)
                } header: {
                    Text("PUMA 연결")
                } footer: {
                    Text(
                        mode == .relay
                        ? "PC의 모바일 연동 탭에 표시된 Relay 주소, PUMA 기기 ID, 연결코드를 입력합니다."
                        : "Tailscale Serve의 HTTPS 주소와 PC 연결코드만 입력합니다. 같은 Wi-Fi가 아니어도 됩니다."
                    )
                }

                Section {
                    Button {
                        saveAndConnect()
                    } label: {
                        HStack {
                            Spacer()
                            if working { ProgressView().padding(.trailing, 6) }
                            Text("연결")
                                .fontWeight(.bold)
                            Spacer()
                        }
                    }
                    .disabled(working || serverURL.isEmpty || token.count != 6)
                }

                if !client.errorMessage.isEmpty {
                    Section {
                        Text(client.errorMessage)
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("PUMA STOCK")
            .onAppear {
                mode = client.connectionMode
                serverURL = client.serverURL
                deviceID = client.deviceID
                token = client.pairToken
            }
        }
    }

    private func saveAndConnect() {
        working = true
        client.saveConnection(mode: mode, serverURL: serverURL, deviceID: deviceID, token: token)
        Task {
            await client.refresh()
            if client.connected {
                client.startPolling()
            }
            working = false
        }
    }
}

struct MainTabs: View {
    var body: some View {
        TabView {
            NavigationStack { HomeView() }
                .tabItem { Label("홈", systemImage: "house.fill") }
            NavigationStack { CandidateView() }
                .tabItem { Label("조건", systemImage: "line.3.horizontal.decrease.circle") }
            NavigationStack { ChartView() }
                .tabItem { Label("차트", systemImage: "chart.xyaxis.line") }
            NavigationStack { AccountView() }
                .tabItem { Label("잔고", systemImage: "wallet.bifold.fill") }
            NavigationStack { SettingsView() }
                .tabItem { Label("설정", systemImage: "gearshape.fill") }
        }
    }
}

struct HomeView: View {
    @EnvironmentObject var client: PumaClient

    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                StatusCard(client: client)

                HStack(spacing: 10) {
                    MetricCard(
                        title: "현재 종목",
                        value: client.state?.selected?.name ?? client.state?.selected?.code ?? "-",
                        subtitle: client.state?.selected?.code ?? "-"
                    )
                    MetricCard(
                        title: "현재가",
                        value: money(client.state?.selected?.price),
                        subtitle: client.state?.selected?.chartMode ?? "-"
                    )
                }

                PCard(title: "통합 판정") {
                    Text(client.state?.selected?.stage ?? "데이터 대기")
                        .font(.headline)
                        .foregroundStyle(.green)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                PCard(title: "활성 조건검색") {
                    let rows = (client.state?.candidates ?? []).filter { $0.active ?? false }.prefix(6)
                    if rows.isEmpty {
                        Text("활성 후보 없음").foregroundStyle(.secondary)
                    } else {
                        ForEach(Array(rows)) { row in
                            CandidateMiniRow(row: row)
                        }
                    }
                }

                PCard(title: "최근 로그") {
                    let logs = Array((client.state?.logs ?? []).prefix(8))
                    if logs.isEmpty {
                        Text("로그 없음").foregroundStyle(.secondary)
                    } else {
                        ForEach(logs) { row in
                            VStack(alignment: .leading, spacing: 2) {
                                HStack {
                                    Text(row.kind ?? "-").font(.caption).fontWeight(.bold).foregroundStyle(.blue)
                                    Spacer()
                                    Text(row.time ?? "").font(.caption2).foregroundStyle(.secondary)
                                }
                                Text("\(row.stock ?? "")  \(row.text ?? "")")
                                    .font(.caption)
                            }
                            Divider().opacity(0.25)
                        }
                    }
                }

                if !client.errorMessage.isEmpty {
                    Text(client.errorMessage)
                        .font(.caption)
                        .foregroundStyle(.orange)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding()
        }
        .navigationTitle("PUMA STOCK")
        .refreshable { await client.refresh() }
    }
}

struct StatusCard: View {
    @ObservedObject var client: PumaClient

    var body: some View {
        PCard(title: "PC / KIWOOM") {
            HStack {
                Circle()
                    .fill(client.connected && client.pcOnline ? Color.green : Color.red)
                    .frame(width: 10, height: 10)
                Text(client.pcOnline ? "PC ONLINE" : "PC OFFLINE")
                    .fontWeight(.bold)
                Spacer()
                Text(client.state?.live == true ? "REAL" : "SIM")
                    .font(.caption)
                    .fontWeight(.bold)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background((client.state?.live == true ? Color.red : Color.blue).opacity(0.2))
                    .clipShape(Capsule())
            }
            Text(client.state?.status ?? "-")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }
}

struct CandidateView: View {
    @EnvironmentObject var client: PumaClient

    var body: some View {
        List {
            ForEach(client.state?.candidates ?? []) { row in
                Button {
                    Task {
                        do {
                            try await client.selectStock(code: row.code, name: row.name ?? row.code)
                        } catch {
                            client.errorMessage = error.localizedDescription
                        }
                    }
                } label: {
                    VStack(alignment: .leading, spacing: 5) {
                        HStack {
                            Text(row.name ?? row.code).fontWeight(.bold)
                            Text(row.code).font(.caption).foregroundStyle(.secondary)
                            Spacer()
                            if row.active ?? false {
                                Text("LIVE")
                                    .font(.caption2).fontWeight(.bold)
                                    .foregroundStyle(.green)
                            }
                        }
                        Text(row.classification ?? "분석중")
                            .font(.caption)
                            .foregroundStyle(.blue)
                        HStack {
                            ScoreChip(name: "D", value: row.scores?.danta ?? 0)
                            ScoreChip(name: "S", value: row.scores?.swing ?? 0)
                            ScoreChip(name: "B", value: row.scores?.bowl ?? 0)
                        }
                    }
                    .padding(.vertical, 3)
                }
                .buttonStyle(.plain)
            }
        }
        .navigationTitle("조건검색")
        .refreshable { await client.refresh() }
    }
}

struct ChartView: View {
    @EnvironmentObject var client: PumaClient

    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                HStack {
                    VStack(alignment: .leading) {
                        Text(client.state?.selected?.name ?? "종목 선택")
                            .font(.title3).fontWeight(.bold)
                        Text(client.state?.selected?.code ?? "-")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(money(client.state?.selected?.price))
                        .font(.title3).fontWeight(.bold)
                        .foregroundStyle(.red)
                }

                HStack {
                    chartButton("일봉", mode: "DAY")
                    chartButton("5분", mode: "MIN")
                    Spacer()
                    Text("\(client.state?.selected?.chart?.candles?.count ?? 0)봉")
                        .font(.caption).foregroundStyle(.secondary)
                }

                PCard(title: "차트") {
                    CandleChart(payload: client.state?.selected?.chart)
                        .frame(height: 330)
                }

                AnalysisCard(title: "단타 DAY", text: client.state?.selected?.analysis?.danta)
                AnalysisCard(title: "역매공파 SWING", text: client.state?.selected?.analysis?.swing)
                AnalysisCard(title: "밥그릇3 LONG", text: client.state?.selected?.analysis?.bowl)
            }
            .padding()
        }
        .navigationTitle("종목")
    }

    @ViewBuilder
    private func chartButton(_ title: String, mode: String) -> some View {
        let active = (client.state?.selected?.chartMode ?? "DAY") == mode
        Button(title) {
            Task {
                do { try await client.setChartMode(mode) }
                catch { client.errorMessage = error.localizedDescription }
            }
        }
        .buttonStyle(.borderedProminent)
        .tint(active ? .blue : .gray.opacity(0.4))
    }
}

struct AccountView: View {
    @EnvironmentObject var client: PumaClient
    @State private var showOrder = false
    @State private var busy = false

    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                PCard(title: "실전 잠금") {
                    HStack {
                        Image(systemName: client.state?.mobileLiveUnlocked == true ? "lock.open.fill" : "lock.fill")
                        Text(client.state?.mobileLiveUnlocked == true ? "해제됨" : "잠김")
                            .fontWeight(.bold)
                        Spacer()
                        Button(client.state?.mobileLiveUnlocked == true ? "다시 잠금" : "최초 1회 해제") {
                            Task { await toggleLiveLock() }
                        }
                        .buttonStyle(.bordered)
                    }
                }

                PCard(title: "자동매매") {
                    HStack {
                        VStack(alignment: .leading) {
                            Text(client.state?.auto?.enabled == true ? "실행 중" : "중지")
                                .font(.title3).fontWeight(.bold)
                                .foregroundStyle(client.state?.auto?.enabled == true ? .green : .orange)
                            Text(client.state?.auto?.scopeLabel ?? "-")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Button(client.state?.auto?.enabled == true ? "중지" : "전체 후보 시작") {
                            Task { await toggleAuto() }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(busy || client.state?.mobileLiveUnlocked != true)
                    }
                }

                PCard(title: "보유 종목") {
                    let rows = client.state?.positions ?? []
                    if rows.isEmpty {
                        Text("보유 종목 없음").foregroundStyle(.secondary)
                    } else {
                        ForEach(rows) { row in
                            HStack {
                                VStack(alignment: .leading) {
                                    Text(row.name ?? row.code).fontWeight(.bold)
                                    Text("\(row.qty ?? 0)주 · 평균 \(money(row.avgPrice))")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                VStack(alignment: .trailing) {
                                    Text(money(row.currentPrice)).fontWeight(.bold)
                                    Text(String(format: "%+.2f%%", row.pnlPct ?? 0))
                                        .font(.caption)
                                        .foregroundStyle((row.pnlPct ?? 0) >= 0 ? .red : .blue)
                                }
                            }
                            Divider().opacity(0.25)
                        }
                    }
                }

                Button {
                    showOrder = true
                } label: {
                    Label("수동 주문", systemImage: "arrow.up.arrow.down.circle.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(.red)
                .disabled(client.state?.mobileLiveUnlocked != true)
            }
            .padding()
        }
        .navigationTitle("잔고 · 주문")
        .sheet(isPresented: $showOrder) {
            NavigationStack {
                OrderView()
                    .environmentObject(client)
            }
        }
    }

    private func toggleLiveLock() async {
        busy = true
        defer { busy = false }
        do {
            if client.state?.mobileLiveUnlocked == true {
                try await client.lockLive()
            } else {
                try await client.unlockLive()
            }
        } catch {
            client.errorMessage = error.localizedDescription
        }
    }

    private func toggleAuto() async {
        busy = true
        defer { busy = false }
        do {
            if client.state?.auto?.enabled == true {
                try await client.stopAuto()
            } else {
                try await client.startAuto(scope: "ALL")
            }
        } catch {
            client.errorMessage = error.localizedDescription
        }
    }
}

struct OrderView: View {
    @EnvironmentObject var client: PumaClient
    @Environment(\.dismiss) var dismiss
    @State private var code = ""
    @State private var side = "BUY"
    @State private var type = "market"
    @State private var qty = 1
    @State private var price = 0
    @State private var condPrice = 0
    @State private var busy = false
    @State private var error = ""

    var body: some View {
        Form {
            Section("주문") {
                TextField("종목코드", text: $code)
                    .keyboardType(.numberPad)
                Picker("구분", selection: $side) {
                    Text("매수").tag("BUY")
                    Text("매도").tag("SELL")
                }
                .pickerStyle(.segmented)
                Picker("주문방식", selection: $type) {
                    Text("시장가").tag("market")
                    Text("지정가").tag("limit")
                    Text("스톱지정가").tag("stop_limit")
                }
                Stepper("수량 \(qty)주", value: $qty, in: 1...1_000_000)
                if type != "market" {
                    TextField("가격", value: $price, format: .number)
                        .keyboardType(.numberPad)
                }
                if type == "stop_limit" {
                    TextField("조건가격", value: $condPrice, format: .number)
                        .keyboardType(.numberPad)
                }
            }
            if !error.isEmpty {
                Section { Text(error).foregroundStyle(.red) }
            }
            Section {
                Button("주문 요청") {
                    Task { await submit() }
                }
                .disabled(busy || code.isEmpty)
            }
        }
        .navigationTitle("수동 주문")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("닫기") { dismiss() }
            }
        }
        .onAppear {
            code = client.state?.selected?.code ?? ""
        }
    }

    private func submit() async {
        busy = true
        defer { busy = false }
        do {
            try await client.placeOrder(
                code: code,
                side: side,
                orderType: type,
                qty: qty,
                price: price,
                condPrice: condPrice
            )
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct SettingsView: View {
    @EnvironmentObject var client: PumaClient
    @State private var mode: ConnectionMode = .relay
    @State private var serverURL = ""
    @State private var deviceID = ""
    @State private var token = ""

    var body: some View {
        Form {
            Section("연결 상태") {
                LabeledContent("PC", value: client.pcOnline ? "ONLINE" : "OFFLINE")
                LabeledContent("PUMA", value: client.state?.version ?? "-")
                LabeledContent("업데이트", value: client.state?.updatedAt ?? "-")
            }

            Section("연결 설정") {
                Picker("방식", selection: $mode) {
                    ForEach(ConnectionMode.allCases) { item in
                        Text(item.rawValue).tag(item)
                    }
                }
                TextField("HTTPS 주소", text: $serverURL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                if mode == .relay {
                    TextField("PUMA 기기 ID", text: $deviceID)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
                TextField("연결코드 6자리", text: $token)
                    .keyboardType(.numberPad)
                Button("저장하고 다시 연결") {
                    client.saveConnection(
                        mode: mode,
                        serverURL: serverURL,
                        deviceID: deviceID,
                        token: token
                    )
                    client.startPolling()
                }
            }

            Section {
                Button("연결정보 초기화", role: .destructive) {
                    client.clearConnection()
                }
            }

            if !client.errorMessage.isEmpty {
                Section("오류") {
                    Text(client.errorMessage).foregroundStyle(.orange)
                }
            }
        }
        .navigationTitle("설정")
        .onAppear {
            mode = client.connectionMode
            serverURL = client.serverURL
            deviceID = client.deviceID
            token = client.pairToken
        }
    }
}

struct PCard<Content: View>: View {
    let title: String
    let content: Content

    init(title: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).font(.headline)
            content
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}

struct MetricCard: View {
    let title: String
    let value: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.headline).lineLimit(1)
            Text(subtitle).font(.caption2).foregroundStyle(.secondary)
        }
        .padding()
        .frame(maxWidth: .infinity, minHeight: 86, alignment: .leading)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}

struct CandidateMiniRow: View {
    let row: Candidate

    var body: some View {
        HStack {
            VStack(alignment: .leading) {
                Text(row.name ?? row.code).fontWeight(.bold)
                Text(row.classification ?? "-")
                    .font(.caption2).foregroundStyle(.secondary)
            }
            Spacer()
            Text("D\(row.scores?.danta ?? 0) S\(row.scores?.swing ?? 0) B\(row.scores?.bowl ?? 0)")
                .font(.caption2).foregroundStyle(.blue)
        }
    }
}

struct ScoreChip: View {
    let name: String
    let value: Int
    var body: some View {
        Text("\(name) \(value)")
            .font(.caption2).fontWeight(.bold)
            .padding(.horizontal, 7).padding(.vertical, 3)
            .background(Color.blue.opacity(0.15))
            .clipShape(Capsule())
    }
}

struct AnalysisCard: View {
    let title: String
    let text: String?

    var body: some View {
        PCard(title: title) {
            Text(text ?? "-")
                .font(.caption)
                .foregroundStyle(.yellow)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

func money(_ value: Double?) -> String {
    guard let value else { return "-" }
    let f = NumberFormatter()
    f.numberStyle = .decimal
    f.maximumFractionDigits = 0
    return (f.string(from: NSNumber(value: value)) ?? "-") + "원"
}
