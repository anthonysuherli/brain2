import br8n.store.supabase as sup


def test_resolve_project_uses_injected_org_without_login(monkeypatch):
    store = sup.SupabaseStore(access_token="tok", org_id="org-injected")
    monkeypatch.setattr(sup, "_login", lambda: (_ for _ in ()).throw(AssertionError("_login must not be called")))
    monkeypatch.setattr(sup, "_find_or_create", lambda sb, table, match, insert, create: "proj-1")
    monkeypatch.setattr(sup, "service_client", lambda: object())
    org_id, pid = store.resolve_project("repo", create=True)
    assert org_id == "org-injected" and pid == "proj-1"


def test_resolve_project_without_org_falls_back_to_login(monkeypatch):
    store = sup.SupabaseStore(access_token="tok")  # org_id defaults None
    calls = {"login": 0}

    def fake_login():
        calls["login"] += 1
        return ("user-x", "tok")

    monkeypatch.setattr(sup, "_login", fake_login)
    monkeypatch.setattr(sup, "_org_for", lambda uid: "org-from-login")
    monkeypatch.setattr(sup, "_find_or_create", lambda sb, table, match, insert, create: "proj-2")
    monkeypatch.setattr(sup, "service_client", lambda: object())
    org_id, pid = store.resolve_project("repo", create=True)
    assert org_id == "org-from-login" and pid == "proj-2" and calls["login"] == 1
