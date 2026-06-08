# agent/context.py
"""Fetches weather/news context for risk analysis.

Uses the real APIs when keys are configured; otherwise falls back to
local fixtures so the agent (and the demo) work fully offline.
"""
import json
import os

import requests

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name: str) -> dict:
    with open(os.path.join(FIXTURES_DIR, f"{name}.json")) as f:
        return json.load(f)


def get_weather_context(region: str) -> dict:
    api_key = os.environ.get("OPENWEATHER_API_KEY")
    if not api_key:
        return _load_fixture("weather_context")
    try:
        resp = requests.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={"q": region, "appid": api_key},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "region": region,
            "headline": data.get("city", {}).get("name", region) + " forecast retrieved",
            "forecast_date": data.get("list", [{}])[0].get("dt_txt", ""),
            "severity": "unknown",
            "affected_corridors": [],
        }
    except requests.RequestException:
        return _load_fixture("weather_context")


def get_news_context() -> dict:
    api_key = os.environ.get("NEWS_API_KEY")
    if not api_key:
        return _load_fixture("news_context")
    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={"q": "supply chain disruption", "apiKey": api_key, "pageSize": 5},
            timeout=5,
        )
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        return {
            "items": [
                {"headline": a["title"], "source": a["source"]["name"], "published": a["publishedAt"][:10]}
                for a in articles
            ]
        }
    except requests.RequestException:
        return _load_fixture("news_context")
