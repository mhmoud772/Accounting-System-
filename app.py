import sqlite3
import csv
from io import StringIO
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, Response

import os

app = Flask(__name__)
DB_NAME = os.environ.get("DB_PATH", "accounting.db")
app.secret_key = os.environ.get("SECRET_KEY", "super_secure_ledger_key_2026")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "123")

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

# Initialize DB when the app starts
init_db()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def build_transactions_query():
    query = "SELECT * FROM transactions"
    params = []
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    conditions = []
    if start_date:
        conditions.append(" date(created_at) >= ?")
        params.append(start_date)
    if end_date:
        conditions.append(" date(created_at) <= ?")
        params.append(end_date)
        
    if conditions:
        query += " WHERE" + " AND ".join(conditions)
        
    query += " ORDER BY created_at DESC"
    return query, params

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            error = "كلمة المرور غير صحيحة"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route("/")
@login_required
def index():
    conn = get_db_connection()
    query, params = build_transactions_query()
    transactions = conn.execute(query, params).fetchall()
    
    total_income = sum(t['amount'] for t in transactions if t['type'] == 'دخل')
    total_expense = sum(t['amount'] for t in transactions if t['type'] == 'مصروف')
    balance = total_income - total_expense
    conn.close()
    
    return render_template("index.html", 
                           transactions=transactions, 
                           total_income=total_income, 
                           total_expense=total_expense, 
                           balance=balance)

@app.route("/add", methods=["POST"])
@login_required
def add_transaction():
    type_ = request.form.get("type")
    try:
        amount = float(request.form.get("amount", 0))
    except ValueError:
        amount = 0.0
    description = request.form.get("description", "").strip()
    
    if type_ in ["دخل", "مصروف"] and amount > 0 and description:
        with get_db_connection() as conn:
            conn.execute("INSERT INTO transactions (type, amount, description) VALUES (?, ?, ?)", 
                         (type_, amount, description))
            conn.commit()
            
    return redirect(url_for("index"))

@app.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete_transaction(id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM transactions WHERE id = ?", (id,))
        conn.commit()
    return redirect(url_for("index"))

@app.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_transaction(id):
    conn = get_db_connection()
    if request.method == "POST":
        type_ = request.form.get("type")
        try:
            amount = float(request.form.get("amount", 0))
        except ValueError:
            amount = 0.0
        description = request.form.get("description", "").strip()
        
        if type_ in ["دخل", "مصروف"] and amount > 0 and description:
            conn.execute("UPDATE transactions SET type = ?, amount = ?, description = ? WHERE id = ?", 
                         (type_, amount, description, id))
            conn.commit()
        conn.close()
        return redirect(url_for("index"))
    
    transaction = conn.execute("SELECT * FROM transactions WHERE id = ?", (id,)).fetchone()
    conn.close()
    if not transaction:
        return redirect(url_for("index"))
    
    return render_template("edit.html", t=transaction)

@app.route("/export")
@login_required
def export_csv():
    conn = get_db_connection()
    query, params = build_transactions_query()
    transactions = conn.execute(query, params).fetchall()
    conn.close()
    
    def generate():
        data = StringIO()
        writer = csv.writer(data)
        # BOM for Excel Arabic support
        data.write('\ufeff')
        writer.writerow(('رقم العملية', 'النوع', 'المبلغ', 'الوصف', 'التاريخ'))
        yield data.getvalue()
        data.seek(0)
        data.truncate(0)
        
        for t in transactions:
            writer.writerow((t['id'], t['type'], t['amount'], t['description'], t['created_at']))
            yield data.getvalue()
            data.seek(0)
            data.truncate(0)

    return Response(generate(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=transactions.csv'})

@app.route("/admin")
@login_required
def admin():
    conn = get_db_connection()
    query, params = build_transactions_query()
    # Apply limit explicitly for admin page
    transactions = conn.execute(query + " LIMIT 10", params).fetchall()
    count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    conn.close()
    return render_template("admin.html", count=count, transactions=transactions)

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/stats")
def stats():
    conn = get_db_connection()
    transactions = conn.execute("SELECT * FROM transactions").fetchall()
    conn.close()
    
    total_income = sum(t['amount'] for t in transactions if t['type'] == 'دخل')
    total_expense = sum(t['amount'] for t in transactions if t['type'] == 'مصروف')
    balance = total_income - total_expense
    
    return jsonify({
        "total_income": total_income,
        "total_expense": total_expense,
        "balance": balance
    })

@app.route("/logs")
def logs():
    conn = get_db_connection()
    transactions = conn.execute("SELECT * FROM transactions ORDER BY created_at DESC LIMIT 10").fetchall()
    conn.close()
    
    logs_data = []
    for t in transactions:
        logs_data.append({
            "timestamp": t['created_at'],
            "level": "INFO",
            "message": f"عملية {t['type']} بقيمة {t['amount']} - {t['description']}"
        })
    return jsonify({"logs": logs_data})

@app.route("/action", methods=["POST"])
def action():
    data = request.json or {}
    action_type = data.get("action")
    if action_type == "restart":
        return jsonify({"status": "success", "message": "تم إعادة التشغيل بنجاح (محاكاة)"})
    elif action_type == "stop":
        return jsonify({"status": "success", "message": "تم إيقاف الخدمة بنجاح (محاكاة)"})
    return jsonify({"status": "error", "message": "إجراء غير مدعوم"}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8002, debug=True)
