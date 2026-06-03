# Privacy & Data Handling — brain2

> brain2 is **local-first**. By default your captured context never leaves your
> machine. This document explains what brain2 stores, where, and what the
> optional cloud tier changes.

This is a plain-language statement of how the brain2 software handles data. It
is not a contract. The software is provided "AS IS" under the [MIT
License](../LICENSE), without warranty.

## What brain2 captures

brain2's job is to remember your working context. When you capture, it records:

- the current git branch, repo, and a diff stat;
- which files were open and the cursor position;
- a one-line "hypothesis" you write describing what you're doing;
- derived structure for the cross-repo activity knowledge graph (repos,
  branches, files, work sessions, and distilled tasks).

**You decide when to capture.** brain2 does not silently record in the
background; capture is an explicit command.

## Where it's stored

### Free / local tier (default)

- All data is stored on your machine in a local SQLite database at
  `~/.brain2/brain.db` (override with `BRAIN2_DB_PATH`).
- The local API binds to `127.0.0.1` only and is not reachable off-device.
- **No data is transmitted to the maintainer or any third party.** There is no
  telemetry, no analytics beacon, and no usage reporting in the local tier.

### Paid / cloud tier (optional, opt-in)

- If you choose the cloud tier, captures are stored in a Supabase backend
  (Postgres + pgvector) scoped to your organization via row-level security.
- Authentication is via Supabase GoTrue (e.g. Sign in with Apple). Your data is
  scoped to your own org; the design goal is that no other tenant can read it.
- You are sending your captured context to a hosted service when you use this
  tier. Choose what you capture accordingly.

## Secrets and sensitive data

Because brain2 snapshots git diffs and open files, a capture **can include
secrets** that happen to be in your working tree (API keys, `.env` values,
tokens). brain2 does not scrub these for you. Treat your brain2 store with the
same care as your source tree, and avoid capturing while secrets are staged in
the diff.

## Third parties

- The local tier contacts no third party for storage.
- The optional **explore / gap-fill** feature and any LLM-backed distillation
  send the relevant prompt/content to the configured AI provider/model gateway
  to do their work. This happens only when you invoke those features. Review
  your provider's data policy; do not run explore over sensitive content you
  don't want sent to that provider.
- The cloud tier uses Supabase as the storage processor.

## Your control

- Delete your local store at any time: remove `~/.brain2/brain.db`.
- The local tier is fully functional offline and never phones home.
- No selling of data, ever. brain2's business model (if any) is the hosted
  tier's convenience, not your data.

## Changes

This statement may change as brain2 evolves. The current version always lives
in this file in the official repository.

*Last updated: 2026-06-03.*
