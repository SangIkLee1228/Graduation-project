"""
Semantic ID 각 레벨(C1/C2/C3)의 의미 분석

fig_a_rating_per_level.png  - 레벨별 평점 분포 비교 (분산 얼마나 설명하나)
fig_b_tsne_levels.png       - t-SNE 동일 좌표에서 C1/C2/C3 색상 비교
fig_c_keywords_l1.png       - L1 클러스터별 특징 키워드 (TF-IDF)
fig_d_keywords_l2.png       - L2 클러스터별 특징 키워드 (TF-IDF)
"""

import json, re, numpy as np
from pathlib import Path
from collections import defaultdict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.manifold import TSNE
from sentence_transformers import SentenceTransformer
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns

sns.set_theme(style="whitegrid", font_scale=1.05)
PALETTE16 = sns.color_palette("tab20", 16)

ROOT = Path(__file__).resolve().parents[3]

SIDS_PATH     = ROOT / "semantic_ids/rq_kmeans/artifacts/hotel_semantic_ids_twkim.json"
PROFILES_PATH = ROOT / "data/hotel_profiles.json"
OUT_DIR       = ROOT / "semantic_ids/rq_kmeans/analysis"
DPI           = 300

STOPWORDS = {
    "a","an","the","and","or","but","in","on","of","for","to","is","are","was",
    "were","be","been","being","with","at","by","from","this","that","it","its",
    "as","has","have","had","which","who","their","there","than","also","hotel",
    "london","guests","offers","located","near","just","well","making","ideal",
    "overall","experience","stay","great","good","nice","very","more","most",
    "many","some","all","they","from","short","walk","providing","making",
    "particularly","convenient","within","area","rooms","staff","service",
    "while","however","though","although","known","place","features",
}


def load_data():
    with open(SIDS_PATH, encoding="utf-8") as f:
        sids = json.load(f)
    with open(PROFILES_PATH, encoding="utf-8") as f:
        profiles = json.load(f)
    rows = []
    for key, v in sids.items():
        p = profiles.get(key, {})
        rows.append({
            "c1": v["semantic_id"][0],
            "c2": v["semantic_id"][1],
            "c3": v["semantic_id"][2],
            "avg_rating": p.get("avg_rating", np.nan),
            "profile":    p.get("profile", ""),
            "hotel_name": v["hotel_name"],
        })
    return rows


