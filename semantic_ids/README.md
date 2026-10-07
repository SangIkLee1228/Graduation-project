# Semantic ID 파이프라인

동일한 1,619개 호텔 프로파일(`data/hotel_profiles.json`)을 두 방식으로 양자화한다.
각 방식의 생성 코드, 분석 코드·그림(`analysis/`), 데이터·모델(`artifacts/`)을 분리했다.
기존 브랜치의 결과 파일과 체크포인트는 재학습 없이 그대로 보존했다.

| 방식 | 임베딩 | 양자화 | 3토큰 고유 조합 | 최종 4토큰 고유 ID |
|---|---|---|---:|---:|
| `rq_kmeans/` | all-MiniLM-L6-v2, 384차원 | K=16, 3단계 잔차 K-means | 988 | 1,619 |
| `rqvae/` | sentence-t5-base, 768차원 | 32차원 잠재공간, 256코드 × 3단계 | 1,617 | 1,619 |

K-means의 C4는 같은 3토큰 그룹 내 잔차 크기 순위(0~8), RQ-VAE의 C4는 입력 순서에 따른 중복 구분 번호(0~1)다.
두 방식의 코드 번호는 서로 대응하지 않는다. 호텔 URL을 기준으로 비교한다.

## 실행

프로젝트 루트에서 의존성을 설치한 후 실행한다.

```bash
pip install -r requirements.txt

# K-means RQ
python semantic_ids/rq_kmeans/build_semantic_ids_twkim.py
python semantic_ids/rq_kmeans/analysis/analyze_semantic_ids_twkim.py
python semantic_ids/rq_kmeans/analysis/analyze_level_semantics_twkim.py

# RQ-VAE: 임베딩 → 학습 및 ID 생성 → 분석
python semantic_ids/rqvae/embed_profiles.py
python semantic_ids/rqvae/rqvae.py
python semantic_ids/rqvae/analysis/analyze_semantic_ids.py
```

파이프라인의 경로는 소스 파일 위치를 기준으로 계산하므로 다른 작업 디렉토리에서도 실행 가능하다.
생성 스크립트를 다시 실행하면 기존 산출물을 덮어쓴다. 모델 최초 로딩에는 다운로드가 필요하다.

## 보존된 산출물

- `rq_kmeans/artifacts/hotel_semantic_ids_twkim.json`: 호텔별 고유 ID.
- `rq_kmeans/analysis/`: 분석 스크립트 2개, 기존 그림 10개.
- `rqvae/artifacts/hotel_embeddings.npy`: Sentence-T5 임베딩.
- `rqvae/artifacts/hotel_embedding_ids.json`: 임베딩 행과 호텔의 대응.
- `rqvae/artifacts/rqvae.pt`: 기존 학습 모델의 state_dict.
- `rqvae/artifacts/hotel_semantic_ids.json`: 호텔별 고유 ID.
- `rqvae/analysis/`: 분석 스크립트 1개, 기존 그림 2개.

RQ-VAE 체크포인트에는 임베딩 표준화의 mean/std가 저장되어 있지 않다.
새 호텔에 대한 추론을 구현할 때 전처리 통계와 모델 설정도 함께 저장해야 한다.
K-means 방식도 신규 호텔 추론을 위해 코드북 저장을 추가해야 한다.
기존 그래프는 원 브랜치의 산출물이며 이번 정리에서 재생성하지 않았다.

방법 상세: [K-means RQ](rq_kmeans/README.md), [RQ-VAE](rqvae/README.md).
다음 작업: [평가 및 추천 모델 실험 계획](../docs/EXPERIMENT_PLAN.md).
