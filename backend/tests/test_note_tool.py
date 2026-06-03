"""Local-tier test for the brain2_note MCP tool + the Stop session-note hook.

Mirrors test_livingdocs_notes.py: BRAIN2_BACKEND=local + a tmp BRAIN2_DB_PATH wire
the real SQLiteStore (no storage mocks); only the embedder is faked so no OpenAI
call is made (embed_batch is async, so the fake is async), and the synopsis rebuild
is patched so the post-write hook is a no-op (no Anthropic). The local-store
singleton cache is cleared before and after so the tmp DB is honored.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

DIM = 1536

HOOKS_DIR = Path(__file__).resolve().parents[2] / "hooks"


def _fake_vec(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    v = [0.0] * DIM
    for i in range(8):
        v[i] = (h[i] / 255.0) or 0.01
    return v


async def _fake_embed_batch(texts):
    return [_fake_vec(t) for t in texts]


async def test_brain2_note_persists_and_schedules(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "local")
    monkeypatch.setenv("BRAIN2_DB_PATH", str(tmp_path / "brain.db"))
    monkeypatch.setenv("BRAIN2_LIVING_DOCS", "0")  # schedule_distill becomes a no-op

    import brain2.livingdocs.notes as notes_mod
    import brain2.store as store_pkg
    from brain2.interfaces.mcp import server

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
        "brain2_session_note_hook", HOOKS_DIR / "session-note.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    directive = mod.build_note_directive("proj", "main")
    assert "brain2_note" in directive
    assert "proj" in directive
    assert "main" in directive
