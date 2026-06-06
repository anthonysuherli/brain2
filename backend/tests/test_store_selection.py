"""get_store() backend selection.

Selection order: BR8N_BACKEND env (explicit) → else cloud iff Supabase creds
present → else local. get_settings() is lru_cached, so tests that flip the
cred-sniffing path clear that cache after patching the environment.
"""

from __future__ import annotations

import br8n.config as config
import br8n.store as store_pkg
from br8n.store import SQLiteStore, SupabaseStore, get_store


def _reset_settings_cache() -> None:
    config.get_settings.cache_clear()


def test_explicit_local(monkeypatch, tmp_path):
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "sel-local.db"))
    store_pkg._local_stores.clear()
    assert isinstance(get_store(), SQLiteStore)


def test_explicit_cloud_with_fake_creds(monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "cloud")
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-key")
    _reset_settings_cache()
    try:
        assert isinstance(get_store("tok"), SupabaseStore)
    finally:
        _reset_settings_cache()


def test_auto_cloud_when_creds_present(monkeypatch):
    monkeypatch.delenv("BR8N_BACKEND", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-key")
    _reset_settings_cache()
    try:
        assert isinstance(get_store(), SupabaseStore)
    finally:
        _reset_settings_cache()


def test_auto_local_when_no_creds(monkeypatch, tmp_path):
    monkeypatch.delenv("BR8N_BACKEND", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    # Settings loads env_file=.env, so a dev's populated .env would leak creds
    # back in past the delenv above. Neutralize the file so only process env is read.
    monkeypatch.setitem(config.Settings.model_config, "env_file", None)
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "sel-auto.db"))
    _reset_settings_cache()
    store_pkg._local_stores.clear()
    try:
        assert isinstance(get_store(), SQLiteStore)
    finally:
        _reset_settings_cache()


def test_local_store_is_cached(monkeypatch, tmp_path):
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "sel-cache.db"))
    store_pkg._local_stores.clear()
    a = get_store()
    b = get_store("ignored-token")
    assert a is b  # same connection reused across calls
