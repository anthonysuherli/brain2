import SwiftUI

/// Navigation target for a specific repo+branch resume card.
struct ResumeTarget: Hashable {
    let project: String
    let kb: String
}

/// The "glance before standup" screen: cross-repo hotspots + your repos.
struct HomeView: View {
    @Environment(AuthStore.self) private var auth
    @State private var projectsState: LoadState<[ProjectSummary]> = .loading
    @State private var stats: ActivityStats?

    var body: some View {
        NavigationStack {
            Group {
                switch projectsState {
                case .loading:
                    LoadingView()
                case .failed(let message):
                    ErrorView(message: message) { Task { await load() } }
                case .loaded(let projects) where projects.isEmpty:
                    EmptyStateView(
                        title: "No activity yet",
                        message: "Capture from your editor and your repos will show up here.",
                        systemImage: "macbook.and.iphone"
                    )
                case .loaded(let projects):
                    content(projects)
                }
            }
            .navigationTitle("br8n")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Sign out") { auth.signOut() }
                        .tint(Theme.accent)
                }
            }
            .navigationDestination(for: ProjectSummary.self) { RepoDetailView(project: $0) }
            .navigationDestination(for: ResumeTarget.self) {
                ResumeCardView(project: $0.project, kb: $0.kb)
            }
        }
        .task { await load() }
    }

    private func content(_ projects: [ProjectSummary]) -> some View {
        List {
            if let hotspots = stats?.hotspots, !hotspots.repos.isEmpty {
                Section("Hotspots") {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(hotspots.repos) { HotspotChip(hotspot: $0) }
                        }
                        .padding(.vertical, 4)
                    }
                    .listRowInsets(EdgeInsets(top: 4, leading: 12, bottom: 4, trailing: 12))
                }
            }

            Section("Repos") {
                ForEach(projects) { project in
                    NavigationLink(value: project) { RepoRow(project: project) }
                }
            }
        }
        .listStyle(.insetGrouped)
        .refreshable { await load() }
    }

    private func load() async {
        let client = auth.makeClient()
        // Parallel fetch; the repo list is the spine, stats are decorative.
        async let projectsResult = client.projects()
        async let statsResult = try? client.activityStats()

        do {
            let projects = try await projectsResult
            stats = await statsResult
            projectsState = .loaded(projects.sortedByRecency())
        } catch APIError.unauthorized {
            auth.signOut()
        } catch {
            projectsState = .failed((error as? APIError)?.localizedDescription ?? "Couldn't load your repos.")
        }
    }
}

private struct RepoRow: View {
    let project: ProjectSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(project.project)
                .font(.body.weight(.semibold))
                .foregroundStyle(Theme.ink)
            HStack(spacing: 6) {
                Text("^[\(project.kbs.count) branch](inflect: true)")
                if let recent = project.mostRecentActivity {
                    Text("·")
                    Text(RelativeTime.ago(recent))
                }
                if project.totalSnapshots > 0 {
                    Text("·")
                    Text("^[\(project.totalSnapshots) snapshot](inflect: true)")
                }
            }
            .font(.caption)
            .foregroundStyle(Theme.faint)
        }
        .padding(.vertical, 2)
    }
}

private struct HotspotChip: View {
    let hotspot: Hotspot

    var body: some View {
        HStack(spacing: 5) {
            Image(systemName: "flame.fill")
                .font(.caption2)
                .foregroundStyle(Theme.accent)
            Text(hotspot.label)
                .font(.caption.weight(.medium))
                .foregroundStyle(Theme.ink)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(Theme.accent.opacity(0.08), in: Capsule())
    }
}

extension Array where Element == ProjectSummary {
    /// Most-recently-active repos first; never-captured repos sink to the bottom.
    func sortedByRecency() -> [ProjectSummary] {
        sorted { ($0.mostRecentActivity ?? "") > ($1.mostRecentActivity ?? "") }
    }
}

extension ProjectSummary {
    var mostRecentActivity: String? {
        kbs.compactMap(\.lastActivity).max()
    }

    var totalSnapshots: Int {
        kbs.reduce(0) { $0 + $1.snapshotCount }
    }
}
