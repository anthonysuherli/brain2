"""Runtime configuration — adapted from Delapan for brain2.

Two layers:
* ``Settings`` — secrets and infra (API keys, Supabase, CORS). From env / .env.
* ``AppConfig`` — tunable knobs. From config.yaml + ``B2_<SECTION>__<FIELD>`` env overrides.

brain2 shares the same Supabase instance as Delapan, so the infra env var
names (SUPABASE_URL, OPENAI_API_KEY, etc.) are intentionally identical.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env", extra="ignore"
    )

    # Supabase (shared with Delapan). Optional: the free/local tier
    # (BRAIN2_BACKEND=local, SQLite) boots with NONE of these set. The cloud
    # tier requires them — clients.supabase.service_client() raises a clear
    # error only when actually called without creds (not at import/Settings time).
    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_anon_key: str | None = Field(default=None, alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str | None = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_jwt_secret: str | None = Field(default=None, alias="SUPABASE_JWT_SECRET")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")

    # LLM provider keys. `openai_api_key` powers embeddings (needed in BOTH
    # tiers) but stays optional here so Settings construction never explodes;
    # the embedding client surfaces a clear error if it is actually missing.
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    # Vercel AI Gateway (Phase 3 explore) — cloud-only, optional.
    ai_gateway_api_key: str | None = Field(default=None, alias="AI_GATEWAY_API_KEY")
    ai_gateway_base_url: str = Field(
        default="https://ai-gateway.vercel.sh/v1", alias="AI_GATEWAY_BASE_URL"
    )

    # Tavily (Phase 3 gap-fill)
    tavily_api_key: str | None = Field(default=None, alias="TAVILY_API_KEY")

    # brain2 REST API key — sent by VS Code extension in Authorization: Bearer
    brain2_api_key: str = Field(default="", alias="BRAIN2_API_KEY")

    # MCP / KB auth (Supabase GoTrue user — shared with Delapan)
    mcp_user_email: str = Field(default="dev@divergence.local", alias="DVG_MCP_USER_EMAIL")
    mcp_user_password: str = Field(default="dev-password-123", alias="DVG_MCP_USER_PASSWORD")

    # CORS
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "vscode-webview://*"],
        alias="CORS_ORIGINS",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


# =============================================================================
# Tunable application config (YAML-backed)
# =============================================================================


class AgentConfig(BaseModel):
    model: str = "claude-sonnet-4-6"
    fast_model: str = "claude-haiku-4-5"
    temperature: float = 0.2
    max_tokens: int = 4096
    thinking_budget: int = 0


class SearchConfig(BaseModel):
    default_limit: int = 10
    max_limit: int = 50
    min_similarity: float = 0.0
    max_finding_chunks: int = 25


class TiersConfig(BaseModel):
    band1_min: float = 0.55
    band2_min: float = 0.40
    band3_min: float = 0.25
    rich_hit_count: int = 3
    preamble_char_budget: int = 5000  # resume card is tighter than a chat preamble


class SynopsisConfig(BaseModel):
    model: str = "claude-haiku-4-5"
    rebuild_delta: int = 5  # snapshots accumulate faster than research findings
    rebuild_max_age_hours: int = 168
    max_entries: int = 6


class ExplorationConfig(BaseModel):
    """Phase 3 — gap-fill explore pipeline."""

    planner_model: str = "anthropic/claude-sonnet-4.6"
    extraction_model: str = "anthropic/claude-sonnet-4.6"
    extraction_fallback_model: str = "openai/gpt-4o-mini"
    evaluation_model: str = "anthropic/claude-sonnet-4.6"
    temperature: float = 0.0
    reasoning_effort: str | None = None

    search_depth: str = "advanced"
    max_results_per_query: int = 20
    fallback_result_threshold: int = 5
    expansion_result_threshold: int = 3
    max_concurrent_searches: int = 5

    max_pages: int = 15
    max_concurrent_extractions: int = 10
    max_content_per_page: int = 100_000

    fuzzy_match_threshold: float = 0.80
    min_confidence_threshold: float = 0.2

    enable_evaluation: bool = True

    default_max_findings: int = 12
    max_findings: int = 40


class EmbeddingConfig(BaseModel):
    model: str = "text-embedding-3-small"
    dim: int = 1536
    input_char_cap: int = 8192
    chunk_max_chars: int = 1800


class ActivityConfig(BaseModel):
    """Activity knowledge graph — the per-user, cross-repo work graph.

    Populated automatically on every capture: a deterministic structural pass
    (Repo/Branch/File/Session nodes from snapshot fields) plus an optional LLM
    pass that distils the one-line ``hypothesis`` into a concise Task label.
    Both passes are best-effort and never block or fail a capture.
    """

    # Reserved per-org namespace for the activity graph (one KB per user/org).
    project_name: str = "__activity__"
    kb_name: str = "default"

    # LLM task distillation (hypothesis → short Task label). When disabled or it
    # fails, the raw hypothesis is used as the Task label — the graph still grows.
    task_model: str = "claude-haiku-4-5"
    task_fallback_model: str = "openai/gpt-4o-mini"
    temperature: float = 0.0
    max_task_label_chars: int = 80

    # Caps on what one capture contributes, so a noisy snapshot can't flood the graph.
    max_files_per_session: int = 12
    # Semantic subgraph seeding (brain2_activity query / GET /v1/activity/graph?q=).
    query_min_similarity: float = 0.25
    subgraph_node_cap: int = 200
    subgraph_edge_cap: int = 600
    # Rollup shown on the cross-repo resume card.
    rollup_sessions: int = 6


class LivingDocsConfig(BaseModel):
    """Living Docs — two-layer on-disk documentation (notes → curated tree)."""

    root_dirname: str = ".brain2"
    notes_dirname: str = "notes"
    docs_dirname: str = "docs"
    policy_filename: str = "notes-policy.json"
    state_filename: str = "docs-state.json"
    # Distill debounce: re-distill when N new notes OR T minutes since last run.
    distill_debounce_n: int = 3
    distill_debounce_minutes: int = 60
    # Flat until this many notes exist, then allow taxonomy clustering.
    cluster_min_notes: int = 5
    distill_model: str = "claude-haiku-4-5"
    distill_fallback_model: str = "openai/gpt-4o-mini"
    temperature: float = 0.0
    # Auto-capture watcher.
    watch_interval_seconds: int = 180


class ConceptConfig(BaseModel):
    """Concept distillation — the synthesis tier above findings/activity.

    Runs select->synthesize->evaluate->reconcile over a KB's evidence to produce
    `concept` KG nodes. Best-effort and gated; never blocks capture/explore.
    """

    # Synthesis LLM (evidence cluster -> candidate concepts).
    synth_model: str = "anthropic/claude-sonnet-4.6"
    synth_fallback_model: str = "openai/gpt-5.4-mini"
    temperature: float = 0.0

    # Neighborhood selection caps.
    neighborhood_cap: int = 30          # max findings fed to one synthesis call
    max_concepts_per_pass: int = 6      # cap candidates from one synthesis call

    # Reconcile (Phase A: new vs reinforce).
    reconcile_min_sim: float = 0.78     # cosine: above => same concept, reinforce
    reconcile_fuzzy: float = 0.80       # SequenceMatcher claim-title ratio

    # Quality gate (reuses the exploration critic).
    enable_evaluation: bool = True
    min_confidence: float = 0.2


class KnowledgeGraphConfig(BaseModel):
    """KG intent schema — proposer + validator knobs.

    Model slugs use the Vercel AI Gateway dotted format (same as ExplorationConfig)
    because the proposer runs as a pipeline pass through the gateway.
    """

    extraction_model: str = "anthropic/claude-sonnet-4.6"
    extraction_fallback_model: str = "openai/gpt-4o-mini"
    temperature: float = 0.0
    reasoning_effort: str | None = None

    max_findings: int = 120  # cap on findings fed to the schema proposer
    max_finding_chars: int = 1200  # per-finding content truncation in the prompt
    max_nodes: int = 500  # cap on nodes kept after extraction collapse


class DriftConfig(BaseModel):
    """Schema-drift detector — decides *when* to offer the KG-schema wizard.

    Reads off the built graph's type distribution (``kg_stats().by_type``) against
    the KB's approved intent schema. A node is a **residual** when its type is
    ``"other"`` or (a schema is set and) its type isn't one the schema declares —
    i.e. the extractor kept signal the ontology couldn't place. Two fire modes:

    - **cold_start** — no schema set yet and the graph has crossed ``cold_start_min_nodes``
      ("enough collected to propose a first schema").
    - **drift** — a schema is set and the residual ratio over the graph crossed
      ``drift_ratio`` with at least ``drift_floor`` residual nodes ("reality moved
      past the ontology").

    Both are gated/debounced so a declined offer doesn't re-nag every session:
    cold_start reuses the ``init_offered`` stamp; drift re-arms only once residual
    grows by ``rearm_delta`` beyond the count stamped at the last offer.
    """

    min_nodes: int = 8           # below this the graph is too small to judge at all
    cold_start_min_nodes: int = 12  # enough nodes (no schema) to propose a first ontology
    drift_ratio: float = 0.30    # residual / total at/above which the ontology is "drifting"
    drift_floor: int = 4         # absolute residual floor (a tiny graph can't trip drift)
    rearm_delta: int = 6         # extra residual growth before a declined drift offer re-arms


class PublicApiConfig(BaseModel):
    preamble_default_limit: int = 12
    preamble_max_limit: int = 40
    findings_default_limit: int = 20
    findings_max_limit: int = 100
    graph_default_depth: int = 2
    graph_max_depth: int = 4
    graph_node_cap: int = 500
    graph_edge_cap: int = 2000
    min_similarity: float = 0.0


class MonitoringConfig(BaseModel):
    default_window_days: int = 30
    staleness_days: int = 30
    low_confidence_threshold: float = 0.4
    high_confidence_threshold: float = 0.7
    coverage_gap_min_findings: int = 2
    finding_scan_cap: int = 5000
    retention_days: int = 90


class AppConfig(BaseModel):
    agent: AgentConfig = Field(default_factory=AgentConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    tiers: TiersConfig = Field(default_factory=TiersConfig)
    synopsis: SynopsisConfig = Field(default_factory=SynopsisConfig)
    exploration: ExplorationConfig = Field(default_factory=ExplorationConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    activity: ActivityConfig = Field(default_factory=ActivityConfig)
    living_docs: LivingDocsConfig = Field(default_factory=LivingDocsConfig)
    concept: ConceptConfig = Field(default_factory=ConceptConfig)
    knowledge_graph: KnowledgeGraphConfig = Field(default_factory=KnowledgeGraphConfig)
    drift: DriftConfig = Field(default_factory=DriftConfig)
    public_api: PublicApiConfig = Field(default_factory=PublicApiConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)


_ENV_PREFIX = "B2_"
_NESTED_DELIM = "__"


def _config_path() -> Path:
    override = os.getenv("BRAIN2_CONFIG_FILE")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / "config.yaml"


def _load_file(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config file {path} must contain a YAML mapping")
    return data


def _env_overrides() -> dict:
    out: dict[str, dict] = {}
    for key, value in os.environ.items():
        if not key.startswith(_ENV_PREFIX) or _NESTED_DELIM not in key:
            continue
        section, _, field = key[len(_ENV_PREFIX) :].partition(_NESTED_DELIM)
        if not section or not field:
            continue
        out.setdefault(section.lower(), {})[field.lower()] = value
    return out


def _deep_merge(base: dict, override: dict) -> dict:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    data: dict = {}
    _deep_merge(data, _load_file(_config_path()))
    _deep_merge(data, _env_overrides())
    return AppConfig.model_validate(data)
