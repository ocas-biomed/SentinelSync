from flask import Flask, request, render_template, redirect, url_for, session, jsonify
from datetime import datetime
import sqlite3
import uuid

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Initializes the sqlite3 Database
def init_db():
    conn = sqlite3.connect('sentinel.db')
    cur = conn.cursor()

    # Creates tables if new
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            severity TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            case_number TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT,
            case_number TEXT,
            resolved INTEGER DEFAULT 0
        )
    ''')

    # Patch: adds a status column to reports
    try:
        cur.execute("ALTER TABLE reports ADD COLUMN status TEXT DEFAULT 'Pending'")
    except sqlite3.OperationalError:
        pass  # already exists

    # Patch!! to add a timestamp to reports
    try:
        cur.execute("ALTER TABLE notifications ADD COLUMN timestamp TEXT")
    except sqlite3.OperationalError:
        pass  # already exists

    # Add demo users
    cur.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)",
                ('nurse1', 'pass123', 'nurse'))
    cur.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)",
                ('admin', 'adminpass', 'admin'))

    conn.commit()
    conn.close()



init_db()

# Verify User Credentials
def verify_user(username, password):
    conn = sqlite3.connect('sentinel.db')
    cur = conn.cursor()
    cur.execute("SELECT id, role FROM users WHERE username=? AND password=?", (username, password))
    user = cur.fetchone()
    conn.close()
    return user

# Routes like login, register, dashobard, reports, admin summarty, etc. to direct you to the right page
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        conn = sqlite3.connect('sentinel.db')
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                        (username, password, role))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            return '<p>Username already exists. <a href="/register">Try again</a></p>'
    return render_template("register.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = verify_user(username, password)
        if user:
            session['user_id'] = user[0]
            session['role'] = user[1]
            return redirect(url_for('dashboard'))
        return '<p>Invalid credentials. <a href="/login">Try again</a></p>'
    return render_template("login.html")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template("dashboard.html", role=session.get('role'))

@app.route('/submit', methods=['GET', 'POST'])
def submit():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        try:
            title = request.form['title']
            description = request.form['description']
            severity = request.form['severity']
            timestamp = datetime.now().isoformat()
            case_number = str(uuid.uuid4())[:8]
            conn = sqlite3.connect('sentinel.db')
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO reports (user_id, title, description, severity, timestamp, case_number)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session['user_id'], title, description, severity, timestamp, case_number))
            if severity == 'Critical':
                message = f"Critical Event: {title}"
                cur.execute("""
                    INSERT INTO notifications (user_id, message, case_number, timestamp)
                    VALUES (?, ?, ?, ?)
                """, (session['user_id'], message, case_number, timestamp))
            conn.commit()
            conn.close()
            return f'<p>Report submitted. Case #: {case_number} <a href="/submit">Submit another</a></p>'
        except Exception as e:
            return f'<p>Error: {e}</p>'
    return render_template("submit.html")

@app.route('/reports')
def reports():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('sentinel.db')
    cur = conn.cursor()
    cur.execute("SELECT title, severity, timestamp, case_number FROM reports WHERE user_id=? ORDER BY timestamp DESC", (session['user_id'],))
    rows = cur.fetchall()
    conn.close()
    return render_template("reports.html", reports=rows)

@app.route('/notifications')
def notifications():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('sentinel.db')
    cur = conn.cursor()
    cur.execute("SELECT id, message, case_number FROM notifications WHERE user_id=? AND resolved=0", (session['user_id'],))
    notes = cur.fetchall()
    conn.close()
    return render_template("notifications.html", notifications=notes)

@app.route('/resolve/<int:nid>')
def resolve(nid):
    conn = sqlite3.connect('sentinel.db')
    cur = conn.cursor()
    cur.execute("UPDATE notifications SET resolved=1 WHERE id=?", (nid,))
    conn.commit()
    conn.close()
    return redirect(url_for('notifications'))

@app.route('/admin/summary')
def admin_summary():
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    conn = sqlite3.connect('sentinel.db')
    cur = conn.cursor()
    cur.execute("SELECT id, title, severity, timestamp, case_number FROM reports ORDER BY timestamp DESC")
    reports = cur.fetchall()
    conn.close()
    return render_template("admin_summary.html", reports=reports)

@app.route('/admin/review/<case_number>', methods=['POST'])
def admin_review(case_number):
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))

    new_status = request.form.get('status')

    try:
        conn = sqlite3.connect('sentinel.db')
        cur = conn.cursor()
        cur.execute("UPDATE reports SET status = ? WHERE case_number = ?", (new_status, case_number))
        cur.execute("SELECT user_id FROM reports WHERE case_number = ?", (case_number,))
        result = cur.fetchone()

        if result:
            user_id = result[0]
            message = f"Your event (Case #{case_number}) has been marked as '{new_status}'."
            timestamp = datetime.now().isoformat()
            cur.execute("""
                INSERT INTO notifications (user_id, message, case_number, timestamp)
                VALUES (?, ?, ?, ?)
            """, (user_id, message, case_number, timestamp))

        conn.commit()
        conn.close()

        return '''
            <p>Status updated and notification sent successfully!</p>
            <p><a href="/admin/summary">← Back to Admin Summary</a></p>
        '''
    except Exception as e:
        return f"<p>Error updating status: {e}</p><p><a href='/admin/summary'>Back</a></p>"

@app.route('/api/report_summary')
def api_report_summary():
    if session.get('role') != 'admin':
        return jsonify({})
    conn = sqlite3.connect('sentinel.db')
    cur = conn.cursor()
    cur.execute("SELECT severity, COUNT(*) FROM reports GROUP BY severity")
    data = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    return jsonify(data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)
