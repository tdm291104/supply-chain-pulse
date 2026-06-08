# demo/scenario.py
"""Resets the demo to the perfect-storm state. Idempotent — safe to run
any number of times before recording. Run directly: `python -m demo.scenario`."""
import os

from data.seed_db import seed
from db.database import Database

WEBHOOK_HINT = (
    "Demo ready. Trigger the webhook with:\n"
    "  curl -X POST http://localhost:8000/webhook/fivetran \\\n"
    "    -H 'X-Fivetran-Signature: <see WEBHOOK_SECRET>' \\\n"
    "    -d '{\"event\": \"sync_end\", \"data\": {\"connection_id\": \"conn_orders_001\", "
    "\"status\": \"successful\", \"sync_id\": \"demo_sync\"}}'\n"
    "...or click \"Sync now\" on the orders connection in the Pipeline tab."
)


def reset_to_perfect_storm(*, db: Database, data_dir: str, log_path: str = "logs/tool_calls.jsonl") -> None:
    seed(db, data_dir=data_dir)  # truncates+reloads tables/views from the CSVs

    # Force the perfect-storm numbers regardless of what generation produced.
    db.execute("UPDATE inventory SET current_stock = 9, reorder_point = 14, lead_time_days = 21 WHERE sku = 'SKU-C01'")
    db.execute("""
        UPDATE supplier_performance
        SET avg_delay_days = 4.2, last_30d_on_time_rate = 0.58, reliability_score = 0.61
        WHERE supplier_id = 'SUP-001'
    """)
    db.execute("DELETE FROM risk_alerts")

    if os.path.exists(log_path):
        open(log_path, "w").close()
    else:
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        open(log_path, "w").close()


if __name__ == "__main__":
    db_path = os.environ.get("DUCKDB_PATH", "./data/supply_chain.duckdb")
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    database = Database(db_path)
    reset_to_perfect_storm(db=database, data_dir=data_dir)
    database.close()
    print(WEBHOOK_HINT)
