# HotelRec 기반 런던 호텔 추천 시스템 — 졸업 프로젝트

TripAdvisor 리뷰 데이터셋(HotelRec)을 이용해 런던 호텔에 대한 **Semantic ID** 기반 추천 시스템을 구현하는 학부 졸업 프로젝트입니다.

TIGER 등에서 제안된 Semantic ID 방식과 관계형 DB 기반 추천 기법을 결합하는 것을 목표로 하며, 전체 데이터 중 리뷰가 가장 많은 **런던(geo_id: g186338)** 데이터에 한정해 적용합니다.

---

## 디렉토리 구조

```
Graduation-project/
├── data/                          # 원본 데이터 및 초기 처리 스크립트
├── scripts/                       # 전처리 · EDA 파이프라인 (01~12번)
├── eda-alldata-output/            # 전체 데이터 EDA 결과물
├── eda-london-output/             # 런던 전체(46 geo_id) EDA 결과물
├── eda-london-g186338-output/     # 런던 중심부(g186338 단독) EDA 결과물
├── semantic_ids/                  # 구현 완료된 Semantic ID 두 방식
│   ├── rq_kmeans/                 # MiniLM + K-means RQ
│   └── rqvae/                     # Sentence-T5 + RQ-VAE
├── docs/                          # 평가 및 후속 실험 계획
├── requirements.txt               # Python 패키지 목록
└── README.md
```

---

## 데이터셋

| 파일 | 크기 | 설명 |
|------|------|------|
| `data/HotelRec.txt` | 47 GB | HotelRec 전체 리뷰 데이터 (50,264,531건). JSON 배열 형식. git 미포함 |
| `data/Full_HotelRec.zip` | 14 GB | 위 파일의 압축본. git 미포함 |
| `data/hotelrec_geo_186338.json` | 673 MB | g186338 (London England) 에 해당하는 리뷰만 사전 추출한 파일. git 미포함 |

### 레코드 구조

```json
{
  "hotel_url":      "Hotel_Review-g186338-d123456-Reviews-HotelName-London_England.html",
  "author":         "reviewer_id",
  "date":           "2018-05-01T00:00:00",
  "rating":         4.0,
  "title":          "Great stay",
  "text":           "The room was clean and ...",
  "property_dict":  {
    "service": 4.0, "cleanliness": 5.0, "value": 3.0,
    "location": 5.0, "rooms": 4.0, "sleep quality": 4.0
  }
}
```

### 전체 데이터 주요 통계 (02_validate.py 결과)

| 항목 | 값 |
|------|-----|
| 총 리뷰 수 | 50,264,531건 |
| 고유 호텔 수 | 365,057개 |
| 날짜 범위 | 2001-02 ~ 2019-09 |
| 평균 텍스트 길이 | 691자 |
| 평점 평균 | 4.15 / 5.0 |

---

## data/ 폴더 상세

| 파일 | 설명 |
|------|------|
| `smart_sampling.py` | 호텔별 리뷰를 최대 20개로 스마트 샘플링. 최신 리뷰 우선 + 평점 구간별 균등 샘플링(1점 2개, 2점 2개, 3점 4개, 4점 6개, 5점 6개). 입력: `hotelrec_geo_186338.json` |
| `generate_profiles.py` | 샘플링된 리뷰 20개를 LLM(GPT-4o-mini)에 전달해 호텔별 3문장 프로파일 생성. Luxia Cloud API 사용. `.env`에 `LUXIA_API_KEY` 필요 |
| `hotel_profiles.json` | `generate_profiles.py` 출력. 호텔 URL → `{hotel_id, hotel_name, avg_rating, profile(3문장 텍스트)}` 매핑 |

### hotel_profiles.json 구조

```json
{
  "Hotel_Review-g186338-d123456-...html": {
    "hotel_id":      "123456",
    "hotel_name":    "Hotel Name London",
    "avg_rating":    4.2,
    "strategy":      "primary_3yr",
    "total_reviews": 850,
    "sampled_count": 20,
    "profile":       "This centrally-located hotel offers ... Key strengths include ... Guests occasionally note ..."
  }
}
```

