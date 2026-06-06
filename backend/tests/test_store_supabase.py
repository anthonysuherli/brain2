"""SupabaseStore unit tests against a fake Supabase client.

No live Supabase here: a small fake reproduces the chainable
`.table().select().eq()....execute()` and `.rpc().execute()` surface and records
the calls it received, so we assert on the queries the store issues (table,
filters, payloads) rather than mocking the store itself.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

import br8n.store.supabase as supa
from br8n.store import Store, SupabaseStore, get_store


# --- fake supabase client ---------------------------------------------------


@dataclass
class _Result:
    data: list | None = None
    count: int | None = None


class _Query:
    """Records the chained builder calls; returns canned data on execute()."""

    def __init__(self, table: str, log: list, result: _Result, *, insert_raises=False):
        self.table = table
        self.log = log
        self.result = result
        self._insert_raises = insert_raises
        self.op = None
        self.payload = None
        self.filters: dict = {}
        self.select_cols = None
        self.select_kwargs: dict = {}
        self.order_col = None
        self.limit_n = None

    def select(self, cols, **kwargs):
        self.op = "select"
        self.select_cols = cols
        self.select_kwargs = kwargs
        return self

    def insert(self, payload):
        if self._insert_raises:
            raise RuntimeError("boom")
        self.op = "insert"
        self.payload = payload
        return self

    def upsert(self, payload, **kwargs):
        self.op = "upsert"
        self.payload = payload
        self.upsert_kwargs = kwargs
        return self

    def update(self, payload):
        self.op = "update"
        self.payload = payload
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, col, val):
        self.filters[col] = val
        return self

    def order(self, col, desc=False):
        self.order_col = (col, desc)
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def execute(self):
        self.log.append(self)
        return self.result


class FakeClient:
    """Returns canned _Result per (table, op); records rpc calls."""

    def __init__(self, *, tables=None, rpc_data=None, insert_raises=False):
        # tables: {table_name: _Result}
        self.tables = tables or {}
        self.rpc_data = rpc_data if rpc_data is not None else []
        self.insert_raises = insert_raises
        self.queries: list[_Query] = []
        self.rpc_calls: list[tuple[str, dict]] = []

    def table(self, name):
        result = self.tables.get(name, _Result(data=[]))
        return _Query(name, self.queries, result, insert_raises=self.insert_raises)

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return _RpcCall(_Result(data=self.rpc_data))


class _RpcCall:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


@dataclass
class _Target:
    target_type: str
    target_id: str | None = None


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def patch_clients(monkeypatch):
    """Patch service_client/user_client in the store module to a single fake."""

    def _install(fake: FakeClient) -> FakeClient:
        monkeypatch.setattr(supa, "service_client", lambda: fake)
        monkeypatch.setattr(supa, "user_client", lambda token: fake)
        return fake

    return _install


# --- import smoke -----------------------------------------------------------


def test_import_smoke(monkeypatch):
    # get_store now selects by backend; force cloud to exercise the Supabase path.
    monkeypatch.setenv("BR8N_BACKEND", "cloud")
    assert isinstance(get_store(None), SupabaseStore)
    assert isinstance(get_store("tok"), SupabaseStore)
    # Store is a (non-runtime-checkable) Protocol; assert the surface is present.
    for m in ("match_findings", "insert_findings", "get_finding", "list_findings",
              "count_findings", "delete_finding", "load_synopsis", "upsert_synopsis", "create_exploration",
              "update_exploration", "get_exploration", "resolve_project", "resolve_kb",
              "record_access"):
        assert hasattr(SupabaseStore, m), m
    assert Store is not None


# --- match_findings ---------------------------------------------------------


async def test_match_findings_rpc(patch_clients):
    fake = patch_clients(FakeClient(rpc_data=[{"id": "f1", "similarity": 0.9}]))
    store = SupabaseStore()
    out = await store.match_findings("kb1", [0.1, 0.2], match_count=5, min_similarity=0.3)

    assert out == [{"id": "f1", "similarity": 0.9}]
    name, params = fake.rpc_calls[0]
    assert name == "match_findings"
    assert params == {
        "query_embedding": [0.1, 0.2],
        "match_kb_id": "kb1",
        "match_count": 5,
        "min_similarity": 0.3,
    }


# --- insert_findings --------------------------------------------------------


async def test_insert_findings(patch_clients):
    fake = patch_clients(
        FakeClient(tables={"findings": _Result(data=[{"id": "a"}, {"id": "b"}])})
    )
    store = SupabaseStore(access_token="tok")
    ids = await store.insert_findings([{"kb_id": "kb1", "title": "t"}, {"kb_id": "kb1"}])

    assert ids == ["a", "b"]
    q = fake.queries[-1]
    assert q.table == "findings"
    assert q.op == "insert"
    assert q.payload == [{"kb_id": "kb1", "title": "t"}, {"kb_id": "kb1"}]


async def test_insert_findings_empty(patch_clients):
    fake = patch_clients(FakeClient())
    store = SupabaseStore()
    assert await store.insert_findings([]) == []
    assert fake.queries == []  # no DB call


# --- get / list / delete ----------------------------------------------------


def test_get_finding(patch_clients):
    fake = patch_clients(
        FakeClient(tables={"findings": _Result(data=[{"id": "f1", "title": "T"}])})
    )
    store = SupabaseStore("tok")
    row = store.get_finding("kb1", "f1")

    assert row == {"id": "f1", "title": "T"}
    q = fake.queries[-1]
    assert q.table == "findings" and q.op == "select"
    assert q.filters == {"kb_id": "kb1", "id": "f1"}


def test_get_finding_missing(patch_clients):
    patch_clients(FakeClient(tables={"findings": _Result(data=[])}))
    with pytest.raises(RuntimeError, match="finding not found"):
        SupabaseStore().get_finding("kb1", "nope")


def test_list_findings(patch_clients):
    fake = patch_clients(
        FakeClient(tables={"findings": _Result(data=[{"id": "f1"}, {"id": "f2"}])})
    )
    out = SupabaseStore().list_findings("kb1", category="doc", limit=10)

    assert out == {"count": 2, "findings": [{"id": "f1"}, {"id": "f2"}]}
    q = fake.queries[-1]
    assert q.filters == {"kb_id": "kb1", "category": "doc"}
    assert q.order_col == ("created_at", True)
    assert q.limit_n == 10


def test_delete_finding(patch_clients):
    fake = patch_clients(FakeClient(tables={"findings": _Result(data=[])}))
    out = SupabaseStore("tok").delete_finding("kb1", "f1")

    assert out == {"deleted": "f1"}
    q = fake.queries[-1]
    assert q.table == "findings" and q.op == "delete"
    assert q.filters == {"kb_id": "kb1", "id": "f1"}


# --- count_findings ---------------------------------------------------------


def test_count_findings(patch_clients):
    fake = patch_clients(
        FakeClient(tables={"findings": _Result(data=[{"id": "f1"}], count=42)})
    )
    n = SupabaseStore("tok").count_findings("kb1")

    assert n == 42
    q = fake.queries[-1]
    assert q.table == "findings" and q.op == "select"
    assert q.select_kwargs == {"count": "exact"}
    assert q.filters == {"kb_id": "kb1"}
    assert q.limit_n == 1


def test_count_findings_none_count_defaults_zero(patch_clients):
    # No matching rows → .count is None → returns 0.
    patch_clients(FakeClient(tables={"findings": _Result(data=[], count=None)}))
    assert SupabaseStore().count_findings("kb1") == 0


# --- exploration ------------------------------------------------------------


def test_create_exploration(patch_clients):
    fake = patch_clients(
        FakeClient(tables={"explorations": _Result(data=[{"id": "e1"}])})
    )
    eid = SupabaseStore().create_exploration("org1", "kb1", "find stuff")

    assert eid == "e1"
    q = fake.queries[-1]
    assert q.table == "explorations" and q.op == "insert"
    assert q.payload["org_id"] == "org1"
    assert q.payload["kb_id"] == "kb1"
    assert q.payload["prompt"] == "find stuff"
    assert q.payload["status"] == "pending"


def test_update_exploration(patch_clients):
    fake = patch_clients(FakeClient(tables={"explorations": _Result(data=[])}))
    SupabaseStore().update_exploration("e1", status="completed", finding_ids=["f1"])

    q = fake.queries[-1]
    assert q.op == "update"
    assert q.payload == {"status": "completed", "finding_ids": ["f1"]}
    assert q.filters == {"id": "e1"}


def test_get_exploration(patch_clients):
    patch_clients(
        FakeClient(tables={"explorations": _Result(data=[{"id": "e1", "status": "x"}])})
    )
    assert SupabaseStore().get_exploration("e1") == {"id": "e1", "status": "x"}

    patch_clients(FakeClient(tables={"explorations": _Result(data=[])}))
    assert SupabaseStore().get_exploration("none") is None


# --- synopsis ---------------------------------------------------------------


def test_upsert_synopsis(patch_clients):
    fake = patch_clients(
        FakeClient(tables={"kbs": _Result(data=[{"org_id": "org1"}])})
    )
    SupabaseStore().upsert_synopsis("kb1", [{"topic": "t", "gloss": "g"}], 5, "gpt-4o-mini")

    q = fake.queries[-1]
    assert q.table == "kb_synopsis" and q.op == "upsert"
    assert q.payload["kb_id"] == "kb1"
    assert q.payload["org_id"] == "org1"
    assert q.payload["content"] == [{"topic": "t", "gloss": "g"}]
    assert q.payload["finding_count_at_build"] == 5
    assert q.payload["model"] == "gpt-4o-mini"
    assert q.upsert_kwargs == {"on_conflict": "kb_id"}


def test_upsert_synopsis_missing_kb_raises(patch_clients):
    patch_clients(FakeClient(tables={"kbs": _Result(data=[])}))
    with pytest.raises(RuntimeError, match="cannot upsert synopsis"):
        SupabaseStore().upsert_synopsis("kb1", [], 0, "gpt-4o-mini")


# --- tenancy: find-or-create ------------------------------------------------


def test_resolve_project_existing(patch_clients, monkeypatch):
    fake = patch_clients(FakeClient(tables={"projects": _Result(data=[{"id": "p1"}])}))
    monkeypatch.setattr(supa, "_login", lambda: ("u1", "tok"))
    monkeypatch.setattr(supa, "_org_for", lambda uid: "org1")

    org_id, pid = SupabaseStore().resolve_project("proj", create=False)

    assert (org_id, pid) == ("org1", "p1")
    q = fake.queries[-1]
    assert q.table == "projects" and q.op == "select"
    assert q.filters == {"org_id": "org1", "name": "proj"}


def test_resolve_project_create(patch_clients, monkeypatch):
    # select returns empty (absent), insert returns the new row.
    class TwoPhase(FakeClient):
        def __init__(self):
            super().__init__()
            self._phase = 0

        def table(self, name):
            # first .table() call -> empty select; second -> insert result
            result = _Result(data=[]) if self._phase == 0 else _Result(data=[{"id": "p9"}])
            self._phase += 1
            return _Query(name, self.queries, result)

    fake = patch_clients(TwoPhase())
    monkeypatch.setattr(supa, "_login", lambda: ("u1", "tok"))
    monkeypatch.setattr(supa, "_org_for", lambda uid: "org1")

    org_id, pid = SupabaseStore().resolve_project("newproj", create=True)
    assert (org_id, pid) == ("org1", "p9")
    assert fake.queries[-1].op == "insert"


def test_resolve_project_absent_no_create(patch_clients, monkeypatch):
    patch_clients(FakeClient(tables={"projects": _Result(data=[])}))
    monkeypatch.setattr(supa, "_login", lambda: ("u1", "tok"))
    monkeypatch.setattr(supa, "_org_for", lambda uid: "org1")

    with pytest.raises(RuntimeError, match="not found"):
        SupabaseStore().resolve_project("missing", create=False)


def test_resolve_kb_existing(patch_clients):
    fake = patch_clients(FakeClient(tables={"kbs": _Result(data=[{"id": "kb9"}])}))
    kb_id = SupabaseStore().resolve_kb("org1", "p1", "mykb", create=False)

    assert kb_id == "kb9"
    q = fake.queries[-1]
    assert q.table == "kbs"
    assert q.filters == {"org_id": "org1", "project_id": "p1", "name": "mykb"}


def test_resolve_kb_absent_no_create(patch_clients):
    patch_clients(FakeClient(tables={"kbs": _Result(data=[])}))
    with pytest.raises(RuntimeError, match="not found"):
        SupabaseStore().resolve_kb("org1", "p1", "missing", create=False)


# --- monitoring: best-effort ------------------------------------------------


async def test_record_access_inserts(patch_clients):
    fake = patch_clients(FakeClient(tables={"access_events": _Result(data=[])}))
    await SupabaseStore().record_access(
        org_id="org1",
        kb_id="kb1",
        surface="mcp",
        targets=[_Target("finding", "f1"), _Target("preamble")],
        query_text="q",
    )
    q = fake.queries[-1]
    assert q.table == "access_events" and q.op == "insert"
    assert q.payload == [
        {
            "org_id": "org1",
            "kb_id": "kb1",
            "target_type": "finding",
            "target_id": "f1",
            "surface": "mcp",
            "api_key_id": None,
            "query_text": "q",
        },
        {
            "org_id": "org1",
            "kb_id": "kb1",
            "target_type": "preamble",
            "target_id": None,
            "surface": "mcp",
            "api_key_id": None,
            "query_text": "q",
        },
    ]


async def test_record_access_empty_noop(patch_clients):
    fake = patch_clients(FakeClient())
    await SupabaseStore().record_access(
        org_id="o", kb_id="k", surface="mcp", targets=[]
    )
    assert fake.queries == []


async def test_record_access_swallows_exceptions(patch_clients):
    patch_clients(FakeClient(insert_raises=True))
    # Must not raise even though the insert blows up.
    await SupabaseStore().record_access(
        org_id="o",
        kb_id="k",
        surface="mcp",
        targets=[_Target("finding", "f1")],
    )


# --- activity knowledge graph -----------------------------------------------


async def test_update_kg_node_properties_only(patch_clients):
    fake = patch_clients(FakeClient(tables={"kg_nodes": _Result(data=[])}))
    await SupabaseStore().update_kg_node(
        "kb1", "n1", properties={"body": "new", "confidence": 0.9}
    )
    q = fake.queries[-1]
    assert q.table == "kg_nodes" and q.op == "update"
    assert q.payload == {"properties": {"body": "new", "confidence": 0.9}}
    # filtered by both id and kb_id
    assert q.filters.get("id") == "n1"
    assert q.filters.get("kb_id") == "kb1"
    # not provided → not written
    assert "grounded_in" not in q.payload
    assert "embedding" not in q.payload


async def test_update_kg_node_with_grounded_and_embedding(patch_clients):
    fake = patch_clients(FakeClient(tables={"kg_nodes": _Result(data=[])}))
    await SupabaseStore().update_kg_node(
        "kb1",
        "n1",
        properties={"body": "x"},
        grounded_in=["f1", "f2"],
        embedding=[0.1, 0.2, 0.3],
    )
    q = fake.queries[-1]
    assert q.table == "kg_nodes" and q.op == "update"
    assert q.payload["properties"] == {"body": "x"}
    assert q.payload["grounded_in"] == ["f1", "f2"]
    assert q.payload["embedding"] == [0.1, 0.2, 0.3]
    assert q.filters.get("id") == "n1"
    assert q.filters.get("kb_id") == "kb1"


def test_list_kg_nodes_selects_and_returns_grounded_in(patch_clients):
    fake = patch_clients(
        FakeClient(
            tables={
                "kg_nodes": _Result(
                    data=[
                        {
                            "id": "n1",
                            "type": "concept",
                            "label": "Auth",
                            "properties": {"body": "x"},
                            "grounded_in": ["f1"],
                            "created_at": "2026-06-01",
                        }
                    ]
                )
            }
        )
    )
    rows = SupabaseStore().list_kg_nodes("kb1", type="concept")
    q = fake.queries[-1]
    assert "grounded_in" in q.select_cols
    assert rows[0]["grounded_in"] == ["f1"]
