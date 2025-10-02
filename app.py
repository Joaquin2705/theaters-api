import os, sqlite3
from flask import Flask, request, jsonify
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "/mnt/theaters/theaters.db")
INIT_SCHEMA = bool(int(os.getenv("INIT_SCHEMA", "1")))

app = Flask(__name__)

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    try: yield conn
    finally: conn.close()

def rows_to_dicts(rows): return [dict(r) for r in rows]

def build_where(filt):
    if not filt: return "", []
    keys = list(filt.keys())
    return " WHERE " + " AND ".join([f"{k} = ?" for k in keys]), [filt[k] for k in keys]

def init_schema():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS cinemas(
            id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, ciudad TEXT, distrito TEXT, nro_salas INTEGER DEFAULT 0);""")
        c.execute("""CREATE TABLE IF NOT EXISTS salas(
            id INTEGER PRIMARY KEY, cine_id INTEGER NOT NULL, numero INTEGER NOT NULL,
            capacidad INTEGER, tipo_sala TEXT,
            CONSTRAINT uq_sala_cine_numero UNIQUE(cine_id,numero),
            FOREIGN KEY(cine_id) REFERENCES cinemas(id) ON DELETE CASCADE);""")
        conn.commit()

if INIT_SCHEMA: init_schema()

class SQLiteAPI:
    def __init__(self, data):
        self.db_path = data.get("database", DB_PATH)
        self.table = data.get("table")
        self.data = data
        if not self.table: raise ValueError("Falta 'table'")

    def read(self):
        filt = self.data.get("Filter", {})
        where, params = build_where(filt)
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.row_factory = sqlite3.Row; conn.execute("PRAGMA foreign_keys=ON;")
            return rows_to_dicts(conn.execute(f"SELECT * FROM {self.table}{where};", params).fetchall())

    def write(self):
        doc = self.data.get("Document")
        if not isinstance(doc, dict) or not doc: raise ValueError("Falta 'Document'")
        cols = ", ".join(doc.keys()); vals = list(doc.values())
        qs = ", ".join(["?"] * len(vals))
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            cur = conn.execute(f"INSERT INTO {self.table} ({cols}) VALUES ({qs});", vals)
            conn.commit(); return {"Status": "Successfully Inserted", "rowid": cur.lastrowid}

    def update(self):
        filt = self.data.get("Filter"); updates = self.data.get("DataToBeUpdated")
        if not isinstance(filt, dict) or not filt: raise ValueError("Falta 'Filter'")
        if not isinstance(updates, dict) or not updates: raise ValueError("Falta 'DataToBeUpdated'")
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        set_vals = list(updates.values())
        where, where_vals = build_where(filt)
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            cur = conn.execute(f"UPDATE {self.table} SET {set_clause}{where};", set_vals + where_vals)
            conn.commit(); return {"Status": "Successfully Updated" if cur.rowcount else "Nothing was updated."}

    def delete(self):
        filt = self.data.get("Filter")
        if not isinstance(filt, dict) or not filt: raise ValueError("Falta 'Filter'")
        where, params = build_where(filt)
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            cur = conn.execute(f"DELETE FROM {self.table}{where};", params)
            conn.commit(); return {"Status": "Successfully Deleted" if cur.rowcount else "Document not found."}

@app.route("/")
def base(): return jsonify({"Status":"UP","db_path":DB_PATH})

@app.route("/sqlite", methods=["GET","POST","PUT","DELETE"])
def sqlite_router():
    data = request.get_json(silent=True) or {}
    try:
        api = SQLiteAPI(data)
        if request.method == "GET":    return jsonify(api.read())
        if request.method == "POST":   return jsonify(api.write())
        if request.method == "PUT":    return jsonify(api.update())
        if request.method == "DELETE": return jsonify(api.delete())
    except Exception as e:
        return jsonify({"Error": str(e)}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=False)
