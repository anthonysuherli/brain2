import Foundation

/// Build-time defaults. The base URL is overridable at runtime from the Sign in
/// screen (stored in `UserDefaults`); these are just the first-launch values.
enum Config {
    /// Default API origin. Points at the loopback dev server so the app runs
    /// against `python -m br8n.api.main` out of the box on a simulator; change
    /// to the hosted origin (e.g. https://api.br8n.dev) for device builds.
    static let defaultBaseURL = "http://127.0.0.1:8002"

    /// When true, the app treats the backend as the no-auth loopback local tier
    /// and skips the Sign in gate. Off for hosted/cloud builds.
    static let localTierNoAuth = false
}
