# Multi-user Deploy + Real Auth — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the single shared service identity with per-Apple-user auth + isolation, add the Apple→Supabase bridge, harden the activity-KG read/write path against cross-org leaks, and deploy the cloud tier on Fly.io.

**Architecture:** A FastAPI dependency (`require_principal`) verifies the request's Supabase GoTrue JWT (HS256 vs `SUPABASE_JWT_SECRET`), yields a `Principal(user_id, org_id, access_token)`, and threads it through `resolve_tenant` and the `Store` so every cloud read/write scopes to the caller's org — killing the hardcoded `_login()` on the request path. A thin `/v1/auth/apple` endpoint delegates Apple-token verification + user provisioning to Supabase via `sign_in_with_id_token`. The iOS app sends the Apple `identityToken`, stores the returned session, and sends it as Bearer thereafter.

**Tech Stack:** Python 3.11, FastAPI, `supabase-py`, `pyjwt[crypto]` (already deps), pytest + pytest-asyncio + httpx; Swift/SwiftUI; Fly.io + Docker; Supabase (GoTrue + pgvector + RLS).

**Design doc:** `docs/plans/2026-05-30-multiuser-deploy-auth-design.md`

**Working dir:** all backend paths are under `backend/`. Run tests from `backend/` with the venv: `.venv/bin/pytest …` (or `uv run pytest …`).

**Ground truth already verified (do not re-litigate):**
- `handle_new_user` trigger on `auth.users` auto-creates `orgs` + `org_members(role='owner')` for every new GoTrue signup (Apple included). New Apple users get an org for free.
- RLS is correct + org-scoped on all phone-read tables but **bypassed** today (service client + `kb_id`-only KG reads). `pyjwt[crypto]` and `Settings.supabase_jwt_secret` already exist (`config.py:34`; secret currently unused).
- Native Apple `identityToken.aud` = the app **bundle id** (not a Services ID) → goes in Supabase's Apple "Client IDs".

---

## Phase A — Backend auth rewire + security hardening (one PR/branch)

> These tasks are coupled: shipping the auth rewire without the KG org-scoping leaves cross-org reads open. Land Phase A as a single reviewable unit.

### Task A1: `Principal` type (shared, cycle-free)

**Files:**
- Modify: `backend/brain2/agent/state.py` (add `Principal` beside `TenantContext`)
- Test: `backend/tests/test_principal.py`

> `Principal` lives in `agent/state.py` (which imports nothing from `brain2`) so both `api/auth.py` and `interfaces/mcp/tenancy.py` can import it without the cycle `tenancy → api.auth → store → store.supabase → tenancy`.

**Step 1 — Write the failing test:**
```python
# backend/tests/test_principal.py
from brain2.agent.state import Principal

def test_principal_defaults_to_user():
    p = Principal(user_id="u1", org_id="o1", access_token="tok")
    assert p.is_service is False
    assert (p.user_id, p.org_id, p.access_token) == ("u1", "o1", "tok")
```

**Step 2 — Run, expect fail:** `.venv/bin/pytest tests/test_principal.py -v` → `ImportError: cannot import name 'Principal'`.

**Step 3 — Implement** (append to `agent/state.py`):
```python
@dataclass
class Principal:
    """Authenticated caller for a cloud request (or the local single user)."""

    user_id: str
    org_id: str
    access_token: str
    is_service: bool = False
```

**Step 4 — Run, expect pass.**

**Step 5 — Commit:** `git add backend/brain2/agent/state.py backend/tests/test_principal.py && git commit -m "feat(auth): add Principal type for per-user tenancy"`

---

### Task A2: JWT verification + `require_principal` dependency

**Files:**
- Modify: `backend/brain2/api/auth.py`
- Modify: `backend/brain2/interfaces/mcp/tenancy.py` (add `_org_for_or_create`)
- Test: `backend/tests/test_principal_auth.py`

