# tests/test_scenario.py
import os
import tempfile

from data.seed_db import seed
from db.database import Database
from demo.scenario import reset_to_perfect_storm


def test_reset_to_perfect_storm_seeds_expected_state_and_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.duckdb")
        log_path = os.path.join(tmp, "tool_calls.jsonl")
        with open(log_path, "w") as f:
            f.write('{"tool": "stale_entry"}\n')

        db = Database(db_path)
        data_dir = os.path.join(os.path.dirname(__file__), "..", "data")

        for _ in range(2):  # idempotency check
            reset_to_perfect_storm(db=db, data_dir=data_dir, log_path=log_path)

        stock = db.query("SELECT current_stock FROM inventory WHERE sku = 'SKU-C01'")
        assert stock["current_stock"][0] == 9

        alerts = db.query("SELECT COUNT(*) AS n FROM risk_alerts")
        assert alerts["n"][0] == 0

        with open(log_path) as f:
            assert f.read().strip() == ""

        db.close()
