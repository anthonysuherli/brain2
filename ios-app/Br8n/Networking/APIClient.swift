import Foundation

/// Thin async REST client for the br8n cloud API.
///
/// Read-only in v1: it fetches the three surfaces the home + card screens need.
/// Auth is injected as closures so the client stays decoupled from `AuthStore`
/// (and trivially testable): `tokenProvider` supplies the current Bearer token,
/// `onRefresh` is called once on a 401 to silently refresh before one retry.
final class APIClient {
    private let baseURL: URL
    private let session: URLSession
    private let tokenProvider: () async -> String?
    private let onRefresh: () async -> Bool
    private let decoder: JSONDecoder

    init(
        baseURL: URL,
        session: URLSession = .shared,
        tokenProvider: @escaping () async -> String? = { nil },
        onRefresh: @escaping () async -> Bool = { false }
    ) {
        self.baseURL = baseURL
        self.session = session
        self.tokenProvider = tokenProvider
        self.onRefresh = onRefresh
        self.decoder = JSONDecoder()
    }

    // MARK: - Endpoints

    func projects() async throws -> [ProjectSummary] {
        let res: ProjectsResponse = try await get("/v1/projects")
        return res.projects
    }

    func resume(project: String, kb: String) async throws -> ResumeCard {
        try await get(
            "/v1/resume/\(escape(project))/\(escape(kb))",
            query: [URLQueryItem(name: "format", value: "json")]
        )
    }

    func activityStats() async throws -> ActivityStats {
        try await get("/v1/activity/stats")
    }

    // MARK: - Core

    private func get<T: Decodable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        let data = try await send(path: path, query: query, allowRefresh: true)
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(String(describing: error))
        }
    }

    private func send(path: String, query: [URLQueryItem], allowRefresh: Bool) async throws -> Data {
        guard var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false) else {
            throw APIError.server(status: nil)
        }
        if !query.isEmpty { components.queryItems = query }
        guard let url = components.url else { throw APIError.server(status: nil) }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token = await tokenProvider() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.offline
        }

        guard let http = response as? HTTPURLResponse else {
            throw APIError.server(status: nil)
        }

        switch http.statusCode {
        case 200..<300:
            return data
        case 401:
            // Silent refresh + one retry; a second 401 means re-auth.
            if allowRefresh, await onRefresh() {
                return try await send(path: path, query: query, allowRefresh: false)
            }
            throw APIError.unauthorized
        default:
            throw APIError.server(status: http.statusCode)
        }
    }

    private func escape(_ segment: String) -> String {
        segment.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? segment
    }
}