**Step 1 — Write the failing tests** (mint our own HS256 tokens with the test secret; monkeypatch the org lookup so no Supabase is needed):
```python
# backend/tests/test_principal_auth.py
from __future__ import annotations
import time
import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
import brain2.config as config
import brain2.api.auth as auth

SECRET = "test-jwt-secret"

def _reset():
    config.get_settings.cache_clear()

def _token(sub="user-1", aud="authenticated", exp_delta=3600):
    return jwt.encode({"sub": sub, "aud": aud, "exp": int(time.time()) + exp_delta}, SECRET, algorithm="HS256")

def _creds(tok):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=tok)

def test_local_tier_returns_local_principal(monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "local")
    _reset()
    try:
        p = auth.require_principal(credentials=None)
        assert (p.user_id, p.org_id, p.access_token) == ("local", "local", "")
    finally:
        _reset()

def test_cloud_valid_jwt_yields_principal(monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "cloud")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(auth, "_org_for_or_create", lambda uid: f"org-of-{uid}")
    _reset()
    try:
        p = auth.require_principal(credentials=_creds(_token("user-1")))
        assert p.user_id == "user-1" and p.org_id == "org-of-user-1"
        assert p.access_token  # raw token threaded for RLS
    finally:
        _reset()

def test_cloud_expired_jwt_401(monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "cloud")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(auth, "_org_for_or_create", lambda uid: "org")
    _reset()
    try:
        with pytest.raises(HTTPException) as e:
            auth.require_principal(credentials=_creds(_token(exp_delta=-10)))
        assert e.value.status_code == 401
    finally:
        _reset()

def test_cloud_wrong_secret_401(monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "cloud")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(auth, "_org_for_or_create", lambda uid: "org")
    _reset()
    bad = jwt.encode({"sub": "u", "aud": "authenticated", "exp": int(time.time()) + 60}, "other-secret", algorithm="HS256")
    try:
        with pytest.raises(HTTPException) as e:
            auth.require_principal(credentials=_creds(bad))
        assert e.value.status_code == 401
    finally:
        _reset()

def test_cloud_missing_bearer_401(monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "cloud")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    _reset()
    try:
        with pytest.raises(HTTPException) as e:
            auth.require_principal(credentials=None)
        assert e.value.status_code == 401
    finally:
        _reset()
```

**Step 2 — Run, expect fail:** `AttributeError: module 'brain2.api.auth' has no attribute 'require_principal'`.

**Step 3 — Implement.** Add `_org_for_or_create` to `tenancy.py` (next to `_org_for`):
```python
def _org_for_or_create(user_id: str) -> str:
    """Org for the user; provision one if the signup trigger didn't (first-seen)."""
    try:
        return _org_for(user_id)
    except RuntimeError:
        sb = service_client()
        org = sb.table("orgs").insert(
            {"name": f"{user_id[:8]}'s workspace", "owner_user_id": user_id}
        ).execute().data
        org_id = org[0]["id"]
        sb.table("org_members").insert(
            {"org_id": org_id, "user_id": user_id, "role": "owner"}
        ).execute()
        return org_id
```
Then in `api/auth.py` add imports + the dependency (keep `require_api_key` as-is for service callers):
```python
import jwt
from brain2.agent.state import Principal
from brain2.config import get_settings
from brain2.interfaces.mcp.tenancy import _org_for_or_create


def _verify_supabase_jwt(token: str) -> str:
    """Return the user id (sub) from a Supabase GoTrue access token, or raise 401."""
    secret = get_settings().supabase_jwt_secret
    if not secret:
        raise RuntimeError("SUPABASE_JWT_SECRET is not set — required for the cloud tier")
    try:
        claims = jwt.decode(
            token, secret, algorithms=["HS256"],
            audience="authenticated", options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return claims["sub"]


def require_principal(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> Principal:
    """FastAPI dependency: the authenticated caller. Local tier = single user."""
    if active_backend() == "local":
        return Principal(user_id="local", org_id="local", access_token="")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = credentials.credentials
    user_id = _verify_supabase_jwt(token)
    return Principal(user_id=user_id, org_id=_org_for_or_create(user_id), access_token=token)
```
> Import note: `api/auth.py` importing `tenancy._org_for_or_create` is safe — `tenancy` does not import `api.auth`. The `Principal` import comes from `agent.state`, not `auth`, so no cycle.

**Step 4 — Run, expect pass** (all 5).

**Step 5 — Commit:** `git commit -m "feat(auth): require_principal verifies Supabase JWT, provisions org"`

---

### Task A3: `get_store` + `SupabaseStore` accept `org_id` (stop re-login)

**Files:**
- Modify: `backend/brain2/store/__init__.py:57-70` (`get_store`)
- Modify: `backend/brain2/store/supabase.py:53-54, 220-280` (`__init__`, `resolve_project`, `list_projects`)
- Test: `backend/tests/test_store_org_threading.py`

