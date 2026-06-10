"""
RQ-VAE (Residual Quantization VAE) - TIGER 방식 Semantic ID 생성
hotel_embeddings.npy (1619, 768) -> Semantic ID (c1, c2, c3) per hotel
"""

import json
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset

# ── 설정 ──────────────────────────────────────────────────────────
EMB_PATH    = "C:/Users/SANGIK/Graduation-project/data/hotel_embeddings.npy"
IDS_PATH    = "C:/Users/SANGIK/Graduation-project/data/hotel_embedding_ids.json"
OUTPUT_PATH = "C:/Users/SANGIK/Graduation-project/data/hotel_semantic_ids.json"
CKPT_PATH   = "C:/Users/SANGIK/Graduation-project/data/rqvae.pt"

INPUT_DIM    = 768
LATENT_DIM   = 32
HIDDEN_DIMS  = [512, 256, 128]
NUM_CODEBOOKS = 3       # depth (c1, c2, c3)
CODEBOOK_SIZE = 256     # 코드북당 코드 수

EPOCHS       = 200
BATCH_SIZE   = 64
LR           = 1e-3
COMMITMENT_BETA = 0.25

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
SEED = 42

torch.manual_seed(SEED)
np.random.seed(SEED)


# ── 모델 정의 ─────────────────────────────────────────────────────
class MLP(nn.Module):
    def __init__(self, in_dim, hidden_dims, out_dim):
        super().__init__()
        dims = [in_dim] + hidden_dims + [out_dim]
        layers = []
        for i in range(len(dims) - 1):
            layers.append(nn.Linear(dims[i], dims[i + 1]))
            if i < len(dims) - 2:
                layers.append(nn.ReLU())
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


class ResidualQuantizer(nn.Module):
    """순차적 잔차 양자화: depth개의 codebook을 차례로 적용"""

    def __init__(self, num_codebooks, codebook_size, latent_dim):
        super().__init__()
        self.codebooks = nn.ModuleList([
            nn.Embedding(codebook_size, latent_dim) for _ in range(num_codebooks)
        ])
        for cb in self.codebooks:
            nn.init.uniform_(cb.weight, -1.0 / codebook_size, 1.0 / codebook_size)

    def forward(self, z):
        """
        z: (B, latent_dim)
        반환:
          z_q: 양자화된 벡터 (B, latent_dim) - straight-through estimator 적용
          codes: (B, num_codebooks) 각 단계에서 선택된 코드 인덱스
          commitment_loss: codebook + commitment loss 합
        """
        residual = z
        z_q = torch.zeros_like(z)
        codes = []
        loss = 0.0

        for cb in self.codebooks:
            # residual과 codebook 벡터 간 거리 계산
            dist = (
                residual.pow(2).sum(1, keepdim=True)
                - 2 * residual @ cb.weight.t()
                + cb.weight.pow(2).sum(1)
            )
            code_idx = dist.argmin(dim=1)            # (B,)
            quantized = cb(code_idx)                  # (B, latent_dim)

            # codebook loss + commitment loss
            loss = loss + F.mse_loss(quantized, residual.detach())
            loss = loss + COMMITMENT_BETA * F.mse_loss(quantized.detach(), residual)

            z_q = z_q + quantized
            residual = residual - quantized.detach()  # 다음 단계는 잔차에 대해 양자화
            codes.append(code_idx)

        # straight-through estimator: forward는 z_q, backward는 z의 gradient 사용
        z_q_st = z + (z_q - z).detach()
        codes = torch.stack(codes, dim=1)  # (B, num_codebooks)
        return z_q_st, codes, loss


class RQVAE(nn.Module):
    def __init__(self, input_dim, hidden_dims, latent_dim, num_codebooks, codebook_size):
        super().__init__()
        self.encoder = MLP(input_dim, hidden_dims, latent_dim)
        self.quantizer = ResidualQuantizer(num_codebooks, codebook_size, latent_dim)
        self.decoder = MLP(latent_dim, hidden_dims[::-1], input_dim)

    def forward(self, x):
        z = self.encoder(x)
        z_q, codes, q_loss = self.quantizer(z)
        x_recon = self.decoder(z_q)
        return x_recon, codes, q_loss


