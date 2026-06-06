from __future__ import annotations
import br8n.config as config
from br8n.agent.state import Principal
import br8n.interfaces.mcp.tenancy as tenancy


def _reset():
    config.get_settings.cache_clear()


def test_local_resolve_ignores_principal(monkeypatch, tmp_path):
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "b.db"))
    _reset()
    try:
        ctx = tenancy.resolve_tenant("myrepo", "main", create=True)
        assert ctx.user_id == "local" and ctx.project_id and ctx.kb_id
        assert ctx.access_token == ""
    finally:
        _reset()


def test_cloud_principal_threads_org_and_token(monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "cloud")
    _reset()

    captured = {}

    class _FakeStore:
        def resolve_project(self, name, *, create):
            return ("org-from-principal", "proj-1")
        def resolve_kb(self, org_id, project_id, name, *, create):
            return "kb-1"

    def fake_get_store(access_token=None, *, org_id=None):
        captured["access_token"] = access_token
        captured["org_id"] = org_id
        return _FakeStore()

    # If _login() is called on the principal path, that's a bug.
    monkeypatch.setattr(tenancy, "_login", lambda: (_ for _ in ()).throw(AssertionError("_login must not run on the principal path")))
    monkeypatch.setattr("br8n.store.get_store", fake_get_store)
    monkeypatch.setattr("br8n.store.active_backend", lambda: "cloud")

    p = Principal(user_id="user-9", org_id="org-from-principal", access_token="jwt-tok")
    try:
        ctx = tenancy.resolve_tenant("repo", "branch", principal=p, create=False)
        assert ctx.user_id == "user-9"
        assert ctx.org_id == "org-from-principal"
        assert ctx.access_token == "jwt-tok"
        assert captured == {"access_token": "jwt-tok", "org_id": "org-from-principal"}
    finally:
        _reset()
