"""
07_kcore_filter.py — K-core 필터링.
   사용자가 K번 이상 리뷰하고, 호텔도 K번 이상 받은 것만 남깁니다.
   협업 필터링·추천 시스템의 표준 전처리.

   K=5: 활성 사용자/호텔만 (가장 일반적)
   K=10: 더 dense
   K=20: 매우 dense (실험용)

사용법:
   python scripts/07_kcore_filter.py            # 기본 K=5
   python scripts/07_kcore_filter.py --k 10
"""
import argparse
from pathlib import Path

import duckdb  # pip install duckdb

ROOT = Path(__file__).resolve().parent.parent
IN_PATH = ROOT / "output" / "hotelrec_normalized.parquet"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5, help="K-core 값 (default: 5)")
    ap.add_argument("--max-iter", type=int, default=20, help="수렴 최대 반복 (default: 20)")
    args = ap.parse_args()

    if not IN_PATH.exists():
        print(f"❌ 입력 없음: {IN_PATH}")
        print("   먼저 06_normalize.py를 실행하세요.")
        return

    out_path = ROOT / "output" / f"hotelrec_kcore{args.k}.parquet"
    con = duckdb.connect()

    # 초기 카운트
    total = con.execute(f"SELECT COUNT(*) FROM '{IN_PATH}'").fetchone()[0]
    print(f"📂 입력: {IN_PATH}")
    print(f"📊 전체 레코드: {total:,}")
    print(f"🎯 K = {args.k}\n")

    # 반복적으로 user/hotel 활성도가 K 미만인 것 제거 (K-core는 fixed point)
    con.execute(f"""
        CREATE OR REPLACE TABLE r AS
        SELECT user_idx, hotel_idx, rating
        FROM '{IN_PATH}'
        WHERE user_idx >= 0 AND hotel_idx >= 0
    """)

    prev_n = -1
    for it in range(args.max_iter):
        cur_n = con.execute("SELECT COUNT(*) FROM r").fetchone()[0]
        print(f"  iter {it}: 남은 레코드 {cur_n:,}")
        if cur_n == prev_n:
            print(f"  수렴 완료 (iter {it})")
            break
        prev_n = cur_n

        con.execute(f"""
            CREATE OR REPLACE TABLE r AS
            WITH uc AS (SELECT user_idx, COUNT(*) c FROM r GROUP BY user_idx),
                 hc AS (SELECT hotel_idx, COUNT(*) c FROM r GROUP BY hotel_idx)
            SELECT r.*
            FROM r
            JOIN uc USING (user_idx)
            JOIN hc USING (hotel_idx)
            WHERE uc.c >= {args.k} AND hc.c >= {args.k}
        """)

    # 통계
    n_final = con.execute("SELECT COUNT(*) FROM r").fetchone()[0]
    n_users = con.execute("SELECT COUNT(DISTINCT user_idx) FROM r").fetchone()[0]
    n_hotels = con.execute("SELECT COUNT(DISTINCT hotel_idx) FROM r").fetchone()[0]
    density = n_final / (n_users * n_hotels) * 100 if n_users and n_hotels else 0

    # K-core 통과한 user/hotel만 추려서 원본의 모든 컬럼을 가져옴
    con.execute(f"""
        COPY (
            SELECT n.*
            FROM '{IN_PATH}' n
            JOIN (SELECT DISTINCT user_idx FROM r) u USING (user_idx)
            JOIN (SELECT DISTINCT hotel_idx FROM r) h USING (hotel_idx)
        ) TO '{out_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    print("\n" + "=" * 60)
    print(f"K-core (K={args.k}) 필터링 완료")
    print("=" * 60)
    print(f"보존 레코드:   {n_final:,} ({n_final/total*100:.2f}%)")
    print(f"보존 사용자:   {n_users:,}")
    print(f"보존 호텔:     {n_hotels:,}")
    print(f"행렬 밀도:     {density:.4f}%")
    out_size = out_path.stat().st_size / (1024 ** 2)
    print(f"출력 크기:     {out_size:.1f} MB")
    print(f"저장:          {out_path}")


if __name__ == "__main__":
    main()
