import AuthenticationServices
import SwiftUI

/// First screen: brand, Sign in with Apple, and a connection config the dev
/// build needs until the hosted `/v1/auth/apple` exchange ships.
struct SignInView: View {
    @Environment(AuthStore.self) private var auth
    @State private var coordinator = AppleSignInCoordinator()
    @State private var showConnection = false

    var body: some View {
        @Bindable var auth = auth

        VStack(spacing: 28) {
            Spacer()

            VStack(spacing: 10) {
                Image(systemName: "brain")
                    .font(.system(size: 56, weight: .light))
                    .foregroundStyle(Theme.accent)
                Text("brain2")
                    .font(.largeTitle.weight(.bold))
                    .foregroundStyle(Theme.ink)
                Text("Pick up exactly where you left off.")
                    .font(.subheadline)
                    .foregroundStyle(Theme.muted)
                    .multilineTextAlignment(.center)
            }

            Spacer()

            VStack(spacing: 14) {
                SignInWithAppleButton(.signIn) { request in
                    request.requestedScopes = [.fullName, .email]
                } onCompletion: { _ in
                    // The native button drives the same flow; the exchange to a
                    // Supabase session is the v2 server step. For now, guide the
                    // user to the connection sheet.
                    showConnection = true
                }
                .signInWithAppleButtonStyle(.black)
                .frame(height: 50)
                .clipShape(RoundedRectangle(cornerRadius: 12))

                Button {
                    showConnection = true
                } label: {
                    Text("Connect to a server")
                        .font(.subheadline.weight(.medium))
                }
                .tint(Theme.accent)

                if let error = auth.lastError {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .multilineTextAlignment(.center)
                }
            }
            .padding(.horizontal, 32)
            .padding(.bottom, 40)
        }
        .sheet(isPresented: $showConnection) {
            ConnectionSheet()
                .presentationDetents([.medium])
        }
    }
}

/// Dev/local connection config: base URL + optional pasted token. Goes away once
/// Sign in with Apple → Supabase exchange is live.
private struct ConnectionSheet: View {
    @Environment(AuthStore.self) private var auth
    @Environment(\.dismiss) private var dismiss
    @State private var token = ""

    var body: some View {
        @Bindable var auth = auth

        NavigationStack {
            Form {
                Section("Server") {
                    TextField("Base URL", text: $auth.baseURLString)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                }
                Section {
                    SecureField("API token (optional)", text: $token)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                } header: {
                    Text("Token")
                } footer: {
                    Text("Leave empty for the loopback local tier. Paste a cloud API token to connect to a hosted server.")
                }
            }
            .navigationTitle("Connect")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Connect") {
                        if token.isEmpty {
                            auth.continueWithoutAuth()
                        } else {
                            auth.signIn(token: token)
                        }
                        dismiss()
                    }
                }
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }
}
