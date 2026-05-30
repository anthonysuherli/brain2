"""Cross-user isolation gate (cloud tier) — the multi-user merge gate.

This is an INTEGRATION test: it needs a live Supabase (the cloud tier) and two
real GoTrue users. It is skipped unless explicitly enabled, so it never runs in
the offline unit suite. Enable it with:

    BRAIN2_RUN_ISOLATION_IT=1
    BRAIN2_BACKEND=cloud
    SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY / SUPABASE_JWT_SECRET
    BRAIN2_TEST_USER_A_EMAIL / BRAIN2_TEST_USER_A_PASSWORD
    BRAIN2_TEST_USER_B_EMAIL / BRAIN2_TEST_USER_B_PASSWORD

Each user must already exist (the `handle_new_user` trigger gives each its own
org on signup). The test signs in as A, captures a snapshot under a unique repo,
then — as B — asserts none of A's data is visible through the per-user read
surfaces. This is the regression that proves the service-client + kb_id-only KG
path can no longer leak across orgs once tenancy is JWT-driven.
"""

from __future__ import annotations

import os
import time
import uuid

import pytest

_ENABLED = os.getenv("BRAIN2_RUN_ISOLATION_IT") == "1"

pytestmark = pytest.mark.skipif(
    not _ENABLED,
    reason="cloud cross-user isolation IT — set BRAIN2_RUN_ISOLATION_IT=1 (+ cloud creds and two test users)",
)


def _login(email: str, password: str) -> str:
    """GoTrue password login → access token (mirrors tenancy._login)."""
    from supabase import create_client

    anon = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
    res = anon.auth.sign_in_with_password({"email": email, "password": password})
    assert res.session, f"login failed for {email}"
    return res.session.access_token


@pytest.fixture()
def client():
    # Force the cloud tier and build the app fresh under that backend.
    os.environ["BRAIN2_BACKEND"] = "cloud"
    import brain2.config as config

    config.get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from brain2.api.main import create_app

    return TestClient(create_app())


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_user_b_cannot_see_user_a_activity(client):
    token_a = _login(
        os.environ["BRAIN2_TEST_USER_A_EMAIL"], os.environ["BRAIN2_TEST_USER_A_PASSWORD"]
    )
    token_b = _login(
        os.environ["BRAIN2_TEST_USER_B_EMAIL"], os.environ["BRAIN2_TEST_USER_B_PASSWORD"]
    )

    # A unique repo + hypothesis so we can prove they never surface for B.
    repo = f"iso-A-{uuid.uuid4().hex[:8]}"
    kb = "main"
    secret_hypothesis = f"SECRET-A-{uuid.uuid4().hex[:8]}"

    # --- A captures a snapshot -------------------------------------------------
    cap = client.post(
        "/v1/capture",
        headers=_auth(token_a),
        json={
            "project": repo,
            "kb": kb,
            "trigger": "manual",
            "captured_at": "2026-05-30T00:00:00Z",
            "branch": kb,
            "hypothesis": secret_hypothesis,
            "open_files": ["a.py"],
            "cursor_file": "a.py",
            "cursor_line": 1,
        },
    )
    assert cap.status_code == 200, cap.text
    # Give the fire-and-forget activity-KG population a moment to land.
    time.sleep(2.0)

    # --- B must not see any of A's data ---------------------------------------
    projects_b = client.get("/v1/projects", headers=_auth(token_b))
    assert projects_b.status_code == 200, projects_b.text
    b_project_names = {p["project"] for p in projects_b.json()["projects"]}
    assert repo not in b_project_names, "LEAK: B sees A's repo in /v1/projects"

    stats_b = client.get("/v1/activity/stats", headers=_auth(token_b))
    assert stats_b.status_code == 200, stats_b.text
    b_repo_hotspots = {
        h.get("label") for h in stats_b.json().get("hotspots", {}).get("repos", [])
    }
    assert repo not in b_repo_hotspots, "LEAK: B sees A's repo in /v1/activity/stats"

    graph_b = client.get("/v1/activity/graph", headers=_auth(token_b))
    assert graph_b.status_code == 200, graph_b.text
    b_graph_text = graph_b.text
    assert repo not in b_graph_text, "LEAK: B sees A's repo in /v1/activity/graph"
    assert secret_hypothesis not in b_graph_text, "LEAK: B sees A's hypothesis in the graph"

    # B resolving A's project by name must not return A's resume card. With
    # create=False, A's project does not exist in B's org → non-200 or empty,
    # but it must NEVER contain A's secret hypothesis.
    resume_b = client.get(
        f"/v1/resume/{repo}/{kb}", headers=_auth(token_b), params={"format": "json"}
    )
    assert secret_hypothesis not in resume_b.text, "LEAK: B reads A's resume hypothesis"

    # --- sanity: A CAN see its own data (the test isn't vacuously passing) -----
    projects_a = client.get("/v1/projects", headers=_auth(token_a))
    assert projects_a.status_code == 200, projects_a.text
    a_project_names = {p["project"] for p in projects_a.json()["projects"]}
    assert repo in a_project_names, "A should see its own freshly-captured repo"
