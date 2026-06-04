"""
01_peek.py — HotelRec.txt의 앞 N건만 읽어 스키마와 샘플을 출력합니다.

사용법:
    python scripts/01_peek.py
    python scripts/01_peek.py --n 50
"""
import argparse
import json
from pathlib import Path

# 프로젝트 루트 = 이 파일의 부모의 부모 (scripts/.. = project_root)
ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "HotelRec.txt"


def clean_line(line: str) -> str:
    """전체 JSON 배열로 감싸인 파일에서 한 줄을 안전하게 분리."""
    return line.strip().rstrip(",").strip("[]").strip()


def peek(path: Path, n: int = 100):
    records = []
    with path.open("r", encoding="utf-8") as f:
        for i, raw in enumerate(f):
            if len(records) >= n:
                break
            line = clean_line(raw)
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[line {i}] 파싱 실패: {e}")
    return records


def main():
    ap = argparse.ArgumentParser(description="HotelRec 앞 N건 미리보기")
    ap.add_argument("--n", type=int, default=100, help="읽을 줄 수 (default: 100)")
    args = ap.parse_args()

    if not DATA_PATH.exists():
        print(f"❌ 파일을 찾을 수 없습니다: {DATA_PATH}")
        print("   data/ 폴더에 HotelRec.txt가 있는지 확인하세요.")
        return

    print(f"📂 파일: {DATA_PATH}")
    size_gb = DATA_PATH.stat().st_size / (1024 ** 3)
    print(f"📏 크기: {size_gb:.2f} GB\n")

    records = peek(DATA_PATH, n=args.n)
    print(f"✅ 정상 파싱: {len(records)}건\n")

    if not records:
        return

    # 키 집합
    all_keys = set()
    for r in records:
        all_keys.update(r.keys())
    print("🔑 발견된 키:", sorted(all_keys), "\n")

    # property_dict 서브키
    prop_keys = set()
    for r in records:
        pd_ = r.get("property_dict") or {}
        prop_keys.update(pd_.keys())
    print("🏨 property_dict 서브키:", sorted(prop_keys), "\n")

    # 첫 레코드 예시
    print("📝 첫 레코드:")
    print(json.dumps(records[0], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