---

## scripts/ 폴더 상세

전처리·EDA 파이프라인이 번호 순서대로 구성돼 있습니다. 자세한 내용은 **[scripts/README.md](scripts/README.md)** 를 참고하세요.

### 파이프라인 흐름

```
HotelRec.txt (47GB)
    │
    ├── 01_peek.py          스키마 미리보기 (콘솔 출력)
    ├── 02_validate.py      전체 검증 통계  →  eda-alldata-output/validation_stats.json
    ├── 03_sample.py        랜덤 샘플링     →  eda-alldata-output/sample_{k}.jsonl
    ├── 04_filter_parquet.py  품질 필터링   →  eda-alldata-output/hotelrec_filtered.parquet
    ├── 05_eda.py           전체 EDA 차트   →  eda-alldata-output/eda_*.png
    ├── 06_normalize.py     정규화 + ID 매핑 → eda-alldata-output/hotelrec_normalized.parquet
    ├── 07_kcore_filter.py  K-core 필터링   →  eda-alldata-output/hotelrec_kcore{k}.parquet
    ├── 08_make_views.py    학습/검증 분할   →  eda-alldata-output/views/
    ├── 09_geo_analysis.py  지역별 분포 분석 →  eda-alldata-output/geo_stats.csv + geo_*.png
    │
    └── 10_extract_london.py  런던 추출     →  eda-london-output/london_reviews.json
            │
            ├── 11_london_eda.py   런던(46 geo) EDA  →  eda-london-output/london_eda_*.png
            └── 12_g186338_eda.py  런던 중심부 EDA   →  eda-london-g186338-output/g186338_eda_*.png
```

### 스크립트 요약

