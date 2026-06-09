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
                try:
                    answer = self._gemini.generate_text(
                        system_instruction="You are Supply Chain Pulse Agent's conversational assistant. Always respond in English.",
                        prompt=prompt,
                    )
                except Exception:
                    answer = _format_data_response(rows, view_name)
                return answer, [view_name]

        return _FALLBACK, []


def _format_data_response(df, view_name: str) -> str:
    """Plain-text fallback when Gemini is unavailable — formats the raw rows."""
    if df.empty:
        return f"No data available in {view_name}."

    if view_name == "v_supply_risk_summary":
        lines = ["Here are your top supply chain risks:\n"]
        for _, row in df.iterrows():
            risk = int(row.get("risk_score") or 0)
            days = row.get("days_until_stockout")
            stock = row.get("current_stock", "?")
            icon = "🔴" if risk > 0 else "🟢"
            days_str = f"**{int(days)} days** until stockout" if days is not None else "stock OK"
            lines.append(
                f"{icon} **{row['sku']}** ({row['name']}): "
                f"{int(stock)} units in stock, {days_str}"
                + (f", risk score **{risk}**" if risk > 0 else "")
            )
        return "\n\n".join(lines)

    if view_name == "v_supplier_reliability":
        lines = ["Here is the supplier reliability comparison:\n"]
        for _, row in df.iterrows():
            rate = float(row.get("on_time_rate_30d") or 0)
            delay = float(row.get("avg_delay_days_30d") or 0)
            orders = int(row.get("delivered_orders_30d") or 0)
            icon = "🔴" if rate < 0.65 else ("🟡" if rate < 0.85 else "🟢")
            lines.append(
                f"{icon} **{row['supplier_id']}**: "
                f"**{rate*100:.0f}%** on-time (30d), "
                f"avg **{delay:.1f} day** delay, "
                f"{orders} deliveries"
            )
        return "\n\n".join(lines)

    # Generic fallback
    lines = [f"Data from **{view_name}**:\n"]
    for _, row in df.iterrows():
        parts = [f"{col}: {val}" for col, val in row.items() if val is not None]
        lines.append("• " + " | ".join(parts))
    return "\n".join(lines)
