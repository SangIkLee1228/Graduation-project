import re
from typing import Protocol

from .catalog import Candidate, Catalog, Ranker
from .chat_llm import LLMUnavailable, Reasons
from .chat_models import (
    ChatRequest, ChatResponse, Conversation, HotelReference, MessageEntry, Preference, PreferenceEdit,
    PreferenceLabel, RECENT_RECOMMENDATION_LISTS, Recommendation, RecommendationList,
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
HOTEL_REFERENCE = re.compile(
    r"(?:그|이|저)\s*(?:호텔|숙소|곳|카드)|그거|그것|이거|이것|저거|저것|"
    r"(?:방금|아까|직전(?:에)?|이전(?:에)?|처음(?:에)?|그\s*전(?:에)?)\s*(?:추천|나온|보여)|추천\s*(?:목록|카드)|"
    r"(?:첫|두|세|[1-3])\s*번(?:째|\s*(?:호텔|숙소))|[1-3]\s*번\s*(?:은|는|을|를|말고|빼)|"
    r"첫째|둘째|셋째|맨\s*(?:위|아래)|\b(?:first|second|third|that one|this one|those)\b",
    re.IGNORECASE,
)
FIRST_LIST = re.compile(
    r"처음(?:에)?\s*(?:추천|나온|보여)|첫\s*번\s*째\s*추천\s*(?:목록|리스트)|"
    r"\bin\s+the\s+first\s+list\b",
    re.IGNORECASE,
)
PREVIOUS_LIST = re.compile(r"그\s*전(?:에)?\s*(?:추천|나온|보여|목록)|한\s*번\s*전")
EARLIER_LIST = re.compile(r"아까|이전(?:에)?\s*(?:추천|나온|보여)")
CARD_RANK = re.compile(
    r"(첫|두|세)\s*번\s*째|(?<!\d)([1-3])\s*번(?=\s|은|는|을|를|만|도|말고|빼|[,.!?]|$)|"
    r"(첫째|둘째|셋째)|"
    r"\b(first|second|third)\s+(?:hotel|one|card)\b",
    re.IGNORECASE,
)
RANKS = {
    "첫": 1, "두": 2, "세": 3, "1": 1, "2": 2, "3": 3,
    "첫째": 1, "둘째": 2, "셋째": 3, "first": 1, "second": 2, "third": 3,
}
SINGULAR_REFERENCE = re.compile(r"(?:그|이|저)\s*(?:호텔|숙소|곳|카드)(?!들)|그거|그것|이거|이것|저거|저것")
WHOLE_LIST = re.compile(r"전부|모두|전체|다\s*(?:빼|제외)|\ball\b", re.IGNORECASE)
EXCLUSION_REQUEST = re.compile(r"빼|제외|말고|제거|싫|\b(?:exclude|skip|remove|instead)\b", re.IGNORECASE)
GENERIC_EDIT = re.compile(
    r"(?:[\s,.!?]|호텔|숙소|조건|대신|다른|다시|빼|제외|말고|추천|보여|해|줘|주세요|요|고|서|는|은|을|를)+"
)
EXPLICIT_RESET = re.compile(
    r"(?:처음\s*부터|새로)\s*(?:다시\s*)?시작(?:해(?:줘|주세요|요)?|하자|할래|할게|합시다)?(?![가-힣])|"
    r"(?:대화|검색|조건)(?:을|를|은|는)?\s*초기화(?:해(?:줘|주세요|요)?|하자)?(?![가-힣])|"
    r"(?<!don't )(?<!not )\b(?:start over|reset (?:the )?(?:chat|search))\b",
    re.IGNORECASE,
)
CONDITION_REFERENCE = re.compile(r"(?:그|이|저)\s*조건|이렇게|그렇게|저렇게")
ASK_FOR_REFERENCE = "어떤 호텔이나 조건을 바꾸고 싶으세요? 호텔 이름이나 추천 순서, 바꿀 조건을 알려 주세요."


class ChatLLM(Protocol):
    async def interpret(self, message: str, conversation: Conversation) -> PreferenceEdit: ...

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


def referenced_hotel_ids(message: str, shown: list[RecommendationList]) -> set[str] | None:
    normalized = message.casefold()
    names: dict[str, set[str]] = {}
    for batch in shown:
        for hotel in batch.hotels:
            name = hotel.name.casefold()
            if name in normalized:
                names.setdefault(name, set()).add(hotel.id)
    if names:
        return set().union(*names.values()) if all(len(ids) == 1 for ids in names.values()) else set()
    if not HOTEL_REFERENCE.search(message):
        return None

    remaining = FIRST_LIST.sub("", message)
    if remaining != message:
        batches = [batch for batch in shown if batch.number == 1]
    elif PREVIOUS_LIST.search(message):
        batches = shown[-2:-1]
    elif EARLIER_LIST.search(message):
        batches = shown
    else:
        batches = shown[-1:]
    if not batches:
        return set()

    ranks = {
        RANKS[next(group for group in match.groups() if group is not None).casefold()]
        for match in CARD_RANK.finditer(remaining)
    }
    if ranks:
        if any(max(ranks) > len(batch.hotels) for batch in batches):
            return set()
        matching = [{batch.hotels[rank - 1].id for rank in ranks} for batch in batches]
        return matching[0] if all(ids == matching[0] for ids in matching) else set()

    eligible = {hotel.id for batch in batches for hotel in batch.hotels}
    if len(eligible) > 1 and (
        len(batches) > 1 or (SINGULAR_REFERENCE.search(message) and not WHOLE_LIST.search(message))
    ):
        return set()
    return eligible


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

        explicit_reset = bool(EXPLICIT_RESET.search(request.message))
        context = Conversation() if explicit_reset else previous
        edit = await self.llm.interpret(request.message, context)
        clarification = (edit.clarification or "").strip()
        shown = context.shown_recommendations
        targets = referenced_hotel_ids(request.message, shown)
        requested_exclusions = set(edit.exclude_hotel_ids) if targets is not None else set()
        quote = (edit.condition_change_quote or "").strip()
        separate_condition = (
            bool(quote) and quote in request.message and not GENERIC_EDIT.fullmatch(quote)
            and referenced_hotel_ids(quote, shown) is None
        )
        apply_conditions = not requested_exclusions or separate_condition
        preferences = apply_edit(context.preferences, edit) if apply_conditions else context.preferences
        reset = explicit_reset or (edit.reset and apply_conditions)
        excluded_ids = set() if reset else set(context.excluded_hotel_ids)
        if targets is not None and (
            requested_exclusions - targets or (not targets and EXCLUSION_REQUEST.search(request.message))
        ):
            clarification = clarification or ASK_FOR_REFERENCE
        elif (
            (targets is not None or CONDITION_REFERENCE.search(request.message))
            and preferences == context.preferences
            and not (requested_exclusions - excluded_ids or reset)
        ):
            clarification = clarification or ASK_FOR_REFERENCE
        if len(preferences) > 12:
            clarification = clarification or "조건은 최대 12개까지 적용할 수 있어요. 어떤 조건을 빼면 될까요?"
        if "outside_london" in edit.unsupported:
            clarification = clarification or "런던에서 찾고 싶은 지역이 있나요?"
        if clarification:
            preferences = context.preferences
            excluded_ids = set(context.excluded_hotel_ids)
        else:
            excluded_ids.update(requested_exclusions)

        labels = [PreferenceLabel(label=p.label, mode=p.mode) for p in preferences]
        labels.extend(
            PreferenceLabel(label=f"호텔 · {self.catalog.hotels[hotel_id].name}", mode="excluded")
            for hotel_id in sorted(excluded_ids) if hotel_id in self.catalog.hotels
        )
        picks = []
        unsupported = [label for code, label in UNSUPPORTED_LABELS.items() if code in edit.unsupported]
        notes = f" {' · '.join(unsupported)}은 확인할 수 없어요." if unsupported else ""
        if clarification or not any(p.mode != "excluded" for p in preferences):
            status = "clarification"
            reply = clarification or "런던에서 선호하는 지역이나 숙소 분위기를 알려 주세요."
        else:
            candidates = self.ranker.rank(self.catalog.search(preferences, excluded_ids))[:3]
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
        reset = explicit_reset or (reset and not clarification)
        if reset:
            shown = []
        if picks:
            last_number = shown[-1].number if shown else 0
            shown = [*shown, RecommendationList(
                number=None if last_number is None else last_number + 1,
                hotels=[HotelReference(id=hotel.id, name=hotel.name, reason=hotel.reason) for hotel in picks],
            )][-RECENT_RECOMMENDATION_LISTS:]
        state = Conversation(
            preferences=preferences,
            recommendation_lists=shown,
            excluded_hotel_ids=sorted(excluded_ids),
            history=[
                *([] if reset else previous.history),
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
