"""
03_sample.py — Reservoir Sampling으로 균등 랜덤 샘플을 추출합니다.
파일을 1회만 스트리밍하면서 메모리는 O(k)만 사용합니다.

사용법:
    python scripts/preprocessing/03_sample.py              # 기본 100,000건
    python scripts/preprocessing/03_sample.py --k 500000   # 500k건
    python scripts/preprocessing/03_sample.py --k 10000 --seed 7
"""
import argparse
import json
import random
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data/raw" / "HotelRec.txt"


def clean_line(line: str) -> str:
    return line.strip().rstrip(",").strip("[]").strip()


def reservoir_sample(path: Path, k: int, seed: int = 42):
    """k개 균등 랜덤 샘플. Algorithm R by Vitter."""
    rng = random.Random(seed)
    reservoir = []
    file_size = path.stat().st_size

    pbar = tqdm(
        total=file_size, unit="B", unit_scale=True, unit_divisor=1024,
        desc="샘플링 중", smoothing=0.1
    )
    n_seen = 0
    n_parse_err = 0

    try:
        with path.open("r", encoding="utf-8") as f:
            for raw in f:
                pbar.update(len(raw.encode("utf-8")))

                line = clean_line(raw)
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    n_parse_err += 1
                    continue

                if len(reservoir) < k:
                    reservoir.append(rec)
                else:
                    j = rng.randint(0, n_seen)
                    if j < k:
                        reservoir[j] = rec
                n_seen += 1
    finally:
        pbar.close()

    return reservoir, n_seen, n_parse_err


def main():
    ap = argparse.ArgumentParser(description="HotelRec Reservoir Sampling")
    ap.add_argument("--k", type=int, default=100_000, help="샘플 크기 (default: 100000)")
    ap.add_argument("--seed", type=int, default=42, help="난수 시드 (default: 42)")
    ap.add_argument("--out", type=str, default=None, help="출력 경로 (default: data/processed/sample_{k}.jsonl)")
    args = ap.parse_args()

    if not DATA_PATH.exists():
        print(f"❌ 파일 없음: {DATA_PATH}")
        return

    out_path = Path(args.out) if args.out else ROOT / "data/processed" / f"sample_{args.k}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"📂 입력: {DATA_PATH}")
    print(f"🎯 목표 샘플 수: {args.k:,}")
    print(f"🎲 시드: {args.seed}\n")

    sample, n_seen, n_err = reservoir_sample(DATA_PATH, args.k, args.seed)

    # JSON Lines 저장
    with out_path.open("w", encoding="utf-8") as f:
        for rec in sample:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\n✅ 추출 완료")
    print(f"  전체 검사 레코드: {n_seen:,}")
    print(f"  파싱 오류:        {n_err:,}")
    print(f"  추출된 샘플:      {len(sample):,}")
    print(f"  저장 위치:        {out_path}")


if __name__ == "__main__":
    main()
