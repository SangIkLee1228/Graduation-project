"""
08_make_views.py — 용도별로 데이터셋을 쪼개고, 시간 기반 train/val/test split 생성.

생성되는 파일들:
   data/splits/
   ├── rec_train.parquet   # 추천 시스템 학습용 (text 제외, 가볍고 빠름)
   ├── rec_val.parquet
   ├── rec_test.parquet
   ├── nlp_balanced.parquet  # NLP용 — 평점 클래스 균형 샘플
   ├── hotels.parquet         # 호텔 메타데이터 (호텔별 집계)
   └── users.parquet          # 사용자 메타데이터

시간 기반 split:
   train: ~2017
   val:   2018
   test:  2019
"""
import argparse
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]

VIEWS_DIR = ROOT / "data/splits"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=None, help="입력 Parquet (default: kcore5 우선, 없으면 normalized)")
    ap.add_argument("--nlp-per-class", type=int, default=100_000,
                    help="NLP용 평점별 샘플 크기 (default: 100k)")
    args = ap.parse_args()

    # 입력 자동 선택
    if args.input:
        in_path = Path(args.input)
    else:
        candidates = [
            ROOT / "data/processed" / "hotelrec_kcore5.parquet",
            ROOT / "data/processed" / "hotelrec_normalized.parquet",
        ]
        in_path = next((p for p in candidates if p.exists()), None)

    if not in_path or not in_path.exists():
        print(f"❌ 입력 없음. 먼저 06_normalize.py 또는 07_kcore_filter.py를 실행하세요.")
        return

    VIEWS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"📂 입력: {in_path}\n")

    con = duckdb.connect()
    src = f"'{in_path}'"

    # === 1) 추천 시스템용 (text 제외, 시간 기반 split) ===
    print("1/4) 추천용 train/val/test 생성")
    splits = {
        "rec_train": "year > 0 AND year <= 2017",
        "rec_val":   "year = 2018",
        "rec_test":  "year = 2019",
    }
    for name, where in splits.items():
        out = VIEWS_DIR / f"{name}.parquet"
        con.execute(f"""
            COPY (
                SELECT user_idx, hotel_idx, hotel_id, rating, date, year,
                       sub_service, sub_cleanliness, sub_value, sub_location,
                       sub_rooms, sub_sleep_quality
                FROM {src}
                WHERE {where}
            ) TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        n = con.execute(f"SELECT COUNT(*) FROM '{out}'").fetchone()[0]
        size_mb = out.stat().st_size / (1024 ** 2)
        print(f"   {name}: {n:,} 행, {size_mb:.1f} MB")

    # === 2) NLP용 — 평점 균형 샘플 ===
    print(f"\n2/4) NLP용 평점 균형 샘플 (각 평점 {args.nlp_per_class:,}건)")
    out = VIEWS_DIR / "nlp_balanced.parquet"
    con.execute(f"""
        COPY (
            SELECT user_idx, hotel_idx, rating, title, text, text_len, year
            FROM (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY rating ORDER BY random()) AS rn
                FROM {src}
                WHERE text IS NOT NULL AND length(text) >= 50
            )
            WHERE rn <= {args.nlp_per_class}
        ) TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    n = con.execute(f"SELECT COUNT(*) FROM '{out}'").fetchone()[0]
    dist = con.execute(f"SELECT rating, COUNT(*) FROM '{out}' GROUP BY rating ORDER BY rating").fetchall()
    size_mb = out.stat().st_size / (1024 ** 2)
    print(f"   nlp_balanced: 총 {n:,}건, {size_mb:.1f} MB")
    print(f"   클래스 분포: {dict(dist)}")

    # === 3) 호텔 메타데이터 집계 ===
    print(f"\n3/4) 호텔별 메타데이터 집계")
    out = VIEWS_DIR / "hotels.parquet"
    con.execute(f"""
        COPY (
            SELECT
                hotel_idx, hotel_id, ANY_VALUE(hotel_url) AS hotel_url,
                COUNT(*) AS n_reviews,
                AVG(rating) AS mean_rating,
                STDDEV(rating) AS std_rating,
                AVG(sub_service) AS mean_service,
                AVG(sub_cleanliness) AS mean_cleanliness,
                AVG(sub_value) AS mean_value,
                AVG(sub_location) AS mean_location,
                AVG(sub_rooms) AS mean_rooms,
                AVG(sub_sleep_quality) AS mean_sleep_quality,
                MIN(year) AS first_year,
                MAX(year) AS last_year
            FROM {src}
            GROUP BY hotel_idx, hotel_id
        ) TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    n = con.execute(f"SELECT COUNT(*) FROM '{out}'").fetchone()[0]
    size_mb = out.stat().st_size / (1024 ** 2)
    print(f"   hotels: {n:,}개 호텔, {size_mb:.1f} MB")

    # === 4) 사용자 메타데이터 집계 ===
    print(f"\n4/4) 사용자별 메타데이터 집계")
    out = VIEWS_DIR / "users.parquet"
    con.execute(f"""
        COPY (
            SELECT
                user_idx,
                COUNT(*) AS n_reviews,
                AVG(rating) AS mean_rating,
                STDDEV(rating) AS std_rating,
                COUNT(DISTINCT hotel_idx) AS n_unique_hotels,
                MIN(year) AS first_year,
                MAX(year) AS last_year
            FROM {src}
            GROUP BY user_idx
        ) TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    n = con.execute(f"SELECT COUNT(*) FROM '{out}'").fetchone()[0]
    size_mb = out.stat().st_size / (1024 ** 2)
    print(f"   users: {n:,}명, {size_mb:.1f} MB")

    print(f"\n✅ 모든 view 생성 완료: {VIEWS_DIR}")
    print(f"\n로드 예시:")
    print(f"   import pandas as pd")
    print(f"   train = pd.read_parquet(r'{VIEWS_DIR / 'rec_train.parquet'}')")
    print(f"   nlp = pd.read_parquet(r'{VIEWS_DIR / 'nlp_balanced.parquet'}')")
    print(f"   hotels = pd.read_parquet(r'{VIEWS_DIR / 'hotels.parquet'}')")


if __name__ == "__main__":
    main()
