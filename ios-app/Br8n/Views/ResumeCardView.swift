import SwiftUI

/// The payoff: a native layout of the JSON resume. Hypothesis leads, then the
/// synopsis, the snapshot timeline, the cross-repo rollup, and a collapsible
/// preamble. This is where reading structured JSON (not a webview) earns its keep.
struct ResumeCardView: View {
    let project: String
    let kb: String

    @Environment(AuthStore.self) private var auth
    @State private var state: LoadState<ResumeCard> = .loading

    var body: some View {
        Group {
            switch state {
            case .loading:
                LoadingView()
            case .failed(let message):
                ErrorView(message: message) { Task { await load() } }
            case .loaded(let card):
                loaded(card)
            }
        }
        .navigationTitle(kb)
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func loaded(_ card: ResumeCard) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header(card)

                if let hypothesis = card.hypothesis, !hypothesis.isEmpty {
                    HypothesisBlock(text: hypothesis)
                }

                if !card.synopsis.isEmpty {
                    Section(label: "Context") {
                        VStack(alignment: .leading, spacing: 10) {
                            ForEach(card.synopsis, id: \.topic) { SynopsisRow(entry: $0) }
                        }
                    }
                }

                if !card.snapshots.isEmpty {
                    Section(label: "Recent snapshots") {
                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(card.snapshots) { SnapshotRow(snapshot: $0) }
                        }
                    }
                }

                if !card.activity.isEmpty {
                    Section(label: "Across repos") {
                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(card.activity, id: \.self) { ActivityRow(entry: $0) }
                        }
                    }
                }

                PreambleDisclosure(xml: card.preamble)
            }
            .padding()
        }
        .background(Color(hex: 0xFAFAF8))
    }

    private func header(_ card: ResumeCard) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("\(card.project) / \(card.kb)")
                    .font(.headline)
                    .foregroundStyle(Theme.ink)
                Spacer()
                CoverageBadge(coverage: card.coverage)
            }
            if card.snapshotCount > 0 {
                Text("^[\(card.snapshotCount) snapshot](inflect: true)")
                    .font(.caption)
                    .foregroundStyle(Theme.faint)
            }
        }
    }

    private func load() async {
        do {
            let card = try await auth.makeClient().resume(project: project, kb: kb)
            state = .loaded(card)
        } catch APIError.unauthorized {
            auth.signOut()
        } catch {
            state = .failed((error as? APIError)?.localizedDescription ?? "Couldn't load this card.")
        }
    }
}

// MARK: - Building blocks

private struct Section<Content: View>: View {
    let label: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(label.uppercased())
                .font(.caption2.weight(.semibold))
                .tracking(1)
                .foregroundStyle(Theme.muted)
            content
        }
    }
}

private struct HypothesisBlock: View {
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("HYPOTHESIS")
                .font(.caption2.weight(.semibold))
                .tracking(1)
                .foregroundStyle(Theme.accent)
            Text(text)
                .font(.title3.weight(.medium))
                .foregroundStyle(Theme.ink)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(.white, in: RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(Theme.accent.opacity(0.18), lineWidth: 1)
        )
    }
}

private struct SynopsisRow: View {
    let entry: SynopsisEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(entry.topic)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(Theme.accent)
            Text(entry.gloss)
                .font(.subheadline)
                .foregroundStyle(Theme.ink)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

private struct SnapshotRow: View {
    let snapshot: ResumeSnapshot

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(snapshot.title)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(Theme.ink)
            if !snapshot.capturedAt.isEmpty {
                Text(RelativeTime.ago(snapshot.capturedAt))
                    .font(.caption.monospaced())
                    .foregroundStyle(Theme.faint)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(.white, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(.black.opacity(0.06)))
    }
}

private struct ActivityRow: View {
    let entry: ActivityEntry

    private var location: String {
        entry.branch.isEmpty ? entry.repo : "\(entry.repo)/\(entry.branch)"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            if !location.isEmpty {
                Text(location)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(Theme.ink)
            }
            HStack(spacing: 6) {
                if !entry.capturedAt.isEmpty {
                    Text(RelativeTime.ago(entry.capturedAt))
                }
                if !entry.hypothesis.isEmpty {
                    Text("·")
                    Text(entry.hypothesis).lineLimit(1)
                }
            }
            .font(.caption)
            .foregroundStyle(Theme.faint)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(.white, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(.black.opacity(0.06)))
    }
}

private struct PreambleDisclosure: View {
    let xml: String
    @State private var expanded = false

    var body: some View {
        DisclosureGroup(isExpanded: $expanded) {
            ScrollView(.horizontal, showsIndicators: false) {
                Text(xml)
                    .font(.caption2.monospaced())
                    .foregroundStyle(Theme.muted)
                    .textSelection(.enabled)
                    .padding(.top, 6)
            }
        } label: {
            Text("Preamble")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Theme.muted)
        }
        .tint(Theme.muted)
    }
}
