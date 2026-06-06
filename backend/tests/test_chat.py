"""Tests for POST /v1/chat — the funnel chat agent.

Grounding + streaming are mocked: the endpoint's job is to tap the preamble, build
the persona/funnel system prompt, and stream deltas as SSE. We verify that wiring,
not the LLM or the store.
"""

from fastapi.testclient import TestClient

import br8n.api.chat as chatmod
from br8n.agent.state import Principal
from br8n.api.auth import require_principal
from br8n.api.chat import build_system_prompt
from br8n.api.main import create_app


class _Ctx:
    """Stand-in for a resolved TenantContext."""

    access_token = ""
    org_id = "local"
    kb_id = "kb-1"


async def _fake_preamble(query, *, store, kb_id, depth="normal"):
    return ("<preamble><synopsis><entry topic=\"br8n\">an engine</entry></synopsis></preamble>", "rich")


async def _fake_stream(*, model, messages, temperature=0.3, max_tokens=None, fallback_model=None):
    # Assert the grounding made it into the system prompt the model would see.
    assert messages[0]["role"] == "system"
    assert "<preamble>" in messages[0]["content"]
    for tok in ["Hello", ", ", "world"]:
        yield tok


def _client(monkeypatch) -> TestClient:
    monkeypatch.setattr(chatmod, "resolve_tenant", lambda *a, **k: _Ctx())
    monkeypatch.setattr(chatmod, "get_store", lambda *a, **k: object())
    monkeypatch.setattr(chatmod, "select_preamble", _fake_preamble)
    monkeypatch.setattr(chatmod, "stream_completion", _fake_stream)
    app = create_app()
    app.dependency_overrides[require_principal] = lambda: Principal(
        user_id="local", org_id="local", access_token=""
    )
    return TestClient(app)


def test_chat_streams_grounded_answer(monkeypatch):
    client = _client(monkeypatch)
    r = client.post("/v1/chat", json={"message": "what is br8n?"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    body = r.text
    assert "Hello" in body and "world" in body
    assert "[DONE]" in body


def test_chat_replays_history(monkeypatch):
    client = _client(monkeypatch)
    r = client.post(
        "/v1/chat",
        json={
            "message": "and the paid tier?",
            "history": [
                {"role": "user", "content": "what is br8n?"},
                {"role": "assistant", "content": "an OSS resume engine"},
            ],
        },
    )
    assert r.status_code == 200
    assert "[DONE]" in r.text


def test_chat_disabled_returns_404(monkeypatch):
    monkeypatch.setenv("BR8N_CHAT", "0")
    client = _client(monkeypatch)
    r = client.post("/v1/chat", json={"message": "hi"})
    assert r.status_code == 404


def test_chat_empty_message_422(monkeypatch):
    client = _client(monkeypatch)
    r = client.post("/v1/chat", json={"message": "   "})
    assert r.status_code == 422


def test_chat_missing_agent_kb_503(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("kb not found")

    monkeypatch.setattr(chatmod, "resolve_tenant", _boom)
    monkeypatch.setattr(chatmod, "select_preamble", _fake_preamble)
    monkeypatch.setattr(chatmod, "stream_completion", _fake_stream)
    app = create_app()
    app.dependency_overrides[require_principal] = lambda: Principal("local", "local", "")
    client = TestClient(app)
    r = client.post("/v1/chat", json={"message": "hi"})
    assert r.status_code == 503


# --- pure helper -------------------------------------------------------------

def test_build_system_prompt_carries_preamble_and_funnel():
    sys = build_system_prompt("<preamble><empty/></preamble>")
    assert "<preamble><empty/></preamble>" in sys
    assert "delapan" in sys
    assert "MIT" in sys
