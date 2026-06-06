# Statusline Resume-Cue Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite `scripts/br8n-statusline.py` from a cross-branch portfolio into a single-focus two-line resume cue: hypothesis + state-adaptive trust bar (drift verdict, age, churn glyphs, action hint).

**Architecture:** Pure-function core (`parse_diff_stat_block`, `compute_drift`, `classify`, `render_line2`) unit-tested in isolation; thin I/O shell (`main`) wires git, SQLite/Supabase fetch, and the never-fail wrapper. Old portfolio renderer preserved behind `BR8N_STATUSLINE=portfolio`.

**Tech Stack:** Python 3.11, stdlib only (sqlite3, subprocess, urllib, re, json, tempfile), pytest for tests.

**Working directory for all commands:** `.worktrees/feat/statusline-resume-cue` (the isolated worktree).

---

### Task 1: Test scaffold + `parse_diff_stat_block`

Parses the `**Git diff stat**:` block from a stored snapshot's `content` field into a set of file paths. This is the foundation for drift computation.

**Files:**
- Create: `scripts/test_statusline.py`
- Modify: `scripts/br8n-statusline.py`

**Step 1: Write the failing tests**

Create `scripts/test_statusline.py`:

```python
"""Tests for br8n-statusline.py pure functions."""
import importlib.util, sys, os, pathlib

# Load the script as a module without executing main()
_SCRIPT = pathlib.Path(__file__).parent / "br8n-statusline.py"
spec = importlib.util.spec_from_file_location("statusline", _SCRIPT)
sl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sl)


# ── parse_diff_stat_block ──────────────────────────────────────────────────

def test_parse_diff_stat_basic():
    content = (
        "**Hypothesis**: fix the thing\n\n"
        "**Git diff stat**:\n```\n"
        " src/foo.py | 3 +++\n"
        " src/bar.py | 1 -\n"
        " 2 files changed, 3 insertions(+), 1 deletion(-)\n"
        "```\n"
    )
    assert sl.parse_diff_stat_block(content) == {"src/foo.py", "src/bar.py"}


def test_parse_diff_stat_empty_content():
    assert sl.parse_diff_stat_block("") == set()
    assert sl.parse_diff_stat_block(None) == set()


def test_parse_diff_stat_no_block():
    assert sl.parse_diff_stat_block("**Hypothesis**: just a thought") == set()


def test_parse_diff_stat_truncated():
    # adapter truncates at _MAX_DIFF_CHARS=2000 chars — summary line may be cut
    content = (
        "**Git diff stat**:\n```\n"
        " a/b/c.py | 5 +++++\n"
        " x/y/z.ts | 2 --\n"
        "```\n"
    )
    assert sl.parse_diff_stat_block(content) == {"a/b/c.py", "x/y/z.ts"}


def test_parse_diff_stat_plus_n_more():
    # git diff --stat can emit " ... and N more" on wide diffs
    content = (
        "**Git diff stat**:\n```\n"
        " src/alpha.py | 1 +\n"
        " ... and 3 more\n"
        "```\n"
    )
    result = sl.parse_diff_stat_block(content)
    assert "src/alpha.py" in result
    assert "... and 3 more" not in result  # not treated as a path
```

**Step 2: Run — expect failure (function missing)**

```bash
cd .worktrees/feat/statusline-resume-cue
python -m pytest scripts/test_statusline.py::test_parse_diff_stat_basic -v
```
Expected: `AttributeError: module 'statusline' has no attribute 'parse_diff_stat_block'`

**Step 3: Implement `parse_diff_stat_block` in `scripts/br8n-statusline.py`**

Add after the ANSI constants block (around line 50), before the git helpers:

```python
# ── diff-stat parsing ────────────────────────────────────────────────────────
_DIFF_BLOCK_RE = re.compile(r"\*\*Git diff stat\*\*:\s*```[^\n]*\n(.*?)```", re.DOTALL)
_DIFF_PATH_RE  = re.compile(r"^\s+(.+?)\s+\|")  # " path/to/file.py | N ±"


