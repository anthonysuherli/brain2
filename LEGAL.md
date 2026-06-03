# brain2 — Legal & Governance Index

> The table of contents for everything that licenses, governs, and protects
> brain2 and its maintainer. brain2 ships under the **MIT License**; this page
> is the map to the documents that surround it.
>
> **Copyright (c) 2026 Anthony Suherli** — see [NOTICE](NOTICE).
>
> *Disclaimer: these are standard open-source governance documents, not legal
> advice. Have counsel review the privacy and trademark documents before
> relying on them commercially.*

## The documents

| Document | Purpose | Protects the founder by… |
|---|---|---|
| [LICENSE](LICENSE) | The MIT License — the actual grant. | The **"AS IS" / no-warranty / no-liability** clause. This is the single most important shield: it caps your legal exposure for a free tool. |
| [NOTICE](NOTICE) | Copyright, trademark carve-out, Delapan relationship, third-party pointer. | Asserts ownership and states clearly that the name and the Delapan engine are *not* part of the MIT grant. |
| [LICENSING.md](LICENSING.md) | Decision record: *why* MIT, alternatives weighed, apply-it checklist. | Documents intent and the brain2-vs-Delapan license split, so the choice is defensible and repeatable. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute + the **inbound = outbound** rule. | Every PR is licensed to you under MIT; no contributor can later claim their code wasn't licensed. |
| [DCO](DCO) | Developer Certificate of Origin 1.1. | Each contributor certifies (via `git commit -s`) they have the right to submit their code — your IP-provenance backstop, lighter than a CLA. |
| [TRADEMARKS.md](TRADEMARKS.md) | Name & logo use policy. | Keeps the **"brain2" name yours** even though the code is free — forks must rename. |
| [SECURITY.md](SECURITY.md) | Private vulnerability disclosure process. | Controlled, coordinated disclosure instead of surprise public zero-days; sets best-effort (not contractual) expectations. |
| [PRIVACY.md](PRIVACY.md) | What brain2 stores, where, and the local-first guarantee. | A clear, honest data statement limits liability and builds trust; documents that the local tier never phones home. |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | Community behavior standards (Contributor Covenant 2.1). | Gives you the stated authority to remove bad actors and contributions. |

## The license split (read this first)

| Project | License | Why |
|---|---|---|
| **brain2** (this repo) | **MIT** | A dev-tool plugin where adoption *is* the value. Maximizes installs, forks, contributions. |
| **Delapan** (the engine brain2 forks) | Source-available / BUSL | Separate work, commercially protected. **Not** covered by this repo's MIT grant. |

Signaling matters: a genuinely-MIT brain2 next to a commercially-protected
Delapan shows you know *when* to give away and *when* to protect.

## Operational risks — cleared 2026-06-03

These are actions, not documents — they protect you more than any license text.
Status after the cleanup pass:

- [x] **Secrets in git history — audited clean, no rewrite needed.** Full-history
  scan: no real `.env` ever committed (only `.env.example`), **zero** hits for
  the shared Supabase project ref, and no real JWT/`sk-`/`tvly-` token blobs in
  any commit. The "secret-pattern" matches were all variable *names*, a
  `"fake-key"` test value, and `fly secrets set …=…` doc placeholders. No
  `git filter-repo` rewrite was required. *(Re-audit if a real key is ever
  committed and pushed.)*
- [x] **Supabase schema ownership documented.** [supabase/README.md](supabase/README.md)
  declares brain2's copy MIT (the author re-licensing their own work), kept in
  sync manually like the rest of the engine fork — no shared file with two
  licenses, no cross-repo dependency.
- [x] **Third-party license inventory generated** →
  [LICENSES/THIRD-PARTY.md](LICENSES/THIRD-PARTY.md). 102 deps, all permissive
  (MIT/BSD/Apache + 3 file-level MPL-2.0), **no GPL/AGPL/LGPL** — compatible with
  MIT distribution. brain2's own package now declares `license = "MIT"` in
  `backend/pyproject.toml`.
- [x] **Year/holder confirmed** — `2026 Anthony Suherli` across all files.

## Applying / maintaining

- The MIT copyright line is `Copyright (c) 2026 Anthony Suherli`.
- Update the year range as the project continues (`2026–<year>`).
- If patent exposure ever becomes a concern, swap MIT → Apache-2.0 (adds an
  explicit patent grant + `NOTICE` conventions). One-file change; see
  [LICENSING.md](LICENSING.md).
- Keep this index in sync when you add or remove a governance document.
