"""Small helpers to talk to PostgreSQL."""
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from config.settings import DATABASE_URL


def get_connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True)


def fetch_all(sql, params=None):
    with get_connection() as conn:
        return conn.execute(sql, params).fetchall()


def fetch_one(sql, params=None):
    with get_connection() as conn:
        return conn.execute(sql, params).fetchone()


def execute(sql, params=None):
    """Runs INSERT / UPDATE / DELETE. Returns the row if the SQL has RETURNING."""
    with get_connection() as conn:
        cur = conn.execute(sql, params)
        return cur.fetchone() if cur.description else None


def as_json(data):
    return Jsonb(data)
