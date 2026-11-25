import asyncio
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx
from redis.asyncio import Redis

from server.app.catalog import Candidate, Catalog, Hotel, SemanticIDRanker
from server.app.chat import ChatService
from server.app.chat_llm import LLMUnavailable, LuxiaChat, Reason, Reasons
from server.app.chat_models import Preference, PreferenceEdit
from server.app.chat_store import RedisConversations
from server.app.main import app

TEST_REDIS = os.getenv("TEST_REDIS_URL")
CATALOG_PATH = Path(__file__).resolve().parents[2] / "frontend/public/data/hotels.json"


def hotel(id_, profile, sid):
    return Hotel(
        id=str(id_), name=f"Hotel {id_}", url=f"Hotel_Review-{id_}.html",
        profile=profile, rating=4.0, sid=sid,
    )


def preference(label, mode, term, category="amenity"):
    return Preference(label=label, mode=mode, terms=[term], category=category)


PARK = preference("하이드파크", "required", "Hyde Park", "location")
QUIET = preference("조용한 분위기", "preferred", "quiet", "atmosphere")
POOL = preference("수영장 제외", "excluded", "swimming pool")
FIXTURE_CATALOG = Catalog([
    hotel(1, "Quiet rooms beside Hyde Park. There is a swimming pool.", (1, 2, 3, 0)),
    hotel(2, "Near Hyde Park with quiet family rooms. There is no swimming pool.", (1, 2, 3, 1)),
    hotel(3, "Quiet hotel far from Hyde Park.", (9, 2, 3, 0)),
])


class CatalogTests(unittest.TestCase):
    def test_catalog_and_booking_links(self):
        catalog = Catalog.load(CATALOG_PATH)
        self.assertEqual(len(catalog.hotels), 1619)
        self.assertTrue(catalog.search([PARK, QUIET]))
        self.assertEqual(
            {link.platform for link in next(iter(catalog.hotels.values())).booking_links()},
            {"tripadvisor", "booking", "google_maps"},
        )
        with self.assertRaises(ValueError):
            Catalog([hotel(1, "A", (1, 2, 3, 0)), hotel(2, "B", (1, 2, 3, 0))])

    def test_required_excluded_and_negative_evidence(self):
        self.assertEqual([c.hotel_id for c in FIXTURE_CATALOG.search([PARK, QUIET, POOL])], ["2"])
        self.assertEqual(
            [c.hotel_id for c in FIXTURE_CATALOG.search([PARK, preference("수영장", "required", "swimming pool")])],
            ["1"],
        )

    def test_semantic_id_changes_order(self):
        candidates = [
            Candidate("1", (1, 2, 3, 0), 10, {}),
            Candidate("2", (2, 0, 0, 0), 9.8, {}),
            Candidate("3", (1, 2, 3, 1), 9.0, {}),
        ]
        self.assertEqual([c.hotel_id for c in SemanticIDRanker().rank(candidates)], ["1", "3", "2"])


class LuxiaTests(unittest.IsolatedAsyncioTestCase):
    async def test_parse_validate_and_timeout(self):
        def respond(request):
            self.assertEqual(request.headers["apikey"], "test-key")
            body = json.loads(request.content)
            message = json.loads(body["messages"][1]["content"])["message"]
            if message == "timeout":
                raise httpx.ReadTimeout("timeout")
            content = "not JSON" if message == "invalid" else (
                "```json\n" + PreferenceEdit(add=[PARK]).model_dump_json() + "\n```"
            )
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            llm = LuxiaChat(http, "test-key")
            self.assertEqual((await llm.interpret("valid", [], [])).add, [PARK])
            for message in ("invalid", "timeout"):
                with self.assertRaises(LLMUnavailable):
                    await llm.interpret(message, [], [])


class FakeLLM:
    def __init__(self):
        self.interpreted = 0
        self.fallback_reasons = False
        self.release = asyncio.Event()
        self.concurrent = 0

    async def interpret(self, message, preferences, history):
        self.interpreted += 1
        if message == "해석 실패":
            raise LLMUnavailable
        if message.startswith("동시"):
            self.concurrent += 1
            if self.concurrent == 2:
                self.release.set()
            await asyncio.wait_for(self.release.wait(), timeout=5)
        return {
            "처음": PreferenceEdit(add=[PARK, QUIET]),
            "수영장 빼줘": PreferenceEdit(add=[POOL]),
            "조용할 필요 없어": PreferenceEdit(remove_labels=[QUIET.label]),
            "처음부터": PreferenceEdit(reset=True),
            "결과 없음": PreferenceEdit(add=[preference("헬리패드", "required", "helipad")]),
            "가격": PreferenceEdit(unsupported=["price"]),
        }.get(message, PreferenceEdit())

    async def explain(self, hotels):
        if self.fallback_reasons:
            raise LLMUnavailable
        return Reasons(reasons=[
            Reason(hotel_id=hotel["hotel_id"], evidence=next(iter(hotel["matching_evidence"].values())),
                   reason="호텔 프로파일에 하이드파크 인근이라고 소개돼 있어요.")
            for hotel in hotels
        ])


