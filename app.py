import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort
from sqlalchemy import create_engine, Integer, String, ForeignKey, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, scoped_session
from werkzeug.middleware.proxy_fix import ProxyFix

# -------------------------------------------------
# Flask & DB BAŞLANGIÇ
# -------------------------------------------------
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)  # Render/nginx proxy fix
app.secret_key = os.getenv("SECRET_KEY", "moon-secret-key")  # PROD: Render > Environment

# Kalıcılık için Render'da DATABASE_URL'i bir diske ver:
# sqlite:////var/data/cafe.db   (Settings > Disks: /var/data olarak bağla)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///cafe.db")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionFactory = sessionmaker(bind=engine, future=True)
DBSession = scoped_session(SessionFactory)


class Base(DeclarativeBase):
    pass


# -------------------------------------------------
# MODELLER
# -------------------------------------------------
class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)   # ör: 'milkshake'
    title: Mapped[str] = mapped_column(String(128), nullable=False)            # ör: 'Milkshake'
    img: Mapped[str] = mapped_column(String(256), nullable=True)               # ör: 'milkshake.jpg'
    price: Mapped[str] = mapped_column(String(64), nullable=True)              # ör: '139.00 TL'
    note: Mapped[str] = mapped_column(Text, nullable=True)

    flavors: Mapped[list["Flavor"]] = relationship(
        "Flavor", back_populates="category", cascade="all, delete-orphan"
    )


class Flavor(Base):
    __tablename__ = "flavors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    category: Mapped["Category"] = relationship("Category", back_populates="flavors")


# -------------------------------------------------
# ŞEMA GÜVENCE: eski tabloda eksik kolonları ekle
# -------------------------------------------------
def ensure_schema():
    with engine.connect() as conn:
        cols = [row[1] for row in conn.execute(text('PRAGMA table_info(categories)')).fetchall()]

    # 'key' yoksa ekle
    if 'key' not in cols:
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE categories ADD COLUMN "key" TEXT'))
        # Eski kayıtlara makul key ata (title'dan slug)
        s = DBSession()
        try:
            cats = s.query(Category).all()
            for c in cats:
                if not getattr(c, 'key', None):
                    slug = (c.title or "").lower().strip().replace(" ", "-")
                    c.key = slug if slug else f"cat-{c.id}"
            s.commit()
        finally:
            s.close()

    # Diğer olası eksikler
    extra = []
    if 'img' not in cols:   extra.append(('img',   'TEXT'))
    if 'price' not in cols: extra.append(('price', 'TEXT'))
    if 'note' not in cols:  extra.append(('note',  'TEXT'))
    if extra:
        with engine.begin() as conn:
            for name, typ in extra:
                conn.execute(text(f'ALTER TABLE categories ADD COLUMN "{name}" {typ}'))


# -------------------------------------------------
# SEED (ilk kurulumda yükle)
# -------------------------------------------------
def seed_if_empty():
    s = DBSession()
    try:
        if s.query(Category).count() > 0:
            return
        cats = [
            dict(key="milkshake",   title="Milkshake",   img="milkshake.jpeg",   price="139.00 TL",
                 items=['çilek','kavun','muz','karamel','mango','çikolata']),
            dict(key="frappe",      title="Frappe",      img="frappe.jpg",       price="119.00 TL",
                 items=['black forest','strawberry','affagato','vanilan supreme']),
            dict(key="soguk-kahve", title="Soğuk Kahve", img="soguk_kahve.avif", price="129.00 TL",
                 items=['latte','caramel latte','mocha','white mocha']),
            dict(key="frozen",      title="Frozen",      img="frozen.jpg",       price="129.00 TL",
                 items=['karpuz','kavun','mango','elma','orman meyvesi','kivi']),
            dict(key="cool-lime",   title="Cool Lime",   img="cool_lime.jpg",    price="99.00 TL",
                 items=['çilek','nane','elma']),
            dict(key="bubble-tea",  title="Bubble Tea",  img="bubble_tea.avif",  price="149.00 TL",
                 items=['çilek','mango','çikolata','yaban mersini']),
        ]
        for c in cats:
            cat = Category(key=c["key"], title=c["title"], img=c["img"], price=c["price"])
            s.add(cat)
            s.flush()  # cat.id için
            for f in c["items"]:
                s.add(Flavor(name=f, category_id=cat.id))
        s.commit()
        print("✅ Seed: varsayılan Moon Cafe menüsü yüklendi.")
    finally:
        s.close()


# ---- tablo oluştur + schema düzelt + seed ----
Base.metadata.create_all(engine)
ensure_schema()
seed_if_empty()