def parse_diff_stat_block(content: str | None) -> set:
    """Return the set of file paths from a snapshot's **Git diff stat** block."""
    if not content:
        return set()
    m = _DIFF_BLOCK_RE.search(content)
    if not m:
        return set()
    paths = set()
    for line in m.group(1).splitlines():
        pm = _DIFF_PATH_RE.match(line)
        if pm:
            paths.add(pm.group(1).strip())
    return paths
```

**Step 4: Run all parse tests — expect pass**

```bash
python -m pytest scripts/test_statusline.py -k "parse" -v
```
Expected: 5 tests PASSED

**Step 5: Commit**

```bash
git add scripts/test_statusline.py scripts/br8n-statusline.py
git commit -m "test+feat(statusline): parse_diff_stat_block with tests"
```

---

### Task 2: `compute_drift` and `classify`

**Files:**
- Modify: `scripts/test_statusline.py` (append tests)
- Modify: `scripts/br8n-statusline.py` (add functions)

**Step 1: Append failing tests to `scripts/test_statusline.py`**

```python
# ── compute_drift ──────────────────────────────────────────────────────────

def test_compute_drift_identical():
    files = {"a.py", "b.py"}
    moved, commits = sl.compute_drift(files, files, 0)
    assert moved == 0
    assert commits == 0


def test_compute_drift_files_entered():
    captured = {"a.py"}
    current  = {"a.py", "b.py", "c.py"}  # 2 new files
    moved, commits = sl.compute_drift(captured, current, 0)
    assert moved == 2


def test_compute_drift_files_left():
    captured = {"a.py", "b.py", "c.py"}
    current  = {"a.py"}  # 2 files left the dirty set
    moved, commits = sl.compute_drift(captured, current, 0)
    assert moved == 2


def test_compute_drift_commits():
    moved, commits = sl.compute_drift(set(), set(), 3)
    assert commits == 3


def test_compute_drift_combined():
    captured = {"a.py", "b.py"}
    current  = {"b.py", "c.py"}  # a left, c entered = 2 moved
    moved, commits = sl.compute_drift(captured, current, 1)
    assert moved == 2
    assert commits == 1


# ── classify ──────────────────────────────────────────────────────────────

def test_classify_no_capture():
    state = sl.classify(snapshot=None, age_secs=0, moved=0, commits_since=0)
    assert state == "NO_CAPTURE"


def test_classify_fresh():
    state = sl.classify(snapshot={"hyp": "x"}, age_secs=100, moved=0, commits_since=0)
    assert state == "FRESH"


def test_classify_drifted_by_files():
    state = sl.classify(
        snapshot={"hyp": "x"},
        age_secs=100,
        moved=sl.DRIFT_FILES_WARN,   # exactly at threshold
        commits_since=0,
    )
    assert state == "DRIFTED"


def test_classify_drifted_by_commits():
    state = sl.classify(
        snapshot={"hyp": "x"},
        age_secs=100,
        moved=0,
        commits_since=1,
    )
    assert state == "DRIFTED"


def test_classify_drifted_beats_idle():
    # Age past IDLE threshold but also has commits — should be DRIFTED, not IDLE
    state = sl.classify(
        snapshot={"hyp": "x"},
        age_secs=sl.IDLE_AGE + 100,
        moved=0,
        commits_since=2,
    )
    assert state == "DRIFTED"


def test_classify_idle():
    state = sl.classify(
        snapshot={"hyp": "x"},
        age_secs=sl.IDLE_AGE + 100,
        moved=0,
        commits_since=0,
    )
    assert state == "IDLE"


def test_classify_stale_but_not_idle_is_fresh():
    # Past STALE_AGE but under IDLE_AGE, no drift → FRESH (color changes but state is FRESH)
    state = sl.classify(
        snapshot={"hyp": "x"},
        age_secs=sl.STALE_AGE + 60,
        moved=0,
        commits_since=0,
    )
    assert state == "FRESH"
