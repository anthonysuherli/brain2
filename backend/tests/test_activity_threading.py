import br8n.knowledge_graph.activity as activity


def test_resolve_activity_target_threads_token_and_org(monkeypatch):
    captured = {}

    class _FakeStore:
        def resolve_project(self, name, *, create):
            return ("org-resolved", "proj-act")
        def resolve_kb(self, org_id, project_id, name, *, create):
            return "kb-act"

    def fake_get_store(access_token=None, *, org_id=None):
        captured["access_token"] = access_token
        captured["org_id"] = org_id
        return _FakeStore()

    monkeypatch.setattr(activity, "get_store", fake_get_store)
    store, org_id, kb_id = activity.resolve_activity_target(
        access_token="jwt-tok", org_id="org-X", create=True
    )
    assert captured == {"access_token": "jwt-tok", "org_id": "org-X"}
    assert (org_id, kb_id) == ("org-resolved", "kb-act")


def test_activity_rollup_passes_org_to_target(monkeypatch):
    seen = {}

    def fake_safe_target(*, access_token=None, org_id=None, create):
        seen["access_token"] = access_token
        seen["org_id"] = org_id
        return None  # no activity yet → rollup returns []

    monkeypatch.setattr(activity, "_safe_target", fake_safe_target)
    out = activity.activity_rollup(access_token="t2", org_id="org-Y")
    assert out == [] and seen == {"access_token": "t2", "org_id": "org-Y"}