# -------------------------------------------------
# YARDIMCI
# -------------------------------------------------
def require_login():
    return bool(session.get("admin"))

ADMIN_USER = os.getenv("ADMIN_USER", "mudur")
ADMIN_PASS = os.getenv("ADMIN_PASS", "1234")


# -------------------------------------------------
# ROUTES (MÜŞTERİ)
# -------------------------------------------------
@app.route("/")
def root():
    return redirect(url_for("menu"))

@app.route("/menu")
def menu():
    # Ön yüzde JS, /api/cold-data'dan çekecek
    return render_template("menu.html")

@app.route("/api/cold-data")
def api_cold_data():
    s = DBSession()
    try:
        cats = s.query(Category).order_by(Category.id.asc()).all()
        out = []
        for c in cats:
            out.append({
                "id": c.id,
                "key": c.key,
                "title": c.title,
                "img": c.img or "",
                "price": c.price or "",
                "items": [f.name for f in c.flavors]
            })
        return jsonify({"categories": out})
    finally:
        s.close()


# -------------------------------------------------
# ROUTES (ADMIN)
# -------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USER and password == ADMIN_PASS:
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_login.html", error="Hatalı kullanıcı adı/şifre.")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

@app.route("/admin/dashboard")
def admin_dashboard():
    if not require_login():
        return redirect(url_for("admin_login"))
    s = DBSession()
    try:
        cat_count = s.query(Category).count()
        flv_count = s.query(Flavor).count()
        return render_template("admin_dashboard.html", cat_count=cat_count, flv_count=flv_count)
    finally:
        s.close()

@app.route("/admin/cold")
def admin_cold():
    if not require_login():
        return redirect(url_for("admin_login"))
    s = DBSession()
    try:
        cats = s.query(Category).order_by(Category.id.asc()).all()
        return render_template("admin_cold.html", cats=cats)
    finally:
        s.close()

@app.route("/admin/cold/add", methods=["POST"])
def admin_cold_add():
    if not require_login():
        return abort(403)
    key = request.form.get("key", "").strip()
    title = request.form.get("title", "").strip()
    img = request.form.get("img", "").strip()
    price = request.form.get("price", "").strip()
    if not key or not title:
        return redirect(url_for("admin_cold"))
    s = DBSession()
    try:
        exists = s.query(Category).filter_by(key=key).first()
        if not exists:
            s.add(Category(key=key, title=title, img=img, price=price))
            s.commit()
    finally:
        s.close()
    return redirect(url_for("admin_cold"))

@app.route("/admin/cold/delete/<int:cat_id>", methods=["POST"])
def admin_cold_delete(cat_id):
    if not require_login():
        return abort(403)
    s = DBSession()
    try:
        cat = s.query(Category).filter_by(id=cat_id).first()
        if cat:
            s.delete(cat)
            s.commit()
    finally:
        s.close()
    return redirect(url_for("admin_cold"))

@app.route("/admin/flavors/<int:cat_id>")
def admin_flavors(cat_id):
    if not require_login():
        return redirect(url_for("admin_login"))
    s = DBSession()
    try:
        cat = s.query(Category).filter_by(id=cat_id).first()
        if not cat:
            return redirect(url_for("admin_cold"))
        return render_template("admin_flavors.html", cat=cat, flavors=cat.flavors)
    finally:
        s.close()

@app.route("/admin/flavors/<int:cat_id>/add", methods=["POST"])
def admin_flavors_add(cat_id):
    if not require_login():
        return abort(403)
    name = request.form.get("name", "").strip()
    if not name:
        return redirect(url_for("admin_flavors", cat_id=cat_id))
    s = DBSession()
    try:
        cat = s.query(Category).filter_by(id=cat_id).first()
        if cat:
            s.add(Flavor(name=name, category_id=cat.id))
            s.commit()
    finally:
        s.close()
    return redirect(url_for("admin_flavors", cat_id=cat_id))

@app.route("/admin/flavors/<int:cat_id>/delete/<int:flavor_id>", methods=["POST"])
def admin_flavors_delete(cat_id, flavor_id):
    if not require_login():
        return abort(403)
    s = DBSession()
    try:
        flv = s.query(Flavor).filter_by(id=flavor_id, category_id=cat_id).first()
        if flv:
            s.delete(flv)
            s.commit()
    finally:
        s.close()
    return redirect(url_for("admin_flavors", cat_id=cat_id))


# -------------------------------------------------
# LOCAL GELİŞTİRME
# -------------------------------------------------
if __name__ == "__main__":
    # Local'de debug açık. Render prod'da gunicorn kullanıyor.
    app.run(debug=True, host="0.0.0.0", port=5000)
