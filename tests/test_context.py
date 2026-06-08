# tests/test_context.py
import os

from agent.context import get_news_context, get_weather_context


def test_weather_context_falls_back_to_fixture(monkeypatch):
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    ctx = get_weather_context(region="Gulf Coast")
    assert "Hurricane" in ctx["headline"]
    assert ctx["region"] == "Gulf Coast"


def test_news_context_falls_back_to_fixture(monkeypatch):
    monkeypatch.delenv("NEWS_API_KEY", raising=False)
    ctx = get_news_context()
    assert len(ctx["items"]) >= 1
    assert "headline" in ctx["items"][0]
