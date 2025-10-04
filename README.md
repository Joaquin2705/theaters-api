🎬 API SQLite con NFS y Docker

Este proyecto muestra cómo montar un volumen compartido con NFS entre dos máquinas virtuales (MV DB y MV APP), correr SQLite en un contenedor y levantar una API Flask que interactúa con la base de datos.

📦 Requisitos

Dos máquinas virtuales:

MV DB (servidor NFS + contenedor SQLite)

MV APP (cliente NFS + contenedor API)

Docker y Docker Compose instalados.

NFS instalado (server en MV DB, client en MV APP).

Red privada entre ambas (ej. 172.31.0.0/16).

⚙️ MV DB — Servidor NFS
1) Instalar NFS Server
sudo apt-get update
sudo apt-get install -y nfs-kernel-server

2) Crear carpeta compartida
sudo mkdir -p /srv/theaters
sudo chown -R nobody:nogroup /srv/theaters
sudo chmod 777 /srv/theaters

3) Exportar vía NFS

Sustituye la red según tu caso (ej. 172.31.0.0/16).

echo '/srv/theaters 172.31.0.0/16(rw,sync,no_subtree_check)' | sudo tee /etc/exports
sudo exportfs -ra

4) Verificar NFS activo
sudo ss -lntp | grep 2049

🖥️ MV APP — Cliente NFS
1) Instalar NFS Client
sudo apt-get update
sudo apt-get install -y nfs-common

2) Crear punto de montaje
sudo mkdir -p /mnt/theaters

3) Montar el export del servidor

Cambia 172.31.24.15 por la IP de MV DB.

sudo mount -t nfs -o vers=4.2,proto=tcp 172.31.24.15:/srv/theaters /mnt/theaters

4) (Chequeo) Ver archivo de BD si ya existe
ls -l /mnt/theaters/theaters.db


Ejemplo de salida:

-rw-r--r-- 1 root root 16384 Oct  4 19:03 /mnt/theaters/theaters.db

🗄️ MV DB — Contenedor SQLite
1) Preparar carpeta de trabajo
cd ~
mkdir sqlite-docker
cd sqlite-docker

2) docker-compose.yml (SQLite)
version: '3'
services:
  sqlite3:
    image: nouchka/sqlite3:latest
    container_name: sqlite_db
    stdin_open: true
    tty: true
    volumes:
      - /srv/theaters:/mnt/theaters:rw

3) Levantar servicio
docker compose up -d

4) Crear/abrir la base de datos
docker exec -it sqlite_db sqlite3 /mnt/theaters/theaters.db

5) Esquema inicial
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

🧩 MV APP — API Flask
1) Directorio del proyecto
mkdir -p ~/theaters-api
cd ~/theaters-api

2) app.py
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
    try:
        yield conn
    finally:
        conn.close()

def rows_to_dicts(rows):
    return [dict(r) for r in rows]

def build_where(filt):
    if not filt:
        return "", []
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

if INIT_SCHEMA:
    init_schema()

class SQLiteAPI:
    def __init__(self, data):
        self._db_path = data.get("database", DB_PATH)
        self.table = data.get("table")
        self.data = data
        if not self.table:
            raise ValueError("Falta 'table'")

    def read(self):
        filt = self.data.get("Filter", {})
        where, params = build_where(filt)
        with sqlite3.connect(self._db_path, check_same_thread=False) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON;")
            return rows_to_dicts(conn.execute(f"SELECT * FROM {self.table}{where};", params))

    def write(self):
        doc = self.data.get("Document")
        if not isinstance(doc, dict) or not doc:
            raise ValueError("Falta 'Document'")
        cols = ",".join(doc.keys())
        vals = list(doc.values())
        qs = ",".join(["?"] * len(vals))
        with sqlite3.connect(self._db_path, check_same_thread=False) as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            cur = conn.execute(f"INSERT INTO {self.table} ({cols}) VALUES ({qs});", vals)
            conn.commit()
            return {"Status": "Successfully Inserted", "rowid": cur.lastrowid}

    def update(self):
        filt = self.data.get("Filter")
        updates = self.data.get("DataToBeUpdate")
        if not isinstance(filt, dict) or not filt:
            raise ValueError("Falta 'Filter'")
        if not isinstance(updates, dict) or not updates:
            raise ValueError("Falta 'DataToBeUpdate'")
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        set_vals = list(updates.values())
        where, where_vals = build_where(filt)
        with sqlite3.connect(self._db_path, check_same_thread=False) as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            cur = conn.execute(f"UPDATE {self.table} SET {set_clause}{where};", set_vals + where_vals)
            conn.commit()
            return {"Status": "Successfully Updated" if cur.rowcount else "No Rows Updated"}

    def delete(self):
        filt = self.data.get("Filter")
        if not isinstance(filt, dict) or not filt:
            raise ValueError("Falta 'Filter'")
        where, params = build_where(filt)
        with sqlite3.connect(self._db_path, check_same_thread=False) as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            cur = conn.execute(f"DELETE FROM {self.table}{where};", params)
            conn.commit()
            return {"Status": "Successfully Deleted" if cur.rowcount else "No Rows Deleted"}

