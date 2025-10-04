# 🎬 API SQLite con NFS y Docker

Este proyecto demuestra cómo montar un volumen compartido mediante **NFS** entre dos máquinas virtuales (MV DB y MV APP), ejecutar SQLite en un contenedor y exponer una **API Flask** para consultar e insertar datos.

---

## 📦 Requisitos

- Dos máquinas virtuales (MV DB y MV APP).
- Docker y Docker Compose instalados.
- NFS instalado y configurado.

---

## ⚙️ Configuración

### 🔹 MV DB (Servidor NFS)

Instalar NFS:

```bash
sudo apt-get update
sudo apt-get install -y nfs-kernel-server
Configurar carpeta compartida:

bash
Copiar código
sudo mkdir -p /srv/theaters
sudo chown -R nobody:nogroup /srv/theaters
sudo chmod 777 /srv/theaters
echo '/srv/theaters 172.31.0.0/16(rw,sync,no_subtree_check)' | sudo tee /etc/exports
sudo exportfs -ra
sudo ss -lntp | grep 2049
🔹 MV APP (Cliente NFS)
Instalar cliente NFS:

bash
Copiar código
sudo apt-get update
sudo apt-get install -y nfs-common
Montar volumen:

bash
Copiar código
sudo mkdir -p /mnt/theaters
sudo mount -t nfs -o vers=4.2,proto=tcp 172.31.24.15:/srv/theaters /mnt/theaters
🗄️ MV DB (Contenedor SQLite)
Crear directorio:

bash
Copiar código
cd ~
mkdir sqlite-docker
cd sqlite-docker
Crear docker-compose.yml:

yaml
Copiar código
version: '3'
services:
  sqlite3:
    image: nouchka/sqlite3:latest
    container_name: sqlite_db
    stdin_open: true
    tty: true
    volumes:
      - /srv/theaters:/mnt/theaters:rw
Levantar servicio:

bash
Copiar código
docker compose up -d
Entrar al contenedor y crear la base de datos:

bash
Copiar código
docker exec -it sqlite_db sqlite3 /mnt/theaters/theaters.db
Crear tablas iniciales:

sql
Copiar código
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
🖥️ MV APP (API Flask)
Crear directorio:

bash
Copiar código
mkdir -p ~/theaters-api
cd ~/theaters-api
Archivo app.py:

python
Copiar código
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
            id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, 
            ciudad TEXT, distrito TEXT, nro_salas INTEGER DEFAULT 0);""")
        c.execute("""CREATE TABLE IF NOT EXISTS salas(
            id INTEGER PRIMARY KEY, cine_id INTEGER NOT NULL, 
            numero INTEGER NOT NULL, capacidad INTEGER, tipo_sala TEXT,
            CONSTRAINT uq_sala_cine_numero UNIQUE(cine_id,numero),
            FOREIGN KEY(cine_id) REFERENCES cinemas(id) ON DELETE CASCADE);""")
        conn.commit()

if INIT_SCHEMA: init_schema()

class SQLiteAPI:
    def __init__(self, data):
        self._db_path = data.get("database", DB_PATH)
        self.table = data.get("table")
        self.data = data
        if not self.table: raise ValueError("Falta 'table'")

    def read(self):
        filt = self.data.get("Filter", {})
        where, params = build_where(filt)
        with sqlite3.connect(self._db_path, check_same_thread=False) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON;")
            return rows_to_dicts(conn.execute(f"SELECT * FROM {self.table}{where};", params))

    def write(self):
        doc = self.data.get("Document")
        if not isinstance(doc, dict) or not doc: raise ValueError("Falta 'Document'")
        cols = ",".join(doc.keys()); vals = list(doc.values())
        qs = ",".join(["?"] * len(vals))
        with sqlite3.connect(self._db_path, check_same_thread=False) as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            cur = conn.execute(f"INSERT INTO {self.table} ({cols}) VALUES ({qs});", vals)
            conn.commit(); return {"Status": "Successfully Inserted", "rowid": cur.lastrowid}

    def update(self):
        filt = self.data.get("Filter"); updates = self.data.get("DataToBeUpdate")
        if not isinstance(filt, dict) or not filt: raise ValueError("Falta 'Filter'")
        if not isinstance(updates, dict) or not updates: raise ValueError("Falta 'DataToBeUpdate'")
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        set_vals = list(updates.values())
        where, where_vals = build_where(filt)
        with sqlite3.connect(self._db_path, check_same_thread=False) as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            cur = conn.execute(f"UPDATE {self.table} SET {set_clause}{where};", set_vals + where_vals)
            conn.commit(); return {"Status": "Successfully Updated" if cur.rowcount else "No Rows Updated"}

    def delete(self):
        filt = self.data.get("Filter")
        if not isinstance(filt, dict) or not filt: raise ValueError("Falta 'Filter'")
        where, params = build_where(filt)
        with sqlite3.connect(self._db_path, check_same_thread=False) as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            cur = conn.execute(f"DELETE FROM {self.table}{where};", params)
            conn.commit(); return {"Status": "Successfully Deleted" if cur.rowcount else "No Rows Deleted"}

@app.route("/")
def base(): return jsonify({"Status": "UP", "db_path": DB_PATH})

@app.route("/sqlite", methods=["GET","POST","PUT","DELETE"])
def sqlite_router():
    data = request.get_json(silent=True) or {}
    try:
        api = SQLiteAPI(data)
        if request.method == "GET": return jsonify(api.read())
        if request.method == "POST": return jsonify(api.write())
        if request.method == "PUT": return jsonify(api.update())
        if request.method == "DELETE": return jsonify(api.delete())
    except Exception as e:
        return jsonify({"Error": str(e)}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=False)
📜 Dockerfile de la API
dockerfile
Copiar código
FROM python:3.12-slim
WORKDIR /programas/api-sqlite
RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 && rm -rf /var/lib/apt/lists/*
RUN pip install flask
COPY app.py .
ENV DB_PATH=/mnt/theaters/theaters.db
ENV INIT_SCHEMA=1
EXPOSE 8001
CMD ["python", "./app.py"]
📜 docker-compose.yml de la API
yaml
Copiar código
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
Levantar servicio:

bash
Copiar código
docker compose up -d --build
🧪 Probar con Postman
Ejemplo POST:

css
Copiar código
POST http://<IP_PUBLICA>:8001/sqlite

{
  "table": "cinemas",
  "Document": {
    "nombre": "Cine Plaza Norte",
    "ciudad": "Lima",
    "distrito": "Independencia"
  }
}
Respuesta:

json
Copiar código
{
  "Status": "Successfully Inserted",
  "rowid": 1
}
🔍 Verificación de datos en SQLite
bash
Copiar código
docker exec -it api_sqlite sqlite3 /mnt/theaters/theaters.db
sql
Copiar código
.tables
SELECT * FROM cinemas;
Resultado esperado:

Copiar código
1|Cine Plaza Norte|Lima|Independencia|0
