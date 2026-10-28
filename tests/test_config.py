"""Settings read secrets from the process env; ALFRED_API_KEY is an alias for
the Things agent key (the 1Password infra-alerts Environment uses that name)."""

import importlib


def _settings(monkeypatch, **env):
    for k in ("THINGS_AGENT_API_KEY", "ALFRED_API_KEY", "SHERLOCK_DASHBOARD_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import src.config as cfg

    importlib.reload(cfg)
    return cfg.Settings(_env_file=None)


def test_api_key_accepts_alfred_api_key_alias(monkeypatch):
    s = _settings(monkeypatch, ALFRED_API_KEY="k-alias")
    assert s.things_agent_api_key == "k-alias"


def test_env_name_still_wins_over_alias(monkeypatch):
    s = _settings(monkeypatch, THINGS_AGENT_API_KEY="k-env", ALFRED_API_KEY="k-alias")
    assert s.things_agent_api_key == "k-env"


def test_dashboard_token_from_env(monkeypatch):
    s = _settings(monkeypatch, ALFRED_API_KEY="k", SHERLOCK_DASHBOARD_TOKEN="dash")
    assert s.sherlock_dashboard_token == "dash"
