import SwiftUI

@main
struct PUMAMobileApp: App {
    @StateObject private var client = PumaClient()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(client)
                .preferredColorScheme(.dark)
                .onAppear {
                    if client.isConfigured {
                        client.startPolling()
                    }
                }
        }
    }
}
