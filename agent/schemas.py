# agent/schemas.py
"""Structured-output schema for Gemini's risk analysis response.

RISK_REPORT_SCHEMA is passed to Gemini as the JSON response schema
(response_mime_type="application/json"), so parsing is never brittle.
"""
from dataclasses import dataclass, field
from typing import Any

RISK_REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "severity": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
        "affected_skus": {"type": "array", "items": {"type": "string"}},
        "risk_sources": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
        "recommended_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "impact": {"type": "string"},
                    "cost_delta": {"type": "string"},
                },
                "required": ["action", "impact", "cost_delta"],
            },
        },
        "requires_approval": {"type": "boolean"},
    },
    "required": [
        "severity", "affected_skus", "risk_sources", "summary",
        "recommended_actions", "requires_approval",
    ],
}


@dataclass
class RiskReport:
    severity: str
    affected_skus: list[str]
    risk_sources: list[str]
    summary: str
    recommended_actions: list[dict[str, Any]] = field(default_factory=list)
    requires_approval: bool = True

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RiskReport":
        return cls(
            severity=raw["severity"],
            affected_skus=list(raw["affected_skus"]),
            risk_sources=list(raw["risk_sources"]),
            summary=raw["summary"],
            recommended_actions=list(raw.get("recommended_actions", [])),
            requires_approval=bool(raw.get("requires_approval", True)),
        )
