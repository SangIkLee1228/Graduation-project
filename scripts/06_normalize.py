"""
06_normalize.py — 정규화 단계.
   - hotel_url에서 hotel_id (TripAdvisor 숫자 ID) 추출
   - property_dict 노이즈 키 제거 (userrating.prompt.*, ur_question.*)
   - sub-rating을 표준 6개 컬럼 + 2개 sparse 컬럼으로 평탄화
   - 텍스트 컷오프 (너무 짧거나 너무 긴 것 제거)
   - 정수 인덱싱을 위한 user_id, item_id 매핑 생성
   - 결과: hotelrec_normalized.parquet + id_maps.pkl

용도: 이후의 모든 가공의 출발점.
"""
import json
import pickle
import re
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "HotelRec.txt"
OUT_PARQUET = ROOT / "output" / "hotelrec_normalized.parquet"
OUT_MAPS = ROOT / "output" / "id_maps.pkl"

# --- 설정값 (필요에 맞게 조정) ---
MIN_TEXT_LEN = 50          # 50자 미만 텍스트는 제거
MAX_TEXT_LEN = 5000        # 5000자 초과는 잘라냄 (제거 아님)
BATCH_SIZE = 200_000

# 정상 sub-rating 키 (검증 결과 기반)
CANONICAL_KEYS = {
    "service", "cleanliness", "value", "location",
    "rooms", "sleep quality",
}
# 일부 호텔에만 존재하지만 의미 있는 키 — 별도 컬럼으로 유지
EXTRA_KEYS = {
    "check in / front desk", "business service (e.g., internet access)",
}
# 나머지 (userrating.prompt.*, ur_question.* 등) 노이즈는 폐기

HOTEL_ID_RE = re.compile(r"-d(\d+)-")


def clean_line(line: str) -> str:
    return line.strip().rstrip(",").strip("[]").strip()


def normalize_prop_dict(pd_: dict) -> dict:
    """sub-rating 표준화. 노이즈 키 제거."""
    if not isinstance(pd_, dict):
        return {}
    result = {}
    for k, v in pd_.items():
        k_low = k.lower().strip()
        if k_low in CANONICAL_KEYS or k_low in EXTRA_KEYS:
            try:
                result[k_low] = float(v)
            except (TypeError, ValueError):
                pass
        # 그 외는 폐기
    return result


def to_col_name(k: str) -> str:
    return "sub_" + k.replace(" ", "_").replace("/", "").replace("(", "").replace(")", "").replace(",", "").replace(".", "").replace("__", "_").strip("_")


SUB_COLS = [to_col_name(k) for k in sorted(CANONICAL_KEYS | EXTRA_KEYS)]

SCHEMA = pa.schema([
    ("hotel_id", pa.int64()),
    ("hotel_url", pa.string()),
    ("user_idx", pa.int32()),       # 정수 인코딩
    ("hotel_idx", pa.int32()),      # 정수 인코딩
    ("date", pa.string()),
    ("year", pa.int16()),
    ("rating", pa.float32()),
    ("title", pa.string()),
    ("text", pa.string()),
    ("text_len", pa.int32()),
    *[(c, pa.float32()) for c in SUB_COLS],
])


def main():
    if not DATA_PATH.exists():
        print(f"❌ 파일 없음: {DATA_PATH}")
        return

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    file_size = DATA_PATH.stat().st_size

    # --- Pass 1: user/hotel 인덱싱을 위한 매핑 작성 ---
    print("Pass 1/2: ID 매핑 생성")
    user2idx, hotel2idx = {}, {}
    pbar = tqdm(total=file_size, unit="B", unit_scale=True, desc="Pass 1", smoothing=0.1)
    with DATA_PATH.open("r", encoding="utf-8") as f:
        for raw in f:
            pbar.update(len(raw.encode("utf-8")))
            line = clean_line(raw)
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            url = r.get("hotel_url")
            author = r.get("author")
            if url and url not in hotel2idx:
                hotel2idx[url] = len(hotel2idx)
            if author and author not in user2idx:
                user2idx[author] = len(user2idx)
    pbar.close()
    print(f"  고유 호텔: {len(hotel2idx):,} | 고유 사용자: {len(user2idx):,}")

    # 매핑 저장
    with OUT_MAPS.open("wb") as f:
        pickle.dump({"user2idx": user2idx, "hotel2idx": hotel2idx}, f)
    print(f"  매핑 저장: {OUT_MAPS}\n")

    # --- Pass 2: 정규화 + Parquet 작성 ---
    print("Pass 2/2: 정규화 & Parquet 작성")
    writer = pq.ParquetWriter(OUT_PARQUET, SCHEMA, compression="zstd", compression_level=3)
    batch = []
    n_total = n_kept = n_text_short = n_text_truncated = 0

    pbar = tqdm(total=file_size, unit="B", unit_scale=True, desc="Pass 2", smoothing=0.1)
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
                continue

            text = r.get("text") or ""
            if len(text) < MIN_TEXT_LEN:
                n_text_short += 1
                continue
            if len(text) > MAX_TEXT_LEN:
                text = text[:MAX_TEXT_LEN]
                n_text_truncated += 1

            url = r.get("hotel_url") or ""
            m = HOTEL_ID_RE.search(url)
            hotel_id = int(m.group(1)) if m else 0

            date_str = r.get("date") or ""
            year = 0
            if len(date_str) >= 4 and date_str[:4].isdigit():
                year = int(date_str[:4])

            pd_normalized = normalize_prop_dict(r.get("property_dict"))
            sub_vals = {to_col_name(k): pd_normalized.get(k) for k in (CANONICAL_KEYS | EXTRA_KEYS)}

            rating = r.get("rating")
            if not isinstance(rating, (int, float)):
                continue

            row = {
                "hotel_id": hotel_id,
                "hotel_url": url,
                "user_idx": user2idx.get(r.get("author"), -1),
                "hotel_idx": hotel2idx.get(url, -1),
                "date": date_str,
                "year": year,
                "rating": float(rating),
                "title": r.get("title") or "",
                "text": text,
                "text_len": len(text),
                **sub_vals,
            }
            batch.append(row)
            n_kept += 1

            if len(batch) >= BATCH_SIZE:
                writer.write_table(pa.Table.from_pandas(pd.DataFrame(batch), schema=SCHEMA, preserve_index=False))
                batch.clear()

    if batch:
        writer.write_table(pa.Table.from_pandas(pd.DataFrame(batch), schema=SCHEMA, preserve_index=False))
    writer.close()
    pbar.close()

    out_size = OUT_PARQUET.stat().st_size / (1024 ** 3)
    print("\n" + "=" * 60)
    print("정규화 완료")
    print("=" * 60)
    print(f"입력 레코드:       {n_total:,}")
    print(f"보존:              {n_kept:,} ({n_kept/n_total*100:.1f}%)")
    print(f"텍스트 짧아서 제거: {n_text_short:,} (<{MIN_TEXT_LEN}자)")
    print(f"텍스트 잘림:       {n_text_truncated:,} (>{MAX_TEXT_LEN}자)")
    print(f"출력 크기:         {out_size:.2f} GB  (← 원본 47GB 대비 {out_size/47*100:.0f}%)")
    print(f"저장:              {OUT_PARQUET}")


if __name__ == "__main__":
    main()
