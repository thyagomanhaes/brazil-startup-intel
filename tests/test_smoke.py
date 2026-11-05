"""T1 smoke test: the data Postgres is up and answers queries.

Runs inside the `tests` container (D-050). The DSN comes from the
environment so the same test works against any target.
"""
import os

import psycopg


def test_data_postgres_answers_select_1():
    dsn = os.environ["DATA_PG_DSN"]
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        assert conn.execute("SELECT 1").fetchone() == (1,)
