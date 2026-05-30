import SwiftUI

/// Coverage band pill — same three states as the webview card.
struct CoverageBadge: View {
    let coverage: Coverage

    var body: some View {
        let colors = Theme.coverageColors(coverage)
        Text(coverage.rawValue.uppercased())
            .font(.caption2.weight(.bold))
            .tracking(0.5)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .foregroundStyle(colors.fg)
            .background(colors.bg, in: Capsule())
    }
}

/// Skeleton placeholder rows — shown on payoff screens instead of a bare spinner.
struct LoadingView: View {
    var rows = 4

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(0..<rows, id: \.self) { _ in
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.gray.opacity(0.12))
                    .frame(height: 56)
            }
        }
        .padding()
        .redacted(reason: .placeholder)
        .accessibilityLabel("Loading")
    }
}

/// Intentional empty state — distinct from an error. Day-one before any capture.
struct EmptyStateView: View {
    let title: String
    let message: String
    var systemImage = "tray"

    var body: some View {
        ContentUnavailableView {
            Label(title, systemImage: systemImage)
        } description: {
            Text(message)
        }
    }
}

/// Recoverable error with a retry affordance — never a dead end.
struct ErrorView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        ContentUnavailableView {
            Label("Something went wrong", systemImage: "exclamationmark.triangle")
        } description: {
            Text(message)
        } actions: {
            Button("Retry", action: retry)
                .buttonStyle(.borderedProminent)
                .tint(Theme.accent)
        }
    }
}

/// A small async-state machine the screens reuse: loading → loaded | empty | error.
enum LoadState<Value> {
    case loading
    case loaded(Value)
    case failed(String)
}
