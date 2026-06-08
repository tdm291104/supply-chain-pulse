# tests/test_seed_db.py
import os
import tempfile

from db.database import Database
from data.seed_db import seed


def test_seed_creates_tables_views_and_loads_data():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.duckdb")
        db = Database(db_path)
        seed(db, data_dir=os.path.join(os.path.dirname(__file__), "..", "data"))

        orders = db.query("SELECT COUNT(*) AS n FROM orders")
        assert orders["n"][0] == 50

        inventory = db.query("SELECT COUNT(*) AS n FROM inventory")
        assert inventory["n"][0] == 20

        risk = db.query(
            "SELECT * FROM v_supply_risk_summary WHERE sku = 'SKU-C01'"
        )
        assert len(risk) == 1
        assert risk["days_until_stockout"][0] <= 14

        reliability = db.query(
            "SELECT * FROM v_supplier_reliability WHERE supplier_id = 'SUP-001'"
        )
        assert len(reliability) == 1
        assert reliability["on_time_rate_30d"][0] < 1.0

        forecast = db.query("SELECT COUNT(*) AS n FROM v_stockout_forecast")
        assert forecast["n"][0] > 0

        db.close()


def test_seed_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.duckdb")
        db = Database(db_path)
        data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        seed(db, data_dir=data_dir)
        seed(db, data_dir=data_dir)
        orders = db.query("SELECT COUNT(*) AS n FROM orders")
        assert orders["n"][0] == 50
        db.close()