# ── Fig A: 레벨별 평점 분포 ────────────────────────────────────────────────────
def fig_a_rating_per_level(rows):
    """각 레벨 코드별 평균 평점 bar chart 3개. 분산이 클수록 해당 레벨이 품질을 잘 설명."""
    fig, axes = plt.subplots(1, 3, figsize=(16, 4), sharey=True)
    for ax, level, label in zip(axes, ["c1","c2","c3"], ["C1 (L1)","C2 (L2)","C3 (L3)"]):
        cluster_r = defaultdict(list)
        for r in rows:
            if not np.isnan(r["avg_rating"]):
                cluster_r[r[level]].append(r["avg_rating"])
        x = sorted(cluster_r)
        means = [np.mean(cluster_r[c]) for c in x]
        stds  = [np.std(cluster_r[c])  for c in x]
        overall_std = np.std([r["avg_rating"] for r in rows if not np.isnan(r["avg_rating"])])
        between_std = np.std(means)

        ax.bar(x, means, yerr=stds, color=[PALETTE16[c] for c in x],
               edgecolor="white", linewidth=0.4, capsize=3,
               error_kw={"elinewidth": 1, "alpha": 0.6})
        ax.axhline(np.mean(means), color="crimson", linestyle="--", linewidth=1.1)
        ax.set_title(f"{label}\nbetween-cluster σ = {between_std:.3f}", fontsize=11)
        ax.set_xlabel("Cluster Code")
        ax.set_xticks(x)
        ax.set_xticklabels(x, fontsize=7)
        ax.set_ylim(1, 5.5)
    axes[0].set_ylabel("Avg Rating")
    fig.suptitle("Fig A. Average Rating per Cluster Code at Each Level\n"
                 "(Higher between-cluster σ → level explains quality better)", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig_a_rating_per_level.png", dpi=DPI)
    plt.close(fig)
    print("fig_a saved")


# ── Fig B: t-SNE with C1 / C2 / C3 coloring ──────────────────────────────────
def fig_b_tsne_levels(rows):
    print("  fig_b: embedding...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    embs  = model.encode([r["profile"] for r in rows],
                         show_progress_bar=True, batch_size=64)
    print("  fig_b: t-SNE...")
    xy = TSNE(n_components=2, perplexity=30, random_state=42,
              max_iter=1000).fit_transform(embs)

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    for ax, level, title in zip(axes,
                                 ["c1","c2","c3"],
                                 ["C1 (L1) — 1st Residual",
                                  "C2 (L2) — 2nd Residual",
                                  "C3 (L3) — 3rd Residual"]):
        codes = [r[level] for r in rows]
        for c in range(16):
            mask = [i for i,v in enumerate(codes) if v==c]
            ax.scatter(xy[mask,0], xy[mask,1],
                       color=PALETTE16[c], label=str(c),
                       s=12, alpha=0.7, linewidths=0)
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("t-SNE Dim 1"); ax.set_ylabel("t-SNE Dim 2")
        ax.legend(title="Code", fontsize=6, ncol=2,
                  markerscale=1.5, title_fontsize=7,
                  loc="upper right", framealpha=0.7)
    fig.suptitle("Fig B. Same t-SNE Projection — Colored by C1 / C2 / C3\n"
                 "(Well-separated clusters → level encodes clear semantic axis)", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig_b_tsne_levels.png", dpi=DPI)
    plt.close(fig)
    print("fig_b saved")


# ── Fig C / D: TF-IDF 키워드 per L1, L2 ──────────────────────────────────────
def _keyword_figure(rows, level: str, fname: str, title: str):
    """각 클러스터의 특징 키워드를 TF-IDF로 추출해 수평 bar chart로 시각화."""
    cluster_docs = defaultdict(list)
    for r in rows:
        cluster_docs[r[level]].append(r["profile"])
    codes = sorted(cluster_docs)

    # 각 클러스터를 하나의 문서로 합침 → TF-IDF
    corpus = [" ".join(cluster_docs[c]) for c in codes]
    vec = TfidfVectorizer(
        max_features=300,
        stop_words=list(STOPWORDS),
        token_pattern=r"[a-zA-Z]{4,}",   # 4글자 이상 영문만
        ngram_range=(1, 1),
    )
    tfidf = vec.fit_transform(corpus).toarray()  # (n_clusters, vocab)
    vocab = vec.get_feature_names_out()

    TOP_N = 6
    ncols = 4
    nrows = (len(codes) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 4, nrows * 2.2))
    axes = axes.flatten()

    for i, c in enumerate(codes):
        top_idx  = np.argsort(tfidf[i])[::-1][:TOP_N]
        top_words = [vocab[j] for j in top_idx]
        top_scores = [tfidf[i][j] for j in top_idx]
        ax = axes[i]
        ax.barh(top_words[::-1], top_scores[::-1], color=PALETTE16[c], alpha=0.85)
        n = len(cluster_docs[c])
        ax.set_title(f"Code {c}  (n={n})", fontsize=9, fontweight="bold")
        ax.tick_params(axis="y", labelsize=8)
        ax.tick_params(axis="x", labelsize=7)
        ax.set_xlabel("TF-IDF", fontsize=7)

    for j in range(len(codes), len(axes)):
        axes[j].set_visible(False)

    fig.suptitle(title, fontsize=12, y=1.01)
    fig.tight_layout()
    fig.savefig(OUT_DIR / fname, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"{fname} saved")


if __name__ == "__main__":
    rows = load_data()
    print(f"호텔 수: {len(rows)}")

    fig_a_rating_per_level(rows)
    fig_b_tsne_levels(rows)
    _keyword_figure(rows, "c1", "fig_c_keywords_l1.png",
                    "Fig C. Top TF-IDF Keywords per L1 (C1) Cluster")
    _keyword_figure(rows, "c2", "fig_d_keywords_l2.png",
                    "Fig D. Top TF-IDF Keywords per L2 (C2) Cluster")

    print(f"\n완료: {OUT_DIR}/")
