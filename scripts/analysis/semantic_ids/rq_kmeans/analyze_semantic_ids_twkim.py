"""
Semantic ID 성질 분석 및 시각화
: artifacts/semantic_ids/rq_kmeans/hotel_semantic_ids_twkim.json 기반

생성 파일 (analysis/ 폴더):
  fig1_l1_distribution.png   - L1 클러스터별 호텔 수
  fig2_l1_avg_rating.png     - L1 클러스터별 평균 평점 ± std
  fig3_l1_rating_boxplot.png - L1 클러스터별 평점 분포 (box plot)
  fig4_l1l2_heatmap.png      - L1×L2 co-occurrence heatmap
  fig5_id_uniqueness.png     - 전체 ID [c1,c2,c3,c4] 고유성 분석
  fig6_tsne.png              - t-SNE 2D projection (L1 색상)
"""

import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import seaborn as sns
from collections import Counter
from pathlib import Path

sns.set_theme(style="whitegrid", font_scale=1.1)
PALETTE = sns.color_palette("tab20", 16)

ROOT = Path(__file__).resolve().parents[4]

SIDS_PATH     = ROOT / "artifacts/semantic_ids/rq_kmeans/hotel_semantic_ids_twkim.json"
PROFILES_PATH = ROOT / "data/processed/hotel_profiles.json"
OUT_DIR       = ROOT / "reports/semantic_ids/rq_kmeans"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DPI           = 300


def load_data():
    with open(SIDS_PATH, encoding="utf-8") as f:
        sids = json.load(f)
    with open(PROFILES_PATH, encoding="utf-8") as f:
        profiles = json.load(f)

    rows = []
    for key, v in sids.items():
        p = profiles.get(key, {})
        rows.append({
            "hotel_name": v["hotel_name"],
            "c1": v["semantic_id"][0],
            "c2": v["semantic_id"][1],
            "c3": v["semantic_id"][2],
            "sid_str": v["semantic_id_str"],
            "avg_rating": p.get("avg_rating", np.nan),
            "total_reviews": p.get("total_reviews", np.nan),
            "profile": p.get("profile", ""),
        })
    return rows


# ── Figure 1: L1 cluster size distribution ────────────────────────────────────
def fig1_l1_distribution(rows):
    counts = Counter(r["c1"] for r in rows)
    x = sorted(counts)
    y = [counts[c] for c in x]

    fig, ax = plt.subplots(figsize=(10, 4))
    bars = ax.bar(x, y, color=[PALETTE[c] for c in x], edgecolor="white", linewidth=0.5)
    ax.axhline(np.mean(y), color="crimson", linestyle="--", linewidth=1.2, label=f"Mean = {np.mean(y):.1f}")
    ax.set_xlabel("L1 Cluster Code")
    ax.set_ylabel("Number of Hotels")
    ax.set_title("Fig 1. Hotel Count per L1 Cluster")
    ax.set_xticks(x)
    ax.legend()
    for bar, v in zip(bars, y):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 1.5, str(v),
                ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig1_l1_distribution.png", dpi=DPI)
    plt.close(fig)
    print("fig1 saved")


