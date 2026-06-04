# scripts/ — 전처리·EDA 파이프라인 설명

이 폴더에는 HotelRec 데이터셋을 전처리하고 런던(geo_id: g186338) 데이터를 추출·분석하는 스크립트들이 순서대로 들어 있습니다.

---

## 전체 파이프라인 흐름

```
data/HotelRec.txt (47 GB, 전체 리뷰)
    │
    ├─ 01_peek.py          데이터 구조 미리보기 (콘솔 출력만)
    │
    ├─ 02_validate.py      전체 파일 스트리밍 → 통계 수집
    │       └─ eda-alldata-output/validation_stats.json
    │
    ├─ 03_sample.py        Reservoir Sampling → 소규모 샘플 추출
    │       └─ eda-alldata-output/sample_{k}.jsonl
    │
    ├─ 04_filter_parquet.py  품질 필터링 → Parquet 변환
    │       └─ eda-alldata-output/hotelrec_filtered.parquet
    │
    ├─ 05_eda.py           전체 데이터 EDA 차트 생성
    │       └─ eda-alldata-output/eda_*.png
    │
    ├─ 06_normalize.py     정규화 + user/hotel 정수 인덱싱
    │       └─ eda-alldata-output/hotelrec_normalized.parquet
    │       └─ eda-alldata-output/id_maps.pkl
    │
    ├─ 07_kcore_filter.py  K-core 필터링 (비활성 사용자·호텔 제거)
    │       └─ eda-alldata-output/hotelrec_kcore{k}.parquet
    │
    ├─ 08_make_views.py    용도별 데이터셋 분리 (train/val/test, NLP, 메타)
    │       └─ eda-alldata-output/views/
    │
    ├─ 09_geo_analysis.py  지역별 리뷰·호텔 분포 분석
    │       └─ eda-alldata-output/geo_stats.csv
    │       └─ eda-alldata-output/geo_*.png
    │
    └─ 10_extract_london.py  런던 리뷰만 추출
            └─ eda-london-output/london_reviews.json
                    │
                    └─ 11_london_eda.py  런던 전용 EDA 차트
                            └─ eda-london-output/london_eda_*.png
```

---

## 출력 폴더

| 폴더 | 내용 |
|------|------|
| `eda-alldata-output/` | 전체 HotelRec 데이터를 처리한 결과물 (스크립트 02~09) |
| `eda-london-output/` | 런던 한정 결과물 (스크립트 10~11) |

---

## 스크립트별 상세 설명

---

### 01_peek.py — 데이터 구조 미리보기

**목적**: HotelRec.txt의 처음 N건을 읽어 스키마와 샘플 레코드를 콘솔에 출력합니다. 파일을 처음 접할 때 데이터 구조를 빠르게 파악하기 위한 용도입니다.

**입력**: `data/HotelRec.txt`  
**출력**: 콘솔 출력만 (파일 저장 없음)

**실행 방법**:
```bash
python scripts/01_peek.py          # 기본 100건
python scripts/01_peek.py --n 50   # 50건만
```

**출력 내용**:
- 발견된 최상위 키 목록 (`hotel_url`, `author`, `date`, `rating`, `title`, `text`, `property_dict`)
- `property_dict`의 서브키 목록 (`service`, `cleanliness`, `value`, `location`, `rooms`, `sleep quality` 등)
- 첫 번째 레코드 전체 내용 (JSON pretty-print)

---

### 02_validate.py — 데이터 품질 검증 및 통계 수집

**목적**: 47GB 전체 파일을 한 줄씩 스트리밍하면서 데이터 품질 통계를 수집합니다. 후속 전처리 기준(필터 조건, 정규화 방법)을 결정하기 위한 근거 데이터를 생성합니다.

**입력**: `data/HotelRec.txt`  
**출력**: `eda-alldata-output/validation_stats.json`

**실행 방법**:
```bash
python scripts/02_validate.py
```

