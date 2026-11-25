from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, UUID4

Message = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Term = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Category = Literal["location", "property_type", "atmosphere", "amenity", "traveler"]


class ChatRequest(BaseModel):
    message: Message
    request_id: UUID4
    conversation_id: UUID4 | None = None


class Preference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Category
    label: Label
    terms: list[Term] = Field(min_length=1, max_length=5)
    mode: Literal["required", "preferred", "excluded"]


class PreferenceEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    remove_labels: list[Label] = Field(default_factory=list, max_length=12)
    add: list[Preference] = Field(default_factory=list, max_length=12)
    reset: bool = False
    clarification: str | None = Field(default=None, max_length=300)
    unsupported: list[Literal["price", "availability", "outside_london", "other"]] = Field(
        default_factory=list, max_length=4
    )


class PreferenceLabel(BaseModel):
    label: str
    mode: Literal["required", "preferred", "excluded"]


class BookingLink(BaseModel):
    platform: str
    label: str
    href: str


class Recommendation(BaseModel):
    id: str
    name: str
    profile: str
    rating: float
    sid: tuple[int, int, int, int]
    reason: str
    booking_links: list[BookingLink]


class ChatResponse(BaseModel):
    conversation_id: UUID4
    status: Literal["recommendations", "clarification", "no_matches"]
    reply: str
    preferences: list[PreferenceLabel]
    recommendations: list[Recommendation] = Field(default_factory=list, max_length=3)


class MessageEntry(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class Conversation(BaseModel):
    preferences: list[Preference] = Field(default_factory=list)
    history: list[MessageEntry] = Field(default_factory=list)
    revision: int = 0


class CompletedRequest(BaseModel):
    message: str
    response: ChatResponse