# ── Figure 2: L1 average rating with error bars ────────────────────────────────
def fig2_l1_avg_rating(rows):
    from collections import defaultdict
    cluster_ratings = defaultdict(list)
    for r in rows:
        if not np.isnan(r["avg_rating"]):
            cluster_ratings[r["c1"]].append(r["avg_rating"])

    x = sorted(cluster_ratings)
    means = [np.mean(cluster_ratings[c]) for c in x]
    stds  = [np.std(cluster_ratings[c])  for c in x]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(x, means, yerr=stds, color=[PALETTE[c] for c in x],
           edgecolor="white", linewidth=0.5, capsize=4, error_kw={"elinewidth": 1.2})
    ax.axhline(np.mean(means), color="crimson", linestyle="--", linewidth=1.2,
               label=f"Overall Mean = {np.mean(means):.2f}")
    ax.set_xlabel("L1 Cluster Code")
    ax.set_ylabel("Average Rating")
    ax.set_title("Fig 2. Average Rating per L1 Cluster (± std)")
    ax.set_xticks(x)
    ax.set_ylim(1, 5.5)
    ax.legend()
    for xi, m in zip(x, means):
        ax.text(xi, m + 0.12, f"{m:.2f}", ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig2_l1_avg_rating.png", dpi=DPI)
    plt.close(fig)
    print("fig2 saved")


# ── Figure 3: L1 rating box plot ──────────────────────────────────────────────
def fig3_l1_rating_boxplot(rows):
    from collections import defaultdict
    cluster_ratings = defaultdict(list)
    for r in rows:
        if not np.isnan(r["avg_rating"]):
            cluster_ratings[r["c1"]].append(r["avg_rating"])

    x = sorted(cluster_ratings)
    data = [cluster_ratings[c] for c in x]

    fig, ax = plt.subplots(figsize=(13, 5))
    bp = ax.boxplot(data, patch_artist=True, medianprops={"color": "black", "linewidth": 1.5},
                    whiskerprops={"linewidth": 1}, capprops={"linewidth": 1})
    for patch, c in zip(bp["boxes"], x):
        patch.set_facecolor(PALETTE[c])
        patch.set_alpha(0.8)
    ax.set_xticklabels(x)
    ax.set_xlabel("L1 Cluster Code")
    ax.set_ylabel("Average Rating")
    ax.set_title("Fig 3. Rating Distribution per L1 Cluster (Box Plot)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig3_l1_rating_boxplot.png", dpi=DPI)
    plt.close(fig)
    print("fig3 saved")


# ── Figure 4: L1×L2 co-occurrence heatmap ─────────────────────────────────────
def fig4_l1l2_heatmap(rows):
    matrix = np.zeros((16, 16), dtype=int)
    for r in rows:
        matrix[r["c1"], r["c2"]] += 1

    fig, ax = plt.subplots(figsize=(9, 7))
    sns.heatmap(matrix, ax=ax, cmap="YlOrRd", annot=True, fmt="d",
                annot_kws={"size": 7}, linewidths=0.3,
                cbar_kws={"label": "Hotel Count"})
    ax.set_xlabel("L2 Cluster Code")
    ax.set_ylabel("L1 Cluster Code")
    ax.set_title("Fig 4. L1 × L2 Co-occurrence Heatmap")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig4_l1l2_heatmap.png", dpi=DPI)
    plt.close(fig)
    print("fig4 saved")


# ── Figure 5: Full ID uniqueness ──────────────────────────────────────────────
def fig5_id_uniqueness(rows):
    id_counts = Counter(r["sid_str"] for r in rows)
    freq_dist = Counter(id_counts.values())  # {공유 호텔 수: 그 ID 개수}

    labels = sorted(freq_dist)
    values = [freq_dist[k] for k in labels]
    total_ids   = len(id_counts)
    unique_ids  = freq_dist.get(1, 0)
    collision_ids = total_ids - unique_ids

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # 왼쪽: bar chart of frequency distribution
    ax = axes[0]
    ax.bar([str(l) for l in labels], values, color=sns.color_palette("Blues_d", len(labels)))
    ax.set_xlabel("Hotels Sharing the Same ID")
    ax.set_ylabel("Number of Distinct IDs")
    ax.set_title("ID Sharing Distribution")
    for xi, v in enumerate(values):
        ax.text(xi, v + 0.3, str(v), ha="center", va="bottom", fontsize=9)

    # 오른쪽: pie chart unique vs collision
    ax2 = axes[1]
    ax2.pie(
        [unique_ids, collision_ids],
        labels=[f"Unique IDs\n({unique_ids})", f"Shared IDs\n({collision_ids})"],
        colors=["#4C72B0", "#DD8452"],
        autopct="%1.1f%%", startangle=140,
        textprops={"fontsize": 11},
    )
    ax2.set_title(f"ID Uniqueness\n(Total distinct IDs: {total_ids} / {len(rows)} hotels)")

    fig.suptitle("Fig 5. Full Semantic ID [c1-c2-c3-c4] Uniqueness Analysis", fontsize=13)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig5_id_uniqueness.png", dpi=DPI)
    plt.close(fig)
    print("fig5 saved")


# ── Figure 6: t-SNE ────────────────────────────────────────────────────────────
def fig6_tsne(rows):
    from sentence_transformers import SentenceTransformer
    from sklearn.manifold import TSNE

    print("  t-SNE: embedding profiles...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    texts = [r["profile"] for r in rows]
    embs  = model.encode(texts, show_progress_bar=True, batch_size=64)

    print("  t-SNE: fitting...")
    tsne = TSNE(n_components=2, perplexity=30, random_state=42, max_iter=1000)
    xy   = tsne.fit_transform(embs)

    l1_codes = [r["c1"] for r in rows]

    fig, ax = plt.subplots(figsize=(10, 8))
    for c in range(16):
        mask = [i for i, v in enumerate(l1_codes) if v == c]
        ax.scatter(xy[mask, 0], xy[mask, 1],
                   color=PALETTE[c], label=f"L1={c}", s=18, alpha=0.75, linewidths=0)
    ax.legend(loc="upper right", fontsize=8, ncol=2, markerscale=1.5,
              title="L1 Code", title_fontsize=9)
    ax.set_title("Fig 6. t-SNE of Hotel Profile Embeddings (colored by L1 Cluster)")
    ax.set_xlabel("t-SNE Dim 1")
    ax.set_ylabel("t-SNE Dim 2")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig6_tsne.png", dpi=DPI)
    plt.close(fig)
    print("fig6 saved")


if __name__ == "__main__":
    rows = load_data()
    print(f"호텔 수: {len(rows)}")

    fig1_l1_distribution(rows)
    fig2_l1_avg_rating(rows)
    fig3_l1_rating_boxplot(rows)
    fig4_l1l2_heatmap(rows)
    fig5_id_uniqueness(rows)
    fig6_tsne(rows)

    print(f"\n완료: {OUT_DIR}/")
