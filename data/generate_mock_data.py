# data/generate_mock_data.py
"""Deterministically generates mock_orders.csv and mock_inventory.csv.

Run as a script to (re)write the CSVs under data/. The generation is
seeded so the perfect-storm numbers are stable across runs.
"""
import csv
import hashlib
import math
import os
import random
from datetime import date, timedelta

SUPPLIERS = [
    ("SUP-001", 30),  # Apex Materials Inc. — 60%
    ("SUP-002", 15),  # Vertex Fabrics LLC — 30%
    ("SUP-003", 5),   # Meridian Components — 10%
]

SKUS = [
    ("SKU-C01", "Raw cotton fabric", 21, 9, 14, 1.65, 1.8),
    ("SKU-C02", "Polyester lining", 7, 18, 10, 1.65, 1.2),
    ("SKU-B01", "Buttons, assorted", 3, 240, 80, 1.65, 6.0),
    ("SKU-T01", "Sewing thread", 5, 95, 40, 1.65, 3.0),
] + [
    (f"SKU-X{i:02d}", f"Generic component {i}", 5 + (i % 10), 50 + i, 20 + i, 1.65, 2.0)
    for i in range(1, 17)
]

ORDER_START = date(2026, 3, 10)  # 90 days before ORDER_END
ORDER_END = date(2026, 6, 8)
APEX_DEGRADE_DATE = date(2026, 4, 1)  # last ~60 days on time, then degrading
SKU_IDS = [s[0] for s in SKUS]


def _supplier_sequence(rng: random.Random, count: int) -> list[str]:
    pool: list[str] = []
    for supplier_id, n in SUPPLIERS:
        pool.extend([supplier_id] * n)
    rng.shuffle(pool)
    return pool[:count]


def generate_orders(seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    suppliers = _supplier_sequence(rng, 50)
    span_days = (ORDER_END - ORDER_START).days
    orders = []
    in_transit_indices = set(rng.sample(range(50), 10))

    for i, supplier_id in enumerate(suppliers):
        order_date = ORDER_START + timedelta(days=int(i * span_days / 50))
        sku = "SKU-C01" if rng.random() < 0.4 else rng.choice(SKU_IDS)
        lead_time = next(s[2] for s in SKUS if s[0] == sku)
        eta = order_date + timedelta(days=lead_time)
        quantity = rng.randint(50, 500)
        unit_value = rng.uniform(4.0, 40.0)

        actual_delivery = None
        status = "in_transit"
        if i not in in_transit_indices:
            status = "delivered"
            if supplier_id == "SUP-001" and order_date >= APEX_DEGRADE_DATE:
                delay = rng.randint(2, 7)  # averages ~4.2 days late
            elif supplier_id == "SUP-001":
                delay = rng.randint(-1, 1)
            else:
                delay = rng.randint(-2, 2)
            actual_delivery = eta + timedelta(days=delay)

        orders.append({
            "order_id": f"ORD-{i + 1:04d}",
            "sku": sku,
            "supplier_id": supplier_id,
            "quantity": quantity,
            "order_date": order_date.isoformat(),
            "eta": eta,
            "actual_delivery": actual_delivery,
            "status": status,
            "value_usd": round(quantity * unit_value, 2),
        })

    return orders


def generate_inventory() -> list[dict]:
    rows = []
    for sku, name, lead_time, stock, reorder, z, demand_std in SKUS:
        safety_stock = round(z * demand_std * math.sqrt(lead_time))
        rows.append({
            "sku": sku,
            "name": name,
            "current_stock": stock,
            "safety_stock": safety_stock,
            "reorder_point": reorder,
            "lead_time_days": lead_time,
            "unit_cost": round(4.0 + (int(hashlib.md5(sku.encode()).hexdigest(), 16) % 360) / 10, 2),
        })
    return rows


def write_csvs(out_dir: str) -> None:
    orders = generate_orders()
    inventory = generate_inventory()

    orders_path = os.path.join(out_dir, "mock_orders.csv")
    with open(orders_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(orders[0].keys()))
        writer.writeheader()
        for row in orders:
            row = dict(row)
            row["actual_delivery"] = row["actual_delivery"] or ""
            writer.writerow(row)

    inventory_path = os.path.join(out_dir, "mock_inventory.csv")
    with open(inventory_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(inventory[0].keys()))
        writer.writeheader()
        writer.writerows(inventory)


if __name__ == "__main__":
    write_csvs(os.path.dirname(__file__))
    print("Wrote mock_orders.csv and mock_inventory.csv")
