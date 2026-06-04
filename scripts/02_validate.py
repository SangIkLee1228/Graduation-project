"""
02_validate.py — 47GB 파일을 한 줄씩 스트리밍하며 검증 통계를 수집합니다.
   - 총 레코드 수, 파싱 오류 수
   - 필드별 결측값 비율
   - 평점 분포
   - property_dict 서브키 통계
   - 날짜 범위

결과는 output/validation_stats.json에 저장.
"""
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "HotelRec.txt"
OUT_PATH = ROOT / "output" / "validation_stats.json"


def clean_line(line: str) -> str:
    return line.strip().rstrip(",").strip("[]").strip()


def main():
    if not DATA_PATH.exists():
        print(f"❌ 파일 없음: {DATA_PATH}")
        return

    file_size = DATA_PATH.stat().st_size

    stats = {
        "total": 0,
        "parse_error": 0,
        "empty_lines": 0,
        "missing": {
            "hotel_url": 0, "author": 0, "date": 0,
            "rating": 0, "title": 0, "text": 0,
            "property_dict": 0,
        },
        "rating_dist": Counter(),
        "prop_key_freq": Counter(),
        "text_length": {"min": None, "max": None, "sum": 0, "count": 0},
        "date_range": {"min": None, "max": None},
        "unique_hotels_estimate": set(),  # 메모리 절약을 위해 일정 크기 도달 시 카운트만
        "unique_authors_estimate": set(),
    }

    # 유니크 카운팅은 메모리가 많이 들 수 있어 1M 도달 시 set을 비웁니다.
    UNIQUE_CAP = 1_000_000

    # tqdm: 파일 크기 기준 progress bar
    pbar = tqdm(
        total=file_size, unit="B", unit_scale=True, unit_divisor=1024,
        desc="검증 중", smoothing=0.1
    )

    try:
        with DATA_PATH.open("r", encoding="utf-8") as f:
            for raw in f:
                pbar.update(len(raw.encode("utf-8")))

                line = clean_line(raw)
                if not line:
                    stats["empty_lines"] += 1
                    continue

                stats["total"] += 1
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    stats["parse_error"] += 1
                    continue

                # 결측값 체크
                for key in stats["missing"]:
                    if r.get(key) in (None, "", [], {}):
                        stats["missing"][key] += 1

                # 평점 분포
                rating = r.get("rating")
                if isinstance(rating, (int, float)):
                    stats["rating_dist"][float(rating)] += 1

                # property_dict 서브키
                pd_ = r.get("property_dict") or {}
                if isinstance(pd_, dict):
                    stats["prop_key_freq"].update(pd_.keys())

                # 텍스트 길이
                text = r.get("text") or ""
                if text:
                    L = len(text)
                    tl = stats["text_length"]
                    tl["sum"] += L
                    tl["count"] += 1
                    tl["min"] = L if tl["min"] is None else min(tl["min"], L)
                    tl["max"] = L if tl["max"] is None else max(tl["max"], L)

                # 날짜 범위
                date_str = r.get("date")
                if date_str:
                    dr = stats["date_range"]
                    if dr["min"] is None or date_str < dr["min"]:
                        dr["min"] = date_str
                    if dr["max"] is None or date_str > dr["max"]:
                        dr["max"] = date_str

                # unique 카운팅 (메모리 제한)
                if len(stats["unique_hotels_estimate"]) < UNIQUE_CAP:
                    if r.get("hotel_url"):
                        stats["unique_hotels_estimate"].add(r["hotel_url"])
                if len(stats["unique_authors_estimate"]) < UNIQUE_CAP:
                    if r.get("author"):
                        stats["unique_authors_estimate"].add(r["author"])
    finally:
        pbar.close()

    # 평균 텍스트 길이 계산
    tl = stats["text_length"]
    tl["avg"] = (tl["sum"] / tl["count"]) if tl["count"] else 0

    # set → 카운트 변환 (저장용)
    hotels_n = len(stats["unique_hotels_estimate"])
    authors_n = len(stats["unique_authors_estimate"])
    stats["unique_hotels_estimate"] = (
        f"{hotels_n} (cap {UNIQUE_CAP} 도달, 실제 더 많을 수 있음)"
        if hotels_n >= UNIQUE_CAP else hotels_n
    )
    stats["unique_authors_estimate"] = (
        f"{authors_n} (cap {UNIQUE_CAP} 도달, 실제 더 많을 수 있음)"
        if authors_n >= UNIQUE_CAP else authors_n
    )

    # Counter → dict로 변환 (정렬)
    stats["rating_dist"] = dict(sorted(stats["rating_dist"].items()))
    stats["prop_key_freq"] = dict(stats["prop_key_freq"].most_common())

    # 결측값 비율 추가
    total = max(stats["total"], 1)
    stats["missing_ratio_pct"] = {
        k: round(v / total * 100, 3) for k, v in stats["missing"].items()
    }

    # 저장
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False, default=str)

    # 요약 출력
    print("\n" + "=" * 60)
    print("검증 완료")
    print("=" * 60)
    print(f"총 레코드:      {stats['total']:,}")
    print(f"파싱 오류:      {stats['parse_error']:,}")
    print(f"빈 줄:          {stats['empty_lines']:,}")
    print(f"고유 호텔(est): {stats['unique_hotels_estimate']}")
    print(f"고유 작성자(est): {stats['unique_authors_estimate']}")
    print(f"날짜 범위:      {stats['date_range']['min']} ~ {stats['date_range']['max']}")
    print(f"평균 텍스트 길이: {tl['avg']:.1f}자 (min {tl['min']}, max {tl['max']})")
    print(f"\n결측값 비율(%):")
    for k, v in stats["missing_ratio_pct"].items():
        print(f"  {k:15s}: {v}%")
    print(f"\n평점 분포:")
    for r, c in stats["rating_dist"].items():
        print(f"  {r}: {c:,}")
    print(f"\n📁 상세 결과: {OUT_PATH}")


if __name__ == "__main__":
    main()
