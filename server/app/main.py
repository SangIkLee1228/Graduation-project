import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError

from .catalog import Catalog, SemanticIDRanker
from .chat import ChatService
from .chat_llm import LLMNotConfigured, LLMUnavailable, LuxiaChat
from .chat_models import ChatRequest, ChatResponse
from .chat_store import ConversationConflict, ConversationExpired, RedisConversations

DEFAULT_CATALOG = Path(__file__).resolve().parents[2] / "frontend/public/data/hotels.json"


@asynccontextmanager
async def lifespan(app: FastAPI):
    catalog = Catalog.load(Path(os.environ.get("HOTEL_CATALOG_PATH", DEFAULT_CATALOG)))
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    async with (
        httpx.AsyncClient(timeout=httpx.Timeout(12, connect=3)) as http,
        Redis.from_url(redis_url, socket_connect_timeout=3, socket_timeout=3) as redis,
    ):
        app.state.chat = ChatService(
            catalog, SemanticIDRanker(), LuxiaChat(http, os.getenv("LUXIA_API_KEY", "").strip()),
            RedisConversations(redis),
        )
        app.state.redis = redis
        yield


app = FastAPI(title="Talk to Book API", version="0.2.0", lifespan=lifespan)
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
async def ready(request: Request):
    services = {}
    try:
        async with await psycopg.AsyncConnection.connect(connect_timeout=3) as conn:
            await conn.execute("SELECT 1")
        services["postgres"] = "ok"
    except psycopg.Error:
        services["postgres"] = "unavailable"
    try:
        await request.app.state.redis.ping()
        services["redis"] = "ok"
    except RedisError:
        services["redis"] = "unavailable"
    healthy = all(value == "ok" for value in services.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "unavailable", "services": services},
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request):
    try:
        return await request.app.state.chat.turn(body)
    except ConversationExpired:
        raise HTTPException(404, "conversation_expired") from None
    except ConversationConflict:
        raise HTTPException(409, "conversation_conflict") from None
    except LLMNotConfigured:
        raise HTTPException(503, "llm_not_configured") from None
    except LLMUnavailable:
        raise HTTPException(502, "llm_unavailable") from None
    except RedisError:
        raise HTTPException(503, "conversation_store_unavailable") from None
