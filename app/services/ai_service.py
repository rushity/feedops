"""AI service. Owner: Rushik.

Stable contract (other modules may import these names):
- summarize(text, max_chars=300) -> str
- categorize(text) -> str

Extended (additive — nothing above changes signature):
- analyze_article(article, query=None) -> dict
- is_ai_available() -> bool
- validate_analysis(result) -> (cleaned, errors)

Behaviour:
- Offline fallback (extractive summary, keyword topics, lexicon sentiment)
  always works with no keys and no network, so article reading and search
  keep working when AI is unavailable.
- Remote analysis uses Groq's OpenAI-compatible chat-completions endpoint
  (`https://api.groq.com/openai/v1`) via the standard library only (no new
  dependencies). Config comes ONLY from environment variables — never
  hardcoded:
    GROQ_API_KEY (secret), GROQ_MODEL, GROQ_BASE_URL, GROQ_TIMEOUT,
    FEEDOPS_AI_ENABLED.
  Legacy names still work as fallbacks: FEEDOPS_AI_API_KEY / OPENAI_API_KEY
  for the key, FEEDOPS_AI_MODEL for the model, FEEDOPS_AI_BASE_URL /
  FEEDOPS_AI_TIMEOUT for endpoint/timeout. An explicitly configured base URL
  is always honoured; otherwise Groq's endpoint is the default whenever Groq
  variables are present.
- `article` may be a sqlite3.Row, a dict, or an object with
  title/summary(/content) attributes — the shared schema has title, url,
  summary, category, published_at (no content column; missing fields are
  treated as empty).
- This service never writes to the database (the shared schema has no AI
  columns; persisting analysis needs a Rushit-approved schema change).
"""

import json
import logging
import os
import re
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

# Groq official OpenAI-compatible endpoint and the default free-tier model.
# Verified against https://console.groq.com/docs/models (Production models).
# Groq's free-tier availability and limits can change; GROQ_MODEL overrides this.
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
LEGACY_OPENAI_BASE_URL = "https://api.openai.com/v1"

ALLOWED_SENTIMENTS = ("positive", "neutral", "negative")

TOPIC_KEYWORDS = {
    "technology": ("ai", "software", "tech", "startup", "computer", "app", "data", "chip", "robot"),
    "business": ("market", "stock", "company", "business", "economy", "revenue", "profit", "funding"),
    "science": ("study", "research", "scientist", "discovery", "space", "climate", "physics", "biology"),
    "sports": ("match", "game", "team", "player", "score", "tournament", "league", "coach"),
    "politics": ("election", "government", "minister", "policy", "parliament", "president", "vote"),
    "health": ("health", "doctor", "hospital", "disease", "vaccine", "medical", "wellness"),
    "entertainment": ("movie", "film", "music", "show", "celebrity", "actor", "series"),
}

