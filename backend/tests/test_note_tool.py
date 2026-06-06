"""Local-tier test for the br8n_note MCP tool + the Stop session-note hook.

Mirrors test_livingdocs_notes.py: BR8N_BACKEND=local + a tmp BR8N_DB_PATH wire
the real SQLiteStore (no storage mocks); only the embedder is faked so no OpenAI
call is made (embed_batch is async, so the fake is async), and the synopsis rebuild
is patched so the post-write hook is a no-op (no Anthropic). The local-store
singleton cache is cleared before and after so the tmp DB is honored.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

DIM = 1536

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / "hooks"


def _run_session_note_hook(payload: dict) -> str:
    """Run the Stop hook as a subprocess (as the harness does) → stripped stdout.

    cwd is the repo root (a real git repo) so repo_identity/derive_project_kb pass.
    """
    res = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "session-note.py")],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=str(REPO_ROOT),
        env={**os.environ, "BR8N_LIVING_DOCS": "1"},
        timeout=30,
    )
    return res.stdout.strip()


def _fake_vec(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    v = [0.0] * DIM
    for i in range(8):
        v[i] = (h[i] / 255.0) or 0.01
    return v


async def _fake_embed_batch(texts):
    return [_fake_vec(t) for t in texts]


async def test_br8n_note_persists_and_schedules(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "brain.db"))
    monkeypatch.setenv("BR8N_LIVING_DOCS", "0")  # schedule_distill becomes a no-op

    import br8n.livingdocs.notes as notes_mod
    import br8n.store as store_pkg
    from br8n.interfaces.mcp import server

    store_pkg._local_stores.clear()
    monkeypatch.setattr(notes_mod, "embed_batch", _fake_embed_batch)
    # Keep the synopsis rebuild a no-op (avoid Anthropic on the post-write hook).
    monkeypatch.setattr(notes_mod, "schedule_rebuild", lambda ctx: None)

    res = await server._note_impl(
        project="proj",
        kb="main",
        project_path=str(tmp_path),
        content="## Decisions\nX.",
        session_id="s1",
        title="t",
    )

    assert res["finding_id"]
    assert res["note_path"].endswith(".md")
    assert res["project"] == "proj" and res["kb"] == "main"

    store_pkg._local_stores.clear()


def test_session_note_directive_mentions_tool_and_target():
    """The Stop hook directive names the tool and threads project/kb through."""
    spec = importlib.util.spec_from_file_location(
        "br8n_session_note_hook", HOOKS_DIR / "session-note.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    directive = mod.build_note_directive("proj", "main")
    assert "br8n_note" in directive
    assert "proj" in directive
    assert "main" in directive


def test_stop_hook_blocks_with_reason_not_additional_context():
    """Stop hooks drop `additionalContext`; the hook must use decision=block+reason."""
    out = _run_session_note_hook({"cwd": str(REPO_ROOT), "stop_hook_active": False})
    assert out, "hook should emit JSON on a normal stop in a git repo"
    obj = json.loads(out)
    # Correct Stop-hook continuation contract: decision=block, directive in `reason`.
    assert obj.get("decision") == "block"
    assert "br8n_note" in obj.get("reason", "")
    # The old field is silently ignored on Stop — it must NOT be the mechanism.
    assert "additionalContext" not in obj


def test_stop_hook_silent_when_already_active():
    """Loop guard: when stop_hook_active is set, the hook must not block again."""
    out = _run_session_note_hook({"cwd": str(REPO_ROOT), "stop_hook_active": True})
    assert out == "", "must stay silent when stop_hook_active (prevents infinite loop)"
