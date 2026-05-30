#!/usr/bin/env python3
"""brain2 branch/worktree statusline.

Renders, under the Claude Code prompt box, the live feature being worked on per
git worktree (or per local branch). Each entry's "feature" is the latest captured
hypothesis pulled from the brain2 session KB.

Source of truth follows the active tier (same selection rule as the engine):
  * cloud  — query Supabase via PostgREST (creds from backend/.env). Cached to a
             temp file with a short TTL so we don't hit the network every render.
  * local  — query ~/.brain2/brain.db (SQLite, local tier).
Tier is cloud iff Supabase creds are present and BRAIN2_BACKEND != "local".

Wire it in settings.json:

    "statusLine": {
      "type": "command",
      "command": "python3 /Users/suherli/Repositories/brain2/scripts/brain2-statusline.py"
    }

Contract: read-only, fast, and never fails — on any error it degrades to just the
current branch (or nothing) and exits 0, because a statusline must never break the
prompt. Mapping matches brain2 capture convention: project = repo dir basename,
kb = git branch.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# ── tunables ────────────────────────────────────────────────────────────────
MAX_ENTRIES = 5            # branches/worktrees to show before "+N more"
HYP_WIDTH = 38             # truncate each hypothesis to this many chars
ORG_ID = "local"           # local-tier synthetic tenant
CLOUD_TTL = 8.0            # seconds a cloud result stays fresh on disk
CLOUD_TIMEOUT = 1.5        # seconds before a Supabase request is abandoned
CLOUD_FK = "projects!kbs_project_id_fkey!inner"  # disambiguate kbs→projects FK

# ── ANSI (statuslines render ANSI) ──────────────────────────────────────────
RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
GREEN, CYAN, YELLOW, GREY = "\033[32m", "\033[36m", "\033[33m", "\033[90m"

_HYP_RE = re.compile(r"\*\*Hypothesis\*\*:\s*(.+)", re.IGNORECASE)


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


# ── renderers ────────────────────────────────────────────────────────────────

def _utf8_capable() -> bool:
    lang = os.environ.get("LANG", "") + os.environ.get("LC_ALL", "") + os.environ.get("LC_CTYPE", "")
    return "UTF-8" in lang.upper() or "UTF8" in lang.upper()


def render_line1(project: str, branch: str, hypothesis: str | None, width: int) -> tuple[str, bool]:
    """Return (rendered_line1, hyp_fits). hyp_fits=False means hypothesis was truncated."""
    badge = f"{BOLD}{YELLOW}🧠 {project}{RESET}"
    branch_part = f"{BOLD}{GREEN}▶ {branch}{RESET}"
    prefix = f"{badge}  {branch_part}"
    prefix_plain_len = len(f"🧠 {project}  ▶ {branch}")

    if not hypothesis:
        return prefix, True

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
        return f"   {YELLOW}⚡{RESET} no capture yet · {DIM}/brain2:capture to anchor{RESET}"

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
    """Human-readable age from seconds (pure, no datetime needed)."""
    if secs < 3600:
        return f"{int(secs // 60)}m"
    if secs < 86400:
        return f"{int(secs // 3600)}h"
    return f"{int(secs // 86400)}d"


# ── git helpers ─────────────────────────────────────────────────────────────
def git(cwd: str, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", cwd, *args], capture_output=True, text=True, timeout=2
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


_STATUS_PATH_RE = re.compile(r"^.{2} (.+)$")  # " XY path" from git status --short


def live_diff_files(cwd: str) -> set:
    """Return the set of files currently dirty (modified, staged, or untracked)."""
    raw = git(cwd, "status", "--short")
    if not raw:
        return set()
    paths = set()
    for line in raw.splitlines():
        m = _STATUS_PATH_RE.match(line)
        if m:
            paths.add(m.group(1).strip())
    return paths


def commits_since_capture(cwd: str, captured_at: str) -> int:
    """Return the number of commits on HEAD strictly after captured_at (ISO 8601)."""
    raw = git(cwd, "log", "--format=%aI")
    if not raw:
        return 0
    try:
        dt_captured = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except Exception:
        return 0
    count = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            dt_commit = datetime.fromisoformat(line)
            if dt_commit > dt_captured:
                count += 1
        except Exception:
            pass
    return count


def worktrees(cwd: str):
    raw = git(cwd, "worktree", "list", "--porcelain")
    if not raw:
        return []
    out, path, branch = [], None, None
    for line in raw.splitlines():
        if line.startswith("worktree "):
            path, branch = line[len("worktree "):], None
        elif line.startswith("branch "):
            branch = line[len("branch "):].replace("refs/heads/", "")
        elif line.startswith("detached"):
            branch = "(detached)"
        elif line == "" and path:
            out.append((path, branch))
            path, branch = None, None
    if path:
        out.append((path, branch))
    return out


def local_branches(cwd: str):
    raw = git(cwd, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    return [b for b in raw.splitlines() if b] if raw else []


# ── .env / tier resolution ──────────────────────────────────────────────────
def load_env(root: str) -> dict:
    """Parse backend/.env (best-effort) for Supabase creds."""
    candidates = [
        os.environ.get("BRAIN2_ENV", ""),
        os.path.join(root, "backend", ".env"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", ".env"),
    ]
    env: dict[str, str] = {}
    for path in candidates:
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path) as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
            break
        except Exception:
            continue
    return env


def resolve_tier(env: dict) -> str:
    backend = os.environ.get("BRAIN2_BACKEND") or env.get("BRAIN2_BACKEND")
    if backend in ("local", "cloud"):
        return backend
    if env.get("SUPABASE_URL") and (
        env.get("SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_ANON_KEY")
    ):
        return "cloud"
    return "local"


# ── local-tier source ───────────────────────────────────────────────────────
def db_path() -> str:
    return os.environ.get("BRAIN2_DB_PATH", os.path.expanduser("~/.brain2/brain.db"))


def local_map(project: str) -> dict:
    """Return {kb: (text, created_at)} latest snapshot per kb for a project."""
    path = db_path()
    if not os.path.exists(path):
        return {}
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=0.5)
        conn.execute("PRAGMA query_only = ON")
    except Exception:
        return {}
    out: dict = {}
    try:
        rows = conn.execute(
            """
            SELECT k.name, f.title, f.content, f.created_at
            FROM findings f
            JOIN kbs k      ON f.kb_id = k.id
            JOIN projects p ON k.project_id = p.id
            WHERE p.org_id = ? AND p.name = ? AND f.category = 'snapshot'
            ORDER BY f.created_at DESC
            """,
            (ORG_ID, project),
        ).fetchall()
        for kb, title, content, created in rows:
            if kb in out:
                continue  # rows are DESC → first seen is latest
            out[kb] = (_hyp(title, content), created)
    except Exception:
        pass
    finally:
        conn.close()
    return out


# ── cloud-tier source (Supabase PostgREST, disk-cached) ─────────────────────
def _cache_path(base: str, project: str) -> str:
    tag = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{base}-{project}")
    return os.path.join(tempfile.gettempdir(), f"brain2-sl-{tag}.json")


def cloud_map(project: str, env: dict) -> dict:
    """Return {kb: (text, created_at)} latest snapshot per kb, via Supabase.

    Disk-cached for CLOUD_TTL seconds. On any network failure, falls back to the
    last cached payload (even if stale) so the line keeps showing something.
    """
    base = env.get("SUPABASE_URL", "").rstrip("/")
    key = env.get("SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_ANON_KEY", "")
    if not base or not key:
        return {}

    cache = _cache_path(base, project)
    now = time.time()
    cached = None
    try:
        if os.path.exists(cache):
            with open(cache) as fh:
                cached = json.load(fh)
            if now - cached.get("ts", 0) < CLOUD_TTL:
                return {k: tuple(v) for k, v in cached["data"].items()}
    except Exception:
        cached = None

    select = f"title,content,created_at,kbs!inner(name,{CLOUD_FK}(name))"
    params = urllib.parse.urlencode([
        ("select", select),
        ("category", "eq.snapshot"),
        ("kbs.projects.name", f"eq.{project}"),
        ("order", "created_at.desc"),
        ("limit", "60"),
    ])
    url = f"{base}/rest/v1/findings?{params}"
    req = urllib.request.Request(url, headers={
        "apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=CLOUD_TIMEOUT) as resp:
            rows = json.load(resp)
    except Exception:
        if cached:  # stale-but-present beats blank
            return {k: tuple(v) for k, v in cached.get("data", {}).items()}
        return {}

    out: dict = {}
    for row in rows if isinstance(rows, list) else []:
        kb = (row.get("kbs") or {}).get("name")
        if not kb or kb in out:
            continue
        out[kb] = (_hyp(row.get("title"), row.get("content")), row.get("created_at"))

    try:
        with open(cache, "w") as fh:
            json.dump({"ts": now, "data": {k: list(v) for k, v in out.items()}}, fh)
    except Exception:
        pass
    return out


# ── formatting ──────────────────────────────────────────────────────────────
def _hyp(title, content):
    text = (title or "").strip()
    if not text and content:
        m = _HYP_RE.search(content)
        if m:
            text = m.group(1).strip()
    return text or None


def age(created_at) -> str:
    if not created_at:
        return ""
    try:
        dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        secs = max(0, (datetime.now(timezone.utc) - dt).total_seconds())
    except Exception:
        return ""
    if secs < 3600:
        return f"{int(secs // 60)}m"
    if secs < 86400:
        return f"{int(secs // 3600)}h"
    return f"{int(secs // 86400)}d"


def truncate(text: str, width: int = HYP_WIDTH) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


# ── main ────────────────────────────────────────────────────────────────────
def main() -> None:
    cwd = os.getcwd()
    try:
        data = json.load(sys.stdin)
        cwd = (data.get("workspace") or {}).get("current_dir") or data.get("cwd") or cwd
    except Exception:
        pass

    root = git(cwd, "rev-parse", "--show-toplevel")
    if not root:
        return
    cur_branch = git(cwd, "rev-parse", "--abbrev-ref", "HEAD") or "(detached)"
    cur_project = os.path.basename(root)

    wts = worktrees(cwd)
    if len(wts) > 1:
        entries = [
            (os.path.basename(p), (b or "(detached)"),
             os.path.realpath(p) == os.path.realpath(root))
            for p, b in wts
        ]
    else:
        entries = [(cur_project, b, b == cur_branch) for b in local_branches(cwd)] \
            or [(cur_project, cur_branch, True)]

    env = load_env(root)
    tier = resolve_tier(env)
    fetch = (lambda proj: cloud_map(proj, env)) if tier == "cloud" else local_map

    maps: dict = {}
    rendered = []
    for project, kb, is_current in entries:
        if project not in maps:
            maps[project] = fetch(project)
        text, created = maps[project].get(kb, (None, None))
        rendered.append({
            "kb": kb, "is_current": is_current, "text": text,
            "age": age(created) if created else "", "recency": created or "",
        })

    rendered.sort(key=lambda e: (not e["is_current"], e["recency"] == "",
                                 tuple(-ord(c) for c in e["recency"])))

    overflow = max(0, len(rendered) - MAX_ENTRIES)
    parts = []
    for e in rendered[:MAX_ENTRIES]:
        mark = "▶" if e["is_current"] else "·"
        color = (BOLD + GREEN) if e["is_current"] else CYAN
        name = f"{color}{mark} {e['kb']}{RESET}"
        if e["text"]:
            age_str = f" {GREY}{e['age']}{RESET}" if e["age"] else ""
            feat = f' {DIM}"{truncate(e["text"])}"{RESET}{age_str}'
        else:
            feat = f" {GREY}—{RESET}"
        parts.append(name + feat)

    badge = f"{YELLOW}🧠 {cur_project}{RESET}"
    if tier == "cloud":
        badge += f"{GREY}☁{RESET}"
    line = badge + "  " + f"  {DIM}│{RESET}  ".join(parts)
    if overflow:
        line += f"  {GREY}+{overflow} more{RESET}"
    sys.stdout.write(line)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
