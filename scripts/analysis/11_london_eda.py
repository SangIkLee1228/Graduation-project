"""
11_london_eda.py — 10_extract_london.py 결과물(london_reviews.json)을 로드해
런던 호텔 리뷰 데이터의 탐색적 데이터 분석(EDA)을 수행하고 차트를 저장합니다.

생성 차트 (reports/eda/london/ 폴더):
    london_eda_rating_dist.png   — 평점 분포
    london_eda_text_length.png   — 텍스트 길이 히스토그램
    london_eda_year_dist.png     — 연도별 리뷰 수
    london_eda_sub_ratings.png   — 서브 평점 평균 (service, cleanliness 등)
    london_eda_top_hotels.png    — 리뷰 수 Top 20 호텔

사용법:
    python scripts/analysis/11_london_eda.py
    python scripts/analysis/11_london_eda.py --in data/processed/london_reviews.json
"""
import argparse
import json
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

# Windows Korean 폰트 설정
matplotlib.rcParams["font.family"] = ["Malgun Gothic", "AppleGothic", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "reports/eda/london"
DEFAULT_IN = ROOT / "data/processed/london_reviews.json"


def load_london(path: Path) -> pd.DataFrame:
    print(f"📂 입력: {path}")
    with path.open("r", encoding="utf-8") as f:
        records = json.load(f)
    df = pd.DataFrame(records)

    # property_dict 평탄화
    if "property_dict" in df.columns:
        pd_df = pd.json_normalize(
            df["property_dict"].apply(lambda x: x if isinstance(x, dict) else {})
        )
        pd_df.columns = [f"sub_{c.replace(' ', '_')}" for c in pd_df.columns]
        df = pd.concat([df.drop(columns=["property_dict"]), pd_df], axis=1)

    df["text_len"] = df["text"].fillna("").str.len()
    return df


def main():
    ap = argparse.ArgumentParser(description="런던 호텔 리뷰 EDA")
    ap.add_argument("--in", dest="input", type=str, default=None, help="입력 JSON 경로")
    args = ap.parse_args()

    in_path = Path(args.input) if args.input else DEFAULT_IN
    if not in_path.exists():
        print(f"❌ 입력 파일 없음: {in_path}")
        print("   먼저 scripts/preprocessing/10_extract_london.py를 실행하세요.")
        return

    df = load_london(in_path)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    n_reviews = len(df)
    n_hotels = df["hotel_url"].nunique() if "hotel_url" in df.columns else 0
    print(f"📊 로드 완료: {n_reviews:,} 리뷰 / {n_hotels:,} 호텔\n")

    # 기본 통계 출력
    print("=" * 60)
    print("기본 통계 (런던)")
    print("=" * 60)
    if "rating" in df.columns:
        print(f"평점 평균:      {df['rating'].mean():.2f}")
        print(f"평점 표준편차:  {df['rating'].std():.2f}")
    print(f"텍스트 길이 평균:   {df['text_len'].mean():.0f}자")
    print(f"텍스트 길이 중앙값: {df['text_len'].median():.0f}자")
    print()

    sns.set_theme(style="whitegrid")

    # 1) 평점 분포
    if "rating" in df.columns:
        fig, ax = plt.subplots(figsize=(7, 4))
        df["rating"].value_counts().sort_index().plot(kind="bar", ax=ax, color="steelblue")
        ax.set_title("London — Rating Distribution")
        ax.set_xlabel("Rating")
        ax.set_ylabel("Count")
        plt.tight_layout()
        p = OUT_DIR / "london_eda_rating_dist.png"
        plt.savefig(p, dpi=120)
        plt.close()
        print(f"✅ 저장: {p}")

    # 2) 텍스트 길이 히스토그램
    cap = df["text_len"].quantile(0.99)
    fig, ax = plt.subplots(figsize=(7, 4))
    df[df["text_len"] <= cap]["text_len"].hist(bins=60, ax=ax, color="seagreen")
    ax.set_title(f"London — Text length (≤ 99th pct = {int(cap)} chars)")
    ax.set_xlabel("Characters")
    plt.tight_layout()
    p = OUT_DIR / "london_eda_text_length.png"
    plt.savefig(p, dpi=120)
    plt.close()
    print(f"✅ 저장: {p}")

    # 3) 연도별 리뷰 수
    if "date" in df.columns:
        df["year"] = pd.to_datetime(df["date"], errors="coerce").dt.year
        yc = df["year"].value_counts().sort_index()
        fig, ax = plt.subplots(figsize=(8, 4))
        yc.plot(kind="bar", ax=ax, color="coral")
        ax.set_title("London — Reviews per Year")
        ax.set_xlabel("Year")
        plt.tight_layout()
        p = OUT_DIR / "london_eda_year_dist.png"
        plt.savefig(p, dpi=120)
        plt.close()
        print(f"✅ 저장: {p}")

    # 4) 서브 평점 평균
    sub_cols = [c for c in df.columns if c.startswith("sub_")]
    if sub_cols:
        means = df[sub_cols].mean().sort_values()
        fig, ax = plt.subplots(figsize=(7, 4))
        means.plot(kind="barh", ax=ax, color="indigo")
        ax.set_title("London — Sub-rating averages")
        ax.set_xlabel("Mean rating")
        plt.tight_layout()
        p = OUT_DIR / "london_eda_sub_ratings.png"
        plt.savefig(p, dpi=120)
        plt.close()
        print(f"✅ 저장: {p}")

    # 5) 리뷰 수 Top 20 호텔
    if "hotel_url" in df.columns:
        import re
        hotel_id_re = re.compile(r"-d(\d+)-")

        def extract_hotel_id(url):
            m = hotel_id_re.search(str(url))
            return int(m.group(1)) if m else None

        df["hotel_id"] = df["hotel_url"].map(extract_hotel_id)
        top20 = (
            df.groupby("hotel_id")
            .agg(n_reviews=("rating", "count"), mean_rating=("rating", "mean"))
            .nlargest(20, "n_reviews")
            .reset_index()
        )
        fig, ax = plt.subplots(figsize=(10, 6))
        labels = [f"hotel {hid}" for hid in top20["hotel_id"]]
        ax.barh(labels[::-1], top20["n_reviews"].tolist()[::-1], color="teal")
        ax.set_xlabel("Number of Reviews")
        ax.set_title("London — Top 20 Hotels by Review Count")
        plt.tight_layout()
        p = OUT_DIR / "london_eda_top_hotels.png"
        plt.savefig(p, dpi=120)
        plt.close()
        print(f"✅ 저장: {p}")

    print(f"\n📁 모든 결과: {OUT_DIR}")


if __name__ == "__main__":
    main()
