# tests/test_generate_mock_data.py
from data.generate_mock_data import generate_orders, generate_inventory


def test_generate_orders_has_expected_shape_and_supplier_mix():
    orders = generate_orders(seed=42)
    assert len(orders) == 50
    suppliers = [o["supplier_id"] for o in orders]
    assert suppliers.count("SUP-001") == 30  # 60%
    assert suppliers.count("SUP-002") == 15  # 30%
    assert suppliers.count("SUP-003") == 5   # 10%
    in_transit = [o for o in orders if o["actual_delivery"] is None]
    assert len(in_transit) == 10
    for o in orders:
        assert o["value_usd"] > 0


def test_apex_deliveries_degrade_over_time():
    orders = generate_orders(seed=42)
    apex_delivered = [
        o for o in orders
        if o["supplier_id"] == "SUP-001" and o["actual_delivery"] is not None
    ]
    early = [o for o in apex_delivered if o["order_date"] < "2026-04-01"]
    late = [o for o in apex_delivered if o["order_date"] >= "2026-04-01"]
    assert early, "expected some early Apex orders"
    assert late, "expected some recent Apex orders"

    def avg_delay(rows):
        deltas = [(r["actual_delivery"] - r["eta"]).days for r in rows]
        return sum(deltas) / len(deltas)

    assert avg_delay(early) < avg_delay(late)


def test_generate_inventory_seeds_perfect_storm_numbers():
    inventory = generate_inventory()
    assert len(inventory) == 20
    by_sku = {row["sku"]: row for row in inventory}
    assert by_sku["SKU-C01"]["current_stock"] == 9
    assert by_sku["SKU-C01"]["reorder_point"] == 14
    assert by_sku["SKU-C01"]["lead_time_days"] == 21
    assert by_sku["SKU-C02"]["current_stock"] == 18
    assert by_sku["SKU-C02"]["reorder_point"] == 10