```

**Step 2: Run — expect failure**

```bash
python -m pytest scripts/test_statusline.py -k "drift or classify" -v
```
Expected: `AttributeError: module 'statusline' has no attribute 'compute_drift'`

**Step 3: Implement `compute_drift` and `classify` in `scripts/br8n-statusline.py`**

Add after `parse_diff_stat_block`:

```python
# ── drift & state ────────────────────────────────────────────────────────────
DRIFT_FILES_WARN = 2        # ≥N files moved in/out of changed-set → drifted
STALE_AGE        = 30 * 60  # 30 min: boundary between fresh (green) and dim
IDLE_AGE         = 24 * 3600  # 1 day: quiet idle threshold


def compute_drift(
    captured_files: set, current_files: set, commits_since: int
) -> tuple[int, int]:
    """Return (moved_file_count, commits_since)."""
    moved = len(captured_files.symmetric_difference(current_files))
    return moved, commits_since


def classify(
    snapshot: dict | None,
    age_secs: float,
    moved: int,
    commits_since: int,
) -> str:
    """Return one of: NO_CAPTURE, DRIFTED, IDLE, FRESH.

    Priority: NO_CAPTURE > DRIFTED > IDLE > FRESH
    DRIFTED beats IDLE — advancing but old is drifted, not idle.
    """
    if snapshot is None:
        return "NO_CAPTURE"
    if commits_since >= 1 or moved >= DRIFT_FILES_WARN:
        return "DRIFTED"
    if age_secs >= IDLE_AGE:
        return "IDLE"
    return "FRESH"
```

**Step 4: Run — expect pass**

```bash
python -m pytest scripts/test_statusline.py -k "drift or classify" -v
```
Expected: 12 tests PASSED

**Step 5: Commit**

```bash
git add scripts/test_statusline.py scripts/br8n-statusline.py
git commit -m "test+feat(statusline): compute_drift + classify with tests"
```

---

### Task 3: `render_line1` and `render_line2`

**Files:**
- Modify: `scripts/test_statusline.py` (append tests)
- Modify: `scripts/br8n-statusline.py` (add functions)

**Step 1: Append failing tests**

```python
# ── render_line1 ──────────────────────────────────────────────────────────

def _strip(s):
    """Strip ANSI codes for assertion."""
    import re
    return re.sub(r"\033\[[0-9;]*m", "", s)


def test_render_line1_with_hypothesis():
    line = _strip(sl.render_line1("br8n", "dev", "fix the thing", width=80))
    assert "🧠 br8n" in line
    assert "▶ dev" in line
    assert '"fix the thing"' in line


def test_render_line1_no_hypothesis():
    line = _strip(sl.render_line1("br8n", "dev", None, width=80))
    assert "▶ dev" in line
    assert '"' not in line  # no empty quotes


def test_render_line1_truncates_hypothesis():
    long_hyp = "x" * 100
    line = _strip(sl.render_line1("br8n", "dev", long_hyp, width=60))
    assert "…" in line


# ── render_line2 ──────────────────────────────────────────────────────────

def test_render_line2_no_capture():
    line = _strip(sl.render_line2("NO_CAPTURE", age_secs=0, moved=0, commits=0,
                                   hypothesis=None, hyp_fits=True, utf8=False))
    assert "no capture" in line
    assert "/br8n:capture" in line


def test_render_line2_fresh_no_action():
    line = _strip(sl.render_line2("FRESH", age_secs=60, moved=0, commits=0,
                                   hypothesis="x", hyp_fits=True, utf8=False))
    assert "fresh" in line
    assert "/resume" not in line
    assert "/br8n:capture" not in line


def test_render_line2_fresh_shows_age():
    line = _strip(sl.render_line2("FRESH", age_secs=300, moved=0, commits=0,
                                   hypothesis="x", hyp_fits=True, utf8=False))
    assert "5m" in line


def test_render_line2_drifted_has_action():
    line = _strip(sl.render_line2("DRIFTED", age_secs=1200, moved=3, commits=1,
                                   hypothesis="x", hyp_fits=True, utf8=False))
    assert "drifted" in line
    assert "/resume" in line


