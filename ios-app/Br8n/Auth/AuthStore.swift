import Foundation
import Observation

/// Owns session state + the configured API base URL, and vends a configured
/// `APIClient`. Drives whether the app shows Sign in or Home.
///
/// v1 identity status: Sign in with Apple is wired on the client
/// (`AppleSignIn`), but the Apple→Supabase token exchange runs server-side at a
/// `/v1/auth/apple` endpoint that ships with the cloud deploy (see the design
/// doc, "Backend changes #2"). Until that's live, `signIn(token:)` lets you run
/// the app against the local or hosted API with a pasted token (or no token on
/// the loopback local tier). The session token is persisted in the Keychain.
@MainActor
@Observable
final class AuthStore {
    enum Session: Equatable {
        case signedOut
        case signedIn
    }

    private enum Keys {
        static let token = "session_token"
        static let baseURL = "base_url"
    }

    private(set) var session: Session
    var baseURLString: String {
        didSet { UserDefaults.standard.set(baseURLString, forKey: Keys.baseURL) }
    }

    /// Surfaced to the Sign in screen when an attempt fails.
    var lastError: String?

    init() {
        self.baseURLString = UserDefaults.standard.string(forKey: Keys.baseURL) ?? Config.defaultBaseURL
        self.session = Keychain.get(Keys.token) != nil || Config.localTierNoAuth
            ? .signedIn
            : .signedOut
    }

    var baseURL: URL {
        URL(string: baseURLString) ?? URL(string: Config.defaultBaseURL)!
    }

    /// A client bound to the current token + base URL. On a hard 401 the store
    /// signs out (v1 has no refresh; that lands with the Supabase session work).
    func makeClient() -> APIClient {
        APIClient(
            baseURL: baseURL,
            tokenProvider: { [weak self] in self?.token() },
            onRefresh: { [weak self] in self?.refresh() ?? false }
        )
    }

    private func token() -> String? { Keychain.get(Keys.token) }

    private func refresh() -> Bool {
        // No refresh path in v1 — a 401 means the session is gone.
        signOut()
        return false
    }

    /// Store a session token (the v2 Apple exchange will call this with the
    /// Supabase access token; today it accepts a pasted token for local/hosted).
    func signIn(token: String) {
        Keychain.set(token, for: Keys.token)
        session = .signedIn
        lastError = nil
    }

    /// Local-tier convenience: loopback API needs no token.
    func continueWithoutAuth() {
        session = .signedIn
        lastError = nil
    }

    func signOut() {
        Keychain.delete(Keys.token)
        session = .signedOut
    }
}
