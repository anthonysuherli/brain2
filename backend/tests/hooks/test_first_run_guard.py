"""Tests for hooks/first-run-init.py — the SessionStart first-run guard.

All tests import the hook module directly so functions are testable without
running the hook as a subprocess.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Import the hook module from outside the package tree.
# ---------------------------------------------------------------------------

_HOOK_PATH = Path(__file__).parents[3] / "hooks" / "first-run-init.py"


def _load_hook():
    """Load the hook module by file path (it lives outside backend/)."""
    spec = importlib.util.spec_from_file_location("first_run_init", _HOOK_PATH)
    assert spec is not None and spec.loader is not None, f"Cannot load {_HOOK_PATH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


_hook = _load_hook()
repo_identity = _hook.repo_identity
derive_project_kb = _hook.derive_project_kb
build_directive = _hook.build_directive
check_kb_exists = _hook.check_kb_exists
pending_schema_offer = _hook.pending_schema_offer
build_offer_directive = _hook.build_offer_directive
ensure_global_statusline = _hook.ensure_global_statusline
_statusline_command = _hook._statusline_command


# ---------------------------------------------------------------------------
# repo_identity
# ---------------------------------------------------------------------------


def test_repo_identity_returns_none_for_non_git(tmp_path):
    """A plain directory (no .git) should return None."""
    identity = repo_identity(str(tmp_path))
    assert identity is None


def test_repo_identity_returns_path_for_git_repo_without_remote(tmp_path):
    """A git repo with no remote should fall back to the repo root path."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    identity = repo_identity(str(tmp_path))
    assert identity is not None
    assert str(tmp_path) in identity or tmp_path.name in identity


def test_repo_identity_uses_remote_origin(tmp_path):
    """When origin is set the identity is derived from the remote URL."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/acme/my-repo.git"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    identity = repo_identity(str(tmp_path))
    assert identity is not None
    assert "my-repo" in identity
    assert "acme" in identity
    assert ".git" not in identity


def test_repo_identity_normalizes_ssh_url(tmp_path):
    """SSH shorthand remote URLs should be normalised to host/path form."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:user/cool-project.git"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    identity = repo_identity(str(tmp_path))
    assert identity is not None
    assert "cool-project" in identity
    assert ".git" not in identity
    # Should be lowercase
    assert identity == identity.lower()


# ---------------------------------------------------------------------------
# derive_project_kb
# ---------------------------------------------------------------------------


def test_derive_project_kb_from_cwd(tmp_path):
    """When the repo has no remote the project name is the cwd basename."""
    project, kb = derive_project_kb(str(tmp_path))
    assert project == tmp_path.name or project == tmp_path.name.replace("_", "-")
    # Not a git repo → no branch → kb falls back to "main".
    assert kb == "main"


