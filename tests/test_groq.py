"""Groq AI configuration tests. All HTTP is mocked - no key, quota, or network."""
import json
import urllib.error

import pytest

from app.services import ai_service

ARTICLE = {"title": "AI breakthrough in chip design", "summary": "A great breakthrough promises faster chips."}


def _clear_keys(monkeypatch):
    for var in ("GROQ_API_KEY", "GROQ_MODEL", "GROQ_BASE_URL", "GROQ_TIMEOUT",
                "FEEDOPS_AI_API_KEY", "FEEDOPS_AI_MODEL", "FEEDOPS_AI_BASE_URL",
                "FEEDOPS_AI_TIMEOUT", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _groq_payload(summary="Remote summary.", topics=("technology",)):
    inner = json.dumps({
        "summary": summary,
        "topics": list(topics),
        "category": topics[0],
        "sentiment": "positive",
        "sentiment_score": 0.5,
        "relevance_score": 0.8,
    })
    return json.dumps({"choices": [{"message": {"content": inner}}]}).encode()


def test_no_key_uses_fallback(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("FEEDOPS_AI_ENABLED", "true")
    out = ai_service.analyze_article(ARTICLE)
    assert out["provider"] == "fallback"
    assert out["fallback_used"] is True
    assert out["summary"]


def test_groq_request_targets_groq_and_model(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["auth"] = req.get_header("Authorization")
        captured["payload"] = json.loads(req.data.decode())
        return _FakeResponse(_groq_payload())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    out = ai_service.analyze_article(ARTICLE)

    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert "api.openai.com" not in captured["url"]
    assert captured["payload"]["model"] == "llama-3.3-70b-versatile"
    assert captured["auth"] == "Bearer test-groq-key"
    assert out["provider"] == "groq"
    assert out["fallback_used"] is False
    assert out["model"] == "llama-3.3-70b-versatile"
    assert out["summary"] == "Remote summary."


def test_groq_model_env_override(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.1-8b-instant")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["payload"] = json.loads(req.data.decode())
        return _FakeResponse(_groq_payload())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    out = ai_service.analyze_article(ARTICLE)
    assert captured["payload"]["model"] == "llama-3.1-8b-instant"
    assert out["model"] == "llama-3.1-8b-instant"


def test_legacy_key_still_works(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("FEEDOPS_AI_API_KEY", "legacy-key")

    def fake_urlopen(req, timeout=None):
        return _FakeResponse(_groq_payload())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    out = ai_service.analyze_article(ARTICLE)
    assert out["fallback_used"] is False


def test_timeout_falls_back(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")

    def boom(req, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    out = ai_service.analyze_article(ARTICLE)
    assert out["provider"] == "fallback"
    assert out["fallback_used"] is True
    assert any("timed out" in e for e in out["errors"])


def test_rate_limit_falls_back(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")

    def limited(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", limited)
    out = ai_service.analyze_article(ARTICLE)
    assert out["fallback_used"] is True
    assert any("429" in e for e in out["errors"])


def test_malformed_output_does_not_crash(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")

    def garbage(req, timeout=None):
        return _FakeResponse(b"not json at all")

    monkeypatch.setattr("urllib.request.urlopen", garbage)
    out = ai_service.analyze_article(ARTICLE)
    assert out["fallback_used"] is True
    assert out["summary"]  # fallback summary still produced


def test_auth_failure_falls_back_without_leaking_key(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "bad-key")

    def denied(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", denied)
    out = ai_service.analyze_article(ARTICLE)
    assert out["fallback_used"] is True
    assert "bad-key" not in " ".join(out["errors"])


def test_route_renders_with_groq_unconfigured(client, monkeypatch):
    _clear_keys(monkeypatch)
    res = client.get("/articles/1?analyze=1")
    assert res.status_code == 200
