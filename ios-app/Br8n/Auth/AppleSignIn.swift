import AuthenticationServices
import Foundation

/// Bridges `ASAuthorizationController`'s delegate callbacks into an async call.
///
/// Returns the Apple `identityToken` (a signed JWT). v1 captures it; the v2
/// cloud deploy adds the `/v1/auth/apple` endpoint that exchanges this token for
/// a Supabase session (see the design doc). Until then, `SignInView` uses the
/// manual-token path; this coordinator is the real native flow it will swap to.
@MainActor
final class AppleSignInCoordinator: NSObject, ASAuthorizationControllerDelegate {
    private var continuation: CheckedContinuation<AppleCredential, Error>?

    struct AppleCredential {
        let userID: String
        let identityToken: String
        let email: String?
        let fullName: PersonNameComponents?
    }

    func signIn() async throws -> AppleCredential {
        try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation
            let request = ASAuthorizationAppleIDProvider().createRequest()
            request.requestedScopes = [.fullName, .email]
            let controller = ASAuthorizationController(authorizationRequests: [request])
            controller.delegate = self
            controller.performRequests()
        }
    }

    func authorizationController(
        controller: ASAuthorizationController,
        didCompleteWithAuthorization authorization: ASAuthorization
    ) {
        guard
            let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
            let tokenData = credential.identityToken,
            let token = String(data: tokenData, encoding: .utf8)
        else {
            continuation?.resume(throwing: APIError.server(status: nil))
            continuation = nil
            return
        }
        continuation?.resume(returning: AppleCredential(
            userID: credential.user,
            identityToken: token,
            email: credential.email,
            fullName: credential.fullName
        ))
        continuation = nil
    }

    func authorizationController(
        controller: ASAuthorizationController,
        didCompleteWithError error: Error
    ) {
        continuation?.resume(throwing: error)
        continuation = nil
    }
}