**수집 통계**:
- 총 레코드 수, 파싱 오류 수, 빈 줄 수
- 필드별 결측값 비율 (`hotel_url`, `author`, `date`, `rating`, `title`, `text`, `property_dict`)
- 평점 분포 (1.0~5.0)
- 텍스트 길이 (최솟값, 최댓값, 평균)
- 날짜 범위 (최초~최근 리뷰 날짜)
- 고유 호텔 수 / 고유 작성자 수 (메모리 절약을 위해 최대 1M까지 추적)
- `property_dict` 서브키 출현 빈도

---

### 03_sample.py — 균등 랜덤 샘플링

**목적**: 파일 전체를 한 번만 읽으면서 메모리 효율적으로 균등 랜덤 샘플을 추출합니다. EDA나 모델 프로토타이핑에서 전체 파일 대신 사용할 소규모 데이터셋을 만들기 위해 사용합니다.

**알고리즘**: Reservoir Sampling (Algorithm R, Vitter 1985) — 파일 크기를 몰라도 균등 샘플링이 보장되며, 메모리는 O(k)만 사용합니다.

**입력**: `data/HotelRec.txt`  
**출력**: `eda-alldata-output/sample_{k}.jsonl`

**실행 방법**:
```bash
python scripts/03_sample.py                         # 기본 100,000건
python scripts/03_sample.py --k 500000              # 500k건
python scripts/03_sample.py --k 10000 --seed 7      # 시드 지정
```

---

### 04_filter_parquet.py — 품질 필터링 및 Parquet 변환

**목적**: 원본 JSON 파일에서 품질 기준을 통과한 레코드만 추려 Parquet 형식으로 저장합니다. Parquet은 원본 대비 5~10배 작고, pandas/Spark가 빠르게 읽을 수 있어 이후 분석 속도를 크게 높입니다.

**입력**: `data/HotelRec.txt`  
**출력**: `eda-alldata-output/hotelrec_filtered.parquet`

**실행 방법**:
```bash
python scripts/04_filter_parquet.py
```

**필터 기준**:
- `text`와 `rating` 모두 존재
- 텍스트 길이 ≥ 100자
- 평점 1.0 ~ 5.0 범위

**추가 처리**:
- `hotel_url`에서 TripAdvisor 호텔 ID(`hotel_id`) 추출 (정규식 `-d(\d+)-`)
- `property_dict`를 `sub_service`, `sub_cleanliness`, `sub_value`, `sub_location`, `sub_rooms`, `sub_sleep_quality` 컬럼으로 평탄화
- 배치 크기 200,000건 단위로 디스크에 flush하여 메모리 사용량 제한

---

### 05_eda.py — 전체 데이터 EDA 차트 생성

**목적**: 전처리된 데이터를 로드해 시각화 차트를 생성합니다. 데이터 분포를 직관적으로 파악하고 보고서 자료로 활용합니다.

**입력**: `eda-alldata-output/sample_{k}.jsonl` 또는 `eda-alldata-output/hotelrec_filtered.parquet`  
**출력**: `eda-alldata-output/eda_*.png`

**실행 방법**:
```bash
python scripts/05_eda.py                                             # JSONL 샘플 자동 선택
python scripts/05_eda.py --src parquet                               # Parquet 사용
python scripts/05_eda.py --src jsonl --in eda-alldata-output/sample_100000.jsonl
```

**생성 차트**:
- `eda_rating_dist.png` — 평점(1~5) 분포 막대 차트
- `eda_text_length.png` — 텍스트 길이 히스토그램 (99th percentile 이상치 제외)
- `eda_year_dist.png` — 연도별 리뷰 수 (시간적 분포)
- `eda_sub_ratings.png` — 서브 평점 항목별 평균 (수평 막대 차트)

---

### 06_normalize.py — 정규화 및 정수 인덱싱

**목적**: 추천 시스템 학습에 적합한 형태로 데이터를 정규화합니다. 노이즈 키 제거, 텍스트 길이 컷오프, user/hotel 정수 인코딩을 수행합니다.

