import XCTest
@testable import Brain2

@MainActor
final class AuthStoreTests: XCTestCase {
    override func setUp() {
        super.setUp()
        Keychain.delete("session_token")
    }

    override func tearDown() {
        Keychain.delete("session_token")
        super.tearDown()
    }

    func testStartsSignedOutWithNoToken() {
        let auth = AuthStore()
        XCTAssertEqual(auth.session, .signedOut)
    }

    func testSignInPersistsTokenAndSignsIn() {
        let auth = AuthStore()
        auth.signIn(token: "tok-123")

        XCTAssertEqual(auth.session, .signedIn)
        XCTAssertEqual(Keychain.get("session_token"), "tok-123")
        // A fresh store reads the persisted session.
        XCTAssertEqual(AuthStore().session, .signedIn)
    }

    func testSignOutClearsToken() {
        let auth = AuthStore()
        auth.signIn(token: "tok-123")
        auth.signOut()

        XCTAssertEqual(auth.session, .signedOut)
        XCTAssertNil(Keychain.get("session_token"))
    }

    func testContinueWithoutAuthSignsInWithoutToken() {
        let auth = AuthStore()
        auth.continueWithoutAuth()

        XCTAssertEqual(auth.session, .signedIn)
        XCTAssertNil(Keychain.get("session_token"))
    }

    func testBaseURLFallsBackToDefaultWhenInvalid() {
        let auth = AuthStore()
        auth.baseURLString = ""
        XCTAssertEqual(auth.baseURL.absoluteString, Config.defaultBaseURL)
    }
}
