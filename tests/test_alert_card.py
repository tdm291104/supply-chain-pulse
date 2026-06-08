from ui.components.alert_card import severity_color, format_alert_summary


def test_severity_color_maps_to_palette():
    assert severity_color("HIGH") == "#E24B4A"
    assert severity_color("MEDIUM") == "#EF9F27"
    assert severity_color("LOW") == "#639922"
    assert severity_color("UNKNOWN") == "#639922"


def test_format_alert_summary_includes_skus_and_action():
    summary = format_alert_summary(
        severity="HIGH",
        affected_skus=["SKU-C01"],
        description="Three converging signals threaten supply.",
        recommended_action="Switch to SUP-002 + increase monitoring to 15 min",
    )
    assert "SKU-C01" in summary
    assert "HIGH" in summary
    assert "Switch to SUP-002" in summary
