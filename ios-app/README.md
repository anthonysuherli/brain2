# brain2 iOS companion

A native SwiftUI app — the first standalone UI for brain2. v1 is the **read
spine**: Sign in, browse your cross-repo activity, and read resume cards on your
phone. Capture and push notifications are v2.

Design: [`docs/plans/2026-05-30-ios-companion-design.md`](../docs/plans/2026-05-30-ios-companion-design.md).

## What it does (v1)

- **Home** — your repos (most-recently-active first) with branch counts, last
  activity, and a cross-repo "hotspots" strip from the activity graph.
- **Repo → branches** — drill into a repo's branches (KBs).
- **Resume card** — the payoff: a native layout of the JSON resume (hypothesis
  up top, synopsis, snapshot timeline, cross-repo rollup, collapsible preamble).

It talks to the brain2 cloud API over three reads: `GET /v1/projects`,
`GET /v1/resume/{project}/{kb}?format=json`, and `GET /v1/activity/stats`.

## Project layout

```
Brain2/
  Brain2App.swift          @main + RootView (routes Sign in vs Home)
  Config.swift             default base URL + local-tier flag
  Theme.swift              colours (brain2 accent) + relative-time helper
  Models/Models.swift      Codable mirrors of the API contracts
  Networking/              APIClient (async URLSession, Bearer, 401→refresh→retry)
  Auth/                    Keychain, AuthStore (@Observable session), Apple Sign In
  Views/                   SignIn, Home, RepoDetail, ResumeCard, shared Components
Brain2Tests/               APIClient + AuthStore tests (URLProtocol-mocked)
project.yml                XcodeGen spec
```

## Build

The repo ships sources + an [XcodeGen](https://github.com/yonaskolb/XcodeGen)
spec rather than a checked-in `.xcodeproj` (cleaner diffs).

```bash
brew install xcodegen        # once
cd ios-app
xcodegen generate            # writes Brain2.xcodeproj
open Brain2.xcodeproj        # build/run on the iOS 17+ simulator
```

Requires a full **Xcode** install (not just Command Line Tools).

### Pointing it at a server

- **Local tier (simulator):** run `BRAIN2_BACKEND=local python -m brain2.api.main`
  in `backend/`. The app defaults to `http://127.0.0.1:8002` and the Info.plist
  allows loopback http. On the Sign in screen tap **Connect to a server** and
  leave the token empty (the local tier is loopback, no auth).
- **Hosted/cloud tier:** set the base URL to your deployed origin (e.g.
  `https://api.brain2.dev`) and paste a cloud API token.

## Auth status

Sign in with Apple is wired on the client (`Auth/AppleSignIn.swift` +
`SignInWithAppleButton`), but the **Apple → Supabase session exchange** runs
server-side at a `/v1/auth/apple` endpoint that ships with the cloud deploy (see
the design doc, "Backend changes #2"). Until that's live, use **Connect to a
server** to run against the local or hosted API. Sign in with Apple also needs a
paid Apple Developer team set in `project.yml` (`DEVELOPMENT_TEAM`) and the
capability enabled on the App ID.

## Tests

In Xcode: ⌘U. The data layer (model decoding, the API client's path/format/
Bearer/401 behaviour) and the auth state machine are covered without a network.
