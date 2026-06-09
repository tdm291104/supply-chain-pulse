# tests/test_gemini_client.py
import json

from agent.gemini_client import GeminiClient


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModel:
    def __init__(self, *args, **kwargs):
        self.last_prompt = None

    def generate_content(self, prompt, generation_config=None, **kwargs):
        self.last_prompt = prompt
        return _FakeResponse(json.dumps({
            "severity": "HIGH",
            "affected_skus": ["SKU-C01"],
            "risk_sources": ["weather", "supplier_delay", "inventory"],
            "summary": "Three converging signals threaten SKU-C01 supply.",
            "recommended_actions": [
                {"action": "Emergency order from Vertex Fabrics (SUP-002)",
                 "impact": "Risk reduction: HIGH -> LOW", "cost_delta": "+3.8%"}
            ],
            "requires_approval": True,
        }))


def test_generate_json_parses_model_response(monkeypatch):
    monkeypatch.setattr("agent.gemini_client._build_model", lambda model_name, system_instruction: _FakeModel())
    client = GeminiClient(api_key="fake", model_name="gemini-2.0-flash")
    result = client.generate_json(
        system_instruction="You are a test agent.",
        prompt="Analyze this data.",
        response_schema={"type": "object"},
    )
    assert result["severity"] == "HIGH"
    assert result["affected_skus"] == ["SKU-C01"]


def test_generate_text_returns_plain_string(monkeypatch):
    class _PlainModel(_FakeModel):
        def generate_content(self, prompt, generation_config=None, **kwargs):
            return _FakeResponse("Plain English answer.")

    monkeypatch.setattr("agent.gemini_client._build_model", lambda model_name, system_instruction: _PlainModel())
    client = GeminiClient(api_key="fake", model_name="gemini-2.0-flash")
    assert client.generate_text(system_instruction="x", prompt="y") == "Plain English answer."
