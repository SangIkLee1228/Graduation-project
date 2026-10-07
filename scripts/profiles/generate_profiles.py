"""
호텔 대표 프로파일 생성
: 샘플링된 리뷰 20개 → gpt-4o-mini (Luxia Cloud) → 호텔 대표 텍스트
"""

import json
import time
import re
import os
import requests
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")  # 프로젝트 루트의 .env 파일 로드

# ── 설정 ──────────────────────────────────────────────────────────
API_KEY = os.getenv("LUXIA_API_KEY")
if not API_KEY:
    raise ValueError(".env 파일에 LUXIA_API_KEY가 설정되지 않았습니다.")
ENDPOINT     = "https://bridge.luxiacloud.com/llm/openai/chat/completions/gpt-4o-mini/create"
INPUT_PATH   = ROOT / "data/processed/hotel_sampled_reviews.json"
OUTPUT_PATH  = ROOT / "data/processed/hotel_profiles.json"
ERROR_PATH   = ROOT / "data/processed/hotel_profiles_errors.json"

RETRY_LIMIT  = 3       # 실패 시 재시도 횟수
RETRY_DELAY  = 5       # 재시도 대기 시간 (초)
CALL_DELAY   = 0.5     # 호출 간격 (Rate limit 방지)

# ── 프롬프트 ──────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a travel assistant that summarizes hotel reviews.
Given a set of guest reviews for a hotel, write a concise 3-sentence profile of the hotel.
Cover: (1) overall atmosphere and type, (2) key strengths, (3) notable weaknesses if any.
Be factual and specific. Output plain text only, no bullet points or headers."""

def build_user_prompt(hotel_name: str, avg_rating: float, reviews: list) -> str:
    review_texts = []
    for i, r in enumerate(reviews, 1):
        review_texts.append(
            f"[Review {i} | Rating: {r['rating']}/5]\n"
            f"Title: {r['title']}\n"
            f"{r['text']}"
        )
    reviews_block = "\n\n".join(review_texts)

    return f"""Hotel: {hotel_name}
Overall average rating: {avg_rating:.1f}/5

Guest Reviews:
{reviews_block}

Please write a 3-sentence hotel profile based on the reviews above."""

# ── API 호출 ──────────────────────────────────────────────────────
def call_llm(prompt: str) -> str:
    headers = {
        "apikey": API_KEY,
        "Content-Type": "application/json",
    }
    body = {
        "model": "llm",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        "stream": False,
        "temperature": 0.3,   # 일관된 출력을 위해 낮게 설정
        "max_tokens": 300,
    }

    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            resp = requests.post(ENDPOINT, headers=headers, json=body, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except requests.exceptions.HTTPError as e:
            print(f"  [WARN] HTTP error (attempt {attempt}/{RETRY_LIMIT}): {e}")
        except (KeyError, IndexError) as e:
            print(f"  [WARN] Response parse error (attempt {attempt}/{RETRY_LIMIT}): {e}")
        except requests.exceptions.Timeout:
            print(f"  [WARN] Timeout (attempt {attempt}/{RETRY_LIMIT})")
        except requests.exceptions.ConnectionError:
            print(f"  [WARN] Network error (attempt {attempt}/{RETRY_LIMIT}): check WiFi")
        except Exception as e:
            print(f"  [WARN] Unexpected error (attempt {attempt}/{RETRY_LIMIT}): {type(e).__name__}")

        if attempt < RETRY_LIMIT:
            time.sleep(RETRY_DELAY)

    raise RuntimeError("최대 재시도 횟수 초과")

# ── URL 파싱 유틸 ─────────────────────────────────────────────────
def parse_hotel_url(hotel_url: str) -> tuple[str, str]:
    """hotel_url → (hotel_id, hotel_name)"""
    match = re.match(r"Hotel_Review-g\d+-d(\d+)-Reviews-(.+)-[^-]+\.html", hotel_url)
    if match:
        hotel_id   = match.group(1)
        hotel_name = match.group(2).replace("_", " ")
    else:
        hotel_id   = hotel_url
        hotel_name = hotel_url
    return hotel_id, hotel_name

# ── 메인 ──────────────────────────────────────────────────────────
def main():
    # 입력 로드
    print("샘플링 데이터 로딩 중...")
    with open(INPUT_PATH, encoding="utf-8") as f:
        sampled = json.load(f)

    # 이미 처리된 항목 건너뛰기 (중단 후 재시작 대비)
    existing = {}
    if Path(OUTPUT_PATH).exists():
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            existing = json.load(f)
        print(f"기존 처리 완료: {len(existing)}개 호텔 → 이어서 진행")

    errors = {}
    hotels = list(sampled.items())
    total  = len(hotels)

    for idx, (hotel_url, info) in enumerate(hotels, 1):
        if hotel_url in existing:
            continue  # 이미 처리됨

        hotel_id, hotel_name = parse_hotel_url(hotel_url)
        reviews = info["sampled_reviews"]

        # 평균 평점 계산
        avg_rating = sum(r["rating"] for r in reviews) / len(reviews)

        print(f"[{idx}/{total}] {hotel_name[:45]:<45} | 리뷰 {len(reviews)}개 | 전략: {info['strategy']}")

        try:
            prompt  = build_user_prompt(hotel_name, avg_rating, reviews)
            profile = call_llm(prompt)

            existing[hotel_url] = {
                "hotel_id":    hotel_id,
                "hotel_name":  hotel_name,
                "hotel_url":   hotel_url,
                "avg_rating":  round(avg_rating, 2),
                "strategy":    info["strategy"],
                "total_reviews": info["total_reviews"],
                "sampled_count": info["sampled_count"],
                "profile":     profile,
            }

            # 매 10개마다 중간 저장 (중단 대비)
            if idx % 10 == 0:
                with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                    json.dump(existing, f, ensure_ascii=False, indent=2)
                print(f"  → 중간 저장 완료 ({len(existing)}개)")

        except RuntimeError as e:
            print(f"  [FAIL] {e}")
            errors[hotel_url] = str(e)

        time.sleep(CALL_DELAY)

    # 최종 저장
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    if errors:
        with open(ERROR_PATH, "w", encoding="utf-8") as f:
            json.dump(errors, f, ensure_ascii=False, indent=2)
        print(f"\n[WARN] Failed hotels: {len(errors)} -> {ERROR_PATH}")

    print(f"\n[DONE] Total {len(existing)} hotel profiles saved -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
