import os
import tempfile
from unittest.mock import MagicMock

import pytest

from agent.chat import ChatRouter
from data.seed_db import seed
from db.database import Database


@pytest.fixture
def seeded_db():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.duckdb")
        db = Database(db_path)
        seed(db, data_dir=os.path.join(os.path.dirname(__file__), "..", "data"))
        yield db
        db.close()


def test_highest_risk_sku_question_queries_risk_summary(seeded_db):
    gemini = MagicMock()
    gemini.generate_text.return_value = "SKU-C01 (Raw cotton fabric) is your highest-risk SKU right now."
    router = ChatRouter(db=seeded_db, gemini=gemini)

    answer, views_queried = router.answer("What's my highest-risk SKU?")

    assert "SKU-C01" in answer
    assert "v_supply_risk_summary" in views_queried
    gemini.generate_text.assert_called_once()


def test_supplier_comparison_question_queries_reliability(seeded_db):
    gemini = MagicMock()
    gemini.generate_text.return_value = "SUP-002 has a much higher on-time rate than SUP-001."
    router = ChatRouter(db=seeded_db, gemini=gemini)

    answer, views_queried = router.answer("Compare SUP-001 vs SUP-002 reliability")

    assert "SUP-002" in answer
    assert "v_supplier_reliability" in views_queried


def test_unrecognized_question_lists_suggestions(seeded_db):
    gemini = MagicMock()
    router = ChatRouter(db=seeded_db, gemini=gemini)

    answer, views_queried = router.answer("What's the meaning of life?")

    assert "highest-risk SKU" in answer
    assert views_queried == []
    gemini.generate_text.assert_not_called()