POSITIVE_WORDS = {
    "good", "great", "excellent", "amazing", "breakthrough", "success",
    "successful", "win", "wins", "growth", "record", "best", "praise",
    "happy", "optimistic", "launch",
}
NEGATIVE_WORDS = {
    "bad", "poor", "fail", "failure", "crash", "loss", "losses", "decline",
    "fall", "falls", "risk", "warning", "concern", "kill", "dead",
    "crisis", "scandal", "lawsuit", "layoff",
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


# ---------------------------------------------------------------------------
# Stable contract
# ---------------------------------------------------------------------------

def summarize(text: str, max_chars: int = 300) -> str:
    """Extractive summary: whole sentences up to max_chars, else hard clip."""
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if not text or len(text) <= max_chars:
        return text
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    out, total = [], 0
    for s in sentences:
        if total + len(s) + 1 > max_chars:
            break
        out.append(s)
        total += len(s) + 1
    if out:
        return " ".join(out)
    clipped = text[:max_chars].rsplit(" ", 1)
    return (clipped[0] if len(clipped) > 1 else text[:max_chars]) + "..."


def categorize(text: str) -> str:
    """Keyword topic for a text; 'uncategorized' when nothing matches."""
    lowered = (text or "").lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(k in lowered for k in keywords):
            return topic
    return "uncategorized"


# ---------------------------------------------------------------------------
# Config (environment only — never hardcoded)
# ---------------------------------------------------------------------------

def ai_config():
    """Resolve AI configuration from environment only. Never logs the key."""
    enabled = os.environ.get("FEEDOPS_AI_ENABLED", "true").lower() in (
        "1", "true", "yes", "on",
    )
    api_key = (
        os.environ.get("GROQ_API_KEY")
        or os.environ.get("FEEDOPS_AI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    model = (
        os.environ.get("GROQ_MODEL")
        or os.environ.get("FEEDOPS_AI_MODEL")
        or DEFAULT_GROQ_MODEL
    )
    explicit_base_url = (
        os.environ.get("GROQ_BASE_URL")
        or os.environ.get("FEEDOPS_AI_BASE_URL")
    )
    if explicit_base_url:
        base_url = explicit_base_url.rstrip("/")
    elif os.environ.get("GROQ_API_KEY") or os.environ.get("GROQ_MODEL"):
        base_url = GROQ_BASE_URL
    else:
        # Backward compatibility for deployments already pointing elsewhere.
        base_url = LEGACY_OPENAI_BASE_URL
    try:
        timeout = float(os.environ.get("GROQ_TIMEOUT") or os.environ.get("FEEDOPS_AI_TIMEOUT", "15"))
    except ValueError:
        timeout = 15.0
    provider = "groq" if base_url == GROQ_BASE_URL else "remote"
    return {
        "enabled": enabled,
        "api_key": api_key,
        "model": model,
        "base_url": base_url,
        "timeout": timeout,
        "provider": provider,
    }


def is_ai_available():
    cfg = ai_config()
    return bool(cfg["enabled"] and cfg["api_key"])


# ---------------------------------------------------------------------------
# Offline fallback + validation
# ---------------------------------------------------------------------------

def _field(article, name):
    if article is None:
        return ""
    try:
        if isinstance(article, dict):
            return article.get(name) or ""
        if hasattr(article, "keys"):  # sqlite3.Row
            try:
                return article[name] or ""
            except (KeyError, IndexError):
                return ""
        return getattr(article, name, "") or ""
    except Exception:
        return ""


def _article_text(article):
    parts = [_field(article, "title"), _field(article, "summary"), _field(article, "content")]
    return re.sub(r"\s+", " ", " ".join(p.strip() for p in parts if p and p.strip())).strip()


def _fallback_sentiment(text):
    words = re.findall(r"[a-z]+", text.lower())
    if not words:
        return "neutral", 0.0
    pos = sum(1 for w in words if w in POSITIVE_WORDS)
    neg = sum(1 for w in words if w in NEGATIVE_WORDS)
    score = round((pos - neg) / max(len(words), 1), 4)
    if pos > neg:
        return "positive", abs(score)
    if neg > pos:
        return "negative", -abs(score)
    return "neutral", 0.0


def _fallback_relevance(text, query=None):
    if not text:
        return 0.0
    length_score = min(len(text) / 2000, 1.0)
    bonus = 0.0
    if query:
        qwords = {w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 2}
        if qwords:
            lowered = text.lower()
            bonus = 0.3 * sum(1 for w in qwords if w in lowered) / len(qwords)
    return round(min(max(0.2 + 0.6 * length_score + bonus, 0.0), 1.0), 4)


def fallback_analysis(article, query=None):
    text = _article_text(article)
    topics = [
        topic for topic, kws in TOPIC_KEYWORDS.items() if any(k in text.lower() for k in kws)
    ][:3] or ["uncategorized"]
    sentiment, sentiment_score = _fallback_sentiment(text)
    return {
        "summary": summarize(text, max_chars=800),
        "topics": topics,
        "category": topics[0],
        "sentiment": sentiment,
        "sentiment_score": sentiment_score,
        "relevance_score": _fallback_relevance(text, query),
        "provider": "fallback",
        "fallback_used": True,
        "model": None,
    }


def validate_analysis(result):
    """Validate/clamp a remote AI payload. Returns (cleaned, errors)."""
    errors = []
    cleaned = dict(result or {})

    summary = cleaned.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        errors.append("summary must be a non-empty string")
        cleaned["summary"] = ""
    else:
        cleaned["summary"] = summary.strip()[:2000]

    topics = cleaned.get("topics")
    if topics is None:
        topics = []
    if isinstance(topics, str):
        errors.append("topics must be a list of strings")
        topics = []
    if not isinstance(topics, list):
        errors.append("topics must be a list of strings")
        topics = []
    cleaned_topics = [t.strip()[:60] for t in topics if isinstance(t, str) and t.strip()]
    cleaned["topics"] = cleaned_topics[:5] or ["uncategorized"]

    category = cleaned.get("category")
    if not isinstance(category, str) or not category.strip():
        cleaned["category"] = cleaned["topics"][0]
    else:
        cleaned["category"] = category.strip()[:60]

    if cleaned.get("sentiment") not in ALLOWED_SENTIMENTS:
        errors.append(f"sentiment must be one of {ALLOWED_SENTIMENTS}")
        cleaned["sentiment"] = "neutral"
    try:
        cleaned["sentiment_score"] = float(cleaned.get("sentiment_score", 0.0))
    except (TypeError, ValueError):
        errors.append("sentiment_score must be numeric")
        cleaned["sentiment_score"] = 0.0
    try:
        cleaned["relevance_score"] = float(cleaned.get("relevance_score", 0.0))
    except (TypeError, ValueError):
        errors.append("relevance_score must be numeric")
        cleaned["relevance_score"] = 0.0
    cleaned["relevance_score"] = min(max(cleaned["relevance_score"], 0.0), 1.0)

    return cleaned, errors


# ---------------------------------------------------------------------------
# Remote provider (stdlib only) + reusable entry point
# ---------------------------------------------------------------------------

def _call_remote_ai(text, cfg):
    """POST to the configured chat-completions endpoint (Groq by default).

    Sends only the article text (truncated) plus the JSON contract prompt —
    never secrets, config, or unrelated database content. Raises on failure.
    """
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": "You are a news analysis assistant. Reply with JSON only."},
            {"role": "user", "content": (
                "Analyze the following news article and respond with STRICT JSON only, "
                'with keys: summary (<=150 words), topics (list of 1-3 short strings), '
                "category (single best topic), sentiment (one of "
                "positive/neutral/negative), sentiment_score (number -1..1), "
                f"relevance_score (number 0..1).\n\nARTICLE:\n{text[:6000]}"
            )},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        f"{cfg['base_url']}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RuntimeError("AI rate limit exceeded (HTTP 429)") from exc
        if exc.code in (401, 403):
            raise RuntimeError("AI authentication failed — check API key") from exc
        raise RuntimeError(f"AI request failed (HTTP {exc.code})") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"AI request failed: {exc}") from exc
    try:
        content = json.loads(body)["choices"][0]["message"]["content"]
        parsed = json.loads(content) if isinstance(content, str) else content
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Invalid AI response: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("AI JSON was not an object")
    return parsed


def analyze_article(article, query=None):
    """Reusable analysis for one article (Row, dict, or object).

    Never raises and never touches the DB: remote failures degrade to the
    offline fallback so reading/search keep working. Returns dict with
    summary, topics, category, sentiment, sentiment_score, relevance_score,
    provider, fallback_used, model, validated, errors.
    """
    text = _article_text(article)
    if not text:
        cleaned, _ = validate_analysis({
            "summary": "", "topics": ["uncategorized"], "category": "uncategorized",
            "sentiment": "neutral", "sentiment_score": 0.0, "relevance_score": 0.0,
        })
        cleaned.update({"provider": "fallback", "fallback_used": True,
                        "model": None, "validated": True,
                        "errors": ["empty article text"]})
        return cleaned

    cfg = ai_config()
    if cfg["enabled"] and cfg["api_key"]:
        try:
            raw = _call_remote_ai(text, cfg)
            if "topics" not in raw and isinstance(raw.get("category"), str):
                raw["topics"] = [raw["category"]]
            cleaned, errors = validate_analysis(raw)
            cleaned.update({"provider": cfg["provider"], "fallback_used": False,
                            "model": cfg["model"], "validated": True, "errors": errors})
            if errors and not cleaned.get("summary"):
                fb = fallback_analysis(article, query)
                cleaned["summary"] = fb["summary"]
                cleaned["provider"] = "remote+fallback"
                cleaned["fallback_used"] = True
            return cleaned
        except Exception as exc:
            log.warning("AI remote analysis failed, using fallback: %s", exc)
            fb = fallback_analysis(article, query)
            fb["errors"] = [f"remote AI failed: {exc}"]
            fb["validated"] = True
            return fb

    fb = fallback_analysis(article, query)
    fb["errors"] = ["AI disabled" if not cfg["enabled"] else "AI API key not configured"]
    fb["validated"] = True
    return fb
