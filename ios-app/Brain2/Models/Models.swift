import Foundation

// MARK: - Discovery (/v1/projects)

/// One repo (project) with its branches (KBs). Mirrors `ProjectsResponse` in
/// `brain2/api/projects.py`.
struct ProjectsResponse: Codable {
    let projects: [ProjectSummary]
}

struct ProjectSummary: Codable, Identifiable, Hashable {
    let project: String
    let projectId: String
    let kbs: [KBSummary]

    var id: String { projectId }

    enum CodingKeys: String, CodingKey {
        case project
        case projectId = "project_id"
        case kbs
    }
}

struct KBSummary: Codable, Identifiable, Hashable {
    let kb: String
    let kbId: String
    let lastActivity: String?
    let snapshotCount: Int

    var id: String { kbId }

    enum CodingKeys: String, CodingKey {
        case kb
        case kbId = "kb_id"
        case lastActivity = "last_activity"
        case snapshotCount = "snapshot_count"
    }
}

// MARK: - Resume card (/v1/resume/{project}/{kb}?format=json)

/// Coverage band the preamble assigns. Drives the badge colour on the card.
enum Coverage: String, Codable {
    case rich, sparse, gap

    /// Unknown future values decode as `.gap` rather than throwing.
    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = Coverage(rawValue: raw) ?? .gap
    }
}

struct ResumeCard: Codable, Hashable {
    let coverage: Coverage
    let project: String
    let kb: String
    let snapshotCount: Int
    let hypothesis: String?
    let snapshots: [ResumeSnapshot]
    let synopsis: [SynopsisEntry]
    let activity: [ActivityEntry]
    let preamble: String

    enum CodingKeys: String, CodingKey {
        case coverage, project, kb
        case snapshotCount = "snapshot_count"
        case hypothesis, snapshots, synopsis, activity, preamble
    }
}

struct ResumeSnapshot: Codable, Identifiable, Hashable {
    let id: String
    let title: String
    let capturedAt: String

    enum CodingKeys: String, CodingKey {
        case id, title
        case capturedAt = "captured_at"
    }
}

struct SynopsisEntry: Codable, Hashable {
    let topic: String
    let gloss: String
}

/// One cross-repo work session in the resume rollup. The server emits a flexible
/// dict; these are the keys it always sets (see `activity_rollup`).
struct ActivityEntry: Codable, Hashable {
    let repo: String
    let branch: String
    let capturedAt: String
    let hypothesis: String

    enum CodingKeys: String, CodingKey {
        case repo, branch, hypothesis
        case capturedAt = "captured_at"
    }
}

// MARK: - Activity stats (/v1/activity/stats)

struct ActivityStats: Codable {
    let nodeCount: Int
    let edgeCount: Int
    let byType: [String: Int]
    let byRelation: [String: Int]
    let hotspots: Hotspots

    enum CodingKeys: String, CodingKey {
        case nodeCount = "node_count"
        case edgeCount = "edge_count"
        case byType = "by_type"
        case byRelation = "by_relation"
        case hotspots
    }
}

struct Hotspots: Codable {
    let repos: [Hotspot]
    let files: [Hotspot]
    let tasks: [Hotspot]
}

struct Hotspot: Codable, Identifiable, Hashable {
    let label: String
    let degree: Int

    var id: String { label }
}