| 스크립트 | 역할 | 주요 입력 | 주요 출력 |
|---------|------|---------|---------|
| `01_peek.py` | 데이터 스키마 확인 | HotelRec.txt | 콘솔 출력 |
| `02_validate.py` | 품질 통계 수집 | HotelRec.txt | validation_stats.json |
| `03_sample.py` | 균등 랜덤 샘플링 (Reservoir) | HotelRec.txt | sample_{k}.jsonl |
| `04_filter_parquet.py` | 품질 필터 + Parquet 변환 | HotelRec.txt | hotelrec_filtered.parquet |
| `05_eda.py` | EDA 차트 4종 생성 | filtered.parquet / sample.jsonl / **원본** | eda_*.png |
| `06_normalize.py` | 정규화 + 정수 인덱싱 | HotelRec.txt | hotelrec_normalized.parquet, id_maps.pkl |
| `07_kcore_filter.py` | K-core 필터링 | normalized.parquet | hotelrec_kcore{k}.parquet |
| `08_make_views.py` | train/val/test 분할, NLP용, 메타 집계 | kcore.parquet | views/*.parquet |
| `09_geo_analysis.py` | 지역별 분포 시각화 | hotels.parquet / **원본** | geo_stats.csv, geo_*.png |
| `10_extract_london.py` | 런던 리뷰 추출 (46 geo_id) | HotelRec.txt + geo_stats.csv | london_reviews.json |
| `11_london_eda.py` | 런던 전체 EDA 차트 5종 | london_reviews.json | london_eda_*.png |
| `12_g186338_eda.py` | 런던 중심부 EDA 차트 5종 | london_reviews.json | g186338_eda_*.png |

> `05_eda.py`와 `09_geo_analysis.py`는 `--src raw` / `--raw` 플래그로 사전 처리 없이 HotelRec.txt 원본에서 직접 실행할 수 있습니다.

---

## 출력 폴더 상세

### eda-alldata-output/

전체 HotelRec 데이터를 처리한 결과물입니다.

| 파일 | 설명 |
|------|------|
| `validation_stats.json` | 데이터 품질 통계 (결측값, 평점 분포, 날짜 범위 등) |
| `geo_stats.csv` | 지역별 리뷰 수·호텔 수·평균 평점 (40,771개 geo_id) |
| `eda_rating_dist.png` | 평점 분포 막대 차트 |
| `eda_text_length.png` | 텍스트 길이 히스토그램 |
| `eda_year_dist.png` | 연도별 리뷰 수 |
| `eda_sub_ratings.png` | 서브 평점 항목별 평균 |
| `geo_top30_reviews.png` | 리뷰 수 Top 30 지역 |
| `geo_top30_hotels.png` | 호텔 수 Top 30 지역 |
| `geo_rating_top20.png` | 평균 평점 Top 20 지역 |
| `*.parquet`, `*.jsonl`, `*.pkl`, `views/` | 중간 처리 파일 (git 미포함, 재생성 가능) |

### eda-london-output/

런던 전체(46개 geo_id, 836,435건) EDA 결과입니다.

| 파일 | 설명 |
|------|------|
| `london_reviews.json` | 런던 리뷰 전체 (769 MB, git 미포함) |
| `london_eda_rating_dist.png` | 평점 분포 |
| `london_eda_text_length.png` | 텍스트 길이 히스토그램 |
| `london_eda_year_dist.png` | 연도별 리뷰 수 |
| `london_eda_sub_ratings.png` | 서브 평점 평균 |
| `london_eda_top_hotels.png` | 리뷰 수 Top 20 호텔 |

### eda-london-g186338-output/

런던 중심부(geo_id g186338 단독, 728,654건, 호텔 1,618개) EDA 결과입니다.

| 파일 | 설명 |
|------|------|
| `g186338_eda_rating_dist.png` | 평점 분포 |
| `g186338_eda_text_length.png` | 텍스트 길이 히스토그램 |
| `g186338_eda_year_dist.png` | 연도별 리뷰 수 |
| `g186338_eda_sub_ratings.png` | 서브 평점 평균 |
| `g186338_eda_top_hotels.png` | 리뷰 수 Top 20 호텔 |

### 런던 범위 기준

`10_extract_london.py`는 `geo_stats.csv`에서 `location_slug`에 `"London_England"`가 포함된 geo_id를 모두 선택합니다. Greater London 행정구역(32개 자치구 + City of London) 전체가 포함되며, Heathrow 공항 인근(Hounslow, Hayes, West Drayton 등)도 포함됩니다. Windsor, Watford, Guildford 등 Greater London 경계 밖은 제외됩니다.

---

## 환경 설정

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
pip install duckdb             # scripts/07, 08, 09에 필요
```

`data/generate_profiles.py` 실행 시 `.env` 파일에 API 키가 필요합니다:

```
LUXIA_API_KEY=your_api_key_here
```

---

## 빠른 실행 (사전 처리 없이 EDA만)

`HotelRec.txt`만 있으면 아래 명령으로 전체 EDA와 런던 추출까지 실행할 수 있습니다.

```bash
# 전체 데이터 EDA (약 7분)
python scripts/05_eda.py --src raw

# 지역별 분포 분석 및 geo_stats.csv 생성 (약 7분)
python scripts/09_geo_analysis.py --raw

# 런던 리뷰 추출 (약 6분)
python scripts/10_extract_london.py

# 런던 EDA
python scripts/11_london_eda.py
python scripts/12_g186338_eda.py
```


## Semantic ID 구현 및 다음 단계

두 방식 모두 동일한 1,619개 호텔에 대해 4토큰 고유 ID를 생성했다.
각 방식의 코드, 분석 그래프, 산출물은 `semantic_ids/` 아래에 분리해 보관한다.

- [Semantic ID 실행 및 산출물](semantic_ids/README.md)
- [평가 메트릭 및 BM25·SASRec·BERT4Rec 실험 계획](docs/EXPERIMENT_PLAN.md)

추천 모델 학습과 추천 성능 비교는 아직 수행하지 않았다.
