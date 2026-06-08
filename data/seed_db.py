# data/seed_db.py
"""Creates the supply_chain schema (tables + views) and loads mock CSVs.

Safe to run multiple times: tables/views are dropped and recreated, and
loads truncate-then-insert so row counts stay stable.

BigQuery DDL equivalent: replace VARCHAR -> STRING, DOUBLE -> FLOAT64,
INTEGER -> INT64, and DATE/TIMESTAMP types translate directly.
"""
import os

from db.database import Database

SCHEMA_SQL = """
DROP VIEW IF EXISTS v_stockout_forecast;
DROP VIEW IF EXISTS v_supplier_reliability;
DROP VIEW IF EXISTS v_supply_risk_summary;
DROP TABLE IF EXISTS risk_alerts;
DROP TABLE IF EXISTS supplier_performance;
DROP TABLE IF EXISTS inventory;
DROP TABLE IF EXISTS orders;

CREATE TABLE orders (
  order_id VARCHAR, sku VARCHAR, supplier_id VARCHAR,
  quantity INTEGER, order_date DATE, eta DATE,
  actual_delivery DATE, status VARCHAR, value_usd DOUBLE
);

CREATE TABLE inventory (
  sku VARCHAR, name VARCHAR, current_stock INTEGER, safety_stock INTEGER,
  reorder_point INTEGER, lead_time_days INTEGER,
  unit_cost DOUBLE, last_updated TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE supplier_performance (
  supplier_id VARCHAR, supplier_name VARCHAR, region VARCHAR,
  avg_delay_days DOUBLE, reliability_score DOUBLE,
  last_30d_on_time_rate DOUBLE
);

CREATE TABLE risk_alerts (
  alert_id VARCHAR, created_at TIMESTAMP, severity VARCHAR,
  affected_skus VARCHAR[], risk_type VARCHAR,
  description VARCHAR, recommended_action VARCHAR,
  status VARCHAR, resolved_at TIMESTAMP, approved_by VARCHAR
);
"""

SUPPLIER_SEED_SQL = """
DELETE FROM supplier_performance;
INSERT INTO supplier_performance VALUES
  ('SUP-001', 'Apex Materials Inc.', 'Detroit, MI', 4.2, 0.61, 0.58),
  ('SUP-002', 'Vertex Fabrics LLC', 'Chicago, IL', 0.4, 0.95, 0.97),
  ('SUP-003', 'Meridian Components', 'Columbus, OH', 0.6, 0.93, 0.94);
"""

VIEWS_SQL = """
CREATE VIEW v_supplier_reliability AS
SELECT
  supplier_id,
  COUNT(*) AS delivered_orders_30d,
  AVG(CASE WHEN actual_delivery <= eta THEN 1.0 ELSE 0.0 END) AS on_time_rate_30d,
  AVG(DATE_DIFF('day', eta, actual_delivery)) AS avg_delay_days_30d
FROM orders
WHERE actual_delivery IS NOT NULL
  AND order_date >= (SELECT MAX(order_date) FROM orders) - INTERVAL 30 DAY
GROUP BY supplier_id;

CREATE VIEW v_supply_risk_summary AS
SELECT
  i.sku,
  i.name,
  i.current_stock,
  i.reorder_point,
  i.lead_time_days,
  COALESCE(c.daily_consumption, 0) AS daily_consumption,
  CASE WHEN COALESCE(c.daily_consumption, 0) > 0
       THEN CAST(i.current_stock / c.daily_consumption AS INTEGER)
       ELSE 999 END AS days_until_stockout,
  GREATEST(0, LEAST(100, CAST(
    (i.reorder_point - i.current_stock) * 5
    + (21 - LEAST(i.lead_time_days, 21))
  AS INTEGER))) AS risk_score
FROM inventory i
LEFT JOIN (
  SELECT sku, SUM(quantity) / 90.0 AS daily_consumption
  FROM orders
  GROUP BY sku
) c ON c.sku = i.sku;

CREATE VIEW v_stockout_forecast AS
SELECT
  sku,
  name,
  current_stock,
  daily_consumption,
  days_until_stockout,
  CURRENT_DATE + CAST(days_until_stockout AS INTEGER) AS predicted_stockout_date
FROM v_supply_risk_summary
WHERE daily_consumption > 0;
"""


def seed(db: Database, data_dir: str) -> None:
    db.execute(SCHEMA_SQL)
    db.execute(SUPPLIER_SEED_SQL)

    orders_csv = os.path.join(data_dir, "mock_orders.csv")
    inventory_csv = os.path.join(data_dir, "mock_inventory.csv")
    db.execute(f"""
        INSERT INTO orders
        SELECT order_id, sku, supplier_id, quantity, order_date, eta,
               NULLIF(actual_delivery, '')::DATE, status, value_usd
        FROM read_csv_auto('{orders_csv}', header=True,
                           types={{'actual_delivery': 'VARCHAR'}})
    """)
    db.execute(f"""
        INSERT INTO inventory (sku, name, current_stock, safety_stock,
                               reorder_point, lead_time_days, unit_cost)
        SELECT sku, name, current_stock, safety_stock, reorder_point,
               lead_time_days, unit_cost
        FROM read_csv_auto('{inventory_csv}', header=True)
    """)

    db.execute(VIEWS_SQL)


if __name__ == "__main__":
    import os as _os
    db_path = _os.environ.get("DUCKDB_PATH", "./data/supply_chain.duckdb")
    database = Database(db_path)
    seed(database, data_dir=_os.path.dirname(__file__))
    database.close()
    print(f"Seeded {db_path}")
