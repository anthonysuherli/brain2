"""Web-research exploration pipeline (plan → search → crawl → extract → merge).

Pure of Supabase, SSE, and FastAPI: `run_exploration` takes a prompt + config
and a progress callback, and returns a list of `Finding` objects. `tools/explore.py`
owns persistence. LLM calls route through Vercel AI Gateway; web search/extract
via Tavily.
"""

from brain2.exploration.engine import run_exploration
from brain2.exploration.models import (
    ExplorationPlan,
    Finding,
    RawFinding,
    SearchQuery,
    Source,
)

__all__ = [
    "run_exploration",
    "ExplorationPlan",
    "Finding",
    "RawFinding",
    "SearchQuery",
    "Source",
]
