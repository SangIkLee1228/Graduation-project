"""
호텔별 스마트 샘플링
: 최신 리뷰 우선 + 평점 구간별 균등 샘플링 → 호텔당 최대 20개 리뷰 선택
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta

# ── 설정 ──────────────────────────────────────────────────────────
DATA_PATH   = "data/hotelrec_geo_186338.json"
OUTPUT_PATH = "data/hotel_sampled_reviews.json"

TOTAL_SAMPLE    = 20        # 호텔당 최종 샘플 수
PRIMARY_YEARS   = 3         # 1차 기간 (최근 N년)
FALLBACK_YEARS  = 5         # 2차 기간 (리뷰 부족 시 확장)
MIN_REVIEWS     = 5         # 이 수 미만이면 전체 기간 사용

# 평점 구간별 목표 샘플 수 (합계 = TOTAL_SAMPLE=20)
RATING_QUOTA = {
    1: 2,   # 부정 의견 포착
    2: 2,
    3: 4,   # 중립 의견
    4: 6,
    5: 6,   # 긍정 의견
}


# ── 유틸 ──────────────────────────────────────────────────────────
def parse_date(date_str: str) -> datetime:
    return datetime.fromisoformat(date_str[:10])

def get_cutoff(years: int, latest_date: datetime) -> datetime:
    """데이터셋 기준 최신 날짜로부터 N년 이전"""
    return latest_date - timedelta(days=365 * years)

def rating_tier(rating: float) -> int:
    """소수 평점 → 1~5 정수 구간"""
    return max(1, min(5, round(rating)))

def sample_by_quota(reviews: list, quota: dict) -> list:
    """
    평점 구간별 쿼터에 맞게 샘플링.
    쿼터를 못 채운 구간이 있으면 남은 자리를 다른 구간으로 보충.
    """
    # 구간별 분류
    buckets = defaultdict(list)
    for r in reviews:
        buckets[rating_tier(r["rating"])].append(r)

    selected = []
    unfilled = 0  # 채우지 못한 슬롯 수

    # 1차: 각 구간에서 쿼터만큼 최신순 선택
    for tier, q in quota.items():
        available = sorted(buckets[tier], key=lambda r: r["date"], reverse=True)
        picked = available[:q]  # 최신순 상위 q개
        selected.extend(picked)
        unfilled += q - len(picked)  # 부족한 만큼 기록

    # 2차: 남은 슬롯을 전체 미선택 리뷰에서 보충
    if unfilled > 0:
        selected_ids = {id(r) for r in selected}
        remaining = [r for r in reviews if id(r) not in selected_ids]
        # 최신순 정렬 후 보충 (최신 우선)
        remaining.sort(key=lambda r: r["date"], reverse=True)
        selected.extend(remaining[:unfilled])

    return selected


def select_reviews_for_hotel(reviews: list, latest_date: datetime) -> tuple[list, str]:
    """
    엣지 케이스 처리 포함 호텔 리뷰 선택.
    반환: (선택된 리뷰 리스트, 사용된 전략 설명)
    """
    # 날짜 기준 내림차순 정렬 (최신 우선)
    reviews_sorted = sorted(reviews, key=lambda r: r["date"], reverse=True)

    # ── Case 1: 최근 PRIMARY_YEARS년 필터 ──────────────────────────
    cutoff_primary = get_cutoff(PRIMARY_YEARS, latest_date)
    recent_primary = [r for r in reviews_sorted if parse_date(r["date"]) >= cutoff_primary]

    if len(recent_primary) >= TOTAL_SAMPLE:
        # 충분한 최신 리뷰 → 평점 구간별 샘플링
        sampled = sample_by_quota(recent_primary, RATING_QUOTA)
        return sampled, f"primary_{PRIMARY_YEARS}yr"

    # ── Case 2: 최근 FALLBACK_YEARS년으로 확장 ─────────────────────
    cutoff_fallback = get_cutoff(FALLBACK_YEARS, latest_date)
    recent_fallback = [r for r in reviews_sorted if parse_date(r["date"]) >= cutoff_fallback]

    if len(recent_fallback) >= MIN_REVIEWS:
        # 확장 기간에서 샘플링 (가능한 만큼만)
        sampled = sample_by_quota(recent_fallback, RATING_QUOTA)
        strategy = f"fallback_{FALLBACK_YEARS}yr"
        if len(recent_fallback) < TOTAL_SAMPLE:
            strategy += f"_partial({len(recent_fallback)})"
        return sampled, strategy

    # ── Case 3: 전체 기간 사용 (리뷰 매우 적은 호텔) ───────────────
    sampled = sample_by_quota(reviews_sorted, RATING_QUOTA)
    strategy = f"all_period({len(reviews_sorted)}reviews)"
    return sampled, strategy


# ── 메인 ──────────────────────────────────────────────────────────
def main():
    print("데이터 로딩 중...")
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)

    # 데이터셋 기준 최신 날짜
    latest_date = max(parse_date(r["date"]) for r in data if r.get("date"))
    print(f"데이터셋 최신 날짜: {latest_date.date()}")
    print(f"1차 기준 날짜 (최근 {PRIMARY_YEARS}년): {get_cutoff(PRIMARY_YEARS, latest_date).date()}")
    print(f"2차 기준 날짜 (최근 {FALLBACK_YEARS}년): {get_cutoff(FALLBACK_YEARS, latest_date).date()}")

    # 호텔별 리뷰 그룹핑
    hotel_reviews = defaultdict(list)
    for r in data:
        hotel_reviews[r["hotel_url"]].append(r)

    print(f"\n총 호텔 수: {len(hotel_reviews)}")

    # 호텔별 샘플링
    results = {}
    strategy_counter = defaultdict(int)

    for hotel_url, reviews in hotel_reviews.items():
        sampled, strategy = select_reviews_for_hotel(reviews, latest_date)
        strategy_counter[strategy.split("(")[0]] += 1  # 통계용 (파라미터 제거)

        results[hotel_url] = {
            "hotel_url":      hotel_url,
            "total_reviews":  len(reviews),
            "sampled_count":  len(sampled),
            "strategy":       strategy,
            "sampled_reviews": sampled,
        }

    # 저장
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 요약 출력
    print("\n── 샘플링 전략 사용 현황 ──")
    for s, cnt in sorted(strategy_counter.items()):
        print(f"  {s}: {cnt}개 호텔")

    print(f"\n저장 완료 → {OUTPUT_PATH}")
    print(f"총 {len(results)}개 호텔 프로파일 생성")


if __name__ == "__main__":
    main()
