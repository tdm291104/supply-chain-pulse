"""Risk analysis engine: assembles multi-source context and asks Gemini
to reason over it. Gemini does the reasoning — this module's job is to
gather the right context, call the model, and persist the result.
"""
import json
import uuid
from datetime import datetime, timezone

from agent.context import get_news_context, get_weather_context
from agent.schemas import RISK_REPORT_SCHEMA, RiskReport
from agent.system_prompt import SYSTEM_PROMPT


class SupplyChainAnalyzer:
    def __init__(self, db, mcp, gemini):
        self._db = db
        self._mcp = mcp
        self._gemini = gemini

    async def run_post_sync_analysis(self, connection_id: str) -> RiskReport | None:
        await self._mcp.get_connection_details(connection_id, triggered_by="webhook")

        risk_summary = self._db.query("SELECT * FROM v_supply_risk_summary ORDER BY risk_score DESC LIMIT 5")
        reliability = self._db.query("SELECT * FROM v_supplier_reliability")
        forecast = self._db.query("SELECT * FROM v_stockout_forecast ORDER BY days_until_stockout ASC LIMIT 5")

        weather = get_weather_context(region="Gulf Coast")
        news = get_news_context()

        prompt = self._build_prompt(risk_summary, reliability, forecast, weather, news)
        raw = self._gemini.generate_json(
            system_instruction=SYSTEM_PROMPT,
            prompt=prompt,
            response_schema=RISK_REPORT_SCHEMA,
        )
        report = RiskReport.from_dict(raw)

        if report.severity != "LOW":
            self._save_alert(report)

        return report

    def _build_prompt(self, risk_summary, reliability, forecast, weather, news) -> str:
        return (
            "Analyze the following supply chain signals and respond with a single "
            "JSON risk report as specified in your instructions.\n\n"
            f"Top-risk inventory (v_supply_risk_summary):\n{risk_summary.to_json(orient='records')}\n\n"
            f"Supplier reliability (v_supplier_reliability):\n{reliability.to_json(orient='records')}\n\n"
            f"Stockout forecast (v_stockout_forecast):\n{forecast.to_json(orient='records')}\n\n"
            f"Weather signal:\n{json.dumps(weather)}\n\n"
            f"News signal:\n{json.dumps(news)}\n"
        )

    def _save_alert(self, report: RiskReport) -> None:
        alert_id = f"alert_{uuid.uuid4().hex[:10]}"
        recommended = "; ".join(a["action"] for a in report.recommended_actions) or "No action recommended"
        skus_literal = "[" + ", ".join(f"'{s}'" for s in report.affected_skus) + "]"
        self._db.execute(f"""
            INSERT INTO risk_alerts
                (alert_id, created_at, severity, affected_skus, risk_type,
                 description, recommended_action, status, resolved_at, approved_by)
            VALUES (
                '{alert_id}', current_timestamp, '{report.severity}', {skus_literal},
                '{",".join(report.risk_sources)}', '{report.summary.replace("'", "''")}',
                '{recommended.replace("'", "''")}', 'OPEN', NULL, NULL
            )
        """)
