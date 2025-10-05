from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3

app = Flask(__name__)
app.secret_key = "moon_cafe_secret_change_me"  # prod'da değiştir

DB = "cafe.db"

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def slugify(s):
    return (s.lower()
            .replace(" ", "-")
            .replace("ç","c").replace("ğ","g").replace("ı","i")
            .replace("ö","o").replace("ş","s").replace("ü","u"))

# ----- Settings helpers -----
def get_setting(key, default=""):
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row and row["value"] is not None else default

def set_setting(key, value):
    conn = get_db()
    conn.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value))
    conn.commit()
    conn.close()

# ======= PUBLIC =======
@app.route("/")
def home():
    return redirect(url_for("menu"))

@app.route("/menu")
def menu():
    return render_template("menu.html")

@app.route("/api/menu")
def api_menu():
    # Şimdilik "Soğuk İçecekler" grubu
    conn = get_db()
    cats = conn.execute("""
      SELECT id, title, price, img FROM categories
      WHERE group_name=?
      ORDER BY sort_order ASC, id ASC
    """, ("Soğuk İçecekler",)).fetchall()

    out = []
    for c in cats:
        flavors = conn.execute(
            "SELECT name FROM flavors WHERE category_id=? ORDER BY id ASC",
            (c["id"],)
        ).fetchall()
        out.append({
            "key": slugify(c["title"]),
            "title": c["title"],
            "img": c["img"],
            "price": f"{float(c['price']):.2f} TL",
            "items": [f["name"] for f in flavors]
        })
    conn.close()
    return jsonify(out)

@app.route("/api/announcement")
def api_announcement():
    return jsonify({"text": get_setting("announcement", "")})

# ======= ADMIN AUTH =======
@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        u = request.form.get("username","").strip()
        p = request.form.get("password","")
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=?", (u,p)
        ).fetchone()
        conn.close()
        if row:
            session["user"] = u
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_login.html", error="Hatalı kullanıcı adı veya şifre.")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("user", None)
    return redirect(url_for("admin_login"))

def require_login():
    return ("user" in session)

# ======= ADMIN UI =======
@app.route("/admin")
def admin_dashboard():
    if not require_login():
        return redirect(url_for("admin_login"))
    announcement = get_setting("announcement", "")
    return render_template("admin_dashboard.html", announcement=announcement)

@app.route("/admin/announcement", methods=["POST"])
def admin_announcement_update():
    if not require_login():
        return redirect(url_for("admin_login"))
    msg = request.form.get("announcement","").strip()
    set_setting("announcement", msg)
    return redirect(url_for("admin_dashboard"))

# Soğuk içecek alt-kategorileri
@app.route("/admin/cold")
def admin_cold():
    if not require_login():
        return redirect(url_for("admin_login"))
    conn = get_db()
    cats = conn.execute("""
      SELECT id, title, price, img FROM categories
      WHERE group_name=?
      ORDER BY sort_order ASC, id ASC
    """, ("Soğuk İçecekler",)).fetchall()
    conn.close()
    return render_template("admin_cold.html", cats=cats)

@app.route("/admin/cold/add", methods=["POST"])
def admin_cold_add():
    if not require_login():
        return redirect(url_for("admin_login"))
    title   = request.form["title"].strip()
    price   = float(request.form["price"])
    img     = request.form.get("img","soguk_icecek.jpg").strip()
    conn = get_db()
    conn.execute("""
      INSERT INTO categories(group_name,title,price,img,sort_order)
      VALUES(?,?,?,?,?)
    """, ("Soğuk İçecekler", title, price, img, 999))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_cold"))

@app.route("/admin/cold/<int:cid>/delete", methods=["POST"])
def admin_cold_delete(cid):
    if not require_login():
        return redirect(url_for("admin_login"))
    conn = get_db()
    conn.execute("DELETE FROM categories WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_cold"))

@app.route("/admin/cold/<int:cid>/update", methods=["POST"])
def admin_cold_update(cid):
    if not require_login():
        return redirect(url_for("admin_login"))
    title = request.form["title"].strip()
    price = float(request.form["price"])
    img   = request.form["img"].strip()
    conn = get_db()
    conn.execute("UPDATE categories SET title=?, price=?, img=? WHERE id=?",
                 (title, price, img, cid))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_cold"))

# Tat/çeşit yönetimi
@app.route("/admin/cold/<int:cid>/flavors")
def admin_flavors(cid):
    if not require_login():
        return redirect(url_for("admin_login"))
    conn = get_db()
    cat = conn.execute("SELECT * FROM categories WHERE id=?", (cid,)).fetchone()
    fls = conn.execute("SELECT id, name FROM flavors WHERE category_id=? ORDER BY id ASC", (cid,)).fetchall()
    conn.close()
    return render_template("admin_flavors.html", cat=cat, flavors=fls)

@app.route("/admin/cold/<int:cid>/flavors/add", methods=["POST"])
def admin_flavors_add(cid):
    if not require_login():
        return redirect(url_for("admin_login"))
    name = request.form["name"].strip()
    if name:
        conn = get_db()
        conn.execute("INSERT INTO flavors(category_id, name) VALUES(?,?)", (cid, name))
        conn.commit()
        conn.close()
    return redirect(url_for("admin_flavors", cid=cid))

@app.route("/admin/flavor/<int:fid>/delete", methods=["POST"])
def admin_flavor_delete(fid):
    if not require_login():
        return redirect(url_for("admin_login"))
    conn = get_db()
    cat = conn.execute("SELECT category_id FROM flavors WHERE id=?", (fid,)).fetchone()
    if cat:
        conn.execute("DELETE FROM flavors WHERE id=?", (fid,))
        conn.commit()
        cid = cat["category_id"]
        conn.close()
        return redirect(url_for("admin_flavors", cid=cid))
    conn.close()
    return redirect(url_for("admin_cold"))

if __name__ == "__main__":
    app.run(debug=True)
