import os

import psycopg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError

app = FastAPI(title="Talk to Book API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
    ).split(",") if origin.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/ready")
async def ready():
    services = {}
    try:
        async with await psycopg.AsyncConnection.connect(connect_timeout=3) as conn:
            await conn.execute("SELECT 1")
        services["postgres"] = "ok"
    except psycopg.Error:
        services["postgres"] = "unavailable"
    try:
        async with Redis.from_url(
            os.environ["REDIS_URL"], socket_connect_timeout=3, socket_timeout=3
        ) as client:
            await client.ping()
        services["redis"] = "ok"
    except RedisError:
        services["redis"] = "unavailable"
    healthy = all(value == "ok" for value in services.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "unavailable", "services": services},
    )
