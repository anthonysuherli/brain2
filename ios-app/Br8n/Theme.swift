import SwiftUI

/// br8n's visual language, ported from the resume-card CSS so the native app
/// and the webview card read as one product. Deep-red accent, warm paper
/// background, hairline separators.
enum Theme {
    static let accent = Color(hex: 0x9C2C1F)
    static let ink = Color(hex: 0x1D1D1F)
    static let muted = Color(hex: 0x6E6E73)
    static let faint = Color(hex: 0x8A8A8E)

    /// Coverage band → badge colours (foreground, background).
    static func coverageColors(_ coverage: Coverage) -> (fg: Color, bg: Color) {
        switch coverage {
        case .rich: return (Color(hex: 0x1A6B34), Color(hex: 0xD1F0DA))
        case .sparse: return (Color(hex: 0x856404), Color(hex: 0xFFF3CD))
        case .gap: return (accent, Color(hex: 0xFDE8E4))
        }
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: 1
        )
    }
}

/// Best-effort "2h ago" / "yesterday" from an ISO-8601 string. Falls back to the
/// raw date prefix when parsing fails (the server emits a few ISO variants).
enum RelativeTime {
    private static let iso: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    private static let isoPlain = ISO8601DateFormatter()

    private static let relative: RelativeDateTimeFormatter = {
        let f = RelativeDateTimeFormatter()
        f.unitsStyle = .abbreviated
        return f
    }()

    static func ago(_ string: String) -> String {
        guard !string.isEmpty else { return "" }
        let date = iso.date(from: string) ?? isoPlain.date(from: string)
        guard let date else { return String(string.prefix(16)).replacingOccurrences(of: "T", with: " ") }
        return relative.localizedString(for: date, relativeTo: Date())
    }
}
