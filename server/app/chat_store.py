from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import WatchError

from .chat_models import ChatRequest, ChatResponse, CompletedRequest, Conversation

TTL_SECONDS = 24 * 60 * 60


class ConversationExpired(Exception):
    pass


class ConversationConflict(Exception):
    pass


class RedisConversations:
    def __init__(self, client: Redis):
        self.client = client

    @staticmethod
    def _keys(conversation_id: UUID, request_id: UUID) -> tuple[str, str]:
        key = f"talk-to-book:chat:{{{conversation_id}}}"
        return key, f"{key}:request:{request_id}"

    @staticmethod
    def _replay(value: bytes, request: ChatRequest) -> ChatResponse:
        completed = CompletedRequest.model_validate_json(value)
        if completed.message != request.message:
            raise ConversationConflict
        return completed.response

    async def load(self, conversation_id: UUID, request: ChatRequest) -> Conversation | ChatResponse:
        conversation_key, request_key = self._keys(conversation_id, request.request_id)
        state, completed = await self.client.mget(conversation_key, request_key)
        if completed and state:
            return self._replay(completed, request)
        if request.conversation_id is None:
            if state:
                raise ConversationConflict
            return Conversation()
        if not state:
            raise ConversationExpired
        return Conversation.model_validate_json(state)

    async def commit(
        self, request: ChatRequest, previous_revision: int, state: Conversation, response: ChatResponse
    ) -> ChatResponse:
        conversation_key, request_key = self._keys(response.conversation_id, request.request_id)
        async with self.client.pipeline() as pipe:
            try:
                await pipe.watch(conversation_key, request_key)
                saved, completed = await pipe.mget(conversation_key, request_key)
                if completed and saved:
                    return self._replay(completed, request)
                if saved is None and request.conversation_id is not None:
                    raise ConversationExpired
                if saved and Conversation.model_validate_json(saved).revision != previous_revision:
                    raise ConversationConflict
                pipe.multi()
                pipe.set(conversation_key, state.model_dump_json(), ex=TTL_SECONDS)
                pipe.set(
                    request_key,
                    CompletedRequest(message=request.message, response=response).model_dump_json(),
                    ex=TTL_SECONDS,
                )
                await pipe.execute()
            except WatchError:
                existing = await self.load(response.conversation_id, request)
                if isinstance(existing, ChatResponse):
                    return existing
                raise ConversationConflict from None
        return response