@unittest.skipUnless(TEST_REDIS, "Set TEST_REDIS_URL to run Redis/API integration tests")
class ChatIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = Redis.from_url(TEST_REDIS)
        self.addAsyncCleanup(self.redis.aclose)
        await self.redis.ping()
        self.llm = FakeLLM()
        self.store = RedisConversations(self.redis)
        self.addAsyncCleanup(self.cleanup_conversations)
        self.conversations = set()
        self.original_chat = getattr(app.state, "chat", None)
        app.state.chat = ChatService(FIXTURE_CATALOG, SemanticIDRanker(), self.llm, self.store)
        self.addCleanup(setattr, app.state, "chat", self.original_chat)
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        self.addAsyncCleanup(self.http.aclose)

    async def cleanup_conversations(self):
        for id_ in self.conversations:
            keys = [key async for key in self.redis.scan_iter(f"talk-to-book:chat:{{{id_}}}*")]
            if keys:
                await self.redis.delete(*keys)

    async def post(self, message, conversation_id=None, request_id=None):
        request_id = request_id or str(uuid4())
        self.conversations.add(conversation_id or request_id)
        return await self.http.post("/api/chat", json={
            "message": message, "request_id": request_id, "conversation_id": conversation_id,
        })

    async def test_multiturn_reset_isolation_and_replay(self):
        first_id = str(uuid4())
        initial = await self.post("처음", request_id=first_id)
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()["status"], "recommendations")
        self.assertEqual(initial.json(), (await self.post("처음", request_id=first_id)).json())
        self.assertEqual(self.llm.interpreted, 1)
        self.assertEqual((await self.post("다른 입력", request_id=first_id)).status_code, 409)

        filtered = (await self.post("수영장 빼줘", first_id)).json()
        self.assertEqual([h["id"] for h in filtered["recommendations"]], ["2"])
        self.assertEqual({p["label"] for p in filtered["preferences"]}, {PARK.label, QUIET.label, POOL.label})
        removed = (await self.post("조용할 필요 없어", first_id)).json()
        self.assertEqual({p["label"] for p in removed["preferences"]}, {PARK.label, POOL.label})
        separate = (await self.post("가격")).json()
        self.assertEqual(separate["status"], "clarification")
        self.assertIn("실시간 요금", separate["reply"])
        self.assertEqual(separate["preferences"], [])
        reset = (await self.post("처음부터", first_id)).json()
        self.assertEqual(reset["preferences"], [])
        self.assertEqual(reset["recommendations"], [])

    async def test_failure_no_results_and_expiration(self):
        first_id = str(uuid4())
        await self.post("처음", request_id=first_id)
        state_key = f"talk-to-book:chat:{{{first_id}}}"
        saved = await self.redis.get(state_key)
        self.assertEqual((await self.post("해석 실패", first_id)).status_code, 502)
        self.assertEqual(saved, await self.redis.get(state_key))

        self.llm.fallback_reasons = True
        result = (await self.post("수영장 빼줘", first_id)).json()
        self.assertIn("Near Hyde Park", result["recommendations"][0]["reason"])
        empty = (await self.post("결과 없음", first_id)).json()
        self.assertEqual(empty["status"], "no_matches")
        self.assertEqual(empty["recommendations"], [])
        await self.redis.expire(state_key, 0)
        self.assertEqual((await self.post("수영장 빼줘", first_id)).json()["detail"], "conversation_expired")

    async def test_conflicting_turns_and_history_limit(self):
        first_id = str(uuid4())
        await self.post("처음", request_id=first_id)
        requests = await asyncio.gather(self.post("동시 1", first_id), self.post("동시 2", first_id))
        self.assertEqual(sorted(response.status_code for response in requests), [200, 409])
        for _ in range(7):
            self.assertEqual((await self.post("유지", first_id)).status_code, 200)
        state_key = f"talk-to-book:chat:{{{first_id}}}"
        self.assertEqual(len(json.loads(await self.redis.get(state_key))["history"]), 12)
        self.assertGreater(await self.redis.ttl(state_key), 86000)
        self.assertEqual(len((await self.store.load(
            UUID(first_id), self._new_request(first_id)
        )).history), 12)

    @staticmethod
    def _new_request(conversation_id):
        from server.app.chat_models import ChatRequest
        return ChatRequest(message="유지", request_id=uuid4(), conversation_id=conversation_id)

    async def test_missing_key_without_mutating_state(self):
        first_id = str(uuid4())
        async with httpx.AsyncClient() as http:
            with patch.object(app.state.chat, "llm", LuxiaChat(http, "")):
                response = await self.post("처음", request_id=first_id)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "llm_not_configured")
        self.assertIsNone(await self.redis.get(f"talk-to-book:chat:{{{first_id}}}"))
