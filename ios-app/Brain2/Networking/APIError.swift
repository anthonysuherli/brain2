import Foundation

/// Errors surfaced to the UI as the three states every screen handles.
enum APIError: Error, LocalizedError, Equatable {
    /// No valid session — route to Sign in.
    case unauthorized
    /// Transport/server failure with an optional HTTP status.
    case server(status: Int?)
    /// Response body didn't match the expected shape.
    case decoding(String)
    /// No network / request couldn't be sent.
    case offline

    var errorDescription: String? {
        switch self {
        case .unauthorized:
            return "Your session expired. Sign in again."
        case .server(let status):
            if let status { return "Server error (\(status)). Try again." }
            return "Server error. Try again."
        case .decoding:
            return "Unexpected response from the server."
        case .offline:
            return "You're offline. Check your connection and retry."
        }
    }
}
