"""AI service interface. Owner: Rushik (stub for milestone 3 - do not build out yet).

Contract (stable - other modules may import these names):
- summarize(text, max_chars=300) -> str
- categorize(text) -> str

Current behaviour is a deterministic placeholder so the app and tests run
without API keys. Real LLM integration happens later behind the same signatures.
"""


def summarize(text: str, max_chars: int = 300) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "..."


def categorize(text: str) -> str:  # noqa: ARG001
    # Placeholder - always returns default until AI milestone.
    return "uncategorized"
