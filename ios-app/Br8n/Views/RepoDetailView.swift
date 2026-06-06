import SwiftUI

/// Branches (KBs) for one repo. Each row leads to that branch's resume card.
struct RepoDetailView: View {
    let project: ProjectSummary

    var body: some View {
        List {
            Section {
                ForEach(project.kbs.sortedByRecency()) { kb in
                    NavigationLink(value: ResumeTarget(project: project.project, kb: kb.kb)) {
                        BranchRow(kb: kb)
                    }
                }
            } header: {
                Text("^[\(project.kbs.count) branch](inflect: true)")
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle(project.project)
        .navigationBarTitleDisplayMode(.inline)
    }
}

private struct BranchRow: View {
    let kb: KBSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Image(systemName: "arrow.triangle.branch")
                    .font(.caption)
                    .foregroundStyle(Theme.muted)
                Text(kb.kb)
                    .font(.body.weight(.medium))
                    .foregroundStyle(Theme.ink)
            }
            HStack(spacing: 6) {
                if let last = kb.lastActivity {
                    Text(RelativeTime.ago(last))
                }
                if kb.snapshotCount > 0 {
                    if kb.lastActivity != nil { Text("·") }
                    Text("^[\(kb.snapshotCount) snapshot](inflect: true)")
                }
            }
            .font(.caption)
            .foregroundStyle(Theme.faint)
        }
        .padding(.vertical, 2)
    }
}

extension Array where Element == KBSummary {
    func sortedByRecency() -> [KBSummary] {
        sorted { ($0.lastActivity ?? "") > ($1.lastActivity ?? "") }
    }
}
