# Untitled

## MV DB

```bash
sudo apt-get update
sudo apt-get install -y nfs-kernel-server
```

```bash
sudo mkdir -p /srv/theaters
sudo chown -R nobody:nogroup /srv/theaters
sudo chmod 777 /srv/theaters
echo '/srv/theaters 172.31.0.0/16(rw,sync,no_subtree_check)' | sudo tee /etc/exports
sudo exportfs -ra
sudo ss -lntp | grep 2049
```

## MV APP

```bash
sudo apt-get update
sudo apt-get install -y nfs-common

```

```bash
sudo mkdir -p /mnt/theaters

```

```bash
sudo mount -t nfs -o vers=4.2,proto=tcp 172.31.24.15:/srv/theaters /mnt/theaters
```

## MV  DB

```bash
cd ~
mkdir sqlite-docker
cd sqlite-docker
```

```bash
nano docker-compose.yml
```

```bash
# docker-compose.yml MV BD
version: '3'
services:
  sqlite3:
    image: nouchka/sqlite3:latest
    container_name: sqlite_db
    stdin_open: true
    tty: true
    volumes:
      - /srv/theaters:/mnt/theaters:rw  # Monta la carpeta local que compartes por NFS

```

```bash
docker compose up -d
```

```bash
docker exec -it sqlite_db sqlite3 /mnt/theaters/theaters.db
```

```sql
CREATE TABLE IF NOT EXISTS cinemas(
  id INTEGER PRIMARY KEY,
  nombre TEXT NOT NULL,
  ciudad TEXT,
  distrito TEXT,
  nro_salas INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS salas(
  id INTEGER PRIMARY KEY,
  cine_id INTEGER NOT NULL,
  numero INTEGER NOT NULL,
  capacidad INTEGER,
  tipo_sala TEXT,
  CONSTRAINT uq_sala_cine_numero UNIQUE(cine_id, numero)
);

.tables
```

## MV  App

```bash
ls -l /mnt/theaters/theaters.db 
```

Deberia aparecer algo como:

-rw-r--r-- 1 root root 16384 Oct  4 19:03 /mnt/theaters/theaters.db

```bash
mkdir -p ~/theaters-api
cd ~/theaters-api
```

```bash
nano ~/theaters-api/app.py
```

```bash
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

```

```bash
nano ~/theaters-api/Dockerfile
```

```bash
FROM python:3.12-slim
WORKDIR /programas/api-sqlite
RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 && rm -rf /var/lib/apt/lists/*
RUN pip install flask
COPY app.py .
ENV DB_PATH=/mnt/theaters/theaters.db
ENV INIT_SCHEMA=1
EXPOSE 8001
CMD ["python", "./app.py"]

```

```bash
nano ~/theaters-api/docker-compose.yml
```

```bash
services:
  api-sqlite:
    build: .
    container_name: api_sqlite
    restart: unless-stopped
    ports:
      - "8001:8001"
    environment:
      DB_PATH: "/mnt/theaters/theaters.db"
      INIT_SCHEMA: "1"
    volumes:
      - /mnt/theaters:/mnt/theaters:rw

```

## MV  DB

```bash
sudo chown -R 1000:1000 /srv/theaters 
sudo chmod -R 777 /srv/theaters  
```

## MV  App

```sql
sudo umount /mnt/theaters
sudo mount -t nfs -o vers=4.2,proto=tcp 172.31.24.15:/srv/theaters /mnt/theaters
```

```sql
docker compose up -d --build
```

Usamos ahora postman para agregar data usando la ip publica de la MV

![image.png](Untitled%2027f05b444ba2806c95acc2a8e00cacb3/image.png)

Luego habiendo ya agregado la data

```sql
docker exec -it api_sqlite sqlite3 /mnt/theaters/theaters.db
```

Verificamos que se haya agregado la data….

![image.png](Untitled%2027f05b444ba2806c95acc2a8e00cacb3/image%201.png)

## MV  DB

```sql
docker exec -it sqlite_db sqlite3 /mnt/theaters/theaters.db
```

![image.png](Untitled%2027f05b444ba2806c95acc2a8e00cacb3/image%202.png)
