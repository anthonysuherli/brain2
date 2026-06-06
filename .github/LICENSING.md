# Licensing — br8n

> Decision record + apply-it playbook for open-sourcing this repo.
> Status: **applied + cleaned (2026-06-03).** `LICENSE` (MIT) and the
> founder-protection doc set are committed — see [LEGAL.md](LEGAL.md) for the
> full index. Both operational risks are now cleared: git history was **audited
> clean** of secrets (no `filter-repo` rewrite needed), Supabase schema
> ownership is documented in [supabase/README.md](../supabase/README.md), and the
> third-party inventory is generated at
> [LICENSES/THIRD-PARTY.md](../LICENSES/THIRD-PARTY.md).

## TL;DR

br8n ships under the **MIT License** — fully permissive, OSI-approved "open source."
Anyone may use, modify, and redistribute it, including in closed-source and commercial
products, with no obligations beyond preserving the copyright notice.

br8n is a developer tool (a Claude Code plugin: cross-repo activity/session knowledge
graph). For a tool like this, **adoption is the value** — installs, forks, and
contributions matter more than commercial control. MIT maximizes all three.

## Why MIT (and not the alternatives)

| Option | Verdict |
|---|---|
| **MIT** | ✅ Shortest, most familiar, max adoption. Right for a dev-tool plugin. **Chosen.** |
| Apache-2.0 | ⚠️ Also fine — adds an explicit patent grant + `NOTICE` file, more enterprise-credible. Swap to this if patent exposure ever becomes a concern (one-file change). |
| BUSL / source-available | ❌ Wrong tool here. Nothing to protect commercially; restrictions only suppress adoption. (That model is reserved for the Delapan engine.) |

> **Portfolio note:** keeping br8n genuinely MIT gives you a real OSI-approved
> open-source project to point to alongside the commercially-protected Delapan —
> signaling you know *when* to protect and *when* to give away.

## The copyright line

When you create the `LICENSE` file from the [MIT template](https://opensource.org/license/mit),
use:

```
Copyright (c) 2026 Anthony Suherli
```

## What this means in practice

| Actor | Allowed? |
|---|---|
| Use br8n for anything, including commercially | ✅ |
| Fork, modify, redistribute (open or closed source) | ✅ |
| Submit a PR | ✅ |
| Remove the copyright notice | ❌ (the one MIT obligation) |
| Use the name "br8n" for their own product | ❌ (trademark, not granted by MIT) |

## Dependency note

MIT imposes no license-compatibility constraints on your dependencies (unlike BUSL),
so no copyleft audit is strictly required to *publish*. Still worth a quick pass so the
README's third-party inventory is honest:

```bash
# adjust per br8n's actual stack (backend/ + ios-app/ + site/)
pip-licenses --format=markdown        # if Python
npx license-checker --summary         # if Node
```

## Apply-it checklist

- [x] **Scrub secrets from git *history*** — **audited, none found.** No real
      `.env` ever committed, zero hits for the shared Supabase project ref, no
      real key/token blobs in any commit. No `git filter-repo` rewrite needed.
- [x] **Untangle the shared Supabase schema from Delapan** — documented in
      [supabase/README.md](../supabase/README.md): br8n owns its copy under MIT
      (author re-licensing own work), synced manually, no cross-repo dep.
- [x] Create `LICENSE` from the MIT template with the copyright line above.
- [x] Add `LICENSES/THIRD-PARTY.md` — dependency inventory (102 deps, all
      permissive, no copyleft).
- [x] Add the **License** section to `README.md` (template below).
- [x] Assert trademark on "br8n" — see [TRADEMARKS.md](TRADEMARKS.md) + README footer.
- [x] Founder-protection doc set: `NOTICE`, `CONTRIBUTING.md` + `DCO`, `SECURITY.md`,
      `PRIVACY.md`, `CODE_OF_CONDUCT.md`, indexed by [LEGAL.md](LEGAL.md).

## README "License" section (paste into README.md)

```markdown
## License

br8n is open source under the [MIT License](../LICENSE) — use it for anything,
including commercially, as long as the copyright notice is preserved.

"br8n" is a name used by Anthony Suherli; the license covers the code, not the name.
```

## If you later want the patent grant

Swap MIT → Apache-2.0: replace `LICENSE` with the Apache-2.0 text, add a `NOTICE` file,
and update the README section. No other change. Do this only if br8n grows enough that
patent exposure (yours or a contributor's) becomes a real concern.
