import hashlib
import secrets
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date, timedelta
from typing import Any

DATABASE_URL = os.environ.get("DATABASE_URL")

CATEGORIES = [
    (1, "Еда", "#f97316", "fa-utensils"),
    (2, "Транспорт", "#3b82f6", "fa-bus"),
    (3, "Жильё", "#8b5cf6", "fa-house"),
    (4, "Развлечения", "#ec4899", "fa-gamepad"),
    (5, "Здоровье", "#10b981", "fa-heart-pulse"),
    (6, "Одежда", "#eab308", "fa-shirt"),
    (7, "Прочее", "#64748b", "fa-ellipsis"),
]


def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


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
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    nickname TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    color TEXT NOT NULL,
                    icon TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS expenses (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    amount NUMERIC(12, 2) NOT NULL CHECK(amount > 0),
                    category TEXT NOT NULL REFERENCES categories(name),
                    date DATE NOT NULL,
                    comment TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            for category in CATEGORIES:
                cursor.execute("""
                    INSERT INTO categories (id, name, color, icon)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                """, category)

        connection.commit()


def create_user(nickname: str, password: str) -> dict[str, Any] | None:
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (nickname, password_hash) VALUES (%s, %s) RETURNING id, nickname",
                    (nickname, hash_password(password))
                )
                user = cursor.fetchone()
        connection.commit()
        return dict(user)
    except psycopg2.errors.UniqueViolation:
        return None


def authenticate_user(nickname: str, password: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, nickname, password_hash FROM users WHERE nickname = %s",
                (nickname,)
            )
            user = cursor.fetchone()

    if user and verify_password(password, user["password_hash"]):
        return {"id": user["id"], "nickname": user["nickname"]}
    return None


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, nickname FROM users WHERE id = %s",
                (user_id,)
            )
            user = cursor.fetchone()
    return dict(user) if user else None


def get_user_by_device(device_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT u.id, u.nickname
                FROM devices d
                JOIN users u ON u.id = d.user_id
                WHERE d.device_id = %s
            """, (device_id,))
            user = cursor.fetchone()
    return dict(user) if user else None


def bind_device(device_id: str, user_id: int) -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO devices (device_id, user_id)
                VALUES (%s, %s)
                ON CONFLICT (device_id)
                DO UPDATE SET user_id = EXCLUDED.user_id
            """, (device_id, user_id))
        connection.commit()


def unbind_device(device_id: str) -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM devices WHERE device_id = %s", (device_id,))
        connection.commit()


def get_categories() -> list[dict[str, Any]]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, name, color, icon FROM categories ORDER BY id"
            )
            return [dict(row) for row in cursor.fetchall()]


def get_expenses(user_id: int, period: str = "all", category: str = "", search: str = "") -> list[dict[str, Any]]:
    conditions = ["e.user_id = %s"]
    params: list[Any] = [user_id]

    today = date.today()

    if period == "today":
        conditions.append("e.date = %s")
        params.append(today)
    elif period == "week":
        conditions.append("e.date BETWEEN %s AND %s")
        params.extend([today - timedelta(days=6), today])
    elif period == "month":
        conditions.append("to_char(e.date, 'YYYY-MM') = %s")
        params.append(today.strftime("%Y-%m"))
    elif period == "year":
        conditions.append("EXTRACT(YEAR FROM e.date) = %s")
        params.append(today.year)

    if category:
        conditions.append("e.category = %s")
        params.append(category)

    if search:
        conditions.append("(e.comment ILIKE %s OR e.category ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    query = f"""
        SELECT e.id, e.amount, e.category, c.name AS category_name,
               c.color, c.icon, e.date, e.comment
        FROM expenses e
        JOIN categories c ON c.name = e.category
        WHERE {' AND '.join(conditions)}
        ORDER BY e.date DESC, e.id DESC
    """

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]


def add_expense(user_id: int, payload: dict[str, Any]) -> int:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO expenses (user_id, amount, category, date, comment)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (user_id, payload["amount"], payload["category"],
                  payload["date"], payload["comment"]))
            expense_id = cursor.fetchone()["id"]
        connection.commit()
    return expense_id


def update_expense(user_id: int, expense_id: int, payload: dict[str, Any]) -> bool:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE expenses
                SET amount = %s, category = %s, date = %s, comment = %s
                WHERE id = %s AND user_id = %s
            """, (payload["amount"], payload["category"], payload["date"],
                  payload["comment"], expense_id, user_id))
            updated = cursor.rowcount > 0
        connection.commit()
    return updated


