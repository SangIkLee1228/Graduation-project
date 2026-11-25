import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urlencode

from pydantic import BaseModel, Field

from .chat_models import BookingLink, Preference

TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
SENTENCE = re.compile(r"(?<=[.!?;])\s+")
NEGATION = re.compile(
    r"\b(?:no|not|isn't|aren't|without|lacks?|lack of|limited|insufficient|"
    r"far from|away from|does not (?:have|offer|provide))\b(?:[\s-]+\w+){0,2}[\s-]+$",
    re.IGNORECASE,
)
NEGATED_SUFFIX = re.compile(
    r"^\s+(?:(?:is|are|was|were)\s+)?(?:unavailable|not (?:available|provided|offered)|missing)\b",
    re.IGNORECASE,
)


def tokens(value: str) -> list[str]:
    return TOKEN.findall(unicodedata.normalize("NFKC", value).casefold())


class Hotel(BaseModel):
    id: str = Field(pattern=r"^\d+$")
    name: str
    url: str = Field(pattern=r"^Hotel_Review-[^/?#]+\.html$")
    profile: str
    rating: float = Field(ge=1, le=5)
    sid: tuple[int, int, int, int]

    def booking_links(self) -> list[BookingLink]:
        query = f"{self.name} London"
        return [
            BookingLink(
                platform="tripadvisor", label="TripAdvisor",
                href=f"https://www.tripadvisor.com/{quote(self.url, safe='')}",
            ),
            BookingLink(
                platform="booking", label="Booking.com",
                href=f"https://www.booking.com/searchresults.html?{urlencode({'ss': query})}",
            ),
            BookingLink(
                platform="google_maps", label="지도",
                href=f"https://www.google.com/maps/search/?{urlencode({'api': 1, 'query': query})}",
            ),
        ]


@dataclass(frozen=True)
class Candidate:
    hotel_id: str
    sid: tuple[int, int, int, int]
    score: float
    evidence: dict[str, str]


class Ranker(Protocol):
    def rank(self, candidates: list[Candidate]) -> list[Candidate]: ...


class SemanticIDRanker:
    def rank(self, candidates: list[Candidate]) -> list[Candidate]:
        if not candidates:
            return []
        anchors = candidates[:5]
        max_score = candidates[0].score or 1.0
        lexical_order = {candidate.hotel_id: index for index, candidate in enumerate(candidates)}

        def rank_key(candidate: Candidate):
            prefixes = [
                sum(candidate.sid[:length] == anchor.sid[:length] for length in (1, 2, 3))
                for anchor in anchors
                if candidate.hotel_id != anchor.hotel_id
            ]
            prefix_score = max(prefixes, default=0) / 3
            score = 0.8 * candidate.score / max_score + 0.2 * prefix_score
            return -score, lexical_order[candidate.hotel_id], candidate.hotel_id

        return sorted(candidates, key=rank_key)


def match_patterns(preference: Preference) -> list[re.Pattern]:
    phrases = [tokens(term) for term in preference.terms]
    separators = r"[\s-]+"
    return [
        re.compile(r"\b" + separators.join(map(re.escape, phrase)) + r"\b", re.IGNORECASE)
        for phrase in phrases if phrase
    ]


def matched_sentence(sentences: list[str], patterns: list[re.Pattern]) -> str | None:
    for sentence in sentences:
        for pattern in patterns:
            for match in pattern.finditer(sentence):
                if (
                    NEGATION.search(sentence[:match.start()])
                    or NEGATED_SUFFIX.match(sentence[match.end():])
                ):
                    continue
                return sentence
    return None


class Catalog:
    def __init__(self, hotels: list[Hotel]):
        self.hotels = {hotel.id: hotel for hotel in hotels}
        if not hotels or len(self.hotels) != len(hotels) or len({hotel.sid for hotel in hotels}) != len(hotels):
            raise ValueError("Catalog must have unique hotel IDs and four-token Semantic IDs")
        self.documents = {}
        self.sentences = {}
        self.lengths = {}
        document_frequency: Counter[str] = Counter()
        for hotel in hotels:
            words = tokens(f"{hotel.name} {hotel.profile}")
            self.documents[hotel.id] = Counter(words)
            self.sentences[hotel.id] = [
                unicodedata.normalize("NFKC", sentence)
                for sentence in SENTENCE.split(hotel.profile)
            ]
            self.lengths[hotel.id] = len(words)
            document_frequency.update(self.documents[hotel.id].keys())
        self.avg_length = sum(self.lengths.values()) / len(hotels)
        count = len(hotels)
        self.idf = {word: math.log1p((count - df + 0.5) / (df + 0.5))
                    for word, df in document_frequency.items()}

    @classmethod
    def load(cls, path: Path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        hotels = [Hotel.model_validate(row) for row in payload["hotels"]]
        return cls(hotels)

    def search(self, preferences: list[Preference]) -> list[Candidate]:
        filters = [(preference, match_patterns(preference)) for preference in preferences]
        query = {word for preference in preferences if preference.mode != "excluded"
                 for term in preference.terms for word in tokens(term)}
        candidates = []
        for hotel in self.hotels.values():
            evidence = {}
            for preference, patterns in filters:
                sentences = self.sentences[hotel.id]
                # Required conditions must be supported by the profile itself.
                if preference.mode != "required":
                    sentences = [*sentences, unicodedata.normalize("NFKC", hotel.name)]
                match = matched_sentence(sentences, patterns)
                if (preference.mode == "required" and not match) or (preference.mode == "excluded" and match):
                    break
                if match:
                    evidence[preference.label] = match
            else:
                if evidence:
                    candidates.append(Candidate(hotel.id, hotel.sid, self.bm25(hotel.id, query), evidence))
        return sorted(candidates, key=lambda c: (-c.score, c.hotel_id))[:40]

    def bm25(self, hotel_id: str, query: set[str]) -> float:
        frequencies = self.documents[hotel_id]
        k1, b = 1.2, 0.75
        norm = k1 * (1 - b + b * self.lengths[hotel_id] / self.avg_length)
        return sum(
            self.idf[word] * (k1 + 1) * frequencies[word] / (frequencies[word] + norm)
            for word in sorted(query & frequencies.keys())
        )