# ── 학습 ──────────────────────────────────────────────────────────
def train():
    print(f"Device: {DEVICE}")

    embeddings = np.load(EMB_PATH).astype(np.float32)
    print(f"임베딩 shape: {embeddings.shape}")

    # 정규화 (평균 0, 분산 1) - RQ-VAE 학습 안정화
    mean = embeddings.mean(axis=0, keepdims=True)
    std = embeddings.std(axis=0, keepdims=True) + 1e-8
    embeddings_norm = (embeddings - mean) / std

    x = torch.tensor(embeddings_norm, dtype=torch.float32)
    dataset = TensorDataset(x)
    loader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True)

    model = RQVAE(INPUT_DIM, HIDDEN_DIMS, LATENT_DIM, NUM_CODEBOOKS, CODEBOOK_SIZE).to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)

    print("\n학습 시작...")
    for epoch in range(1, EPOCHS + 1):
        model.train()
        total_recon, total_q = 0.0, 0.0

        for (batch,) in loader:
            batch = batch.to(DEVICE)
            optimizer.zero_grad()

            x_recon, codes, q_loss = model(batch)
            recon_loss = F.mse_loss(x_recon, batch)
            loss = recon_loss + q_loss

            loss.backward()
            optimizer.step()

            total_recon += recon_loss.item() * batch.size(0)
            total_q += q_loss.item() * batch.size(0)

        if epoch % 20 == 0 or epoch == 1:
            n = len(dataset)
            print(f"Epoch {epoch:3d}/{EPOCHS} | recon_loss: {total_recon/n:.4f} | q_loss: {total_q/n:.4f}")

    torch.save(model.state_dict(), CKPT_PATH)
    print(f"\n모델 저장 -> {CKPT_PATH}")

    # ── 전체 데이터에 대해 Semantic ID 생성 ──────────────────────
    model.eval()
    with torch.no_grad():
        x_all = x.to(DEVICE)
        _, codes, _ = model(x_all)
        codes = codes.cpu().numpy()  # (N, num_codebooks)

    return codes


# ── 충돌(collision) 처리 + 저장 ──────────────────────────────────
def assign_semantic_ids(codes):
    """
    codes: (N, num_codebooks) - 각 호텔의 (c1, c2, c3)
    동일한 (c1,c2,c3)을 가진 호텔은 마지막에 sub-index를 추가해 구분
    """
    with open(IDS_PATH, encoding="utf-8") as f:
        id_mapping = json.load(f)

    seen = {}
    results = {}

    for i, entry in enumerate(id_mapping):
        code_tuple = tuple(int(c) for c in codes[i])

        # 충돌 처리: 동일 코드면 sub-index 추가
        if code_tuple in seen:
            seen[code_tuple] += 1
            sub_idx = seen[code_tuple]
        else:
            seen[code_tuple] = 0
            sub_idx = 0

        semantic_id = list(code_tuple) + [sub_idx]

        results[entry["hotel_url"]] = {
            "hotel_id":    entry["hotel_id"],
            "hotel_name":  entry["hotel_name"],
            "semantic_id": semantic_id,            # [c1, c2, c3, sub_idx]
            "semantic_id_str": "_".join(map(str, semantic_id)),
        }

    # 충돌 통계
    n_collisions = sum(1 for v in seen.values() if v > 0)
    max_collision = max(seen.values()) + 1
    print(f"\n고유 (c1,c2,c3) 조합: {len(seen)}개 / 전체 {len(id_mapping)}개")
    print(f"충돌 발생 그룹 수: {n_collisions}개 (최대 충돌 크기: {max_collision})")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] Semantic ID 저장 -> {OUTPUT_PATH}")


if __name__ == "__main__":
    codes = train()
    assign_semantic_ids(codes)
