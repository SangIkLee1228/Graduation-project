"""
09_geo_analysis.py — hotel_url의 geo_id·위치 슬러그를 이용한 지역별 분포 분석

TripAdvisor URL 구조:
    Hotel_Review-g{geo_id}-d{hotel_id}-Reviews-{HotelName}-{City_Region}.html
    e.g. Hotel_Review-g194775-d1121769-Reviews-Hotel_Baltic-Giulianova_Province_of_Teramo_Abruzzo.html

사용법:
    python scripts/analysis/09_geo_analysis.py                 # data/splits/hotels.parquet 사용 (빠름)
    python scripts/analysis/09_geo_analysis.py --full          # hotelrec_filtered.parquet 전체 (느림)
    python scripts/analysis/09_geo_analysis.py --raw           # HotelRec.txt 원본 직접 사용 (매우 느림)
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import duckdb
import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from tqdm import tqdm

# Windows Korean 폰트 설정
matplotlib.rcParams["font.family"] = ["Malgun Gothic", "AppleGothic", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "reports/eda/all"
VIEWS_DIR = ROOT / "data/splits"
DATA_PATH = ROOT / "data/raw" / "HotelRec.txt"

GEO_RE = re.compile(r"-g(\d+)-")
LOC_RE = re.compile(r"-([^-]+)\.html$")


# ──────────────────────────────────────────
# 데이터 로드 & geo 집계
# ──────────────────────────────────────────

def _clean_line(line: str) -> str:
    return line.strip().rstrip(",").strip("[]").strip()


def load_from_raw(path: Path) -> pd.DataFrame:
    """HotelRec.txt 전체를 스트리밍하며 geo_id 단위로 직접 집계합니다.
    레코드 전체가 아닌 집계 딕셔너리만 메모리에 유지하므로 메모리 효율적입니다."""
    file_size = path.stat().st_size
    # geo_id → {n_reviews, hotels(set), rating_sum, location_slug}
    geo_data: dict = defaultdict(lambda: {
        "n_reviews": 0, "hotels": set(), "rating_sum": 0.0, "location_slug": None
    })
    n_err = 0

    pbar = tqdm(total=file_size, unit="B", unit_scale=True,
                unit_divisor=1024, desc="원본 로드 중", smoothing=0.1)
    with path.open("r", encoding="utf-8") as f:
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

            url = r.get("hotel_url") or ""
            if not url:
                continue
            m_geo = GEO_RE.search(url)
            if not m_geo:
                continue
            geo_id = m_geo.group(1)

            g = geo_data[geo_id]
            g["n_reviews"] += 1
            g["hotels"].add(url)
            rating = r.get("rating")
            if isinstance(rating, (int, float)):
                g["rating_sum"] += float(rating)
            if g["location_slug"] is None:
                m_loc = LOC_RE.search(url)
                g["location_slug"] = m_loc.group(1) if m_loc else None
    pbar.close()

    if n_err:
        print(f"  파싱 오류 {n_err:,}건 건너뜀")

    rows = []
    for geo_id, g in geo_data.items():
        n_reviews = g["n_reviews"]
        rows.append({
            "geo_id": geo_id,
            "location_slug": g["location_slug"],
            "n_hotels": len(g["hotels"]),
            "n_reviews": n_reviews,
            "mean_rating": g["rating_sum"] / n_reviews if n_reviews else None,
        })
    geo = pd.DataFrame(rows)
    geo["location_name"] = geo["location_slug"].fillna("").str.replace("_", " ", regex=False)
    return geo


def _extract(url: str):
    m_geo = GEO_RE.search(url)
    m_loc = LOC_RE.search(url)
    return (m_geo.group(1) if m_geo else None,
            m_loc.group(1) if m_loc else None)


def load_from_hotels_parquet(path: Path) -> pd.DataFrame:
    """hotels.parquet (호텔별 집계) → geo_id 단위로 재집계"""
    print(f"📂 입력: {path}")
    df = pd.read_parquet(path, columns=["hotel_id", "hotel_url", "n_reviews", "mean_rating"])
    print(f"   호텔 수: {len(df):,}")

    geo_ids, loc_slugs = zip(*df["hotel_url"].map(lambda u: _extract(str(u))))
    df["geo_id"] = list(geo_ids)
    df["location_slug"] = list(loc_slugs)
    df = df.dropna(subset=["geo_id"])

    df["weighted_rating"] = df["mean_rating"] * df["n_reviews"]

    geo = (
        df.groupby("geo_id")
        .agg(
            n_hotels=("hotel_id", "count"),
            n_reviews=("n_reviews", "sum"),
            _wsum=("weighted_rating", "sum"),
            location_slug=("location_slug", "first"),
        )
        .reset_index()
    )
    geo["mean_rating"] = geo["_wsum"] / geo["n_reviews"]
    geo = geo.drop(columns=["_wsum"])
    geo["location_name"] = geo["location_slug"].str.replace("_", " ", regex=False)
    return geo


def load_from_filtered_parquet(path: Path) -> pd.DataFrame:
    """hotelrec_filtered.parquet → DuckDB로 geo_id 단위 집계 (20 GB, 수 분 소요)"""
    print(f"📂 입력 (전체): {path}")
    con = duckdb.connect()
    q = f"""
        SELECT
            regexp_extract(hotel_url, '-g(\\d+)-', 1)     AS geo_id,
            ANY_VALUE(
                regexp_extract(hotel_url, '-([^-]+)\\.html$', 1)
            )                                              AS location_slug,
            COUNT(DISTINCT hotel_url)                      AS n_hotels,
            COUNT(*)                                       AS n_reviews,
            AVG(rating)                                    AS mean_rating
        FROM read_parquet('{path}')
        WHERE hotel_url IS NOT NULL
          AND length(regexp_extract(hotel_url, '-g(\\d+)-', 1)) > 0
        GROUP BY geo_id
        ORDER BY n_reviews DESC
    """
    geo = con.execute(q).df()
    geo["location_name"] = geo["location_slug"].str.replace("_", " ", regex=False)
    return geo


def finalise(geo: pd.DataFrame) -> pd.DataFrame:
    """정렬·비중 컬럼 추가"""
    geo = geo.sort_values("n_reviews", ascending=False).reset_index(drop=True)
    total = geo["n_reviews"].sum()
    geo["review_pct"] = geo["n_reviews"] / total * 100
    return geo


# ──────────────────────────────────────────
# 차트
# ──────────────────────────────────────────

def _hbar(ax, labels, values, color, xlabel, title):
    ax.barh(labels[::-1], values[::-1], color=color)
    ax.set_xlabel(xlabel)
    ax.set_title(title, fontsize=13, weight="bold")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))


def save_charts(geo: pd.DataFrame):
    sns.set_theme(style="whitegrid")

    # 1) 리뷰 수 Top 30
    top30 = geo.head(30)
    fig, ax = plt.subplots(figsize=(14, 10))
    _hbar(ax, list(top30["location_name"]), list(top30["n_reviews"]),
          color="steelblue", xlabel="Number of Reviews", title="Top 30 Locations by Review Count (HotelRec)")
    for i, (n, pct) in enumerate(zip(reversed(top30["n_reviews"].tolist()),
                                     reversed(top30["review_pct"].tolist()))):
        ax.text(n * 1.005, i, f"{pct:.2f}%", va="center", fontsize=7.5)
    plt.tight_layout()
    p = OUT_DIR / "geo_top30_reviews.png"
    plt.savefig(p, dpi=120)
    plt.close()
    print(f"✅ 저장: {p}")

    # 2) 호텔 수 Top 30
    top30h = geo.nlargest(30, "n_hotels")
    fig, ax = plt.subplots(figsize=(14, 10))
    _hbar(ax, list(top30h["location_name"]), list(top30h["n_hotels"]),
          color="darkorange", xlabel="Number of Hotels", title="Top 30 Locations by Hotel Count (HotelRec)")
    plt.tight_layout()
    p = OUT_DIR / "geo_top30_hotels.png"
    plt.savefig(p, dpi=120)
    plt.close()
    print(f"✅ 저장: {p}")

    # 3) 평균 평점 (리뷰 수 기준 Top 20)
    top20 = geo.head(20)
    overall_mean = (geo["mean_rating"] * geo["n_reviews"]).sum() / geo["n_reviews"].sum()
    colors = ["#d62728" if r < 4.0 else "#2ca02c" if r >= 4.3 else "#1f77b4"
              for r in reversed(top20["mean_rating"].tolist())]
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.barh(list(reversed(top20["location_name"].tolist())),
            list(reversed(top20["mean_rating"].tolist())),
            color=colors)
    ax.set_xlabel("Mean Rating")
    ax.set_xlim(3.5, 5.0)
    ax.set_title("Mean Rating of Top 20 Locations by Review Count", fontsize=13, weight="bold")
    ax.axvline(x=overall_mean, color="black", linestyle="--", alpha=0.6,
               label=f"Weighted mean: {overall_mean:.2f}")
    ax.legend(fontsize=9)
    plt.tight_layout()
    p = OUT_DIR / "geo_rating_top20.png"
    plt.savefig(p, dpi=120)
    plt.close()
    print(f"✅ 저장: {p}")


# ──────────────────────────────────────────
# main
# ──────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="HotelRec 지역 분포 분석")
    ap.add_argument("--full", action="store_true",
                    help="hotelrec_filtered.parquet 전체를 사용 (수 분 소요)")
    ap.add_argument("--raw", action="store_true",
                    help="HotelRec.txt 원본을 직접 사용 (매우 느림, 사전 처리 불필요)")
    args = ap.parse_args()

    hotels_path = VIEWS_DIR / "hotels.parquet"
    filtered_path = ROOT / "data/processed/hotelrec_filtered.parquet"

    if args.raw:
        if not DATA_PATH.exists():
            print(f"❌ 데이터 파일 없음: {DATA_PATH}")
            return
        geo = load_from_raw(DATA_PATH)
        src_label = "HotelRec.txt (전체 원본)"
    elif not args.full and hotels_path.exists():
        geo = load_from_hotels_parquet(hotels_path)
        src_label = "hotels.parquet (k-core 필터 적용)"
    elif filtered_path.exists():
        geo = load_from_filtered_parquet(filtered_path)
        src_label = "hotelrec_filtered.parquet (전체 데이터)"
    else:
        print("❌ 입력 파일 없음. 먼저 04_filter_parquet.py 또는 08_make_views.py를 실행하거나 --raw 옵션을 사용하세요.")
        return

    geo = finalise(geo)
    print(f"   데이터 출처: {src_label}\n")

    # CSV 저장
    out_csv = OUT_DIR / "geo_stats.csv"
    geo.to_csv(out_csv, index=False, encoding="utf-8-sig")

    # 요약 출력
    print("=" * 75)
    print(f"집계 결과 요약")
    print("=" * 75)
    print(f"  고유 geo_id 수: {len(geo):,}")
    print(f"  총 리뷰 수:    {geo['n_reviews'].sum():,}")
    print(f"  총 호텔 수:    {geo['n_hotels'].sum():,}")
    print(f"  CSV 저장:      {out_csv}\n")

    print("=" * 75)
    print(f"{'순위':>4}  {'지역명':<38} {'호텔':>6} {'리뷰':>11} {'비중':>7} {'평점':>6}")
    print("=" * 75)
    for idx, row in geo.head(30).iterrows():
        name = row["location_name"]
        if len(name) > 38:
            name = name[:35] + "..."
        print(f"{idx+1:>4}  {name:<38} {row['n_hotels']:>6,} "
              f"{row['n_reviews']:>11,} {row['review_pct']:>6.2f}% {row['mean_rating']:>6.2f}")
    print("=" * 75)

    print()
    save_charts(geo)
    print(f"\n📁 모든 결과: {OUT_DIR}")


if __name__ == "__main__":
    main()
