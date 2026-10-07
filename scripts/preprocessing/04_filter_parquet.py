"""
04_filter_parquet.py — 조건에 맞는 레코드만 골라 Parquet으로 저장합니다.
   - 메모리 폭발 방지: 일정 크기(BATCH_SIZE)마다 디스크에 flush
   - Parquet은 원본 대비 5~10배 작고 pandas/Spark가 빠르게 로드

기본 필터:
   - text와 rating이 모두 존재
   - 텍스트 길이 >= 100자
   - 평점이 1.0 ~ 5.0 범위

필요 시 should_keep() 함수만 수정해 사용하세요.
"""
import json
import re
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data/raw" / "HotelRec.txt"
OUT_PATH = ROOT / "data/processed" / "hotelrec_filtered.parquet"

BATCH_SIZE = 200_000        # 이만큼 모이면 한 번 flush
MIN_TEXT_LEN = 100


def clean_line(line: str) -> str:
    return line.strip().rstrip(",").strip("[]").strip()


def should_keep(r: dict) -> bool:
    """필터 조건. 필요한 대로 자유롭게 수정하세요."""
    text = r.get("text")
    rating = r.get("rating")
    if not text or rating is None:
        return False
    if not isinstance(rating, (int, float)):
        return False
    if not (1.0 <= rating <= 5.0):
        return False
    if len(text) < MIN_TEXT_LEN:
        return False
    return True


HOTEL_ID_RE = re.compile(r"-d(\d+)-")


def transform(r: dict) -> dict:
    """레코드를 평탄화하고 hotel_id를 추출합니다."""
    url = r.get("hotel_url") or ""
    m = HOTEL_ID_RE.search(url)
    hotel_id = int(m.group(1)) if m else None

    pd_ = r.get("property_dict") or {}
    if not isinstance(pd_, dict):
        pd_ = {}

    return {
        "hotel_url": url,
        "hotel_id": hotel_id,
        "author": r.get("author"),
        "date": r.get("date"),
        "rating": float(r["rating"]),
        "title": r.get("title"),
        "text": r.get("text"),
        "text_len": len(r.get("text") or ""),
        "sub_sleep_quality": pd_.get("sleep quality"),
        "sub_value": pd_.get("value"),
        "sub_rooms": pd_.get("rooms"),
        "sub_service": pd_.get("service"),
        "sub_cleanliness": pd_.get("cleanliness"),
        "sub_location": pd_.get("location"),
    }


# Parquet 스키마 명시 → 타입 안정성 및 일관된 저장
SCHEMA = pa.schema([
    ("hotel_url", pa.string()),
    ("hotel_id", pa.int64()),
    ("author", pa.string()),
    ("date", pa.string()),  # 후속 단계에서 datetime으로 변환 가능
    ("rating", pa.float32()),
    ("title", pa.string()),
    ("text", pa.string()),
    ("text_len", pa.int32()),
    ("sub_sleep_quality", pa.float32()),
    ("sub_value", pa.float32()),
    ("sub_rooms", pa.float32()),
    ("sub_service", pa.float32()),
    ("sub_cleanliness", pa.float32()),
    ("sub_location", pa.float32()),
])


def flush(batch: list, writer: pq.ParquetWriter):
    df = pd.DataFrame(batch)
    # 누락 컬럼이 None이어도 schema에 맞춰 변환
    table = pa.Table.from_pandas(df, schema=SCHEMA, preserve_index=False)
    writer.write_table(table)


def main():
    if not DATA_PATH.exists():
        print(f"❌ 파일 없음: {DATA_PATH}")
        return

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_size = DATA_PATH.stat().st_size

    writer = pq.ParquetWriter(OUT_PATH, SCHEMA, compression="snappy")
    n_total = n_kept = n_err = 0
    batch = []

    pbar = tqdm(
        total=file_size, unit="B", unit_scale=True, unit_divisor=1024,
        desc="필터링 중", smoothing=0.1
    )

    try:
        with DATA_PATH.open("r", encoding="utf-8") as f:
            for raw in f:
                pbar.update(len(raw.encode("utf-8")))

                line = clean_line(raw)
                if not line:
                    continue
                n_total += 1
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    n_err += 1
                    continue

                if not should_keep(r):
                    continue

                batch.append(transform(r))
                n_kept += 1

                if len(batch) >= BATCH_SIZE:
                    flush(batch, writer)
                    batch.clear()

        # 남은 배치 flush
        if batch:
            flush(batch, writer)
    finally:
        pbar.close()
        writer.close()

    print("\n" + "=" * 60)
    print("필터링 완료")
    print("=" * 60)
    print(f"입력 레코드:    {n_total:,}")
    print(f"필터 통과:      {n_kept:,} ({n_kept/max(n_total,1)*100:.1f}%)")
    print(f"파싱 오류:      {n_err:,}")
    out_size = OUT_PATH.stat().st_size / (1024 ** 3)
    print(f"출력 크기:      {out_size:.2f} GB")
    print(f"저장 위치:      {OUT_PATH}")
    print(f"\n로드 예시:")
    print(f"  import pandas as pd")
    print(f"  df = pd.read_parquet(r'{OUT_PATH}')")


if __name__ == "__main__":
    main()
