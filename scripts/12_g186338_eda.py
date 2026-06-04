"""
12_g186338_eda.py — geo_id g186338 (London England 중심부) 단독 EDA

eda-london-output/london_reviews.json (46개 geo_id, 836,435건) 에서
hotel_url에 -g186338- 이 포함된 레코드만 필터링해 EDA 차트를 저장합니다.
기존 eda-london-output/ 파일은 변경하지 않습니다.

생성 차트 (eda-london-g186338-output/ 폴더):
    g186338_eda_rating_dist.png   — 평점 분포
    g186338_eda_text_length.png   — 텍스트 길이 히스토그램
    g186338_eda_year_dist.png     — 연도별 리뷰 수
    g186338_eda_sub_ratings.png   — 서브 평점 평균
    g186338_eda_top_hotels.png    — 리뷰 수 Top 20 호텔

사용법:
    python scripts/12_g186338_eda.py
"""
import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parent.parent
IN_PATH = ROOT / "eda-london-output" / "london_reviews.json"
OUT_DIR = ROOT / "eda-london-g186338-output"

GEO_RE = re.compile(r"-g(\d+)-")
HOTEL_ID_RE = re.compile(r"-d(\d+)-")
TARGET_GEO = "186338"


def load_g186338(path: Path) -> pd.DataFrame:
    print(f"📂 입력: {path}")
    with path.open("r", encoding="utf-8") as f:
        records = json.load(f)
    print(f"   전체 로드: {len(records):,}건")

    filtered = [
        r for r in records
        if (m := GEO_RE.search(r.get("hotel_url") or "")) and m.group(1) == TARGET_GEO
    ]
    print(f"   g186338 필터링 후: {len(filtered):,}건")

    df = pd.DataFrame(filtered)

    if "property_dict" in df.columns:
        pd_df = pd.json_normalize(
            df["property_dict"].apply(lambda x: x if isinstance(x, dict) else {})
        )
        pd_df.columns = [f"sub_{c.replace(' ', '_')}" for c in pd_df.columns]
        df = pd.concat([df.drop(columns=["property_dict"]), pd_df], axis=1)

    df["text_len"] = df["text"].fillna("").str.len()
    return df


def main():
    if not IN_PATH.exists():
        print(f"❌ 입력 파일 없음: {IN_PATH}")
        print("   먼저 scripts/10_extract_london.py를 실행하세요.")
        return

    df = load_g186338(IN_PATH)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    n_reviews = len(df)
    n_hotels = df["hotel_url"].nunique() if "hotel_url" in df.columns else 0
    print(f"\n📊 g186338 통계")
    print("=" * 60)
    print(f"리뷰 수:            {n_reviews:,}")
    print(f"호텔 수:            {n_hotels:,}")
    if "rating" in df.columns:
        print(f"평점 평균:          {df['rating'].mean():.2f}")
        print(f"평점 표준편차:      {df['rating'].std():.2f}")
    print(f"텍스트 길이 평균:   {df['text_len'].mean():.0f}자")
    print(f"텍스트 길이 중앙값: {df['text_len'].median():.0f}자")
    print()

    sns.set_theme(style="whitegrid")

    # 1) 평점 분포
    if "rating" in df.columns:
        fig, ax = plt.subplots(figsize=(7, 4))
        df["rating"].value_counts().sort_index().plot(kind="bar", ax=ax, color="steelblue")
        ax.set_title("London g186338 — Rating Distribution")
        ax.set_xlabel("Rating")
        ax.set_ylabel("Count")
        plt.tight_layout()
        p = OUT_DIR / "g186338_eda_rating_dist.png"
        plt.savefig(p, dpi=120)
        plt.close()
        print(f"✅ 저장: {p}")

    # 2) 텍스트 길이 히스토그램
    cap = df["text_len"].quantile(0.99)
    fig, ax = plt.subplots(figsize=(7, 4))
    df[df["text_len"] <= cap]["text_len"].hist(bins=60, ax=ax, color="seagreen")
    ax.set_title(f"London g186338 — Text length (≤ 99th pct = {int(cap)} chars)")
    ax.set_xlabel("Characters")
    plt.tight_layout()
    p = OUT_DIR / "g186338_eda_text_length.png"
    plt.savefig(p, dpi=120)
    plt.close()
    print(f"✅ 저장: {p}")

    # 3) 연도별 리뷰 수
    if "date" in df.columns:
        df["year"] = pd.to_datetime(df["date"], errors="coerce").dt.year
        yc = df["year"].value_counts().sort_index()
        fig, ax = plt.subplots(figsize=(8, 4))
        yc.plot(kind="bar", ax=ax, color="coral")
        ax.set_title("London g186338 — Reviews per Year")
        ax.set_xlabel("Year")
        plt.tight_layout()
        p = OUT_DIR / "g186338_eda_year_dist.png"
        plt.savefig(p, dpi=120)
        plt.close()
        print(f"✅ 저장: {p}")

    # 4) 서브 평점 평균
    sub_cols = [c for c in df.columns if c.startswith("sub_")]
    if sub_cols:
        means = df[sub_cols].mean().sort_values()
        fig, ax = plt.subplots(figsize=(7, 4))
        means.plot(kind="barh", ax=ax, color="indigo")
        ax.set_title("London g186338 — Sub-rating averages")
        ax.set_xlabel("Mean rating")
        plt.tight_layout()
        p = OUT_DIR / "g186338_eda_sub_ratings.png"
        plt.savefig(p, dpi=120)
        plt.close()
        print(f"✅ 저장: {p}")

    # 5) 리뷰 수 Top 20 호텔
    if "hotel_url" in df.columns:
        def extract_hotel_id(url):
            m = HOTEL_ID_RE.search(str(url))
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
        ax.set_title("London g186338 — Top 20 Hotels by Review Count")
        plt.tight_layout()
        p = OUT_DIR / "g186338_eda_top_hotels.png"
        plt.savefig(p, dpi=120)
        plt.close()
        print(f"✅ 저장: {p}")

    print(f"\n📁 모든 결과: {OUT_DIR}")


if __name__ == "__main__":
    main()
