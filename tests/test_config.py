"""The settings: config.py run afresh, with only the variables a test sets."""

import runpy

import dotenv
import pytest

from expense_agent import config


@pytest.mark.parametrize(
    ("provider", "key", "model"), [("google", "g-key", "gemini"), ("anthropic", "a-key", "claude")]
)
def test_the_provider_picks_its_key_and_its_model(monkeypatch, provider, key, model):
    monkeypatch.setattr(dotenv, "load_dotenv", lambda path: None)  # no .env
    monkeypatch.setenv("PROVIDER", provider)
    monkeypatch.setenv("GOOGLE_API_KEY", "g-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a-key")
    monkeypatch.delenv("MODEL", raising=False)

    settings = runpy.run_path(config.__file__)  # what config.py sets at a fresh start

    assert settings["API_KEY"] == key
    assert settings["MODEL"].startswith(model)
