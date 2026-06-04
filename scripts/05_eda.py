"""
05_eda.py — EDA를 수행하고 차트를 저장합니다.

사용법:
    python scripts/05_eda.py --src raw                                              # 전체 원본 데이터 (느림)
    python scripts/05_eda.py --src parquet                                          # 04번 Parquet 파일
    python scripts/05_eda.py --src jsonl                                            # 03번 샘플 JSONL
    python scripts/05_eda.py --src jsonl --in eda-alldata-output/sample_100000.jsonl
"""
import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "eda-alldata-output"
DATA_PATH = ROOT / "data" / "HotelRec.txt"


def _clean_line(line: str) -> str:
    return line.strip().rstrip(",").strip("[]").strip()


def load_raw() -> pd.DataFrame:
    """HotelRec.txt 전체를 스트리밍하며 EDA에 필요한 컬럼만 추출합니다.
    전체 text는 저장하지 않고 text_len만 보관해 메모리 사용량을 줄입니다."""
    file_size = DATA_PATH.stat().st_size
    ratings, text_lens, dates = [], [], []
    sub_service, sub_cleanliness, sub_value = [], [], []
    sub_location, sub_rooms, sub_sleep_quality = [], [], []
    n_err = 0

    pbar = tqdm(total=file_size, unit="B", unit_scale=True,
                unit_divisor=1024, desc="원본 로드 중", smoothing=0.1)
    with DATA_PATH.open("r", encoding="utf-8") as f:
        for raw in f:
            pbar.update(len(raw.encode("utf-8")))
            line = _clean_line(raw)
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                n_err += 1
                continue

            pd_ = r.get("property_dict") or {}
            if not isinstance(pd_, dict):
                pd_ = {}

            ratings.append(r.get("rating"))
            text_lens.append(len(r.get("text") or ""))
            dates.append(r.get("date"))
            sub_service.append(pd_.get("service"))
            sub_cleanliness.append(pd_.get("cleanliness"))
            sub_value.append(pd_.get("value"))
            sub_location.append(pd_.get("location"))
            sub_rooms.append(pd_.get("rooms"))
            sub_sleep_quality.append(pd_.get("sleep quality"))
    pbar.close()

    if n_err:
        print(f"  파싱 오류 {n_err:,}건 건너뜀")

    return pd.DataFrame({
        "rating": ratings,
        "text_len": text_lens,
        "date": dates,
        "sub_service": sub_service,
        "sub_cleanliness": sub_cleanliness,
        "sub_value": sub_value,
        "sub_location": sub_location,
        "sub_rooms": sub_rooms,
        "sub_sleep_quality": sub_sleep_quality,
    })


def load_jsonl(path: Path) -> pd.DataFrame:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    df = pd.DataFrame(rows)
    # property_dict 평탄화
    if "property_dict" in df.columns:
        pd_df = pd.json_normalize(df["property_dict"].apply(lambda x: x if isinstance(x, dict) else {}))
        pd_df.columns = [f"sub_{c.replace(' ', '_')}" for c in pd_df.columns]
        df = pd.concat([df.drop(columns=["property_dict"]), pd_df], axis=1)
    df["text_len"] = df["text"].fillna("").str.len()
    return df


def main():
    ap = argparse.ArgumentParser(description="HotelRec EDA")
    ap.add_argument("--src", choices=["jsonl", "parquet", "raw"], default="jsonl")
    ap.add_argument("--in", dest="input", type=str, default=None, help="입력 파일 경로 (raw 모드에서는 무시)")
    args = ap.parse_args()

    # 입력 로드
    if args.src == "raw":
        if not DATA_PATH.exists():
            print(f"❌ 데이터 파일 없음: {DATA_PATH}")
            return
        print(f"📂 입력: {DATA_PATH} (전체 원본)")
        df = load_raw()
    else:
        if args.input:
            in_path = Path(args.input)
        elif args.src == "jsonl":
            candidates = sorted(OUT_DIR.glob("sample_*.jsonl"))
            if not candidates:
                print("❌ 샘플 파일이 없습니다. 먼저 03_sample.py를 실행하세요.")
                return
            in_path = candidates[-1]
        else:
            in_path = OUT_DIR / "hotelrec_filtered.parquet"

        if not in_path.exists():
            print(f"❌ 입력 파일 없음: {in_path}")
            return

        print(f"📂 입력: {in_path}")
        if args.src == "jsonl":
            df = load_jsonl(in_path)
        else:
            df = pd.read_parquet(in_path)

    print(f"📊 로드 완료: {len(df):,} rows × {len(df.columns)} cols\n")
    print(df.dtypes, "\n")

    # 기본 통계
    print("=" * 60)
    print("기본 통계")
    print("=" * 60)
    print(f"평점 평균: {df['rating'].mean():.2f}")
    print(f"평점 표준편차: {df['rating'].std():.2f}")
    print(f"텍스트 길이 평균: {df['text_len'].mean():.0f}자")
    print(f"텍스트 길이 중앙값: {df['text_len'].median():.0f}자\n")

    sns.set_theme(style="whitegrid")

    # 1) 평점 분포
    fig, ax = plt.subplots(figsize=(7, 4))
    df["rating"].value_counts().sort_index().plot(kind="bar", ax=ax, color="steelblue")
    ax.set_title("Rating Distribution")
    ax.set_xlabel("Rating")
    ax.set_ylabel("Count")
    plt.tight_layout()
    p = OUT_DIR / "eda_rating_dist.png"
    plt.savefig(p, dpi=120)
    plt.close()
    print(f"✅ 저장: {p}")

    # 2) 텍스트 길이 히스토그램 (이상치 제외)
    cap = df["text_len"].quantile(0.99)
    fig, ax = plt.subplots(figsize=(7, 4))
    df[df["text_len"] <= cap]["text_len"].hist(bins=60, ax=ax, color="seagreen")
    ax.set_title(f"Text length (≤ 99th percentile = {int(cap)} chars)")
    ax.set_xlabel("Characters")
    plt.tight_layout()
    p = OUT_DIR / "eda_text_length.png"
    plt.savefig(p, dpi=120)
    plt.close()
    print(f"✅ 저장: {p}")

    # 3) 연도별 리뷰 수
    if "date" in df.columns:
        df["year"] = pd.to_datetime(df["date"], errors="coerce").dt.year
        yc = df["year"].value_counts().sort_index()
        fig, ax = plt.subplots(figsize=(8, 4))
        yc.plot(kind="bar", ax=ax, color="coral")
        ax.set_title("Reviews per Year")
        ax.set_xlabel("Year")
        plt.tight_layout()
        p = OUT_DIR / "eda_year_dist.png"
        plt.savefig(p, dpi=120)
        plt.close()
        print(f"✅ 저장: {p}")

    # 4) 서브 평점 평균
    sub_cols = [c for c in df.columns if c.startswith("sub_")]
    if sub_cols:
        means = df[sub_cols].mean().sort_values()
        fig, ax = plt.subplots(figsize=(7, 4))
        means.plot(kind="barh", ax=ax, color="indigo")
        ax.set_title("Sub-rating averages")
        ax.set_xlabel("Mean rating")
        plt.tight_layout()
        p = OUT_DIR / "eda_sub_ratings.png"
        plt.savefig(p, dpi=120)
        plt.close()
        print(f"✅ 저장: {p}")

    print(f"\n📁 모든 결과: {OUT_DIR}")


if __name__ == "__main__":
    main()