@app.route("/")
def base():
    return jsonify({"Status": "UP", "db_path": DB_PATH})

@app.route("/sqlite", methods=["GET","POST","PUT","DELETE"])
def sqlite_router():
    data = request.get_json(silent=True) or {}
    try:
        api = SQLiteAPI(data)
        if request.method == "GET":
            return jsonify(api.read())
        if request.method == "POST":
            return jsonify(api.write())
        if request.method == "PUT":
            return jsonify(api.update())
        if request.method == "DELETE":
            return jsonify(api.delete())
    except Exception as e:
        return jsonify({"Error": str(e)}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=False)

3) Dockerfile (API)
FROM python:3.12-slim
WORKDIR /programas/api-sqlite
RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 && rm -rf /var/lib/apt/lists/*
RUN pip install flask
COPY app.py .
ENV DB_PATH=/mnt/theaters/theaters.db
ENV INIT_SCHEMA=1
EXPOSE 8001
CMD ["python", "./app.py"]

4) docker-compose.yml (API)
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

5) Levantar la API
docker compose up -d --build

🧪 Probar la API
POST (crear registro)
POST http://<IP_PUBLICA_O_PRIVADA>:8001/sqlite
Content-Type: application/json


Body:

{
  "table": "cinemas",
  "Document": {
    "nombre": "Cine Plaza Norte",
    "ciudad": "Lima",
    "distrito": "Independencia"
  }
}


Respuesta esperada:

{
  "Status": "Successfully Inserted",
  "rowid": 1
}

GET (listar)
GET http://<IP_PUBLICA_O_PRIVADA>:8001/sqlite
Content-Type: application/json


Body:

{
  "table": "cinemas",
  "Filter": {}
}

🔍 Verificar datos directamente en SQLite
docker exec -it api_sqlite sqlite3 /mnt/theaters/theaters.db

.tables
SELECT * FROM cinemas;


Salida esperada:

1|Cine Plaza Norte|Lima|Independencia|0

🛠️ Troubleshooting (errores comunes)
Error: "attempt to write a readonly database"

Asegúrate de montar NFS en el host y hacer bind-mount al contenedor (como arriba).

Verifica permisos en MV DB:

sudo chown -R nobody:nogroup /srv/theaters
sudo chmod -R 777 /srv/theaters


En MV APP, revisa que el montaje sea rw:

mount | grep /mnt/theaters
# Si aparece ro -> remonta:
sudo mount -o remount,rw /mnt/theaters


Ejecuta contenedores como un usuario no root consistente (opcional):

user: "1000:1000"

Cache de atributos NFS (cambios que “no se ven”)

Usa opciones con menos caché al montar (ej. actimeo=1):

sudo mount -o remount,vers=4.2,proto=tcp,actimeo=1 /mnt/theaters

📤 Publicar tu código en GitHub
git init
git add .
git commit -m "API SQLite con NFS y Docker"
git branch -M main
git remote add origin git@github.com:<tu_usuario>/<tu_repo>.git
git push -u origin main

🐳 (Opcional) Publicar imagen en un registro
Docker Hub
docker login
docker build -t <tu_usuario>/theaters-api:latest .
docker push <tu_usuario>/theaters-api:latest

GitHub Container Registry (GHCR)
docker login ghcr.io -u <tu_usuario>
docker build -t ghcr.io/<tu_usuario>/theaters-api:latest .
docker push ghcr.io/<tu_usuario>/theaters-api:latest

✅ Checklist rápido

 MV DB: NFS server exportando /srv/theaters

 MV APP: NFS client montando en /mnt/theaters

 Contenedor SQLite usando /srv/theaters ↔ /mnt/theaters

 API Flask (Dockerfile + compose) montando /mnt/theaters

 Probar POST/GET en http://<ip>:8001/sqlite

 Verificar datos en sqlite3 /mnt/theaters/theaters.db
