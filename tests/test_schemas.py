# tests/test_schemas.py
from agent.schemas import RISK_REPORT_SCHEMA, RiskReport


def test_risk_report_from_dict_round_trips():
    raw = {
        "severity": "HIGH",
        "affected_skus": ["SKU-C01"],
        "risk_sources": ["weather", "supplier_delay", "inventory"],
        "summary": "Three converging signals threaten SKU-C01 supply.",
        "recommended_actions": [
            {"action": "Emergency order from Vertex Fabrics (SUP-002)",
             "impact": "Risk reduction: HIGH -> LOW",
             "cost_delta": "+3.8%"}
        ],
        "requires_approval": True,
    }
    report = RiskReport.from_dict(raw)
    assert report.severity == "HIGH"
    assert report.affected_skus == ["SKU-C01"]
    assert report.recommended_actions[0]["action"].startswith("Emergency order")
    assert report.requires_approval is True


def test_schema_declares_required_fields():
    required = set(RISK_REPORT_SCHEMA["required"])
    assert required == {
        "severity", "affected_skus", "risk_sources", "summary",
        "recommended_actions", "requires_approval",
    }
