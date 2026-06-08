"""Conversational interface using canned-query routing: recognized
question patterns map to fixed analytic-view queries, and Gemini phrases
the result in English. Chosen over a full tool-calling loop to keep the
chat tab predictable within a tight build timeline.
"""
import re

SUGGESTED_PROMPTS = [
    "What's my highest-risk SKU?",
    "Compare SUP-001 vs SUP-002 reliability",
    "Show me stockout forecast for next 30 days",
]

_ROUTES = [
    (re.compile(r"highest.risk", re.I),
     "v_supply_risk_summary",
     "SELECT * FROM v_supply_risk_summary ORDER BY risk_score DESC LIMIT 3"),
    (re.compile(r"reliab|compare", re.I),
     "v_supplier_reliability",
     "SELECT * FROM v_supplier_reliability"),
    (re.compile(r"stockout|forecast", re.I),
     "v_stockout_forecast",
     "SELECT * FROM v_stockout_forecast ORDER BY days_until_stockout ASC"),
]

_FALLBACK = (
    "I can help with questions like:\n"
    + "\n".join(f"- {p}" for p in SUGGESTED_PROMPTS)
)


class ChatRouter:
    def __init__(self, db, gemini):
        self._db = db
        self._gemini = gemini

    def answer(self, question: str) -> tuple[str, list[str]]:
        for pattern, view_name, sql in _ROUTES:
            if pattern.search(question):
                rows = self._db.query(sql)
                prompt = (
                    f"A user asked: \"{question}\"\n\n"
                    f"Relevant data from {view_name}:\n{rows.to_json(orient='records')}\n\n"
                    "Answer in plain English, citing specific numbers from the data."
                )
                answer = self._gemini.generate_text(
                    system_instruction="You are Supply Chain Pulse Agent's conversational assistant. Always respond in English.",
                    prompt=prompt,
                )
                return answer, [view_name]

        return _FALLBACK, []
