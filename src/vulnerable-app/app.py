"""
VulnShop - en bevisst SÅRBAR nettbutikk laget for attack/defend-øvelser.

VIKTIG:
- Kun til bruk i isolert lab-/øvingsmiljø (egen VM, Docker, eller lukket nettverk).
- IKKE deploy dette på internett eller på en maskin med annen viktig data.
- Se VULNERABILITIES.md for full oversikt over hva som er plantet og hvorfor.

Kjør:
    pip install -r requirements.txt
    python app.py
Åpne http://127.0.0.1:5000
"""

import os
import sqlite3
import subprocess

from flask import (
    Flask, g, request, session, redirect, url_for,
    render_template, send_from_directory, make_response
)

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_ROOT, "vulnshop.db")
UPLOAD_DIR = os.path.join(APP_ROOT, "static", "uploads")
REPORTS_DIR = os.path.join(APP_ROOT, "reports")

app = Flask(__name__)
app.secret_key = "supersecret123"  # (VULN: svak, hardkodet secret key)


# ---------------------------------------------------------------------------
# Database-oppsett
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    first_time = not os.path.exists(DB_PATH)
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,      -- VULN: lagres i klartekst
        email TEXT,
        bio TEXT,
        address TEXT,
        role TEXT DEFAULT 'user'
    );

    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        price REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        username TEXT,
        body TEXT
    );

    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        product_name TEXT,
        price REAL
    );
    """)

    if first_time:
        db.execute(
            "INSERT INTO users (username, password, email, bio, address, role) VALUES (?,?,?,?,?,?)",
            ("admin", "S3cr3tAdminPW!", "admin@vulnshop.local",
             "Systemadministrator. FLAG{idor_admin_profile_found}", "Serverrom 1", "admin"),
        )
        db.execute(
            "INSERT INTO users (username, password, email, bio, address, role) VALUES (?,?,?,?,?,?)",
            ("alice", "alice123", "alice@example.com", "Hei, jeg er Alice!", "Kongens gate 1", "user"),
        )
        db.execute(
            "INSERT INTO users (username, password, email, bio, address, role) VALUES (?,?,?,?,?,?)",
            ("bob", "bob123", "bob@example.com", "Bob liker juice.", "Storgata 5", "user"),
        )

        products = [
            ("Eplejuice", "Frisk og syrlig eplejuice.", 39.0),
            ("Appelsinjuice", "Nypresset appelsinjuice.", 45.0),
            ("Bærmix", "Blanding av bær og revolusjonerende smak.", 55.0),
            ("VIP Gullpakke", "Kun for spesielle kunder.", 999.0),
        ]
        db.executemany(
            "INSERT INTO products (name, description, price) VALUES (?,?,?)", products
        )
        db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Hjelpefunksjoner
# ---------------------------------------------------------------------------

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


# ---------------------------------------------------------------------------
# Ruter
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    db = get_db()
    products = db.execute("SELECT * FROM products").fetchall()
    return render_template("index.html", products=products, user=current_user())


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (username, password, email, bio, address) VALUES (?,?,?,?,?)",
                (
                    request.form["username"],
                    request.form["password"],  # VULN: ingen hashing, ingen passordkrav
                    request.form.get("email", ""),
                    "",
                    request.form.get("address", ""),
                ),
            )
            db.commit()
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            error = "Brukernavnet er allerede tatt."
    return render_template("register.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        db = get_db()

        # VULN: SQL-injection - brukerinput settes rett inn i spørringen.
        # Prøv f.eks. brukernavn:  admin' --
        query = "SELECT * FROM users WHERE username = '{}' AND password = '{}'".format(
            username, password
        )
        try:
            user = db.execute(query).fetchone()
        except sqlite3.OperationalError:
            user = None

        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            # VULN: klienten kan selv sette/lese denne cookien og endre rolle
            resp = make_response(redirect(url_for("index")))
            resp.set_cookie("role", user["role"])
            return resp
        error = "Feil brukernavn eller passord."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    resp = make_response(redirect(url_for("index")))
    resp.delete_cookie("role")
    return resp


@app.route("/profile/<int:user_id>")
def profile(user_id):
    # VULN: IDOR - ingen sjekk på at innlogget bruker faktisk eier user_id.
    # Alle innloggede brukere kan se enhver annen brukers profil ved å endre id i URL.
    db = get_db()
    profile_user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not profile_user:
        return "Bruker ikke funnet", 404
    return render_template("profile.html", profile_user=profile_user, user=current_user())


@app.route("/search")
def search():
    q = request.args.get("q", "")
    db = get_db()
    # VULN: SQL-injection også her (samme mønster, valgfri ekstra-øvelse)
    query = "SELECT * FROM products WHERE name LIKE '%{}%'".format(q)
    try:
        results = db.execute(query).fetchall()
    except sqlite3.OperationalError:
        results = []
    # VULN: reflektert XSS - "q" rendres direkte inn i siden usanert (se template)
    return render_template("search.html", results=results, q=q)


@app.route("/product/<int:product_id>", methods=["GET", "POST"])
def product(product_id):
    db = get_db()
    if request.method == "POST":
        user = current_user()
        body = request.form.get("body", "")
        # VULN: Stored XSS - kommentaren lagres og rendres senere med |safe i template
        db.execute(
            "INSERT INTO comments (product_id, username, body) VALUES (?,?,?)",
            (product_id, user["username"] if user else "anonym", body),
        )
        db.commit()
    prod = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    comments = db.execute(
        "SELECT * FROM comments WHERE product_id = ?", (product_id,)
    ).fetchall()
    return render_template("product.html", product=prod, comments=comments, user=current_user())


@app.route("/checkout", methods=["POST"])
def checkout():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    # VULN: Prismanipulering - prisen sendes fra klienten (skjult felt) og
    # stoles på direkte i stedet for å slå den opp i databasen server-side.
    product_name = request.form.get("product_name")
    price = request.form.get("price")
    db = get_db()
    db.execute(
        "INSERT INTO orders (user_id, product_name, price) VALUES (?,?,?)",
        (user["id"], product_name, price),
    )
    db.commit()
    return render_template("checkout.html", product_name=product_name, price=price)


@app.route("/upload", methods=["GET", "POST"])
def upload():
    message = None
    if request.method == "POST":
        file = request.files.get("file")
        if file and file.filename:
            # VULN: ingen validering av filtype/størrelse/innhold,
            # og filnavnet brukes rått (mulig path traversal via filnavn også).
            save_path = os.path.join(UPLOAD_DIR, file.filename)
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            file.save(save_path)
            message = "Fil lastet opp: " + file.filename
    return render_template("upload.html", message=message)


@app.route("/download")
def download():
    # VULN: Path traversal - filnavn tas rett fra query-parameter uten sanering.
    # Prøv f.eks. ?file=../app.py eller ?file=../../vulnshop.db
    filename = request.args.get("file", "report1.txt")
    full_path = os.path.join(REPORTS_DIR, filename)
    try:
        with open(full_path, "r", errors="replace") as f:
            content = f.read()
    except Exception as e:
        content = "Kunne ikke lese fil: {}".format(e)
    return render_template("download.html", filename=filename, content=content)


@app.route("/admin")
def admin():
    # VULN: Broken access control - sjekker kun en cookie klienten selv satte
    # ved innlogging, ikke faktisk server-side sesjon/rolle fra databasen.
    role = request.cookies.get("role")
    if role != "admin":
        return "Ingen tilgang (403)", 403
    db = get_db()
    users = db.execute("SELECT * FROM users").fetchall()
    return render_template("admin.html", users=users)


@app.route("/admin/ping", methods=["GET", "POST"])
def admin_ping():
    role = request.cookies.get("role")
    if role != "admin":
        return "Ingen tilgang (403)", 403
    output = None
    if request.method == "POST":
        host = request.form.get("host", "")
        # VULN: Command injection - brukerinput sendes rett til shell.
        # Prøv f.eks. host = "127.0.0.1; cat /etc/passwd"
        cmd = "ping -c 1 " + host
        try:
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
        except Exception as e:
            output = str(e)
    return render_template("admin_ping.html", output=output)


@app.route("/robots.txt")
def robots():
    # VULN: robots.txt lekker skjulte/"hemmelige" stier
    resp = make_response(
        "User-agent: *\n"
        "Disallow: /admin\n"
        "Disallow: /admin/ping\n"
        "Disallow: /static/backup/\n"
    )
    resp.headers["Content-Type"] = "text/plain"
    return resp


@app.route("/static/backup/<path:filename>")
def backup_files(filename):
    # VULN: eksponert backup-mappe med sensitiv info (simulerer feilkonfigurert server)
    return send_from_directory(os.path.join(APP_ROOT, "static", "backup"), filename)


if __name__ == "__main__":
    init_db()
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    app.run(debug=True, host="0.0.0.0", port=5000)
    # VULN: debug=True i "produksjon" gir Werkzeug-debugger/stack traces til klienten