**Step 1 — Write the failing test** (assert the org is taken from the constructor and `_login` is NOT called):
```python
# backend/tests/test_store_org_threading.py
import brain2.store.supabase as sup

def test_resolve_project_uses_injected_org_without_login(monkeypatch):
    store = sup.SupabaseStore(access_token="tok", org_id="org-injected")
    monkeypatch.setattr(sup, "_login", lambda: (_ for _ in ()).throw(AssertionError("_login must not be called")))
    monkeypatch.setattr(sup, "_find_or_create", lambda sb, table, match, insert, create: "proj-1")
    monkeypatch.setattr(sup, "service_client", lambda: object())
    org_id, pid = store.resolve_project("repo", create=True)
    assert org_id == "org-injected" and pid == "proj-1"
```

**Step 2 — Run, expect fail:** `TypeError: __init__() got an unexpected keyword argument 'org_id'`.

**Step 3 — Implement.** `SupabaseStore.__init__`:
```python
    def __init__(self, access_token: str | None = None, org_id: str | None = None) -> None:
        self.access_token = access_token
        self.org_id = org_id
```
Add a helper + use it in `resolve_project` and `list_projects`:
```python
    def _resolve_org(self) -> str:
        """Injected org (per-user request) or the configured login's org (MCP path)."""
        if self.org_id is not None:
            return self.org_id
        user_id, _ = _login()
        return _org_for(user_id)
```
In `resolve_project` replace lines 222-223 (`user_id, _ = _login()` / `org_id = _org_for(user_id)`) with `org_id = self._resolve_org()`. In `list_projects` replace 252-253 likewise. Then `get_store`:
```python
def get_store(access_token: str | None = None, *, org_id: str | None = None) -> Store:
    if active_backend() == "local":
        path = _default_db_path()
        store = _local_stores.get(path)
        if store is None:
            store = SQLiteStore(path)
            _local_stores[path] = store
        return store
    return SupabaseStore(access_token, org_id=org_id)
```

**Step 4 — Run, expect pass.**

**Step 5 — Commit:** `git commit -m "feat(store): inject org_id into SupabaseStore; drop request-path re-login"`

---

### Task A4: `resolve_tenant(principal, …)` + MCP call sites

**Files:**
- Modify: `backend/brain2/interfaces/mcp/tenancy.py:79-123`
- Modify: `backend/brain2/interfaces/mcp/server.py` (call sites — `grep -n resolve_tenant`)
- Test: `backend/tests/test_resolve_tenant_principal.py`

**Step 1 — Write the failing test** (local path needs no Supabase):
```python
# backend/tests/test_resolve_tenant_principal.py
from brain2.agent.state import Principal
from brain2.interfaces.mcp.tenancy import resolve_tenant

def test_local_resolve_ignores_principal(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAIN2_BACKEND", "local")
    monkeypatch.setenv("BRAIN2_DB_PATH", str(tmp_path / "b.db"))
    import brain2.config as config; config.get_settings.cache_clear()
    p = Principal("local", "local", "")
    ctx = resolve_tenant(p, "myrepo", "main", create=True)
    assert ctx.project_id and ctx.kb_id and ctx.user_id == "local"
    config.get_settings.cache_clear()
```

**Step 2 — Run, expect fail:** signature mismatch (`resolve_tenant()` takes `project, kb`).

**Step 3 — Implement** the new `resolve_tenant`:
```python
def resolve_tenant(principal: "Principal", project: str, kb: str, *, create: bool = True) -> TenantContext:
    from brain2.store import active_backend, get_store
    if active_backend() == "local":
        store = get_store()
        org_id, project_id = store.resolve_project(project, create=create)
        kb_id = store.resolve_kb(org_id, project_id, kb, create=create)
        return TenantContext("local", org_id, project_id, kb_id, str(uuid.uuid4()), "")
    store = get_store(principal.access_token, org_id=principal.org_id)
    org_id, project_id = store.resolve_project(project, create=create)
    kb_id = store.resolve_kb(org_id, project_id, kb, create=create)
    return TenantContext(principal.user_id, org_id, project_id, kb_id, str(uuid.uuid4()), principal.access_token)
```
Add `from brain2.agent.state import Principal, TenantContext` (keep existing `TenantContext` import). In `interfaces/mcp/server.py`, build a principal from the configured login at each `resolve_tenant` call site:
```python
from brain2.agent.state import Principal
from brain2.interfaces.mcp.tenancy import _login, _org_for
_uid, _tok = _login()
_principal = Principal(_uid, _org_for(_uid), _tok)
ctx = resolve_tenant(_principal, project, kb, create=...)
```
(Factor a `_mcp_principal()` helper if it appears at all 3 sites.)