def test_derive_project_kb_uses_git_branch(tmp_path):
    """kb is the current git branch (matches skills/MCP/watcher), not always 'main'."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "feature-x"], cwd=tmp_path, check=True)
    _, kb = derive_project_kb(str(tmp_path))
    assert kb == "feature-x"


def test_derive_project_kb_falls_back_to_main_without_branch(tmp_path):
    """Outside a git repo (no branch) kb falls back to 'main'."""
    _, kb = derive_project_kb(str(tmp_path))
    assert kb == "main"


def test_derive_project_kb_cleans_special_chars(tmp_path):
    """Special characters in directory names are replaced with hyphens."""
    special = tmp_path / "my_repo.test"
    special.mkdir()
    project, _ = derive_project_kb(str(special))
    assert "_" not in project
    assert "." not in project


# ---------------------------------------------------------------------------
# build_directive
# ---------------------------------------------------------------------------


def test_build_directive_mentions_project_and_init():
    d = build_directive("my-repo", "main")
    assert "my-repo" in d
    assert "background" in d.lower()
    assert "project-init" in d


def test_build_directive_mentions_schema_wizard():
    d = build_directive("my-repo", "main")
    assert "kg-schema-wizard" in d


def test_build_directive_mentions_kb_name():
    d = build_directive("alpha", "session")
    assert "alpha" in d
    assert "session" in d


def test_build_directive_mentions_mark_init_offered():
    """The directive must reference the stamp call so Claude knows to call it."""
    d = build_directive("my-repo", "main")
    assert "br8n_mark_init_offered" in d


def test_build_directive_references_print_line():
    """The directive must tell Claude to print a visible line for the user."""
    d = build_directive("my-repo", "main")
    assert "Initializing br8n" in d


# ---------------------------------------------------------------------------
# check_kb_exists
# ---------------------------------------------------------------------------


def test_check_kb_exists_returns_true_when_tenant_resolves():
    with patch(
        "br8n.interfaces.mcp.tenancy.resolve_tenant",
        return_value=MagicMock(),
    ):
        result = check_kb_exists("my-project", "main")
    assert result is True


def test_check_kb_exists_returns_false_when_not_found():
    with patch(
        "br8n.interfaces.mcp.tenancy.resolve_tenant",
        side_effect=RuntimeError("kb main not found"),
    ):
        result = check_kb_exists("my-project", "main")
    assert result is False


def test_check_kb_exists_returns_none_on_backend_error():
    """A non-'not found' RuntimeError returns None (fail-closed)."""
    with patch(
        "br8n.interfaces.mcp.tenancy.resolve_tenant",
        side_effect=RuntimeError("connection refused"),
    ):
        result = check_kb_exists("my-project", "main")
    assert result is None


def test_check_kb_exists_returns_none_on_unexpected_exception():
    """Any unexpected exception returns None (fail-closed, not False)."""
    with patch(
        "br8n.interfaces.mcp.tenancy.resolve_tenant",
        side_effect=ImportError("module not found"),
    ):
        result = check_kb_exists("my-project", "main")
    assert result is None


# ---------------------------------------------------------------------------
# main() integration — stdout / silence
# ---------------------------------------------------------------------------


def test_main_emits_directive_for_first_run(capsys, tmp_path):
    """main() should print JSON additionalContext when KB does not exist."""
    with (
        patch.object(_hook, "repo_identity", return_value="github.com/user/repo"),
        patch.object(_hook, "derive_project_kb", return_value=("repo", "main")),
        patch.object(_hook, "check_kb_exists", return_value=False),
    ):
        hook_input = json.dumps({"cwd": str(tmp_path)})
        sys.stdin = __import__("io").StringIO(hook_input)
        try:
            _hook.main()
        finally:
            sys.stdin = sys.__stdin__

    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert "additionalContext" in out
    assert "repo" in out["additionalContext"]


def test_main_silent_when_kb_exists_and_no_offer(capsys, tmp_path):
    """KB exists and the detector has nothing to offer → no output."""
    with (
        patch.object(_hook, "repo_identity", return_value="github.com/user/repo"),
        patch.object(_hook, "derive_project_kb", return_value=("repo", "main")),
        patch.object(_hook, "check_kb_exists", return_value=True),
        patch.object(_hook, "pending_schema_offer", return_value=None),
    ):
        hook_input = json.dumps({"cwd": str(tmp_path)})
        sys.stdin = __import__("io").StringIO(hook_input)
        try:
            _hook.main()
        finally:
            sys.stdin = sys.__stdin__

    captured = capsys.readouterr()
    assert captured.out == ""


def test_main_emits_drift_offer_when_kb_exists(capsys, tmp_path):
    """KB exists and the detector says to offer → emit the drift directive."""
    verdict = {
        "mode": "drift",
        "residual": 12,
        "offer_line": "Your knowledge graph has drifted: 12/40 nodes don't fit schema v2 — reshape it? `/br8n:schema`",
        "should_offer": True,
    }
    with (
        patch.object(_hook, "repo_identity", return_value="github.com/user/repo"),
        patch.object(_hook, "derive_project_kb", return_value=("repo", "main")),
        patch.object(_hook, "check_kb_exists", return_value=True),
        patch.object(_hook, "pending_schema_offer", return_value=verdict),
    ):
        hook_input = json.dumps({"cwd": str(tmp_path)})
        sys.stdin = __import__("io").StringIO(hook_input)
        try:
            _hook.main()
        finally:
            sys.stdin = sys.__stdin__

    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert "additionalContext" in out
    assert "drifted" in out["additionalContext"]
    assert "br8n_mark_drift_offered" in out["additionalContext"]
    assert "residual=12" in out["additionalContext"]


# ---------------------------------------------------------------------------
# build_offer_directive
# ---------------------------------------------------------------------------


def test_build_offer_directive_drift_stamps_drift_marker():
    verdict = {"mode": "drift", "residual": 7, "offer_line": "drifted — reshape? `/br8n:schema`"}
    d = build_offer_directive("repo", "main", verdict)
    assert "br8n_mark_drift_offered" in d
    assert "residual=7" in d
    assert "/br8n:schema" in d
    assert "drifted" in d  # the offer_line is surfaced verbatim


def test_build_offer_directive_cold_start_stamps_init_offered():
    verdict = {"mode": "cold_start", "offer_line": "enough collected — design a schema? `/br8n:schema`"}
    d = build_offer_directive("repo", "main", verdict)
    assert "br8n_mark_init_offered" in d
    assert "br8n_mark_drift_offered" not in d
    assert "do not block" in d.lower()  # non-blocking contract is stated


def test_pending_schema_offer_none_when_gate_disabled(monkeypatch):
    """The BR8N_SCHEMA_DRIFT=0 kill switch short-circuits to None (silent)."""
    monkeypatch.setenv("BR8N_SCHEMA_DRIFT", "0")
    assert pending_schema_offer("repo", "main") is None


def test_main_silent_when_not_git_repo(capsys, tmp_path):
    """main() should produce no output for non-git directories."""
    with patch.object(_hook, "repo_identity", return_value=None):
        hook_input = json.dumps({"cwd": str(tmp_path)})
        sys.stdin = __import__("io").StringIO(hook_input)
        try:
            _hook.main()
        finally:
            sys.stdin = sys.__stdin__

    captured = capsys.readouterr()
    assert captured.out == ""


def test_main_silent_when_backend_unreachable(capsys, tmp_path):
    """main() should be silent (fail-closed) when backend check returns None."""
    with (
        patch.object(_hook, "repo_identity", return_value="github.com/user/repo"),
        patch.object(_hook, "derive_project_kb", return_value=("repo", "main")),
        patch.object(_hook, "check_kb_exists", return_value=None),
    ):
        hook_input = json.dumps({"cwd": str(tmp_path)})
        sys.stdin = __import__("io").StringIO(hook_input)
        try:
            _hook.main()
        finally:
            sys.stdin = sys.__stdin__

    captured = capsys.readouterr()
    assert captured.out == ""


def test_main_handles_session_cwd_key(capsys, tmp_path):
    """main() accepts the nested session.cwd payload shape."""
    with (
        patch.object(_hook, "repo_identity", return_value=None),
    ):
        hook_input = json.dumps({"session": {"cwd": str(tmp_path)}})
        sys.stdin = __import__("io").StringIO(hook_input)
        try:
            _hook.main()
        finally:
            sys.stdin = sys.__stdin__

    # repo_identity returns None → silent exit (correct behaviour)
    captured = capsys.readouterr()
    assert captured.out == ""


# ---------------------------------------------------------------------------
# ensure_global_statusline — register the cross-repo statusline globally
# ---------------------------------------------------------------------------


def _read(path) -> dict:
    return json.loads(Path(path).read_text())


def test_statusline_command_points_at_the_script():
    """The command is `python3 <abs path to scripts/br8n-statusline.py>`."""
    cmd = _statusline_command()
    assert cmd.startswith("python3 ")
    assert cmd.rstrip().endswith("scripts/br8n-statusline.py")
    # Absolute path so it resolves from any repo (global config can't use a
    # repo-relative $CLAUDE_PROJECT_DIR).
    assert "/scripts/br8n-statusline.py" in cmd


def test_ensure_installs_when_no_settings_file(tmp_path):
    """No settings file yet → write one with the br8n statusLine."""
    settings = tmp_path / ".claude" / "settings.json"
    assert ensure_global_statusline(str(settings)) == "installed"
    data = _read(settings)
    assert data["statusLine"]["type"] == "command"
    assert "br8n-statusline.py" in data["statusLine"]["command"]


def test_ensure_installs_when_statusline_absent(tmp_path):
    """Existing settings without a statusLine → install it, keep other keys."""
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"model": "sonnet", "theme": "light"}))
    assert ensure_global_statusline(str(settings)) == "installed"
    data = _read(settings)
    assert data["statusLine"]["command"] == _statusline_command()
    # Other keys are preserved untouched.
    assert data["model"] == "sonnet"
    assert data["theme"] == "light"


def test_ensure_respects_a_users_own_statusline(tmp_path):
    """A non-br8n statusLine is never clobbered."""
    settings = tmp_path / "settings.json"
    mine = {"type": "command", "command": "my-custom-statusline.sh"}
    settings.write_text(json.dumps({"statusLine": mine}))
    assert ensure_global_statusline(str(settings)) == "user-set"
    assert _read(settings)["statusLine"] == mine


def test_ensure_is_idempotent_when_already_current(tmp_path):
    """An already-current br8n statusLine → no rewrite, reports 'present'."""
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"statusLine": {"type": "command", "command": _statusline_command()}})
    )
    before = settings.read_text()
    assert ensure_global_statusline(str(settings)) == "present"
    assert settings.read_text() == before  # byte-for-byte unchanged


def test_ensure_self_heals_a_stale_br8n_path(tmp_path):
    """A br8n statusLine pointing at an old path is updated in place."""
    settings = tmp_path / "settings.json"
    stale = "python3 /old/location/br8n/scripts/br8n-statusline.py"
    settings.write_text(json.dumps({"statusLine": {"type": "command", "command": stale}}))
    assert ensure_global_statusline(str(settings)) == "updated"
    assert _read(settings)["statusLine"]["command"] == _statusline_command()


def test_ensure_returns_error_on_malformed_settings(tmp_path):
    """Malformed JSON is left untouched (returns 'error', never raises)."""
    settings = tmp_path / "settings.json"
    settings.write_text("{ this is not json")
    assert ensure_global_statusline(str(settings)) == "error"
    # File is not overwritten — we never destroy a settings file we can't parse.
    assert settings.read_text() == "{ this is not json"


def test_ensure_never_raises(tmp_path):
    """Any unexpected failure degrades to 'error', never an exception."""
    # A directory where the settings file should be → write/read fails internally.
    bogus = tmp_path / "adir"
    bogus.mkdir()
    assert ensure_global_statusline(str(bogus)) == "error"


def test_main_registers_global_statusline(tmp_path):
    """main() always registers the global statusline (even outside a git repo)."""
    with (
        patch.object(_hook, "ensure_global_statusline") as mock_ensure,
        patch.object(_hook, "repo_identity", return_value=None),
    ):
        hook_input = json.dumps({"cwd": str(tmp_path)})
        sys.stdin = __import__("io").StringIO(hook_input)
        try:
            _hook.main()
        finally:
            sys.stdin = sys.__stdin__
    mock_ensure.assert_called_once()