def test_render_line2_drifted_ascii_glyphs():
    line = _strip(sl.render_line2("DRIFTED", age_secs=600, moved=3, commits=1,
                                   hypothesis="x", hyp_fits=True, utf8=False))
    assert "f3" in line   # ASCII fallback for ╓3
    assert "c1" in line   # ASCII fallback for ⎇1


def test_render_line2_drifted_utf8_glyphs():
    line = _strip(sl.render_line2("DRIFTED", age_secs=600, moved=3, commits=1,
                                   hypothesis="x", hyp_fits=True, utf8=True))
    assert "╓3" in line
    assert "⎇1" in line


def test_render_line2_drifted_omits_zero_glyphs():
    line = _strip(sl.render_line2("DRIFTED", age_secs=600, moved=0, commits=1,
                                   hypothesis="x", hyp_fits=True, utf8=True))
    assert "╓" not in line  # 0 files moved — omit


def test_render_line2_idle_quiet():
    line = _strip(sl.render_line2("IDLE", age_secs=90000, moved=0, commits=0,
                                   hypothesis="x", hyp_fits=True, utf8=False))
    assert "idle" in line
    assert "/resume" not in line
    assert "/br8n:capture" not in line


def test_render_line2_idle_echoes_hyp_when_truncated():
    # hypothesis was truncated on line 1 → echo it briefly on line 2
    line = _strip(sl.render_line2("IDLE", age_secs=90000, moved=0, commits=0,
                                   hypothesis="refactor adapter", hyp_fits=False, utf8=False))
    assert "refactor adapter" in line


def test_render_line2_idle_no_echo_when_fits():
    line = _strip(sl.render_line2("IDLE", age_secs=90000, moved=0, commits=0,
                                   hypothesis="refactor adapter", hyp_fits=True, utf8=False))
    # hypothesis already visible on line 1 — don't repeat it
    assert "refactor adapter" not in line
```

**Step 2: Run — expect failure**

```bash
python -m pytest scripts/test_statusline.py -k "render" -v
```
Expected: `AttributeError: module 'statusline' has no attribute 'render_line1'`

**Step 3: Implement `render_line1` and `render_line2`**

Add after `classify` in `scripts/br8n-statusline.py`:

```python
# ── renderers ────────────────────────────────────────────────────────────────

def _utf8_capable() -> bool:
    lang = os.environ.get("LANG", "") + os.environ.get("LC_ALL", "") + os.environ.get("LC_CTYPE", "")
    return "UTF-8" in lang.upper() or "UTF8" in lang.upper()


def render_line1(project: str, branch: str, hypothesis: str | None, width: int) -> tuple[str, bool]:
    """Return (rendered_line1, hyp_fits).

    hyp_fits is True when the hypothesis was not truncated.
    """
    badge = f"{BOLD}{YELLOW}🧠 {project}{RESET}"
    branch_part = f"{BOLD}{GREEN}▶ {branch}{RESET}"
    prefix = f"{badge}  {branch_part}"
    prefix_plain_len = len(f"🧠 {project}  ▶ {branch}")  # rough sans-ANSI width

    if not hypothesis:
        return prefix, True

    # budget = width minus badge/branch/quotes/spaces overhead
    budget = max(20, min(60, width - prefix_plain_len - 4))  # 4 = 2 spaces + 2 quotes
    truncated = len(hypothesis) > budget
    hyp_text = (hypothesis[:budget - 1] + "…") if truncated else hypothesis
    hyp_part = f'  {DIM}"{hyp_text}"{RESET}'
    return prefix + hyp_part, not truncated


