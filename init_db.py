import sqlite3

DB = "cafe.db"
conn = sqlite3.connect(DB)
c = conn.cursor()

# Kullanıcılar
c.execute("""
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL
)
""")

# Kategoriler (alt-kategori seviyesinde)
c.execute("""
CREATE TABLE IF NOT EXISTS categories(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  group_name TEXT NOT NULL,    -- "Soğuk İçecekler"
  title TEXT NOT NULL,         -- "Milkshake", "Frappe", ...
  price REAL NOT NULL,
  img TEXT NOT NULL,
  sort_order INTEGER DEFAULT 999
)
""")

# Tat/çeşitler
c.execute("""
CREATE TABLE IF NOT EXISTS flavors(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE
)
""")

# Genel ayarlar (duyuru/kampanya mesajı vs.)
c.execute("""
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
)
""")
c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('announcement', '')")

# Müdür hesabı
c.execute("INSERT OR IGNORE INTO users(username, password) VALUES(?,?)", ("mudur","1234"))

# Soğuk içecek alt-kategorileri
cold = [
  ("Soğuk İçecekler","Milkshake",   139.00, "milkshake.jpeg",   1),
  ("Soğuk İçecekler","Frappe",      119.00, "frappe.jpg",       2),
  ("Soğuk İçecekler","Soğuk Kahve", 129.00, "soguk_kahve.avif", 3),
  ("Soğuk İçecekler","Frozen",      129.00, "frozen.jpg",       4),
  ("Soğuk İçecekler","Cool Lime",    99.00, "cool_lime.jpg",    5),
  ("Soğuk İçecekler","Bubble Tea",  149.00, "bubble_tea.avif",  6),
]
for row in cold:
  c.execute("INSERT INTO categories(group_name, title, price, img, sort_order) VALUES(?,?,?,?,?)", row)

# Tat/çeşitler
def flavors_for(title):
  m = {
    "Milkshake":   ["çilek","kavun","muz","karamel","mango","çikolata"],
    "Frappe":      ["black forest","strawberry","affagato","vanilan supreme"],
    "Soğuk Kahve": ["latte","caramel latte","mocha","white mocha"],
    "Frozen":      ["karpuz","kavun","mango","elma","orman meyvesi","kivi"],
    "Cool Lime":   ["çilek","nane","elma"],
    "Bubble Tea":  ["çilek","mango","çikolata","yaban mersini"],
  }
  return m.get(title, [])

# Eklenen kategoriler için tatları da yükle
c.execute("SELECT id, title FROM categories")
for cid, title in c.fetchall():
  for f in flavors_for(title):
    c.execute("INSERT INTO flavors(category_id, name) VALUES(?,?)", (cid, f))

conn.commit()
conn.close()
print("✅ Veritabanı hazır: cafe.db (mudur/1234, soğuk içecekler + tatlar + duyuru)")