**Step 4 — Run, expect pass.** Also run the MCP-touching suite: `.venv/bin/pytest tests/test_activity_flow.py tests/test_engine_local.py -v`.

**Step 5 — Commit:** `git commit -m "feat(tenancy): resolve_tenant takes Principal; MCP builds one from _login"`

---

### Task A5: Endpoints adopt `require_principal`

**Files (modify each router + handler):**
- `backend/brain2/api/resume.py` (router dep + `resolve_tenant(principal, …)`; build stores with `org_id`)
- `backend/brain2/api/capture.py:57`
- `backend/brain2/api/explore.py:62`
- `backend/brain2/api/projects.py:17,38-41`
- Test: `backend/tests/test_api_read_surfaces.py` (extend) — assert local-tier still works end to end via the app, and a cloud-tier request with no Bearer → 401.

**Pattern for each router:** change `dependencies=[Depends(require_api_key)]` → `dependencies=[Depends(require_principal)]`, add `principal: Principal = Depends(require_principal)` to handlers that need tenancy, and thread it:
- `projects.list_projects`: `store = get_store(principal.access_token, org_id=principal.org_id)` then `store.list_projects()`.
- `resume` / `capture` / `explore`: `resolve_tenant(principal, project, kb, create=…)`; anywhere a store is built for finding ops, use `get_store(principal.access_token, org_id=principal.org_id)`.

**Steps:** (1) extend `test_api_read_surfaces.py` with a `BRAIN2_BACKEND=cloud` + no-`SUPABASE_JWT_SECRET`/no-Bearer case asserting 401 on `/v1/projects`; and keep the existing local-tier 200 path. (2) run → fail. (3) apply the router/handler edits. (4) run → pass. (5) `git commit -m "feat(api): scope /v1 data endpoints to the authenticated principal"`.

---

### Task A6: Org-scope the activity-KG reads + derive write org from kb

**Files:**
- Modify: `backend/brain2/store/supabase.py:288-481` (`upsert_kg_nodes`, `upsert_kg_edges`, `match_kg_nodes`, `get_kg_subgraph`, `list_kg_nodes`, `kg_stats`)
- Modify: `backend/brain2/store/base.py` (update the protocol signatures if `org_id` becomes a param)
- Test: `backend/tests/test_kg_org_scoping.py`

**Decision:** the cloud `SupabaseStore` already carries `self.org_id` (Task A3). Use it directly — no new method params needed (keeps `base.py` + `SQLiteStore` untouched). For **reads**, add `.eq("org_id", self.org_id)` when `self.org_id is not None`. For the `match_kg_nodes` RPC, pass an `match_org_id` arg (requires a one-line RPC signature update — see Task A6b) OR post-filter returned rows by `org_id` in Python as the minimal change. For **writes**, set `row["org_id"] = self.org_id` (assert non-null) instead of `nd.get("org_id")`/`e.get("org_id")`.

**Step 1 — Write the failing test** (a fake query-builder records `.eq` calls):
```python
# backend/tests/test_kg_org_scoping.py
import brain2.store.supabase as sup

class _Q:
    def __init__(self, sink): self.sink = sink
    def select(self, *a, **k): return self
    def eq(self, col, val): self.sink.append((col, val)); return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def execute(self): 
        class R: data = []; count = 0
        return R()
class _SB:
    def __init__(self, sink): self.sink = sink
    def table(self, *_): return _Q(self.sink)

def test_list_kg_nodes_filters_by_org(monkeypatch):
    sink = []
    monkeypatch.setattr(sup, "service_client", lambda: _SB(sink))
    store = sup.SupabaseStore(access_token="t", org_id="org-X")
    store.list_kg_nodes("kb-1")
    assert ("org_id", "org-X") in sink and ("kb_id", "kb-1") in sink
```
(Repeat the assertion for `get_kg_subgraph` and `kg_stats`.)

