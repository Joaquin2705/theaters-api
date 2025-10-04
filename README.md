# 🎬 API SQLite con NFS y Docker

Este proyecto muestra cómo montar un volumen compartido con **NFS** entre dos máquinas virtuales (MV DB y MV APP), ejecutar **SQLite** en un contenedor y levantar una **API Flask** que interactúa con la base de datos.

---

## 📦 Requisitos

- Dos máquinas virtuales:
    - **MV DB** (servidor NFS + contenedor SQLite)
    - **MV APP** (cliente NFS + contenedor API)
- Docker y Docker Compose instalados.
- NFS instalado.
- Red privada (ej. `172.31.0.0/16`).
- Para montar necesitamos si o si la IP PRIVADA DE BD

---

## ⚙️ MV DB — Servidor NFS

### Instalar NFS Server

```bash
sudo apt-get update
sudo apt-get install -y nfs-kernel-server

```

### Crear carpeta compartida

```bash
sudo mkdir -p /srv/theaters
sudo chown -R nobody:nogroup /srv/theaters
sudo chmod 777 /srv/theaters

```

### Exportar vía NFS

```bash
echo '/srv/theaters 172.31.0.0/16(rw,sync,no_subtree_check)' | sudo tee /etc/exports
sudo exportfs -ra

```

### Verificar servicio

```bash
sudo ss -lntp | grep 2049

```

---

## 🖥️ MV APP — Cliente NFS

### Instalar cliente NFS

```bash
sudo apt-get update
sudo apt-get install -y nfs-common

```

### Crear punto de montaje

```bash
sudo mkdir -p /mnt/theaters

```

### Montar carpeta NFS

```bash
sudo mount -t nfs -o vers=4.2,proto=tcp 172.31.24.15:/srv/theaters /mnt/theaters

```

### Verificar archivo

```bash
ls -l /mnt/theaters/theaters.db

```

Ejemplo:

```
-rw-r--r-- 1 root root 16384 Oct  4 19:03 /mnt/theaters/theaters.db

```

---

## 🗄️ MV DB — Contenedor SQLite

### Crear directorio

```bash
cd ~
mkdir sqlite-docker
cd sqlite-docker

```

### docker-compose.yml

```yaml
version: '3'
services:
  sqlite3:
    image: nouchka/sqlite3:latest
    container_name: sqlite_db
    stdin_open: true
    tty: true
    volumes:
      - /srv/theaters:/mnt/theaters:rw

```

### Levantar contenedor

```bash
docker compose up -d

```

### Acceder a SQLite

```bash
docker exec -it sqlite_db sqlite3 /mnt/theaters/theaters.db

```

### Crear tablas

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

---

### Cambiar los permisos

```sql
sudo chown -R 1000:1000 /srv/theaters 
sudo chmod -R 777 /srv/theaters  
```

## 🖥️ MV APP — API Flask

### Clonar el repositorio

```bash

git clone https://github.com/Joaquin2705/theaters-api.git 

```

### Desmontar

```sql
sudo umount /mnt/theaters
sudo mount -t nfs -o vers=4.2,proto=tcp 172.31.24.15:/srv/theaters /mnt/theaters
```

### Levantar la API

```bash
docker compose up -d --build

```

Esto construirá la imagen de la API usando el `Dockerfile` incluido en el repo y montará la base de datos SQLite compartida vía NFS.

---

## 🧪 Pruebas con Postman

### POST

```
POST http://<IP_PUBLICA>:8001/sqlite
Content-Type: application/json

```

Body:

```json
{
  "table": "cinemas",
  "Document": {
    "nombre": "Cine Plaza Norte",
    "ciudad": "Lima",
    "distrito": "Independencia"
  }
}

```

Respuesta:

```json
{
  "Status": "Successfully Inserted",
  "rowid": 1
}

```

---

## 🔍 Verificar datos en SQLite

```bash
docker exec -it api_sqlite sqlite3 /mnt/theaters/theaters.db

```

```sql
.tables
SELECT * FROM cinemas;

```

Salida esperada:

```
1|Cine Plaza Norte|Lima|Independencia|0

```
