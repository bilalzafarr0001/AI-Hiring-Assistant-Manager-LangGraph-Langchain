"""
Database setup. Run from the project folder (safe to run again at any time):

    python -m database.setup_db

It will:
1. Create the database (if it does not exist)
2. Create the 5 tables (schema.sql)
3. Upgrade an older database: move its data into the 5 tables and remove the old tables
4. Add demo users and departments (seed.sql)
5. Set a password for the demo HR account (only if it has none yet)
"""
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from config.settings import DATABASE_URL
from services.security import hash_password

DEMO_HR_EMAIL = "hr@bilal.local"
DEMO_HR_PASSWORD = "ChangeMe@123"

# Tables used by older versions of this app. Their data now lives in "candidates".
OLD_APP_TABLES = ["candidate_interviewers", "interviews", "feedback"]
# Tables the old LangGraph PostgresSaver created. The workflow position now lives in "candidates".
OLD_LANGGRAPH_TABLES = ["checkpoint_writes", "checkpoint_blobs", "checkpoints", "checkpoint_migrations"]

HERE = Path(__file__).parent


def create_database_if_missing():
    info = conninfo_to_dict(DATABASE_URL)
    db_name = info.get("dbname")
    admin_url = make_conninfo(DATABASE_URL, dbname="postgres")
    with psycopg.connect(admin_url, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)).fetchone()
        if exists:
            print(f"Database '{db_name}' already exists.")
        else:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
            print(f"Database '{db_name}' created.")


def run_sql_file(filename):
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute((HERE / filename).read_text(encoding="utf-8"))
    print(f"Ran {filename}.")


def upgrade_old_database():
    """Moves data out of the old tables (if any) and removes them. All or nothing."""
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.transaction():
            found = [t for t in OLD_APP_TABLES + OLD_LANGGRAPH_TABLES
                     if conn.execute("SELECT to_regclass(%s)", (f"public.{t}",)).fetchone()[0]]
            if not found:
                return
            if all(t in found for t in OLD_APP_TABLES):
                conn.execute((HERE / "migrate_old_tables.sql").read_text(encoding="utf-8"))
                print("Moved interviewers, interviews and feedback into the candidates table.")
            for table in found:
                conn.execute(sql.SQL("DROP TABLE {} CASCADE").format(sql.Identifier(table)))
            print(f"Removed old tables: {', '.join(found)}.")


def set_demo_hr_password():
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        cur = conn.execute(
            "UPDATE users SET password_hash = %s WHERE email = %s AND password_hash IS NULL",
            (hash_password(DEMO_HR_PASSWORD), DEMO_HR_EMAIL),
        )
        if cur.rowcount:
            print(f"Demo HR login created: {DEMO_HR_EMAIL} / {DEMO_HR_PASSWORD}  (change it after first login!)")


def list_tables():
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename").fetchall()
    return [r[0] for r in rows]


if __name__ == "__main__":
    create_database_if_missing()
    run_sql_file("schema.sql")
    upgrade_old_database()
    run_sql_file("seed.sql")
    set_demo_hr_password()
    tables = list_tables()
    print(f"\nDatabase setup complete. {len(tables)} tables: {', '.join(tables)}")