**입력**: `data/HotelRec.txt`  
**출력**: `eda-alldata-output/hotelrec_normalized.parquet`, `eda-alldata-output/id_maps.pkl`

**실행 방법**:
```bash
python scripts/06_normalize.py
```

**처리 내용 (2-pass)**:
- **Pass 1**: 전체 파일을 읽으며 `user_url→정수` 매핑과 `hotel_url→정수` 매핑 딕셔너리 생성 후 `id_maps.pkl`로 저장
- **Pass 2**: 텍스트 50자 미만 제거, 5,000자 초과 시 잘라냄, `property_dict` 노이즈 키(`userrating.prompt.*`, `ur_question.*`) 폐기, 표준 6개 서브 평점 컬럼(`service`, `cleanliness`, `value`, `location`, `rooms`, `sleep_quality`)으로 정리
- 이후 모든 분석의 출발점이 되는 핵심 파일

---

### 07_kcore_filter.py — K-core 필터링

**목적**: 리뷰 수가 너무 적은 사용자와 호텔을 제거해 행렬 밀도를 높입니다. 협업 필터링 등 추천 시스템의 표준 전처리 단계입니다.

**입력**: `eda-alldata-output/hotelrec_normalized.parquet`  
**출력**: `eda-alldata-output/hotelrec_kcore{k}.parquet`

**실행 방법**:
```bash
python scripts/07_kcore_filter.py          # 기본 K=5
python scripts/07_kcore_filter.py --k 10   # K=10
```

**알고리즘**: K-core 반복 필터링 — 사용자 리뷰 수 < K 이거나 호텔 리뷰 수 < K 인 레코드를 제거하는 과정을 수렴할 때까지 반복합니다. DuckDB SQL로 처리해 대용량 Parquet 파일에서도 빠릅니다.

| K 값 | 의미 |
|------|------|
| 5 | 활성 사용자/호텔만 (가장 일반적) |
| 10 | 더 dense한 데이터 |
| 20 | 매우 dense (실험용) |

---

### 08_make_views.py — 용도별 데이터셋 분리

**목적**: 하나의 정규화된 데이터셋에서 추천 시스템 학습, NLP 분석, 메타데이터 집계 등 용도에 맞는 여러 뷰를 한 번에 생성합니다.

**입력**: `eda-alldata-output/hotelrec_kcore5.parquet` (없으면 `hotelrec_normalized.parquet`)  
**출력**: `eda-alldata-output/views/` 하위 6개 Parquet 파일

**실행 방법**:
```bash
python scripts/08_make_views.py
python scripts/08_make_views.py --nlp-per-class 50000   # NLP 샘플 크기 조정
```

**생성 파일**:

| 파일 | 내용 |
|------|------|
| `rec_train.parquet` | 추천 학습용 (2017년 이하, text 제외) |
| `rec_val.parquet` | 검증용 (2018년) |
| `rec_test.parquet` | 테스트용 (2019년) |
| `nlp_balanced.parquet` | 평점 클래스 균형 샘플 (NLP용, text 포함) |
| `hotels.parquet` | 호텔별 집계 (리뷰 수, 평점 평균, 서브 평점 평균 등) |
| `users.parquet` | 사용자별 집계 (리뷰 수, 평점 평균 등) |

**시간 기반 split**: train(~2017) / val(2018) / test(2019)로 미래 데이터 누수 없이 분리

---

### 09_geo_analysis.py — 지역별 분포 분석

**목적**: TripAdvisor URL에 포함된 `geo_id`를 파싱해 지역별 리뷰 수, 호텔 수, 평균 평점을 집계합니다. 어느 지역이 가장 데이터가 풍부한지 파악하고, 런던 추출(10번 스크립트)의 전 단계 역할을 합니다.

**입력**: `eda-alldata-output/views/hotels.parquet` (빠름) 또는 `eda-alldata-output/hotelrec_filtered.parquet` (전체)  
**출력**: `eda-alldata-output/geo_stats.csv`, `eda-alldata-output/geo_*.png`

