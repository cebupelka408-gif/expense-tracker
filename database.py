import os
from contextlib import contextmanager
import psycopg2
from psycopg2.extras import RealDictCursor

@contextmanager
def connect():
    """Открывает транзакцию и обязательно закрывает соединение."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Добавьте DATABASE_URL в Render Environment")
    db = psycopg2.connect(url, sslmode="require", connect_timeout=15, cursor_factory=RealDictCursor)
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def query(sql, args=(), one=False):
    with connect() as db, db.cursor() as cur:
        cur.execute(sql, args)
        if cur.description:
            return cur.fetchone() if one else cur.fetchall()

def init_db():
    # Та же схема, что в v6: записи не очищаются при деплое.
    with connect() as db, db.cursor() as cur:
        cur.execute("""
        SELECT pg_advisory_xact_lock(684193);
        CREATE SCHEMA IF NOT EXISTS tracker_v6;
        CREATE TABLE IF NOT EXISTS tracker_v6.users (
          id SERIAL PRIMARY KEY, nickname TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tracker_v6.expenses (
          id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES tracker_v6.users(id),
          amount NUMERIC(12,2) NOT NULL CHECK(amount>0), category TEXT NOT NULL,
          date DATE NOT NULL, comment TEXT NOT NULL DEFAULT '');
        CREATE INDEX IF NOT EXISTS expenses_user_date ON tracker_v6.expenses(user_id,date);
        """)
