"""
Semantic ID 분포 및 계층성 분석/시각화
"""

import json
from collections import Counter
import matplotlib.pyplot as plt

SEM_ID_PATH = "C:/Users/SANGIK/Graduation-project/data/hotel_semantic_ids.json"
PROFILE_PATH = "C:/Users/SANGIK/Graduation-project/data/hotel_profiles.json"
OUT_DIR = "C:/Users/SANGIK/Graduation-project/data/"

with open(SEM_ID_PATH, encoding="utf-8") as f:
    sem_ids = json.load(f)
with open(PROFILE_PATH, encoding="utf-8") as f:
    profiles = json.load(f)

c1_list, c2_list, c3_list = [], [], []
for url, info in sem_ids.items():
    c1, c2, c3, _ = info["semantic_id"]
    c1_list.append(c1)
    c2_list.append(c2)
    c3_list.append(c3)

# ── 1. Codebook 사용 분포 ──────────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(15, 4))
for ax, codes, title in zip(axes, [c1_list, c2_list, c3_list], ["c1", "c2", "c3"]):
    counter = Counter(codes)
    counts = sorted(counter.values(), reverse=True)
    ax.bar(range(len(counts)), counts)
    ax.set_title(f"{title} usage distribution\n(used {len(counter)}/256 codes)")
    ax.set_xlabel("code rank")
    ax.set_ylabel("count")
plt.tight_layout()
plt.savefig(OUT_DIR + "codebook_distribution.png", dpi=120)
plt.close()
print("저장: codebook_distribution.png")

for name, codes in [("c1", c1_list), ("c2", c2_list), ("c3", c3_list)]:
    counter = Counter(codes)
    print(f"{name}: 사용된 코드 {len(counter)}/256, 최대 사용 빈도 {max(counter.values())}, 최소 1")

# ── 2. 계층성: 같은 c1을 공유하는 호텔들이 의미적으로 유사한가 ──────
print("\n=== 계층성 확인: c1=가장 빈번한 코드 그룹의 호텔 프로파일 일부 ===")
counter_c1 = Counter(c1_list)
top_c1, top_count = counter_c1.most_common(1)[0]
print(f"c1={top_c1} (총 {top_count}개 호텔) 중 5개 샘플:\n")

shown = 0
for url, info in sem_ids.items():
    if info["semantic_id"][0] == top_c1:
        name = info["hotel_name"]
        profile_text = profiles[url]["profile"][:150]
        print(f"- {name}\n  ID: {info['semantic_id_str']}\n  Profile: {profile_text}...\n")
        shown += 1
        if shown >= 5:
            break

# ── 3. 같은 c1, c2를 공유하는 호텔 (더 세밀한 그룹) ──────────────
print("\n=== 같은 (c1, c2) 그룹 비교 ===")
pair_counter = Counter((c1, c2) for c1, c2 in zip(c1_list, c2_list))
top_pair, top_pair_count = pair_counter.most_common(1)[0]
print(f"(c1,c2)={top_pair} (총 {top_pair_count}개 호텔) 중 5개 샘플:\n")

shown = 0
for url, info in sem_ids.items():
    c1, c2, c3, _ = info["semantic_id"]
    if (c1, c2) == top_pair:
        name = info["hotel_name"]
        profile_text = profiles[url]["profile"][:150]
        print(f"- {name}\n  ID: {info['semantic_id_str']}\n  Profile: {profile_text}...\n")
        shown += 1
        if shown >= 5:
            break

# ── 4. (c1, c2) 그룹 크기 분포 시각화 ─────────────────────────────
fig, ax = plt.subplots(figsize=(8, 4))
group_sizes = sorted(pair_counter.values(), reverse=True)
ax.bar(range(len(group_sizes)), group_sizes)
ax.set_title(f"(c1,c2) group size distribution\n({len(pair_counter)} unique pairs)")
ax.set_xlabel("group rank")
ax.set_ylabel("hotel count")
plt.tight_layout()
plt.savefig(OUT_DIR + "c1c2_group_sizes.png", dpi=120)
plt.close()
print("저장: c1c2_group_sizes.png")
