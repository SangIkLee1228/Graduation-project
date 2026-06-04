"""
10_extract_london.py — HotelRec.txt에서 런던(Greater London) 리뷰만 추출하여 JSON 파일 저장

필터 기준: hotel_url의 geo_id가 geo_stats.csv에서 location_slug에
          'London_England'를 포함하는 모든 항목과 일치하는 레코드

사용법:
    python scripts/10_extract_london.py
    python scripts/10_extract_london.py --out output/my_london.json
"""
import argparse
import json
import re
from pathlib import Path

import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "HotelRec.txt"
GEO_STATS = ROOT / "output" / "geo_stats.csv"

GEO_RE = re.compile(r"-g(\d+)-")


def clean_line(line: str) -> str:
    return line.strip().rstrip(",").strip("[]").strip()


def build_london_geo_set(geo_stats_path: Path) -> tuple[set[str], pd.DataFrame]:
    df = pd.read_csv(geo_stats_path, dtype={"geo_id": str})
    mask = df["location_slug"].str.contains("London_England", case=False, na=False)
    london_df = df[mask].copy()
    return set(london_df["geo_id"]), london_df


def main():
    ap = argparse.ArgumentParser(description="런던(Greater London) 리뷰 추출")
    ap.add_argument("--out", type=str, default=None, help="출력 경로 (default: output/london_reviews.json)")
    args = ap.parse_args()

    if not DATA_PATH.exists():
        print(f"❌ 데이터 파일 없음: {DATA_PATH}")
        return
    if not GEO_STATS.exists():
        print(f"❌ geo_stats.csv 없음: {GEO_STATS}")
        print("   먼저 scripts/09_geo_analysis.py를 실행하세요.")
        return

    out_path = Path(args.out) if args.out else ROOT / "output" / "london_reviews.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 런던 geo_id 세트 구성
    london_set, london_df = build_london_geo_set(GEO_STATS)
    expected_reviews = london_df["n_reviews"].sum()
    print(f"📍 런던(Greater London) geo_id 수: {len(london_set):,}")
    print(f"   포함 지역:")
    for _, row in london_df.nlargest(10, "n_reviews").iterrows():
        print(f"     {row['location_name']:<45} {row['n_reviews']:>8,}건")
    if len(london_df) > 10:
        rest = len(london_df) - 10
        print(f"     ... 외 {rest}개 지역")
    print(f"   예상 총 리뷰: {expected_reviews:,}건\n")

    # HotelRec.txt 스트리밍 → 런던 레코드 추출
    file_size = DATA_PATH.stat().st_size
    n_checked = 0
    n_matched = 0
    n_parse_err = 0

    pbar = tqdm(
        total=file_size, unit="B", unit_scale=True, unit_divisor=1024,
        desc="추출 중", smoothing=0.1,
    )

    with (
        DATA_PATH.open("r", encoding="utf-8") as fin,
        out_path.open("w", encoding="utf-8") as fout,
    ):
        fout.write("[\n")
        first_written = True

        try:
            for raw in fin:
                pbar.update(len(raw.encode("utf-8")))

                line = clean_line(raw)
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    n_parse_err += 1
                    continue

                n_checked += 1

                url = rec.get("hotel_url", "")
                m = GEO_RE.search(url)
                if not m:
                    continue
                if m.group(1) not in london_set:
                    continue

                # 런던 레코드 → JSON 배열에 추가
                if not first_written:
                    fout.write(",\n")
                fout.write(json.dumps(rec, ensure_ascii=False))
                first_written = False
                n_matched += 1
        finally:
            pbar.close()

        fout.write("\n]\n")

    out_size_mb = out_path.stat().st_size / (1024 ** 2)

    print(f"\n{'='*60}")
    print(f"추출 완료")
    print(f"{'='*60}")
    print(f"전체 검사 레코드: {n_checked:,}")
    print(f"파싱 오류:        {n_parse_err:,}")
    print(f"추출된 런던 리뷰: {n_matched:,}")
    print(f"출력 크기:        {out_size_mb:.1f} MB")
    print(f"저장 위치:        {out_path}")
    print(f"\n로드 예시:")
    print(f"  import json")
    print(f"  with open(r'{out_path}', encoding='utf-8') as f:")
    print(f"      data = json.load(f)  # list of dicts")
    print(f"  print(len(data))  # {n_matched:,}")


if __name__ == "__main__":
    main()
