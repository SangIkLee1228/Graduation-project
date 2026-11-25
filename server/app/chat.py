import re
from typing import Protocol

from .catalog import Candidate, Catalog, Ranker
from .chat_llm import LLMUnavailable, Reasons
from .chat_models import (
    ChatRequest, ChatResponse, Conversation, MessageEntry, Preference, PreferenceEdit,
    PreferenceLabel, Recommendation,
)
from .chat_store import RedisConversations

UNSUPPORTED_LABELS = {
    "price": "실시간 요금",
    "availability": "예약 가능 여부",
    "outside_london": "런던 외 지역",
    "other": "카탈로그에서 확인할 수 없는 조건",
}
UNVERIFIABLE_REASON = re.compile(
    r"https?://|www\.|[£$€₩]|\d\s*(?:원|파운드|달러)|예약\s*(?:이?\s*가능|확정)|"
    r"실시간\s*(?:가격|요금|재고)|(?:도보|걸어서)\s*\d+\s*분",
    re.IGNORECASE,
)


class ChatLLM(Protocol):
    async def interpret(
        self, message: str, preferences: list[Preference], history: list[MessageEntry]
    ) -> PreferenceEdit: ...

    async def explain(self, hotels: list[dict]) -> Reasons: ...


def apply_edit(current: list[Preference], edit: PreferenceEdit) -> list[Preference]:
    removed = {label.casefold() for label in edit.remove_labels}
    active = {
        preference.label.casefold(): preference for preference in current
        if not edit.reset and preference.label.casefold() not in removed
    }
    for preference in edit.add:
        active[preference.label.casefold()] = preference
    return list(active.values())


class ChatService:
    def __init__(self, catalog: Catalog, ranker: Ranker, llm: ChatLLM, store: RedisConversations):
        self.catalog = catalog
        self.ranker = ranker
        self.llm = llm
        self.store = store

    async def turn(self, request: ChatRequest) -> ChatResponse:
        # The first request UUID also identifies its conversation so a lost response can be retried.
        conversation_id = request.conversation_id or request.request_id
        previous = await self.store.load(conversation_id, request)
        if isinstance(previous, ChatResponse):
            return previous

        edit = await self.llm.interpret(request.message, previous.preferences, previous.history)
        preferences = apply_edit(previous.preferences, edit)
        clarification = (edit.clarification or "").strip()
        if len(preferences) > 12:
            preferences = previous.preferences
            clarification = "조건은 최대 12개까지 적용할 수 있어요. 어떤 조건을 빼면 될까요?"
        labels = [PreferenceLabel(label=p.label, mode=p.mode) for p in preferences]
        picks = []
        unsupported = [label for code, label in UNSUPPORTED_LABELS.items() if code in edit.unsupported]
        notes = f" {' · '.join(unsupported)}은 확인할 수 없어요." if unsupported else ""
        if clarification or not any(p.mode != "excluded" for p in preferences):
            status = "clarification"
            reply = clarification or "런던에서 선호하는 지역이나 숙소 분위기를 알려 주세요."
        elif "outside_london" in edit.unsupported:
            status = "clarification"
            reply = "런던에서 찾고 싶은 지역이 있나요?"
        else:
            candidates = self.ranker.rank(self.catalog.search(preferences))[:3]
            if candidates:
                status = "recommendations"
                picks = await self.recommend(candidates)
                reply = f"리뷰에 남은 호텔 프로파일을 바탕으로 {len(picks)}곳을 골랐어요."
            else:
                status = "no_matches"
                reply = "호텔 프로파일에서 조건에 맞는 결과를 찾지 못했어요. 조정해도 되는 조건이 있나요?"

        response = ChatResponse(
            conversation_id=conversation_id, status=status, reply=reply + notes,
            preferences=labels, recommendations=picks,
        )
        state = Conversation(
            preferences=preferences,
            history=[
                *previous.history,
                MessageEntry(role="user", content=request.message),
                MessageEntry(role="assistant", content=response.reply),
            ][-12:],
            revision=previous.revision + 1,
        )
        return await self.store.commit(request, previous.revision, state, response)

    async def recommend(self, candidates: list[Candidate]) -> list[Recommendation]:
        hotels = {candidate.hotel_id: self.catalog.hotels[candidate.hotel_id] for candidate in candidates}
        payload = [
            {
                "hotel_id": candidate.hotel_id,
                "hotel_name": hotels[candidate.hotel_id].name,
                "profile": hotels[candidate.hotel_id].profile,
                "matching_evidence": candidate.evidence,
            }
            for candidate in candidates
        ]
        reasons = {}
        try:
            result = await self.llm.explain(payload)
            reasons = {reason.hotel_id: reason for reason in result.reasons}
        except LLMUnavailable:
            pass

        recommendations = []
        for candidate in candidates:
            hotel = hotels[candidate.hotel_id]
            generated = reasons.get(hotel.id)
            text = f"프로파일에서 {', '.join(candidate.evidence)} 관련 내용을 확인했어요. “{next(iter(candidate.evidence.values()))}”"
            if (
                generated and generated.reason.strip()
                and generated.evidence in candidate.evidence.values()
                and not UNVERIFIABLE_REASON.search(generated.reason)
            ):
                text = generated.reason.strip()
            recommendations.append(Recommendation(
                id=hotel.id, name=hotel.name, profile=hotel.profile, sid=hotel.sid,
                rating=hotel.rating, booking_links=hotel.booking_links(), reason=text,
            ))
        return recommendations