def render_line2(
    state: str,
    age_secs: float,
    moved: int,
    commits: int,
    hypothesis: str | None,
    hyp_fits: bool,
    utf8: bool,
) -> str:
    """Return the trust-bar string for line 2."""
    age_str = age_from_secs(age_secs) if age_secs > 0 else ""

    if state == "NO_CAPTURE":
        return f"   {YELLOW}⚡{RESET} no capture yet · {DIM}/br8n:capture to anchor{RESET}"

    if state == "FRESH":
        age_part = f" · captured {age_str} ago" if age_str else ""
        moved_glyph = ""
        if moved > 0:
            g = f"╓{moved}" if utf8 else f"f{moved}"
            moved_glyph = f" · {DIM}{g}{RESET}"
        color = GREEN if age_secs < STALE_AGE else GREY
        return f"   {color}✓{RESET} fresh{age_part}{moved_glyph}"

    if state == "DRIFTED":
        age_part = f" · {age_str} ago" if age_str else ""
        glyphs = []
        if moved > 0:
            glyphs.append(f"╓{moved}" if utf8 else f"f{moved}")
        if commits > 0:
            glyphs.append(f"⎇{commits}" if utf8 else f"c{commits}")
        glyph_part = f" · {DIM}{' '.join(glyphs)}{RESET}" if glyphs else ""
        action = f" · {DIM}/resume to rebuild{RESET}"
        return f"   {YELLOW}⚠{RESET} drifted{age_part}{glyph_part}{action}"

    # IDLE
    age_label = f"idle {age_str}" if age_str else "idle"
    echo = ""
    if hypothesis and not hyp_fits:
        short = truncate(hypothesis, 30)
        echo = f' · last: {DIM}"{short}"{RESET}'
    return f"   {GREY}· {age_label}{echo}{RESET}"


def age_from_secs(secs: float) -> str:
    """Human-readable age from seconds."""
    if secs < 3600:
        return f"{int(secs // 60)}m"
    if secs < 86400:
        return f"{int(secs // 3600)}h"
    return f"{int(secs // 86400)}d"
```

Note: the existing `age()` function in the script parses ISO timestamps; `age_from_secs` is the pure-seconds version used by the renderers and tests. Keep both.

**Step 4: Run — expect pass**

```bash
python -m pytest scripts/test_statusline.py -k "render" -v
```
Expected: 13 tests PASSED

**Step 5: Run all tests so far**

```bash
python -m pytest scripts/test_statusline.py -v
```
Expected: all 30 tests PASSED

**Step 6: Commit**

```bash
git add scripts/test_statusline.py scripts/br8n-statusline.py
git commit -m "test+feat(statusline): render_line1 + render_line2 with tests"
```

---

### Task 4: Integration — `live_diff_files` and `commits_since_capture`

New git helpers that the rewritten `main()` will call. Tested with a real tmpdir git repo.

**Files:**
- Modify: `scripts/test_statusline.py` (append integration tests)
- Modify: `scripts/br8n-statusline.py` (add helpers)

**Step 1: Append integration tests**

```python
# ── live_diff_files + commits_since_capture (integration) ─────────────────
import subprocess, tempfile, pathlib


def _make_repo(tmp: pathlib.Path) -> pathlib.Path:
    """Create a minimal git repo in tmp, return its path."""
    subprocess.run(["git", "init", str(tmp)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp), "config", "user.email", "test@test.com"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp), "config", "user.name", "Test"],
                   check=True, capture_output=True)
    # initial commit so HEAD exists
    (tmp / "README.md").write_text("hi")
    subprocess.run(["git", "-C", str(tmp), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp), "commit", "-m", "init"],
                   check=True, capture_output=True)
    return tmp


def test_live_diff_files_empty(tmp_path):
    repo = _make_repo(tmp_path)
    result = sl.live_diff_files(str(repo))
    assert result == set()


def test_live_diff_files_dirty(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "foo.py").write_text("x = 1")
    result = sl.live_diff_files(str(repo))
    assert "foo.py" in result


def test_commits_since_capture_zero(tmp_path):
    repo = _make_repo(tmp_path)
    # captured_at = now (no commits since)
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    count = sl.commits_since_capture(str(repo), now_iso)
    assert count == 0


