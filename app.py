import os
import csv
import io
import secrets
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from flask import Flask, request, session, render_template, redirect, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash
from database import query, init_db

app = Flask(__name__)
key = os.environ.get("SECRET_KEY")
if not key:
    raise RuntimeError("Добавьте постоянную случайную SECRET_KEY в Environment Render")
app.secret_key = key
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=os.environ.get("RENDER")=="true",
                  PERMANENT_SESSION_LIFETIME=timedelta(days=365), MAX_CONTENT_LENGTH=16384)
CATS = {"Еда":"#fb923c","Транспорт":"#38bdf8","Жильё":"#a78bfa",
        "Развлечения":"#f472b6","Здоровье":"#34d399","Одежда":"#facc15","Прочее":"#94a3b8"}
init_db()

@app.context_processor
def template_context():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return dict(csrf=session["csrf"], cats=CATS, nickname=session.get("nickname"))

@app.before_request
def check_csrf():
    if request.method in ("POST","PUT","DELETE"):
        token = request.headers.get("X-CSRF-Token") or request.form.get("csrf")
        if not token or token != session.get("csrf"):
            return jsonify(error="Обновите страницу: сессия формы устарела"),400

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("uid"):
            return (jsonify(error="Войдите в аккаунт"),401) if request.path.startswith("/api/") else redirect("/auth")
        return fn(*args, **kwargs)
    return wrapped

@app.route("/auth",methods=["GET","POST"])
def auth():
    if session.get("uid"):
        return redirect("/")
    error=""
    mode=request.form.get("mode","login")
    if request.method=="POST":
        nick=request.form.get("nickname","").strip()
        password=request.form.get("password","")
        user=None
        if not 3<=len(nick)<=32 or not 8<=len(password)<=256:
            error="Ник: 3–32 символа; пароль: минимум 8 символов"
        elif mode=="register":
            user=query("INSERT INTO tracker_v6.users(nickname,password_hash) VALUES (%s,%s) ON CONFLICT(nickname) DO NOTHING RETURNING id,nickname",(nick,generate_password_hash(password)),True)
            if not user: error="Ник уже занят"
        else:
            user=query("SELECT * FROM tracker_v6.users WHERE nickname=%s",(nick,),True)
            if not user or not check_password_hash(user["password_hash"],password):
                error="Неверный ник или пароль"
        if not error and user:
            session.clear()
            session.permanent=True
            session.update(uid=user["id"],nickname=user["nickname"])
            return redirect("/")
    return render_template("auth.html",error=error,mode=mode)

@app.post("/logout")
def logout():
    session.clear()
    return redirect("/auth")

@app.get("/")
@app.get("/transactions")
@app.get("/analytics")
@login_required
def home():
    return render_template("dashboard.html",page=request.path)

def expenses():
    rows=query("SELECT id,amount,category,to_char(date,'YYYY-MM-DD') AS date,comment FROM tracker_v6.expenses WHERE user_id=%s ORDER BY date DESC,id DESC",(session["uid"],))
    return [dict(r,amount=float(r["amount"])) for r in rows]

@app.get("/api/expenses")
@login_required
def get_expenses():
    return jsonify(expenses())

def validate():
    data=request.get_json(silent=True)
    if not isinstance(data,dict): raise ValueError("Ожидается JSON-объект")
    try:
        amount=Decimal(str(data.get("amount","")))
        if not amount.is_finite() or not 0<amount<=Decimal("9999999999.99") or amount!=amount.quantize(Decimal("0.01")):
            raise ValueError("Сумма должна быть положительной, максимум 2 знака после запятой")
    except InvalidOperation:
        raise ValueError("Некорректная сумма")
    category=data.get("category")
    if not isinstance(category,str) or category not in CATS: raise ValueError("Неизвестная категория")
    day=date.fromisoformat(str(data.get("date","")))
    if day.isoformat()!=data["date"]: raise ValueError("Дата должна быть YYYY-MM-DD")
    return amount,category,day,str(data.get("comment", ""))[:1000]

@app.post("/api/expenses")
@login_required
def add():
    try: values=validate()
    except (ValueError,TypeError) as exc: return jsonify(error=str(exc)),400
    row=query("INSERT INTO tracker_v6.expenses(amount,category,date,comment,user_id) VALUES (%s,%s,%s,%s,%s) RETURNING id",(*values,session["uid"]),True)
    return jsonify(id=row["id"]),201

@app.route("/api/expenses/<int:ident>",methods=["PUT","DELETE"])
@login_required
def change(ident):
    if request.method=="DELETE":
        row=query("DELETE FROM tracker_v6.expenses WHERE id=%s AND user_id=%s RETURNING id",(ident,session["uid"]),True)
    else:
        try: values=validate()
        except (ValueError,TypeError) as exc: return jsonify(error=str(exc)),400
        row=query("UPDATE tracker_v6.expenses SET amount=%s,category=%s,date=%s,comment=%s WHERE id=%s AND user_id=%s RETURNING id",(*values,ident,session["uid"]),True)
    return (jsonify(success=True),200) if row else (jsonify(error="Запись не найдена"),404)

@app.get("/export/csv")
@login_required
def export():
    out=io.StringIO()
    writer=csv.writer(out,delimiter=";")
    writer.writerow(["Дата","Категория","Сумма BYN","Комментарий"])
    for r in expenses():
        comment=r["comment"]
        if comment.lstrip().startswith(("=","+","-","@")): comment="'"+comment
        writer.writerow([r["date"],r["category"],f'{r["amount"]:.2f}'.replace(".",","),comment])
    return Response("\ufeff"+out.getvalue(),content_type="text/csv; charset=utf-8",headers={"Content-Disposition":"attachment; filename=expenses.csv"})

@app.errorhandler(500)
def failure(error):
    if request.path.startswith("/api/"): return jsonify(error="Ошибка сервера: проверьте Render Logs"),500
    return "Ошибка сервера. Подробности в Render Logs.",500

if __name__=="__main__":
    app.run(port=5000,debug=False)
