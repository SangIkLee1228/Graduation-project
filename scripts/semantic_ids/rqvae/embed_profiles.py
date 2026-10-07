"""
호텔 프로파일 텍스트 -> Sentence-T5 임베딩
"""

from pathlib import Path

import json
import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS_DIR = ROOT / "artifacts/semantic_ids/rqvae"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

INPUT_PATH  = ROOT / "data/processed/hotel_profiles.json"
OUTPUT_EMB_PATH  = ARTIFACTS_DIR / "hotel_embeddings.npy"
OUTPUT_IDS_PATH  = ARTIFACTS_DIR / "hotel_embedding_ids.json"

MODEL_NAME = "sentence-t5-base"


def main():
    print("프로파일 데이터 로딩 중...")
    with open(INPUT_PATH, encoding="utf-8") as f:
        profiles = json.load(f)

    hotel_urls = list(profiles.keys())
    texts = [profiles[url]["profile"] for url in hotel_urls]
    print(f"총 {len(texts)}개 호텔 프로파일")

    print(f"\n{MODEL_NAME} 모델 로딩 중...")
    model = SentenceTransformer(MODEL_NAME)

    print("\n임베딩 생성 중...")
    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=False,
    )

    print(f"\n임베딩 shape: {embeddings.shape}")

    # 저장
    np.save(OUTPUT_EMB_PATH, embeddings)

    # hotel_url 순서를 별도 저장 (임베딩 행 순서와 매칭용)
    id_mapping = [
        {"index": i, "hotel_url": url, "hotel_id": profiles[url]["hotel_id"], "hotel_name": profiles[url]["hotel_name"]}
        for i, url in enumerate(hotel_urls)
    ]
    with open(OUTPUT_IDS_PATH, "w", encoding="utf-8") as f:
        json.dump(id_mapping, f, ensure_ascii=False, indent=2)

    print(f"\n[DONE] 임베딩 저장 -> {OUTPUT_EMB_PATH}")
    print(f"[DONE] ID 매핑 저장 -> {OUTPUT_IDS_PATH}")


if __name__ == "__main__":
    main()
