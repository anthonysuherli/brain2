import XCTest
@testable import Brain2

final class APIClientTests: XCTestCase {
    private let baseURL = URL(string: "https://api.example.test")!

    override func tearDown() {
        MockURLProtocol.handler = nil
        super.tearDown()
    }

    func makeClient(token: String? = nil, onRefresh: @escaping () async -> Bool = { false }) -> APIClient {
        APIClient(
            baseURL: baseURL,
            session: MockURLProtocol.makeSession(),
            tokenProvider: { token },
            onRefresh: onRefresh
        )
    }

    func testProjectsDecodesResponse() async throws {
        MockURLProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/v1/projects")
            let body = """
            {"projects":[{"project":"alpha","project_id":"p1","kbs":[
              {"kb":"main","kb_id":"k1","last_activity":"2026-05-30T05:00:00+00:00","snapshot_count":3}]}]}
            """
            return (200, Data(body.utf8))
        }

        let projects = try await makeClient().projects()
        XCTAssertEqual(projects.count, 1)
        XCTAssertEqual(projects[0].project, "alpha")
        XCTAssertEqual(projects[0].kbs.first?.snapshotCount, 3)
    }

    func testResumeRequestsJSONFormatAndDecodes() async throws {
        MockURLProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/v1/resume/alpha/main")
            XCTAssertTrue(request.url?.query?.contains("format=json") ?? false)
            let body = """
            {"coverage":"rich","project":"alpha","kb":"main","snapshot_count":1,
             "hypothesis":"Fix the timeout","snapshots":[{"id":"s1","title":"Fix the timeout","captured_at":"2026-05-30T05:00:00+00:00"}],
             "synopsis":[{"topic":"Scheduler","gloss":"how jobs queue"}],"activity":[],"preamble":"<preamble></preamble>"}
            """
            return (200, Data(body.utf8))
        }

        let card = try await makeClient(token: "tok").resume(project: "alpha", kb: "main")
        XCTAssertEqual(card.coverage, .rich)
        XCTAssertEqual(card.hypothesis, "Fix the timeout")
        XCTAssertEqual(card.snapshots.count, 1)
        XCTAssertEqual(card.synopsis.first?.topic, "Scheduler")
    }

    func testTokenSentAsBearer() async throws {
        MockURLProtocol.handler = { request in
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer abc123")
            return (200, Data(#"{"projects":[]}"#.utf8))
        }
        _ = try await makeClient(token: "abc123").projects()
    }

    func testUnauthorizedRefreshesOnceThenRetries() async throws {
        var calls = 0
        MockURLProtocol.handler = { _ in
            calls += 1
            if calls == 1 { return (401, Data()) }
            return (200, Data(#"{"projects":[]}"#.utf8))
        }
        var refreshed = false
        let client = makeClient(onRefresh: { refreshed = true; return true })

        _ = try await client.projects()
        XCTAssertTrue(refreshed)
        XCTAssertEqual(calls, 2)
    }

    func testPersistentUnauthorizedThrows() async {
        MockURLProtocol.handler = { _ in (401, Data()) }
        let client = makeClient(onRefresh: { false })

        do {
            _ = try await client.projects()
            XCTFail("expected unauthorized")
        } catch {
            XCTAssertEqual(error as? APIError, .unauthorized)
        }
    }

    func testCoverageDecodesUnknownAsGap() throws {
        let body = #"{"coverage":"weird","project":"p","kb":"k","snapshot_count":0,"snapshots":[],"synopsis":[],"activity":[],"preamble":""}"#
        let card = try JSONDecoder().decode(ResumeCard.self, from: Data(body.utf8))
        XCTAssertEqual(card.coverage, .gap)
    }
}
