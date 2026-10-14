"""프론트엔드 데모용 호텔 데이터를 만든다.

입력:
  - data/processed/hotel_profiles.json        (LLM 프로파일)
  - data/processed/hotel_sampled_reviews.json (상세 화면에 보여줄 리뷰)
  - artifacts/semantic_ids/rq_kmeans/hotel_semantic_ids_twkim.json (K-means Semantic ID)
  - --reviews: 런던 원본 리뷰 (기본 data/raw/hotelrec_geo_186338.json, 최근 평점 추세 계산용)
출력:
  - frontend/public/data/hotels.json

사용법:
  uv run python scripts/demo/build_frontend_data.py [--reviews <path>]
"""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILES = ROOT / "data/processed/hotel_profiles.json"
SAMPLED = ROOT / "data/processed/hotel_sampled_reviews.json"
SEMANTIC_IDS = ROOT / "artifacts/semantic_ids/rq_kmeans/hotel_semantic_ids_twkim.json"
OUTPUT = ROOT / "frontend/public/data/hotels.json"

RECENT_DAYS = 365        # 데이터 마지막 날짜 기준 최근 1년
MIN_RECENT_REVIEWS = 5   # 최근 리뷰가 이보다 적으면 추세를 판단하지 않음
WARN_DROP = 0.5          # 최근 평균이 전체 평균보다 이만큼 낮으면 경고
SAMPLE_REVIEWS = 2
SAMPLE_CHARS = 240


def read_reviews(path):
    """한 줄에 리뷰 하나인 JSON 배열을 줄 단위로 읽는다."""
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip().rstrip(",")
            if line in ("", "[", "]"):
                continue
            yield json.loads(line)


def rating_stats(path):
    reviews = defaultdict(list)
    for r in read_reviews(path):
        reviews[r["hotel_url"]].append((datetime.fromisoformat(r["date"]), r["rating"]))
    cutoff = max(d for rs in reviews.values() for d, _ in rs) - timedelta(days=RECENT_DAYS)
    stats = {}
    for url, rs in reviews.items():
        recent = [rating for d, rating in rs if d >= cutoff]
        stats[url] = {
            "avg": sum(rating for _, rating in rs) / len(rs),
            "recent_avg": sum(recent) / len(recent) if recent else None,
            "recent_count": len(recent),
        }
    return stats, cutoff


def shorten(text):
    if len(text) <= SAMPLE_CHARS:
        return text
    return text[:SAMPLE_CHARS].rsplit(" ", 1)[0] + "…"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reviews", type=Path, default=ROOT / "data/raw/hotelrec_geo_186338.json")
    args = parser.parse_args()

    profiles = json.loads(PROFILES.read_text(encoding="utf-8"))
    sampled = json.loads(SAMPLED.read_text(encoding="utf-8"))
    sids = json.loads(SEMANTIC_IDS.read_text(encoding="utf-8"))
    stats, cutoff = rating_stats(args.reviews)

    hotels = []
    for url, p in profiles.items():
        s = stats[url]
        recent = None
        if s["recent_count"] >= MIN_RECENT_REVIEWS:
            recent = {"avg": round(s["recent_avg"], 2), "count": s["recent_count"]}
        samples = sorted(sampled[url]["sampled_reviews"], key=lambda r: r["date"], reverse=True)
        hotels.append({
            "id": p["hotel_id"],
            "name": p["hotel_name"],
            "url": url,
            "rating": round(s["avg"], 2),
            "reviews": p["total_reviews"],
            "profile": p["profile"],
            "sid": sids[url]["semantic_id"],
            "recent": recent,
            "warn": recent is not None and recent["avg"] <= s["avg"] - WARN_DROP,
            "samples": [
                {"date": r["date"][:10], "rating": r["rating"], "title": r["title"], "text": shorten(r["text"])}
                for r in samples[:SAMPLE_REVIEWS]
            ],
        })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    meta = {"recent_since": cutoff.date().isoformat(), "count": len(hotels)}
    OUTPUT.write_text(json.dumps({"meta": meta, "hotels": hotels}, ensure_ascii=False, separators=(",", ":")),
                      encoding="utf-8")
    print(f"{len(hotels)} hotels → {OUTPUT.relative_to(ROOT)} "
          f"({OUTPUT.stat().st_size / 1e6:.1f} MB), recent since {meta['recent_since']}, "
          f"warn {sum(h['warn'] for h in hotels)}")


if __name__ == "__main__":
    main()
