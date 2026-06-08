# db/database.py
import duckdb
import pandas as pd


class Database:
    """Thin wrapper around DuckDB using BigQuery-flavored standard SQL.

    Swapping to real BigQuery later means changing this class's connection
    and query execution, not the SQL the rest of the app writes.
    """

    def __init__(self, path: str):
        self._conn = duckdb.connect(path)

    def query(self, sql: str) -> pd.DataFrame:
        return self._conn.execute(sql).fetchdf()

    def execute(self, sql: str) -> None:
        self._conn.execute(sql)

    def close(self) -> None:
        self._conn.close()