**Step 2 — Run, expect fail** (`org_id` not in sink).

**Step 3 — Implement:** in each KG read method, after `.eq("kb_id", kb_id)` add:
```python
            q = q.eq("kb_id", kb_id)
            if self.org_id is not None:
                q = q.eq("org_id", self.org_id)
```
In `upsert_kg_nodes`/`upsert_kg_edges`, replace `nd.get("org_id")` / `e.get("org_id")` with:
```python
                "org_id": self.org_id,   # derived from verified tenancy, never caller-supplied
```
and at method entry: `assert self.org_id is not None, "KG writes require a resolved org_id"` (cloud always sets it; local SQLiteStore is a different class).

**Step 4 — Run, expect pass.**

**Step 5 — Commit:** `git commit -m "fix(kg): org-scope activity-KG reads + derive write org from tenancy (close RLS bypass)"`

#### Task A6b (DB, optional but recommended): org-aware `match_kg_nodes`
If you keep the RPC (semantic seeding), add `match_org_id uuid` to `match_kg_nodes` and `WHERE org_id = match_org_id`. Apply via a new migration file (do NOT use the live MCP to mutate prod casually — write the SQL, review, then `supabase` CLI / dashboard). Until then, the Python post-filter in A6 is the safety net. Tracked, not blocking.

---

### Task A7: Thread the principal through the activity module

