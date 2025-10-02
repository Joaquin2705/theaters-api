FROM python:3.12-slim
WORKDIR /programas/api-sqlite
RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 && rm -rf /var/lib/apt/lists/*
RUN pip install flask
COPY app.py .
ENV DB_PATH=/mnt/theaters/theaters.db
ENV INIT_SCHEMA=1
EXPOSE 8001
CMD ["python", "./app.py"]
