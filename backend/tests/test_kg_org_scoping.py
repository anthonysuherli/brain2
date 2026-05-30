import brain2.store.supabase as sup


class _Q:
    def __init__(self, sink, inserts):
        self.sink = sink
        self.inserts = inserts
        self._cols = set()
    def select(self, *a, **k): return self
    def eq(self, col, val):
        self.sink.append((col, val))
        self._cols.add(col)
        return self
    def in_(self, *a, **k): return self
    def or_(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def insert(self, row):
        self.inserts.append(row); return self
    def update(self, *a, **k): return self
    def execute(self):
        # The node existence probe filters on both type and label; return empty
        # for it so upsert_kg_nodes takes the INSERT branch (exercise write path).
        existence_probe = {"type", "label"}.issubset(self._cols)
        rows = [] if existence_probe else [{"id": "n1"}]
        class R:
            data = rows
            count = 0
        return R()


class _SB:
    def __init__(self, sink, inserts):
        self.sink = sink
        self.inserts = inserts
    def table(self, *_):
        return _Q(self.sink, self.inserts)


def _patch(monkeypatch):
    sink, inserts = [], []
    monkeypatch.setattr(sup, "service_client", lambda: _SB(sink, inserts))
    return sink, inserts


def test_list_kg_nodes_filters_by_org_when_set(monkeypatch):
    sink, _ = _patch(monkeypatch)
    sup.SupabaseStore(access_token="t", org_id="org-X").list_kg_nodes("kb-1")
    assert ("org_id", "org-X") in sink and ("kb_id", "kb-1") in sink


def test_list_kg_nodes_no_org_filter_when_none(monkeypatch):
    sink, _ = _patch(monkeypatch)
    sup.SupabaseStore(access_token="t").list_kg_nodes("kb-1")  # org_id=None
    assert ("kb_id", "kb-1") in sink
    assert not any(c == "org_id" for c, _ in sink)


def test_kg_stats_filters_by_org(monkeypatch):
    sink, _ = _patch(monkeypatch)
    sup.SupabaseStore(access_token="t", org_id="org-X").kg_stats("kb-1")
    assert ("org_id", "org-X") in sink


def test_get_kg_subgraph_unseeded_filters_by_org(monkeypatch):
    sink, _ = _patch(monkeypatch)
    sup.SupabaseStore(access_token="t", org_id="org-X").get_kg_subgraph("kb-1")
    assert ("org_id", "org-X") in sink


async def test_upsert_kg_nodes_writes_store_org(monkeypatch):
    sink, inserts = _patch(monkeypatch)
    store = sup.SupabaseStore(access_token="t", org_id="org-X")
    # The fake's existence probe (filters type+label) returns empty, so the node
    # is treated as NEW and the INSERT branch is exercised. The caller-supplied
    # org_id ("ATTACKER-ORG") must be ignored in favour of the store's org.
    await store.upsert_kg_nodes(
        "kb-1", [{"type": "repo", "label": "r", "org_id": "ATTACKER-ORG"}]
    )
    node_inserts = [row for row in inserts if "type" in row]
    assert node_inserts, "expected the insert path to be exercised"
    for row in node_inserts:
        assert row["org_id"] == "org-X"


def test_get_kg_subgraph_seeded_filters_by_org(monkeypatch):
    sink, _ = _patch(monkeypatch)
    sup.SupabaseStore(access_token="t", org_id="org-X").get_kg_subgraph(
        "kb-1", seed_node_ids=["n1"]
    )
    # Both the edges query and the by-id nodes query must carry the org filter.
    assert ("org_id", "org-X") in sink
