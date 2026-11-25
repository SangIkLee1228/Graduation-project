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
from server.app.chat_models import Conversation, HotelReference, Preference, PreferenceEdit, RecommendationList
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
FAMILY = preference("가족용", "preferred", "family rooms", "traveler")
AIRPORT = preference("시티 공항", "required", "London City Airport", "location")
FIXTURE_CATALOG = Catalog([
    hotel(1, "Quiet rooms beside Hyde Park. There is a swimming pool.", (1, 2, 3, 0)),
    hotel(2, "Near Hyde Park with quiet family rooms. There is no swimming pool.", (1, 2, 3, 1)),
    hotel(3, "Quiet hotel far from Hyde Park.", (9, 2, 3, 0)),
    hotel(4, "Near London City Airport.", (9, 2, 3, 1)),
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
            payload = json.loads(body["messages"][1]["content"])
            message = payload["message"]
            if message == "timeout":
                raise httpx.ReadTimeout("timeout")
            self.assertEqual(payload["recommendation_lists"], [
                {"number": 1, "hotels": [
                    {"rank": 1, "hotel_id": "1", "name": "Hotel 1", "reason": "Near Hyde Park"},
                ]},
            ])
            content = "not JSON" if message == "invalid" else (
                "```json\n" + PreferenceEdit(add=[PARK]).model_dump_json() + "\n```"
            )
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            llm = LuxiaChat(http, "test-key")
            conversation = Conversation(recommendation_lists=[
                RecommendationList(number=1, hotels=[
                    HotelReference(id="1", name="Hotel 1", reason="Near Hyde Park"),
                ]),
            ])
            self.assertEqual((await llm.interpret("valid", conversation)).add, [PARK])
            for message in ("invalid", "timeout"):
                with self.assertRaises(LLMUnavailable):
                    await llm.interpret(message, conversation)


class FakeLLM:
    def __init__(self):
        self.interpreted = 0
        self.fallback_reasons = False
        self.release = asyncio.Event()
        self.concurrent = 0

    async def interpret(self, message, conversation):
        self.interpreted += 1
        if message == "해석 실패":
            raise LLMUnavailable
        if message.startswith("동시"):
            self.concurrent += 1
            if self.concurrent == 2:
                self.release.set()
            await asyncio.wait_for(self.release.wait(), timeout=5)
        shown = conversation.shown_recommendations
        if message == "이전 조건은 모두 지우고 처음부터 시작하자":
            if conversation.preferences or conversation.excluded_hotel_ids or shown or conversation.history:
                raise AssertionError("The language model received discarded conversation context")
            return PreferenceEdit(clarification="새 조건을 알려 주세요.")
        if message == "첫 번째 호텔 빼줘":
            if shown:
                return PreferenceEdit(exclude_hotel_ids=[shown[-1].hotels[0].id])
            return PreferenceEdit()
        if message in ("아까 추천한 첫 번째 호텔 빼줘", "그 호텔은 빼줘"):
            return PreferenceEdit(exclude_hotel_ids=[shown[-1].hotels[0].id])
        if message == "처음 추천한 첫 번째 호텔 빼줘":
            return PreferenceEdit(
                exclude_hotel_ids=[shown[0].hotels[0].id], remove_labels=[QUIET.label],
                condition_change_quote="빼줘",
            )
        if message == "첫 번째 호텔 말고 가족용으로":
            return PreferenceEdit(
                exclude_hotel_ids=[shown[-1].hotels[0].id],
                add=[FAMILY], condition_change_quote="가족용으로",
            )
        if message == "조용한 조건은 빼고 그 대신 가족용으로 추천해줘":
            return PreferenceEdit(
                remove_labels=[QUIET.label], add=[FAMILY],
                exclude_hotel_ids=[shown[-1].hotels[0].id],
            )
        return {
            "처음": PreferenceEdit(add=[PARK, QUIET]),
            "수영장 빼줘": PreferenceEdit(add=[POOL]),
            "조용할 필요 없어": PreferenceEdit(remove_labels=[QUIET.label]),
            "시티 공항 근처로 바꿔줘": PreferenceEdit(remove_labels=[PARK.label], add=[AIRPORT]),
            "처음부터": PreferenceEdit(reset=True),
            "결과 없음": PreferenceEdit(add=[preference("헬리패드", "required", "helipad")]),
            "가격": PreferenceEdit(unsupported=["price"]),
            "그 조건": PreferenceEdit(remove_labels=[QUIET.label], clarification="어떤 조건을 빼 드릴까요?"),
            "아까 추천에 없는 호텔은 빼줘": PreferenceEdit(exclude_hotel_ids=["999"], remove_labels=[PARK.label]),
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

    async def test_hotel_reference_and_ambiguous_edits(self):
        first_id = str(uuid4())
        initial = (await self.post("처음", request_id=first_id)).json()
        original_preferences = initial["preferences"]
        first_hotel = initial["recommendations"][0]
        for message in ("그거 말고 이렇게 해줘", "그 조건", "아까 추천에 없는 호텔은 빼줘"):
            result = (await self.post(message, first_id)).json()
            self.assertEqual(result["status"], "clarification")
            self.assertEqual(result["preferences"], original_preferences)
            self.assertEqual(result["recommendations"], [])

        result = (await self.post("첫 번째 호텔 빼줘", first_id)).json()
        self.assertEqual(result["status"], "recommendations")
        self.assertIn({"label": f"호텔 · {first_hotel['name']}", "mode": "excluded"}, result["preferences"])
        for reply in (result, (await self.post("유지", first_id)).json()):
            self.assertNotIn(first_hotel["id"], [hotel["id"] for hotel in reply["recommendations"]])
        edited = (await self.post("조용한 조건은 빼고 그 대신 가족용으로 추천해줘", first_id)).json()
        self.assertEqual(edited["status"], "recommendations")
        self.assertEqual({p["label"] for p in edited["preferences"]}, {
            PARK.label, FAMILY.label, f"호텔 · {first_hotel['name']}",
        })
        self.assertEqual(
            [hotel["id"] for hotel in edited["recommendations"]],
            [hotel["id"] for hotel in result["recommendations"]],
        )
        await self.post("이전 조건은 모두 지우고 처음부터 시작하자", first_id)
        restarted = (await self.post("처음", first_id)).json()
        self.assertEqual(restarted["recommendations"][0]["id"], first_hotel["id"])

    async def test_legacy_conversation_reference_support(self):
        conversation_id = str(uuid4())
        self.conversations.add(conversation_id)
        state_key = f"talk-to-book:chat:{{{conversation_id}}}"
        legacy_state = {
            "preferences": [PARK.model_dump()], "history": [], "revision": 1,
        }
        await self.redis.set(state_key, json.dumps(legacy_state), ex=60)
        result = (await self.post("첫 번째 호텔 빼줘", conversation_id)).json()
        self.assertEqual(result["status"], "clarification")
        self.assertEqual(result["preferences"], [{"label": PARK.label, "mode": PARK.mode}])

        legacy_state["last_recommendations"] = [
            HotelReference(id="1", name="Hotel 1", reason="Near Hyde Park").model_dump(),
        ]
        await self.redis.set(state_key, json.dumps(legacy_state), ex=60)
        original_list = (await self.post("처음 추천한 첫 번째 호텔 빼줘", conversation_id)).json()
        self.assertEqual(original_list["status"], "clarification")
        latest_list = (await self.post("첫 번째 호텔 빼줘", conversation_id)).json()
        self.assertEqual([hotel["id"] for hotel in latest_list["recommendations"]], ["2"])

    async def test_card_references_across_recommendation_lists(self):
        first_id = str(uuid4())
        first = (await self.post("처음", request_id=first_id)).json()
        old_card = first["recommendations"][0]
        vague = (await self.post("그 호텔은 빼줘", first_id)).json()
        self.assertEqual(vague["status"], "clarification")
        self.assertEqual(vague["preferences"], first["preferences"])

        second = (await self.post("시티 공항 근처로 바꿔줘", first_id)).json()
        self.assertEqual([hotel["id"] for hotel in second["recommendations"]], ["4"])
        vague = (await self.post("아까 추천한 첫 번째 호텔 빼줘", first_id)).json()
        self.assertEqual(vague["status"], "clarification")
        self.assertEqual(vague["preferences"], second["preferences"])

        resolved = (await self.post("처음 추천한 첫 번째 호텔 빼줘", first_id)).json()
        self.assertEqual(resolved["status"], "recommendations")
        self.assertEqual([hotel["id"] for hotel in resolved["recommendations"]], ["4"])
        self.assertEqual([p["label"] for p in resolved["preferences"] if p["mode"] == "excluded"], [
            f"호텔 · {old_card['name']}",
        ])
        self.assertEqual([p for p in resolved["preferences"] if p["mode"] != "excluded"], second["preferences"])
        await self.post("처음부터", first_id)
        state_key = f"talk-to-book:chat:{{{first_id}}}"
        state = Conversation.model_validate_json(await self.redis.get(state_key))
        self.assertEqual(state.recommendation_lists, [])
        self.assertEqual(state.excluded_hotel_ids, [])
        self.assertEqual(len(state.history), 2)

    async def test_combined_hotel_exclusion_and_quoted_condition(self):
        first_id = str(uuid4())
        initial = (await self.post("처음", request_id=first_id)).json()
        first_hotel = initial["recommendations"][0]
        edited = (await self.post("첫 번째 호텔 말고 가족용으로", first_id)).json()
        self.assertEqual({p["label"] for p in edited["preferences"]}, {
            PARK.label, QUIET.label, FAMILY.label, f"호텔 · {first_hotel['name']}",
        })

    async def test_conflicting_turns_and_history_limit(self):
        first_id = str(uuid4())
        await self.post("처음", request_id=first_id)
        requests = await asyncio.gather(self.post("동시 1", first_id), self.post("동시 2", first_id))
        self.assertEqual(sorted(response.status_code for response in requests), [200, 409])
        for _ in range(7):
            self.assertEqual((await self.post("유지", first_id)).status_code, 200)
        state_key = f"talk-to-book:chat:{{{first_id}}}"
        state = Conversation.model_validate_json(await self.redis.get(state_key))
        self.assertEqual(len(state.history), 12)
        self.assertEqual([batch.number for batch in state.recommendation_lists], list(range(4, 10)))
        expired_reference = (await self.post("처음 추천한 첫 번째 호텔 빼줘", first_id)).json()
        self.assertEqual(expired_reference["status"], "clarification")
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