def delete_expense(user_id: int, expense_id: int) -> bool:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM expenses WHERE id = %s AND user_id = %s",
                (expense_id, user_id)
            )
            deleted = cursor.rowcount > 0
        connection.commit()
    return deleted


def get_stats(user_id: int, period: str = "month", category: str = "") -> dict[str, Any]:
    today = date.today()
    current_month = today.strftime("%Y-%m")
    previous_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM expenses
                WHERE user_id = %s AND to_char(date, 'YYYY-MM') = %s
            """, (user_id, current_month))
            current_total = float(cursor.fetchone()["total"])

            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM expenses
                WHERE user_id = %s AND to_char(date, 'YYYY-MM') = %s
            """, (user_id, previous_month))
            previous_total = float(cursor.fetchone()["total"])

            cursor.execute("""
                SELECT c.name, c.color, c.icon,
                       COALESCE(SUM(e.amount), 0) AS total,
                       COUNT(e.id) AS count
                FROM categories c
                LEFT JOIN expenses e
                  ON e.category = c.name
                 AND e.user_id = %s
                 AND to_char(e.date, 'YYYY-MM') = %s
                GROUP BY c.id
                HAVING COALESCE(SUM(e.amount), 0) > 0
                ORDER BY total DESC
            """, (user_id, current_month))
            by_category = [dict(row) for row in cursor.fetchall()]

            cursor.execute("""
                SELECT to_char(date, 'YYYY-MM-DD') AS date,
                       SUM(amount) AS total
                FROM expenses
                WHERE user_id = %s AND to_char(date, 'YYYY-MM') = %s
                GROUP BY date
                ORDER BY date
            """, (user_id, current_month))
            by_day = [dict(row) for row in cursor.fetchall()]

            cursor.execute("""
                SELECT to_char(date, 'YYYY-MM') AS month,
                       SUM(amount) AS total
                FROM expenses
                WHERE user_id = %s
                  AND date >= date_trunc('month', CURRENT_DATE - INTERVAL '5 months')
                GROUP BY month
                ORDER BY month
            """, (user_id,))
            by_month = [dict(row) for row in cursor.fetchall()]

            cursor.execute("""
                SELECT e.id, e.amount, e.category, c.name AS category_name,
                       c.color, c.icon, e.date, e.comment
                FROM expenses e
                JOIN categories c ON c.name = e.category
                WHERE e.user_id = %s
                ORDER BY e.date DESC, e.id DESC
                LIMIT 5
            """, (user_id,))
            recent = [dict(row) for row in cursor.fetchall()]

            cursor.execute("""
                SELECT e.id, e.amount, e.category, c.name AS category_name,
                       c.color, c.icon, e.date, e.comment
                FROM expenses e
                JOIN categories c ON c.name = e.category
                WHERE e.user_id = %s
                ORDER BY e.amount DESC
                LIMIT 5
            """, (user_id,))
            top_expenses = [dict(row) for row in cursor.fetchall()]

            cursor.execute("""
                SELECT category, AVG(amount) AS average, COUNT(*) AS count
                FROM expenses
                WHERE user_id = %s
                GROUP BY category
                ORDER BY average DESC
            """, (user_id,))
            average_check = [dict(row) for row in cursor.fetchall()]

    change = 0.0
    if previous_total:
        change = (current_total - previous_total) / previous_total * 100

    days_passed = today.day
    days_in_month = (date(today.year, today.month % 12 + 1, 1) - timedelta(days=1)).day
    forecast = current_total / days_passed * days_in_month if days_passed else 0

    return {
        "currentMonthTotal": current_total,
        "previousMonthTotal": previous_total,
        "changePercent": round(change, 1),
        "averagePerDay": round(current_total / days_passed, 2) if days_passed else 0,
        "topCategory": by_category[0]["name"] if by_category else None,
        "byCategory": by_category,
        "byDay": by_day,
        "byMonth": by_month,
        "recent": recent,
        "topExpenses": top_expenses,
        "averageCheck": average_check,
        "forecast": round(forecast, 2)
    }
