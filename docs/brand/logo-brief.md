# brain2 — Logo Design Instruction (for Claude)

> Paste this whole file to Claude (or any design-capable model/designer) and say:
> **"Generate logo ideas for brain2 following this brief."**
> It is written so Claude can produce concept directions, then render candidates as SVG.

---

## 1. What you're branding

**brain2** is a context-capture and resume engine for developers. It captures a
developer's working intent the moment they get interrupted and replays it as a
30-second "resume card" when they return — killing the ~9.5-minute cost of
rebuilding "where was I?" in your head.

One-line essence: **brain2 remembers where you were so you don't have to rebuild it.**

Mental model words: **memory, resume, snapshot, pick-up-where-you-left-off,
continuity, recall, working state, second brain.**

It is a developer tool (CLI / Claude Code plugin / MCP / iOS companion). The
audience is engineers — so the mark must read at terminal scale and feel native
to a dev toolchain, not consumer-cute.

---

## 2. Design constraints (hard requirements)

- **Works as a 16×16 favicon and a 1024×1024 app icon.** No fine detail that
  collapses when small. Test legibility at 16px in your head before proposing.
- **Monochrome-first.** Must survive as a single solid color (black on white,
  white on black). Color is a layer added on top, never load-bearing.
- **Square-safe and circle-safe.** Should sit comfortably inside the iOS rounded-rect
  and inside a circular avatar without awkward cropping.
- **No literal anatomical brain.** The "brain" cliché (wrinkled organ) is banned —
  it's overused, ages badly, and doesn't say *resume*. Abstract it.
- **The "2" is a feature, not a suffix.** Treat it as "second brain" / "v2 of your
  memory," not a version number bolted on. It can be integral to the mark or omitted
  from the symbol and carried only in the wordmark — propose both.
- **Vector-native.** Final output as clean SVG with simple, unionable paths.

---

## 3. Concept directions to explore (generate ≥5, one per idea)

For each, give: a name, the core metaphor, why it fits brain2, and an SVG sketch.

1. **Bookmark / resume marker** — a bookmark ribbon, a "pin where I was" tab, or a
   play/resume triangle fused with a saved-state dot. Says *pick up exactly here*.
2. **Snapshot bracket** — camera-shutter or `[ ]` capture brackets framing a cursor
   or caret, evoking "capture the current state." Plays well with code aesthetics.
3. **Restore loop** — a circular/return arrow (↺) that loops back to a node, i.e.
   "replay where you left off." Continuity made geometric.
4. **Two-state braid / second brain** — two strokes (past state ↔ resumed state)
   converging, where the negative space or the join forms a "2."
5. **Node + thread (activity graph)** — a small constellation of connected nodes
   (the cross-repo activity graph), with one node lit as "you are here."
6. **Caret/cursor as identity** — the text caret `|` or `▌` as the hero glyph —
   the most native-to-developers symbol of "where you are." Combine with a memory dot.

Encouraged: the strongest marks will **fuse two of these** (e.g. a resume-triangle
that is also the join of a "2", or a caret that doubles as a bookmark).

---

## 4. Visual style targets

- **Geometric, confident, minimal.** Think Vercel / Linear / Raycast register:
  precise, slightly technical, zero gradients-as-crutch.
- **Stroke logic:** pick ONE — either a solid filled mark or a consistent-weight
  stroke mark. Don't mix. If stroke, keep weight optically even at small sizes.
- **Negative space is welcome** but must still resolve at 16px (don't hide the whole
  concept in a sliver of whitespace that disappears).
- **Wordmark:** lowercase `brain2` reads friendlier and more dev-native than
  `Brain2`. The `2` may be a subscript-style or same-baseline. Propose a geometric
  sans (e.g. Inter / Geist / IBM Plex Sans register) — name a specific typeface.

### Color
- Primary palette: propose ONE accent color + neutral. Lean toward a calm,
  trustworthy, "memory/recall" feel — deep indigo/violet or a steady teal both fit
  "thinking + reliable." Avoid alarm-red and generic startup-blue.
- Provide hex values. Provide the monochrome version first, then the colored one.
- Must pass contrast on both light and dark editor backgrounds (it lives in IDEs).

---

## 5. Deliverables (what to return)

For the brief overall:
1. **5–7 distinct concept directions**, each with a 1–2 sentence rationale.
2. For your **top 3**, render an actual **inline SVG** (symbol only) at a viewBox
   that works square. Keep paths minimal and named.
3. For your **#1 pick**, also render: the **lockup** (symbol + `brain2` wordmark,
   horizontal), and a **16px monochrome** version description (what survives, what
   you'd drop).
4. A short **"why this wins"** paragraph tying it back to *capture → resume → continuity*.

---

## 6. Anti-patterns (do NOT do)

- ❌ A realistic/wrinkled brain, a brain with a lightbulb, or a brain with gears.
- ❌ A robot head, a chat bubble, or a generic "AI sparkle."
- ❌ Detail that dies below 32px.
- ❌ Color doing the work a shape should do.
- ❌ Treating "2" as a tacked-on version badge.
- ❌ More than two metaphors crammed into one mark.

---

## 7. Self-check before you present

- Does it still read at 16px in one color? (If not, simplify.)
- Could a developer guess it's about *memory / resume* without the wordmark?
- Is it distinct from the AI-tool herd (sparkles, chat bubbles, neural nets)?
- Does the "2" earn its place as *second brain*, not *version 2*?
