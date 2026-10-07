"""
호텔 Semantic ID 생성
: hotel_profiles.json의 profile 텍스트를 임베딩 후
  3-level Residual Quantization으로 계층적 discrete ID 부여

출력: semantic_ids/rq_kmeans/artifacts/hotel_semantic_ids_twkim.json
"""

import json
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans

ROOT = Path(__file__).resolve().parents[2]

PROFILES_PATH = ROOT / "data/hotel_profiles.json"
OUTPUT_PATH   = ROOT / "semantic_ids/rq_kmeans/artifacts/hotel_semantic_ids_twkim.json"

K      = 16   # codebook 크기 (각 level마다)
LEVELS = 3    # RQ depth
MODEL  = "all-MiniLM-L6-v2"


def residual_quantize(embeddings: np.ndarray, k: int, levels: int):
    """3-level residual quantization. 각 level에서 residual을 K-means로 양자화."""
    codes = []
    centroids_list = []
    residual = embeddings.copy()

    for _ in range(levels):
        km = KMeans(n_clusters=k, random_state=42, n_init="auto")
        km.fit(residual)
        c = km.labels_
        centroids = km.cluster_centers_
        residual = residual - centroids[c]
        codes.append(c)
        centroids_list.append(centroids)

    return codes, centroids_list, residual


def main():
    with open(PROFILES_PATH, encoding="utf-8") as f:
        hotel_profiles = json.load(f)

    keys = list(hotel_profiles.keys())
    texts = [hotel_profiles[k]["profile"] for k in keys]

    print(f"호텔 수: {len(keys)}")
    print("임베딩 중...")
    model = SentenceTransformer(MODEL)
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=64)
    print(f"임베딩 shape: {embeddings.shape}")

    print("Residual Quantization 수행 중...")
    codes, _, final_residual = residual_quantize(embeddings, K, LEVELS)

    # Local Rank: 같은 [c1,c2,c3]를 공유하는 그룹 내에서 최종 잔차 L2 norm 오름차순 순위
    from collections import defaultdict
    group_indices = defaultdict(list)
    for i in range(len(keys)):
        sid_tuple = tuple(int(codes[lvl][i]) for lvl in range(LEVELS))
        group_indices[sid_tuple].append(i)

    local_ranks = np.zeros(len(keys), dtype=int)
    norms = np.linalg.norm(final_residual, axis=1)
    for indices in group_indices.values():
        for rank, i in enumerate(sorted(indices, key=lambda x: norms[x])):
            local_ranks[i] = rank

    results = {}
    for i, key in enumerate(keys):
        sid = [int(codes[lvl][i]) for lvl in range(LEVELS)] + [int(local_ranks[i])]
        results[key] = {
            "hotel_id":       hotel_profiles[key]["hotel_id"],
            "hotel_name":     hotel_profiles[key]["hotel_name"],
            "semantic_id":    sid,
            "semantic_id_str": "-".join(map(str, sid)),
        }

    out = Path(OUTPUT_PATH)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n완료: {out}  ({len(results)}개 호텔)")

    # 간단한 분포 확인
    l1_counts = np.bincount(codes[0], minlength=K)
    print(f"\nL1 cluster 분포 (min/max/mean): "
          f"{l1_counts.min()} / {l1_counts.max()} / {l1_counts.mean():.1f}")


if __name__ == "__main__":
    main()
