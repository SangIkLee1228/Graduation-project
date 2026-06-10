# Semantic ID 생성

## 개요

각 호텔에 계층적 Semantic ID `[c1, c2, c3]`를 부여한다. TIGER 논문의 핵심 아이디어인 **"의미적으로 유사한 아이템은 비슷한 ID prefix를 공유"** 를 따른다.

## 방법

### 1단계: 텍스트 임베딩

`hotel_profiles.json`의 `profile` 필드(LLM이 생성한 호텔 특성 요약)를 sentence-transformer로 벡터화한다.

- 모델: `all-MiniLM-L6-v2`
- 입력: 1,619개 호텔 프로필 텍스트
- 출력: `(1619, 384)` float32 행렬

### 2단계: Residual Quantization (RQ)

TIGER는 RQ-VAE를 학습하지만, 1,619개 샘플에서는 학습 불안정 우려가 있어 **VAE 없이 K-means만으로 RQ를 구현**한다. 핵심 구조는 동일하다.

3개 레벨에 걸쳐 잔차를 반복 양자화한다:

```
L1: K-means(K=16) on embeddings       → code c1, residual r1 = embedding − centroid₁
L2: K-means(K=16) on r1               → code c2, residual r2 = r1 − centroid₂
L3: K-means(K=16) on r2               → code c3
```

최종 ID: `[c1, c2, c3]`  (각 값 ∈ {0, …, 15})

#### RQ vs 계층적 K-means 차이

| | 계층적 K-means | Residual Quantization (채택) |
|---|---|---|
| L2 의미 | L1 클러스터 내부 세분화 | L1이 설명 못한 잔차 분류 |
| 구조 | 트리 (엄격한 상하 관계) | 잔차 분해 (독립적인 축) |
| 표현력 | 낮음 (소규모 서브클러스터) | 높음 (전체 공간 재활용) |

### ID 공간

- 가능한 ID 수: 16³ = 4,096
- 실제 호텔 수: 1,619
- 충돌(동일 ID 공유): 발생 가능, retrieval 모델 학습 시 자연스럽게 처리됨

## 각 자릿수의 의미

**L1 (첫째 자리)** 는 해석이 가장 명확하다. 실제 클러스터 분석 결과, 호텔 **품질 수준 + 숙박 유형**을 주로 포착한다.

| L1 코드 | avg_rating | 주요 특징 |
|--------|-----------|---------|
| 11 | 4.38 | 고품질 B&B / 부티크 |
| 13, 15 | 3.67~3.72 | 중상급 / 펍 호텔 |
| 4 | 3.47 | Aparthotel / 서비스드 아파트 |
| 8 | 3.62 | 체인 호텔 (외곽, Travelodge 등) |
| 6, 9, 12 | 2.99~3.03 | 저가 버짓 / 호스텔 |

**L2, L3 (둘째·셋째 자리)** 는 잔차 공간을 분류하므로 직접 해석이 어렵다. 위치, 편의시설 등 L1이 포착하지 못한 세부 특성을 담는다. Generative retrieval 모델이 학습을 통해 이 패턴의 의미를 내재화한다.

## 파일

| 파일 | 설명 |
|------|------|
| `build_semantic_ids.py` | ID 생성 스크립트 |
| `hotel_semantic_ids.json` | 생성 결과 (1,619개 호텔) |

### 출력 포맷 (`hotel_semantic_ids.json`)

```json
{
  "Hotel_Review-g186338-d12345-...": {
    "hotel_id": "12345",
    "hotel_name": "Example Hotel",
    "semantic_id": [3, 12, 7],
    "semantic_id_str": "3-12-7"
  }
}
```

## 실행

```bash
# 프로젝트 루트에서 실행
python make-semantic-id/build_semantic_ids.py
```

의존성: `sentence-transformers`, `scikit-learn`, `numpy` (`requirements.txt` 참고)

## 참고 논문

- **TIGER** (Rajput et al., 2023): Generative Retrieval을 위한 Semantic ID — RQ-VAE 기반 계층적 discrete ID
- **sentence-transformers** (`all-MiniLM-L6-v2`): 텍스트 의미 유사도 임베딩
