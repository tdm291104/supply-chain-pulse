# tests/test_database.py
import os
import tempfile

from db.database import Database


def test_query_and_execute_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.duckdb")
        db = Database(db_path)
        db.execute("CREATE TABLE widgets (id INTEGER, name VARCHAR)")
        db.execute("INSERT INTO widgets VALUES (1, 'bolt'), (2, 'nut')")
        df = db.query("SELECT * FROM widgets ORDER BY id")
        assert list(df["name"]) == ["bolt", "nut"]
        db.close()
