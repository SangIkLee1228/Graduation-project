import os

import psycopg
from fastapi import FastAPI

app = FastAPI(title="Talk to Book API")


@app.get("/health")
def health():
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as conn:
        conn.execute("SELECT 1")
    return {"status": "ok", "db": "ok"}