**실행 방법**:
```bash
python scripts/09_geo_analysis.py           # hotels.parquet 사용 (빠름)
python scripts/09_geo_analysis.py --full    # 전체 filtered.parquet 사용 (수 분 소요)
```

**생성 차트**:
- `geo_top30_reviews.png` — 리뷰 수 Top 30 지역 (비율 레이블 포함)
- `geo_top30_hotels.png` — 호텔 수 Top 30 지역
- `geo_rating_top20.png` — 리뷰 수 기준 상위 20 지역의 평균 평점

**URL 파싱 패턴**:
```
Hotel_Review-g{geo_id}-d{hotel_id}-Reviews-{HotelName}-{City}.html
```

---

### 10_extract_london.py — 런던 리뷰 추출

**목적**: `geo_stats.csv`에서 `location_slug`에 `London_England`를 포함하는 geo_id를 모두 찾아, 전체 HotelRec.txt에서 해당 지역의 리뷰만 필터링해 저장합니다.

**입력**: `data/HotelRec.txt`, `eda-alldata-output/geo_stats.csv`  
**출력**: `eda-london-output/london_reviews.json`

**실행 방법**:
```bash
python scripts/10_extract_london.py
python scripts/10_extract_london.py --out eda-london-output/my_london.json
```

**처리 흐름**:
1. `geo_stats.csv`에서 `London_England` 포함 geo_id 세트 구성
2. HotelRec.txt를 스트리밍하며 `hotel_url`의 geo_id가 세트에 속하면 추출
3. JSON 배열(`[{...}, {...}, ...]`) 형태로 저장

**결과**: Greater London 내 모든 하위 지역(City of London, Westminster, Kensington 등)의 리뷰를 포함

---

### 11_london_eda.py — 런던 데이터 EDA 차트 생성

**목적**: 10번 스크립트가 추출한 런던 리뷰 데이터만을 대상으로 EDA 차트를 생성합니다. 런던 데이터의 특성을 전체 데이터와 비교하거나 보고서 자료로 활용합니다.

**입력**: `eda-london-output/london_reviews.json`  
**출력**: `eda-london-output/london_eda_*.png`

**실행 방법**:
```bash
python scripts/11_london_eda.py
python scripts/11_london_eda.py --in eda-london-output/london_reviews.json
```

**생성 차트**:
- `london_eda_rating_dist.png` — 평점 분포
- `london_eda_text_length.png` — 텍스트 길이 히스토그램 (99th percentile 캡)
- `london_eda_year_dist.png` — 연도별 리뷰 수 추이
- `london_eda_sub_ratings.png` — 서브 평점 항목별 평균
- `london_eda_top_hotels.png` — 리뷰 수 Top 20 호텔 (hotel_id 기준)

---

## 실행 순서 요약

전체 파이프라인을 처음부터 실행하는 경우:

```bash
# 1. 데이터 구조 확인 (선택)
python scripts/01_peek.py

# 2. 전체 데이터 품질 통계 (선택, 시간 많이 소요)
python scripts/02_validate.py

# 3. 소규모 샘플 추출 (선택, EDA 빠르게 보고 싶을 때)
python scripts/03_sample.py

# 4. 품질 필터링 + Parquet 변환 (필수)
python scripts/04_filter_parquet.py

# 5. EDA 차트 (전체 데이터)
python scripts/05_eda.py --src parquet

# 6. 정규화 (필수)
python scripts/06_normalize.py

# 7. K-core 필터링
python scripts/07_kcore_filter.py

# 8. 용도별 뷰 생성
python scripts/08_make_views.py

# 9. 지역 분포 분석 (런던 추출 전 필수)
python scripts/09_geo_analysis.py

# 10. 런던 리뷰 추출
python scripts/10_extract_london.py

# 11. 런던 EDA 차트
python scripts/11_london_eda.py
```
