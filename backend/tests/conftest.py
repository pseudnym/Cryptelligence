import pytest

@pytest.fixture(autouse=True)
def no_accidental_live_gemini(monkeypatch):
    # Explicit client/settings injection enables Gemini tests. Local .env keys
    # never turn unrelated automated tests into paid external calls.
    monkeypatch.setenv("GEMINI_ENABLED", "false")