def test_commits_since_capture_nonzero(tmp_path):
    repo = _make_repo(tmp_path)
    from datetime import datetime, timezone
    past_iso = "2000-01-01T00:00:00Z"  # far in the past → all commits count
    count = sl.commits_since_capture(str(repo), past_iso)
    assert count >= 1  # at least the "init" commit
```

**Step 2: Run — expect failure**

```bash
python -m pytest scripts/test_statusline.py -k "live_diff or commits_since" -v
```
Expected: `AttributeError: module 'statusline' has no attribute 'live_diff_files'`

**Step 3: Implement the helpers in `scripts/br8n-statusline.py`**

Add after the existing `git()` helper:

```python
def live_diff_files(cwd: str) -> set:
    """Return the set of files currently in the dirty working tree."""
    raw = git(cwd, "diff", "--stat", "HEAD")
    if not raw:
        return set()
    paths = set()
    for line in raw.splitlines():
        m = _DIFF_PATH_RE.match(line)
        if m:
            paths.add(m.group(1).strip())
    return paths


def commits_since_capture(cwd: str, captured_at: str) -> int:
    """Return the number of commits on HEAD since captured_at (ISO 8601)."""
    raw = git(cwd, "rev-list", "--count", f"--since={captured_at}", "HEAD")
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 0
```

**Step 4: Run — expect pass**

```bash
python -m pytest scripts/test_statusline.py -k "live_diff or commits_since" -v
```
Expected: 4 tests PASSED

**Step 5: Run full suite**

```bash
python -m pytest scripts/test_statusline.py -v
```
Expected: all 34 tests PASSED

**Step 6: Commit**

```bash
git add scripts/test_statusline.py scripts/br8n-statusline.py
git commit -m "test+feat(statusline): live_diff_files + commits_since_capture"
```

---

### Task 5: Rewrite `main()` — never-fail integration

Rewrites `main()` to use all the new functions. The old portfolio renderer is preserved behind `BR8N_STATUSLINE=portfolio`. Adds a never-fail integration test that pipes synthetic stdin and checks for exit 0 with two output lines.

**Files:**
- Modify: `scripts/br8n-statusline.py` (rewrite `main`)
- Modify: `scripts/test_statusline.py` (append never-fail + integration tests)

**Step 1: Replace `main()` in `scripts/br8n-statusline.py`**

Locate the existing `main()` function (starts around line 180) and replace it entirely with:

```python
def main() -> None:
    # ── legacy portfolio mode ────────────────────────────────────────────────
    if os.environ.get("BR8N_STATUSLINE") == "portfolio":
        _portfolio_main()
        return

    # ── parse stdin ──────────────────────────────────────────────────────────
    cwd = os.getcwd()
    width = 80
    try:
        data = json.load(sys.stdin)
        cwd = (data.get("workspace") or {}).get("current_dir") or data.get("cwd") or cwd
        width = int((data.get("terminal") or {}).get("width") or 80)
    except Exception:
        pass

    root = git(cwd, "rev-parse", "--show-toplevel")
    if not root:
        return
    cur_branch  = git(cwd, "rev-parse", "--abbrev-ref", "HEAD") or "(detached)"
    cur_project = os.path.basename(root)

    env  = load_env(root)
    tier = resolve_tier(env)
    fetch = (lambda proj: cloud_map(proj, env)) if tier == "cloud" else local_map

    # ── fetch latest snapshot for current branch ─────────────────────────────
    snapshot = None
    age_secs  = 0.0
    try:
        branch_map = fetch(cur_project)
        text, created_at = branch_map.get(cur_branch, (None, None))
        if created_at:
            dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_secs = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())
        if text is not None or created_at is not None:
            # fetch full snapshot content for diff-stat block
            snapshot = {"hyp": text, "created_at": created_at}
    except Exception:
        pass

    # ── drift computation (best-effort) ─────────────────────────────────────
    moved, commits = 0, 0
    try:
        captured_content = _fetch_snapshot_content(cur_project, cur_branch, env, tier)
        captured_files   = parse_diff_stat_block(captured_content)
        current_files    = live_diff_files(root)
        captured_at_str  = (snapshot or {}).get("created_at") or ""
        commits_ct       = commits_since_capture(root, str(captured_at_str)) if captured_at_str else 0
        moved, commits   = compute_drift(captured_files, current_files, commits_ct)
    except Exception:
        pass  # drift failure → render without glyph detail

    state = classify(
        snapshot=snapshot,
        age_secs=age_secs,
        moved=moved,
        commits_since=commits,
    )

    # ── render ───────────────────────────────────────────────────────────────
    utf8   = _utf8_capable()
    hyp    = (snapshot or {}).get("hyp")
    line1, hyp_fits = render_line1(cur_project, cur_branch, hyp, width)
    try:
        line2 = render_line2(state, age_secs, moved, commits, hyp, hyp_fits, utf8)
    except Exception:
        line2 = ""

    if line1:
        sys.stdout.write(line1)
        if line2:
            sys.stdout.write("\n" + line2)