**Files:**
- Modify: `backend/brain2/knowledge_graph/activity.py` (`resolve_activity_target`, `_safe_target`, `query_activity`, `activity_rollup`, `activity_stats`, `schedule_activity_update`/`_run_activity_update`)
- Modify: `backend/brain2/api/activity.py` (router dep + handlers pass `principal`)
- Modify: `backend/brain2/api/capture.py` (pass `principal.org_id` + token into `schedule_activity_update`)
- Test: `backend/tests/test_activity_flow.py` (extend: assert the activity store is built with the caller's org)

**Pattern:** add a keyword `principal: Principal` (or just `access_token: str|None, org_id: str|None`) to each public function; replace `get_store()` with `get_store(access_token, org_id=org_id)`. For the local tier, callers pass the `("local","local","")` principal, so behaviour is unchanged. `api/activity.py`: swap the router dep to `require_principal`, add `principal=Depends(require_principal)`, pass it down. `capture.py`: when scheduling the fire-and-forget update, pass the capturing principal's org so the write lands in the **caller's** `__activity__` KB, not the configured user's.

**Steps:** (1) extend `test_activity_flow.py` to assert `resolve_activity_target` uses an injected org. (2) run → fail. (3) thread the params. (4) run → pass. (5) `git commit -m "feat(activity): scope activity graph reads+writes to the caller's org"`.

---

### Task A8: Cross-user isolation test (merge gate)

**Files:**
- Test: `backend/tests/test_isolation_cloud.py` — **integration**, `@pytest.mark.skipif` when Supabase creds / two seeded users are absent.

**Behaviour:** seed users A and B (each gets an org via the trigger); as A, capture a snapshot under repo `iso-A`; as B, call `/v1/projects`, `/v1/activity/graph`, `/v1/activity/stats`, and a `/v1/resume` for A's repo. Assert none of A's `kg_nodes`/findings/projects appear. Use httpx against an app instance with `BRAIN2_BACKEND=cloud`, minting each user's Bearer via the GoTrue password login (test fixture). Document the seed in the test docstring.

**Steps:** (1) write the skipped-by-default integration test. (2) run locally if creds present, else confirm it skips cleanly. (3) `git commit -m "test(auth): cross-user isolation gate for cloud reads"`.

**End of Phase A — run the full suite:** `.venv/bin/pytest -q` (expect the pre-existing 1 known failure only) + `.venv/bin/ruff check` + `.venv/bin/pyright`.

---

## Phase B — Apple bridge endpoints

### Task B1: `POST /v1/auth/apple`

**Files:**
- Create: `backend/brain2/api/apple_auth.py`
- Modify: `backend/brain2/api/main.py` (include the router)
- Test: `backend/tests/test_apple_auth.py`

**Step 1 — Write the failing test** (mock `sign_in_with_id_token`; no real Supabase/Apple):
```python
# backend/tests/test_apple_auth.py
from fastapi.testclient import TestClient
import brain2.api.apple_auth as mod
from brain2.api.main import create_app

class _Session: access_token="acc"; refresh_token="ref"; expires_in=3600; expires_at=1234
class _User: id="user-apple-1"
class _Resp: session=_Session(); user=_User()

def test_apple_exchange_returns_session(monkeypatch):
    monkeypatch.setattr(mod, "_apple_sign_in", lambda token, nonce: _Resp())
    client = TestClient(create_app())
    r = client.post("/v1/auth/apple", json={"identity_token": "tok", "nonce": "n"})
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"] == "acc" and body["user_id"] == "user-apple-1"

def test_apple_exchange_bad_token_401(monkeypatch):
    def boom(token, nonce): raise mod.AppleAuthError("bad")
    monkeypatch.setattr(mod, "_apple_sign_in", boom)
    client = TestClient(create_app())
    r = client.post("/v1/auth/apple", json={"identity_token": "x", "nonce": "n"})
    assert r.status_code == 401
```

**Step 2 — Run, expect fail** (module missing).

**Step 3 — Implement** `apple_auth.py`:
```python
"""POST /v1/auth/apple — exchange an Apple identityToken for a Supabase session.

Delegates Apple-token verification + GoTrue user provisioning to Supabase via
sign_in_with_id_token. Un-gated (it MINTS the session). No Apple crypto here.
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase import create_client
from brain2.config import get_settings

router = APIRouter(prefix="/v1/auth")


class AppleAuthError(Exception):
    ...


class AppleExchangeRequest(BaseModel):
    identity_token: str
    nonce: str | None = None


class SessionResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    expires_at: int | None = None
    user_id: str


def _apple_sign_in(identity_token: str, nonce: str | None):
    s = get_settings()
    if not (s.supabase_url and s.supabase_anon_key):
        raise AppleAuthError("Supabase not configured")
    anon = create_client(s.supabase_url, s.supabase_anon_key)
    creds: dict = {"provider": "apple", "token": identity_token}
    if nonce:
        creds["nonce"] = nonce
    try:
        return anon.auth.sign_in_with_id_token(creds)
    except Exception as e:  # gotrue AuthApiError et al.
        raise AppleAuthError(str(e)) from e


@router.post("/apple", response_model=SessionResponse)
async def apple_exchange(body: AppleExchangeRequest) -> SessionResponse:
    try:
        res = _apple_sign_in(body.identity_token, body.nonce)
    except AppleAuthError as e:
        raise HTTPException(status_code=401, detail=f"Apple sign-in failed: {e}")
    sess, user = res.session, res.user
    if not sess or not user:
        raise HTTPException(status_code=401, detail="No session from Supabase")
    return SessionResponse(
        access_token=sess.access_token, refresh_token=sess.refresh_token,
        expires_in=sess.expires_in, expires_at=getattr(sess, "expires_at", None),
        user_id=user.id,
    )
```
In `main.py`, `from brain2.api import apple_auth` and `app.include_router(apple_auth.router)` (no auth dependency on this router).

**Step 4 — Run, expect pass.**

**Step 5 — Commit:** `git commit -m "feat(api): POST /v1/auth/apple bridges Apple token to Supabase session"`

---

### Task B2: `POST /v1/auth/refresh` proxy

**Files:** Modify `backend/brain2/api/apple_auth.py` (+ test). Adds a route that POSTs to `{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token` with the `apikey: <anon>` header and `{"refresh_token": …}`, returning the rotated `SessionResponse`. Use `httpx.AsyncClient`. Test by monkeypatching the HTTP call. Commit: `feat(api): POST /v1/auth/refresh proxies GoTrue refresh (keeps anon key server-side)`.

---

## Phase C — Deploy (Fly.io)

### Task C1: Dockerfile + .dockerignore
**Files:** Create `backend/Dockerfile`, `backend/.dockerignore`.
```dockerfile
# backend/Dockerfile
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 BRAIN2_BACKEND=cloud
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .
COPY brain2 ./brain2
EXPOSE 8002
CMD ["sh", "-c", "uvicorn brain2.api.main:app --host 0.0.0.0 --port ${PORT:-8002}"]
```
`.dockerignore`: `.venv`, `.git`, `tests`, `__pycache__`, `*.pyc`, `../ios-app`, `../vscode-extension`. **Verify:** `docker build -t brain2 backend && docker run -e SUPABASE_URL=… -e PORT=8080 -p 8080:8080 brain2` → `curl localhost:8080/health` returns `{"status":"ok"}`. Commit.

### Task C2: fly.toml
**Files:** Create `backend/fly.toml` (app name, primary region, `[http_service]` `internal_port = 8002`, `force_https = true`, `[checks]` HTTP `GET /health`). Commit.

### Task C3: Provision + deploy
Manual/CLI checklist (record commands in PR description):
- `fly launch --no-deploy` (or `fly apps create brain2-api`).
- `fly secrets set SUPABASE_URL=… SUPABASE_ANON_KEY=… SUPABASE_SERVICE_ROLE_KEY=… SUPABASE_JWT_SECRET=… ANTHROPIC_API_KEY=… OPENAI_API_KEY=… TAVILY_API_KEY=…`
- `fly deploy`.
- Smoke: `curl https://<app>.fly.dev/health`; then a JWT-gated read with a real GoTrue token → 200; no token → 401.
- (Optional) attach the `api.brain2.dev` domain: `fly certs add api.brain2.dev` + DNS.

---

## Phase D — Supabase Apple provider (dashboard, one-time)
Checklist (not code; document completion in the PR):
1. Apple Developer portal: App ID has "Sign in with Apple" capability; note the **bundle id** (e.g. `com.brain2.app`).
2. Supabase → Authentication → Providers → Apple → enable; put the **bundle id** in **Client IDs** (native-only → skip Services ID / .p8 / Key ID / Team ID).
3. Confirm `SUPABASE_JWT_SECRET` (Settings → API → JWT secret) matches the Fly secret from C3.
4. Verify with a real device token end to end before iOS rollout (Task E5).

---

## Phase E — iOS wiring

### Task E1: Nonce + Apple request
**Files:** `ios-app/Brain2/Auth/AppleSignIn.swift`. Generate a cryptographically-random `rawNonce`; set `request.nonce = sha256(rawNonce)`; retain `rawNonce` to send to the backend. Add a `sha256(_:)` helper (CryptoKit). Manual build-check in Xcode (`xcodegen generate && open Brain2.xcodeproj`).

### Task E2: Call `/v1/auth/apple` + store session
**Files:** `ios-app/Brain2/Auth/AuthStore.swift`, `Networking/APIClient.swift`, `Auth/Keychain.swift`. On `didCompleteWithAuthorization`, POST `{ identity_token: identityToken, nonce: rawNonce }` to `/v1/auth/apple`; decode `SessionResponse`; persist `access_token` + `refresh_token` + `expires_at` in Keychain (service `dev.brain2.app`); set signed-in state.

### Task E3: Refresh on 401
**Files:** `Networking/APIClient.swift`, `AuthStore.swift`. Replace the v1 "401 → sign out" with: on 401, POST stored `refresh_token` to `/v1/auth/refresh`; persist the **rotated** tokens; retry once; only sign out if refresh fails.

### Task E4: Point at the hosted domain; retire ConnectionSheet
**Files:** `ios-app/Brain2/Config.swift` (base URL → `https://api.brain2.dev` or the Fly URL), `Views/SignInView.swift` (remove the manual base-URL/token `ConnectionSheet`).

### Task E5: TestFlight end-to-end
Real device: Sign in with Apple → lands on Home (`/v1/projects`) → open a resume card. Confirm a second Apple account sees only its own data (the human side of Task A8). Document the run.

---

## Final verification
- Backend: `.venv/bin/pytest -q` green (minus the 1 known pre-existing failure), `ruff` + `pyright` clean.
- `A8` isolation test passes against the deployed cloud tier with two real users.
- `CLAUDE.md`: update the cloud-auth notes (BRAIN2_API_KEY is now service-only; cloud tenancy is JWT-driven; add `/v1/auth/apple` + `/v1/auth/refresh` to the API table) — do this as the last commit.

## Notes for the executor
- DRY/YAGNI/TDD, frequent commits, one task at a time.
- Phase A is the load-bearing, security-critical unit — do not merge it half-done (auth without KG org-scoping = open cross-org reads).
- The live Supabase is the **shared Divergence instance** — never run destructive SQL; schema changes go through reviewed migration files, not ad-hoc MCP writes.
- Local-tier behaviour must stay byte-for-byte unchanged (single user, no auth, loopback) — every `Principal`/`org_id` change forks on `active_backend()`.
