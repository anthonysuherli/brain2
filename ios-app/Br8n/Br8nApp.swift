import SwiftUI

@main
struct Br8nApp: App {
    @State private var auth = AuthStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(auth)
                .tint(Theme.accent)
        }
    }
}

/// Routes between Sign in and Home based on session state.
struct RootView: View {
    @Environment(AuthStore.self) private var auth

    var body: some View {
        switch auth.session {
        case .signedOut:
            SignInView()
        case .signedIn:
            HomeView()
        }
    }
}