```

Also add `_portfolio_main()` by renaming the old `main()` logic. Find the old `main()` body, extract the portfolio logic into:

```python
def _portfolio_main() -> None:
    """Legacy cross-branch portfolio view (BR8N_STATUSLINE=portfolio)."""
    # [paste the old main() body here verbatim, unchanged]
```

And add the helper that fetches raw snapshot content for diff-stat parsing:

```python
def _fetch_snapshot_content(project: str, branch: str, env: dict, tier: str) -> str | None:
    """Return the content field of the latest snapshot for (project, branch), or None."""
    if tier == "cloud":
        return _cloud_snapshot_content(project, branch, env)
    return _local_snapshot_content(project, branch)


def _local_snapshot_content(project: str, branch: str) -> str | None:
    path = db_path()
    if not os.path.exists(path):
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=0.5)
        conn.execute("PRAGMA query_only = ON")
        row = conn.execute(
            """
            SELECT f.content FROM findings f
            JOIN kbs k      ON f.kb_id = k.id
            JOIN projects p ON k.project_id = p.id
            WHERE p.org_id = ? AND p.name = ? AND k.name = ? AND f.category = 'snapshot'
            ORDER BY f.created_at DESC LIMIT 1
            """,
            (ORG_ID, project, branch),
        ).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def _cloud_snapshot_content(project: str, branch: str, env: dict) -> str | None:
    base = env.get("SUPABASE_URL", "").rstrip("/")
    key  = env.get("SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_ANON_KEY", "")
    if not base or not key:
        return None
    select = f"content,kbs!inner(name,{CLOUD_FK}(name))"
    params = urllib.parse.urlencode([
        ("select", select),
        ("category", "eq.snapshot"),
        ("kbs.name", f"eq.{branch}"),
        ("kbs.projects.name", f"eq.{project}"),
        ("order", "created_at.desc"),
        ("limit", "1"),
    ])
    url = f"{base}/rest/v1/findings?{params}"
    req = urllib.request.Request(url, headers={
        "apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=CLOUD_TIMEOUT) as resp:
            rows = json.load(resp)
        if rows and isinstance(rows, list):
            return rows[0].get("content")
    except Exception:
        pass
    return None
```

**Step 2: Append never-fail + smoke tests**

```python
# ── never-fail assertions ─────────────────────────────────────────────────
import subprocess as _sp


def _run_statusline(stdin_json: str, env: dict | None = None) -> tuple[int, str]:
    """Run the statusline script, return (returncode, stdout)."""
    import pathlib
    script = str(pathlib.Path(__file__).parent / "br8n-statusline.py")
    merged_env = {**os.environ, **(env or {})}
    result = _sp.run(
        ["python3", script],
        input=stdin_json,
        capture_output=True,
        text=True,
        env=merged_env,
        timeout=10,
    )
    return result.returncode, result.stdout


def test_never_fails_garbage_stdin():
    code, _ = _run_statusline("not json at all {{{{")
    assert code == 0


def test_never_fails_non_git_cwd():
    code, _ = _run_statusline(
        '{"cwd": "/tmp"}',
        env={"BR8N_BACKEND": "local", "BR8N_DB_PATH": "/dev/null"},
    )
    assert code == 0


def test_never_fails_git_absent(tmp_path):
    # PATH stripped to no git
    code, _ = _run_statusline(
        json.dumps({"cwd": str(tmp_path)}),
        env={"PATH": "/dev/null", "BR8N_BACKEND": "local"},
    )
    assert code == 0


def test_smoke_local_tier_no_capture(tmp_path):
    """Smoke: run in a real git repo with no br8n DB → exits 0, shows branch."""
    repo = _make_repo(tmp_path)
    db = str(tmp_path / "empty.db")
    code, out = _run_statusline(
        json.dumps({"cwd": str(repo)}),
        env={"BR8N_BACKEND": "local", "BR8N_DB_PATH": db},
    )
    assert code == 0
    # Line 1 should show the project name and branch; line 2 should show no-capture
    assert "no capture" in out or out == ""  # empty is also valid (no root)
```

**Step 3: Run — expect pass**

```bash
python -m pytest scripts/test_statusline.py -v
```
Expected: all tests PASSED (the never-fail ones certainly should; smoke may show "no capture").

**Step 4: Manual smoke check — run the script against this repo**

```bash
echo '{"cwd": "'$(pwd)'"}' | BR8N_BACKEND=local python3 scripts/br8n-statusline.py
```

Expected: two lines — line 1 with `🧠 br8n ▶ feat/statusline-resume-cue`, line 2 with `⚡ no capture yet · /br8n:capture to anchor` (since the test worktree has no snapshots).

**Step 5: Commit**

```bash
git add scripts/br8n-statusline.py scripts/test_statusline.py
git commit -m "feat(statusline): rewrite main() as two-line resume cue; keep portfolio behind BR8N_STATUSLINE=portfolio"
```

---

### Task 6: Final polish — update docstring + verify settings.json

**Files:**
- Modify: `scripts/br8n-statusline.py` (docstring only)
- Read: `.claude/settings.json` (no change needed)

**Step 1: Update the module docstring** (top of file, the triple-quoted string)

Replace the old docstring with:

```python
"""br8n resume-cue statusline.

Renders two lines under the Claude Code prompt:
  Line 1 — 🧠 {project} ▶ {branch}  "{hypothesis}"
  Line 2 — state-adaptive trust bar: verdict · age · drift glyphs · action

Four states: NO_CAPTURE, FRESH, DRIFTED, IDLE.
Drift = files moved in/out of dirty set + commits since capture.
Source of truth: local SQLite (~/.br8n/brain.db) or Supabase (cloud tier).

Legacy portfolio view: BR8N_STATUSLINE=portfolio

Contract: read-only, fast, never fails — degrades gracefully at every level,
always exits 0. A statusline must never break the prompt.
"""
```

**Step 2: Verify settings.json still wires correctly**

```bash
cat .claude/settings.json
```

Expected: `"command": "python3 /Users/suherli/Repositories/br8n/scripts/br8n-statusline.py"` — no change needed.

**Step 3: Run full test suite one final time**

```bash
python -m pytest scripts/test_statusline.py -v --tb=short
```
Expected: all tests PASSED

**Step 4: Final commit**

```bash
git add scripts/br8n-statusline.py
git commit -m "docs(statusline): update module docstring for resume-cue design"
```

---

## Completion

After all tasks pass, use **superpowers:finishing-a-development-branch** to merge or PR.

Summary of commits on this branch:
1. `test+feat(statusline): parse_diff_stat_block with tests`
2. `test+feat(statusline): compute_drift + classify with tests`
3. `test+feat(statusline): render_line1 + render_line2 with tests`
4. `test+feat(statusline): live_diff_files + commits_since_capture`
5. `feat(statusline): rewrite main() as two-line resume cue`
6. `docs(statusline): update module docstring for resume-cue design`
