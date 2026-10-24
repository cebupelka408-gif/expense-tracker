import hashlib
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any, Iterator

DB_PATH = "expenses.db"

CATEGORIES = [
    (1, "Еда", "#f97316", "fa-utensils"),
    (2, "Транспорт", "#3b82f6", "fa-bus"),
    (3, "Жильё", "#8b5cf6", "fa-house"),
    (4, "Развлечения", "#ec4899", "fa-gamepad"),
    (5, "Здоровье", "#10b981", "fa-heart-pulse"),
    (6, "Одежда", "#eab308", "fa-shirt"),
    (7, "Прочее", "#64748b", "fa-ellipsis"),
]


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, digest = stored_hash.split("$", 1)
    except ValueError:
        return False
    new_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return secrets.compare_digest(new_hash, digest)


def init_db() -> None:
    with get_connection() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nickname TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                color TEXT NOT NULL,
                icon TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                comment TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (category) REFERENCES categories(name)
            );
        """)
        db.executemany(
            "INSERT OR IGNORE INTO categories (id, name, color, icon) VALUES (?, ?, ?, ?)",
            CATEGORIES
        )


def create_user(nickname: str, password: str) -> dict[str, Any] | None:
    try:
        with get_connection() as db:
            cursor = db.execute(
                "INSERT INTO users (nickname, password_hash) VALUES (?, ?)",
                (nickname, hash_password(password))
            )
            user_id = int(cursor.lastrowid)
    except sqlite3.IntegrityError:
        return None
    return get_user_by_id(user_id)


def authenticate_user(nickname: str, password: str) -> dict[str, Any] | None:
    with get_connection() as db:
        row = db.execute(
            "SELECT id, nickname, password_hash FROM users WHERE nickname = ?",
            (nickname,)
        ).fetchone()
    if row and verify_password(password, row["password_hash"]):
        return {"id": row["id"], "nickname": row["nickname"]}
    return None


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with get_connection() as db:
        row = db.execute("SELECT id, nickname FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_by_device(device_id: str) -> dict[str, Any] | None:
    with get_connection() as db:
        row = db.execute("""
            SELECT u.id, u.nickname FROM devices d
            JOIN users u ON u.id = d.user_id
            WHERE d.device_id = ?
        """, (device_id,)).fetchone()
    return dict(row) if row else None


def bind_device(device_id: str, user_id: int) -> None:
    with get_connection() as db:
        db.execute("""
            INSERT INTO devices (device_id, user_id) VALUES (?, ?)
            ON CONFLICT(device_id) DO UPDATE SET user_id = excluded.user_id
        """, (device_id, user_id))


def unbind_device(device_id: str) -> None:
    with get_connection() as db:
        db.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))


def get_categories() -> list[dict[str, Any]]:
    with get_connection() as db:
        rows = db.execute("SELECT id, name, color, icon FROM categories ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def _period_condition(period: str) -> tuple[str, list[Any]]:
    today = date.today()
    if period == "today":
        return "date(e.date) = ?", [today.isoformat()]
    if period == "week":
        return "date(e.date) BETWEEN ? AND ?", [(today - timedelta(days=6)).isoformat(), today.isoformat()]
    if period == "month":
        return "strftime('%Y-%m', e.date) = ?", [today.strftime("%Y-%m")]
    if period == "year":
        return "strftime('%Y', e.date) = ?", [str(today.year)]
    return "1 = 1", []


def get_expenses(user_id: int, period: str = "all", category: str = "", search: str = "") -> list[dict[str, Any]]:
    condition, params = _period_condition(period)
    query = f"""
        SELECT e.id, e.amount, e.category, c.name AS category_name, c.color, c.icon, e.date, e.comment
        FROM expenses e
        JOIN categories c ON c.name = e.category
        WHERE e.user_id = ? AND {condition}
    """
    params = [user_id] + params
    if category:
        query += " AND e.category = ?"
        params.append(category)
    if search:
        query += " AND (e.comment LIKE ? OR e.category LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    query += " ORDER BY e.date DESC, e.id DESC"
    with get_connection() as db:
        rows = db.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def add_expense(user_id: int, payload: dict[str, Any]) -> int:
    with get_connection() as db:
        cursor = db.execute(
            "INSERT INTO expenses (user_id, amount, category, date, comment) VALUES (?, ?, ?, ?, ?)",
            (user_id, payload["amount"], payload["category"], payload["date"], payload["comment"])
        )
        return int(cursor.lastrowid)


def update_expense(user_id: int, expense_id: int, payload: dict[str, Any]) -> bool:
    with get_connection() as db:
        cursor = db.execute("""
            UPDATE expenses SET amount=?, category=?, date=?, comment=?
            WHERE id=? AND user_id=?
        """, (payload["amount"], payload["category"], payload["date"], payload["comment"], expense_id, user_id))
        return cursor.rowcount > 0


def delete_expense(user_id: int, expense_id: int) -> bool:
    with get_connection() as db:
        cursor = db.execute("DELETE FROM expenses WHERE id=? AND user_id=?", (expense_id, user_id))
        return cursor.rowcount > 0


def get_stats(user_id: int, period: str = "month", category: str = "") -> dict[str, Any]:
    today = date.today()
    current_month = today.strftime("%Y-%m")
    previous_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

    with get_connection() as db:
        current_total = db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE user_id=? AND strftime('%Y-%m', date)=?",
            (user_id, current_month)).fetchone()[0]
        previous_total = db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE user_id=? AND strftime('%Y-%m', date)=?",
            (user_id, previous_month)).fetchone()[0]
        by_category = db.execute("""
            SELECT c.name, c.color, c.icon, COALESCE(SUM(e.amount),0) AS total, COUNT(e.id) AS count
            FROM categories c LEFT JOIN expenses e
              ON e.category=c.name AND e.user_id=? AND strftime('%Y-%m', e.date)=?
            GROUP BY c.id HAVING total>0 ORDER BY total DESC
        """, (user_id, current_month)).fetchall()
        by_day = db.execute(
            "SELECT date, SUM(amount) AS total FROM expenses WHERE user_id=? AND strftime('%Y-%m', date)=? GROUP BY date ORDER BY date",
            (user_id, current_month)).fetchall()
        by_month = db.execute("""
            SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total FROM expenses
            WHERE user_id=? AND date >= date('now','-5 months','start of month')
            GROUP BY month ORDER BY month
        """, (user_id,)).fetchall()
        recent = db.execute("""
            SELECT e.id, e.amount, e.category, c.name AS category_name, c.color, c.icon, e.date, e.comment
            FROM expenses e JOIN categories c ON c.name=e.category
            WHERE e.user_id=? ORDER BY e.date DESC, e.id DESC LIMIT 5
        """, (user_id,)).fetchall()
        top_expenses = db.execute("""
            SELECT e.id, e.amount, e.category, c.name AS category_name, c.color, c.icon, e.date, e.comment
            FROM expenses e JOIN categories c ON c.name=e.category
            WHERE e.user_id=? ORDER BY e.amount DESC LIMIT 5
        """, (user_id,)).fetchall()
        average_check = db.execute(
            "SELECT category, AVG(amount) AS average, COUNT(*) AS count FROM expenses WHERE user_id=? GROUP BY category ORDER BY average DESC",
            (user_id,)).fetchall()

    change = (current_total - previous_total) / previous_total * 100 if previous_total else 0
    days_passed = today.day
    days_in_month = (date(today.year, today.month % 12 + 1, 1) - timedelta(days=1)).day
    forecast = current_total / days_passed * days_in_month if days_passed else 0

    return {
        "currentMonthTotal": current_total,
        "previousMonthTotal": previous_total,
        "changePercent": round(change, 1),
        "averagePerDay": round(current_total / days_passed, 2) if days_passed else 0,
        "topCategory": by_category[0]["name"] if by_category else None,
        "byCategory": [dict(row) for row in by_category],
        "byDay": [dict(row) for row in by_day],
        "byMonth": [dict(row) for row in by_month],
        "recent": [dict(row) for row in recent],
        "topExpenses": [dict(row) for row in top_expenses],
        "averageCheck": [dict(row) for row in average_check],
        "forecast": round(forecast, 2)
    }
