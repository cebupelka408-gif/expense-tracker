from flask import Flask, render_template, request, jsonify, Response, redirect, url_for, session, make_response
from database import (
    init_db, get_expenses, add_expense, update_expense, delete_expense,
    get_categories, get_stats, create_user, authenticate_user,
    get_user_by_device, bind_device, unbind_device, get_user_by_id
)
import csv
import io
import uuid
import os
from datetime import timedelta
from functools import wraps
from typing import Any, Callable

app = Flask(__name__)
app.secret_key = "expense-tracker-local-secret-key-change-me"
app.permanent_session_lifetime = timedelta(days=365)

init_db()


def get_device_id() -> str:
    device_id = request.cookies.get("device_id")
    if not device_id:
        device_id = uuid.uuid4().hex
    return device_id


def current_user() -> dict[str, Any] | None:
    user_id = session.get("user_id")
    if user_id:
        user = get_user_by_id(user_id)
        if user:
            return user

    device_id = get_device_id()
    user = get_user_by_device(device_id)
    if user:
        session.permanent = True
        session["user_id"] = user["id"]
    return user


def login_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for("auth"))
        return view(*args, **kwargs)
    return wrapper


@app.route("/auth", methods=["GET", "POST"])
def auth():
    device_id = get_device_id()
    bound_user = get_user_by_device(device_id)

    if bound_user:
        session.permanent = True
        session["user_id"] = bound_user["id"]
        return redirect(url_for("dashboard"))

    error = ""
    mode = request.form.get("mode", "login")

    if request.method == "POST":
        nickname = request.form.get("nickname", "").strip()
        password = request.form.get("password", "")

        if len(nickname) < 3:
            error = "Ник должен содержать минимум 3 символа"
        elif len(password) < 4:
            error = "Пароль должен содержать минимум 4 символа"
        else:
            user = None
            if mode == "register":
                user = create_user(nickname, password)
                if not user:
                    error = "Такой ник уже занят"
            else:
                user = authenticate_user(nickname, password)
                if not user:
                    error = "Неверный ник или пароль"

            if user:
                bind_device(device_id, user["id"])
                session.permanent = True
                session["user_id"] = user["id"]
                response = make_response(redirect(url_for("dashboard")))
                response.set_cookie("device_id", device_id, max_age=60*60*24*365, httponly=True)
                return response

    return render_template("auth.html", error=error, mode=mode)


@app.route("/logout")
def logout():
    device_id = get_device_id()
    unbind_device(device_id)
    session.clear()
    response = make_response(redirect(url_for("auth")))
    response.delete_cookie("device_id")
    return response


@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html", categories=get_categories(), user=current_user())


@app.route("/transactions")
@login_required
def transactions():
    period = request.args.get("period", "all")
    category = request.args.get("category", "")
    search = request.args.get("search", "")
    expenses = get_expenses(current_user()["id"], period, category, search)
    return render_template("transactions.html", expenses=expenses, categories=get_categories(),
                           period=period, selected_category=category, search=search, user=current_user())


@app.route("/analytics")
@login_required
def analytics():
    return render_template("analytics.html", categories=get_categories(), user=current_user())


def validate_payload(data: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    try:
        amount = round(float(data.get("amount", 0)), 2)
    except (TypeError, ValueError):
        return None, "Некорректная сумма"
    if amount <= 0:
        return None, "Сумма должна быть больше 0"
    if abs(amount * 100 - round(amount * 100)) > 0.001:
        return None, "Допускается не более двух знаков после запятой"
    category = str(data.get("category", "")).strip()
    if category not in {item["name"] for item in get_categories()}:
        return None, "Неизвестная категория"
    date_value = str(data.get("date", "")).strip()
    if len(date_value) != 10 or date_value[4] != "-" or date_value[7] != "-":
        return None, "Некорректная дата"
    comment = str(data.get("comment", "")).strip() or None
    return {"amount": amount, "category": category, "date": date_value, "comment": comment}, ""


@app.route("/api/expenses", methods=["POST"])
@login_required
def api_add_expense():
    data = request.get_json(silent=True) or {}
    payload, error = validate_payload(data)
    if error:
        return jsonify({"error": error}), 400
    try:
        expense_id = add_expense(current_user()["id"], payload)
        return jsonify({"id": expense_id, **payload}), 201
    except Exception:
        return jsonify({"error": "Не удалось сохранить расход"}), 500


@app.route("/api/expenses/<int:expense_id>", methods=["PUT"])
@login_required
def api_update_expense(expense_id: int):
    data = request.get_json(silent=True) or {}
    payload, error = validate_payload(data)
    if error:
        return jsonify({"error": error}), 400
    if not update_expense(current_user()["id"], expense_id, payload):
        return jsonify({"error": "Расход не найден"}), 404
    return jsonify({"id": expense_id, **payload})


@app.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
@login_required
def api_delete_expense(expense_id: int):
    if not delete_expense(current_user()["id"], expense_id):
        return jsonify({"error": "Расход не найден"}), 404
    return jsonify({"success": True})


@app.route("/api/stats")
@login_required
def api_stats():
    return jsonify(get_stats(current_user()["id"],
                             request.args.get("period", "month"),
                             request.args.get("category", "")))


@app.route("/export/csv")
@login_required
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Дата", "Категория", "Сумма BYN", "Комментарий"])
    for expense in get_expenses(current_user()["id"], "all"):
        writer.writerow([expense["date"], expense["category_name"],
                         f"{expense['amount']:.2f}".replace(".", ","), expense["comment"] or ""])
    response = Response("\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = "attachment; filename=expenses.csv"
    return response


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
