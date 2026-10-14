# frontend/ — 웹사이트 데모 (목업)

런던 호텔 추천 서비스 "Talk to Book"의 프론트엔드 목업이다. React + Vite로 만들었고, 아직 백엔드 API와 연결하지 않았다.
실제 호텔 1,619곳의 프로파일·평점·K-means Semantic ID를 정적 JSON으로 읽어 화면을 구성한다.

## 실행

Node.js 20 이상이 필요하다.

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run build      # dist/ 에 정적 파일 생성
```

`public/data/hotels.json`은 Git에 포함되어 있어 바로 실행할 수 있다.

## 화면 구성

| 기능 | 내용 |
|---|---|
| 자연어 검색 | 상단 검색창. "하이드파크 근처 조용한 호텔"처럼 입력하면 해석된 조건과 결과를 보여주고, 프로파일에서 맞은 단어를 강조한다 |
| 카테고리 탭 | Semantic ID 첫 토큰(C1) 클러스터 분석 결과로 나눈 유형 (부티크·B&B, 저가·호스텔 등) |
| 호텔 카드·상세 | 평점, 리뷰 수, LLM 프로파일, Semantic ID 레벨별 의미, 리뷰 샘플, 앞자리가 같은 비슷한 호텔 |
| 예약 링크 | TripAdvisor 호텔 페이지, Booking.com 검색, Google 지도 (사이트로 이동) |
| 최근 평점 경고 | 최근 1년 평균이 전체 평균보다 0.5점 이상 낮으면 "최근 평점 하락" 표시 |
| 에이전트 위젯 | 오른쪽 아래 채팅. 질의를 받아 호텔 3곳을 추천하고 상세 화면·전체 목록으로 연결 |
| 이벤트 기록 | 클릭률·전환률 측정용 이벤트를 `window.dataLayer`(GA4 형식)와 콘솔에 기록 |

## 데모라서 실제와 다른 점

- **에이전트와 검색은 키워드 매칭이다.** `src/lib/search.js`의 한→영 키워드 사전으로 질의를 영어 프로파일과 맞춘다.
  추천 모델이 준비되면 `ChatWidget.jsx`의 `reply()`와 `App.jsx`의 검색을 서버 API 호출로 바꾼다.
- **가격·사진은 없다.** HotelRec에 없는 정보라 Semantic ID 클러스터 색과 이니셜로 썸네일을 대신한다.
- **C1 유형 이름은 클러스터 평균 경향이다.** 개별 호텔과 맞지 않을 수 있다 (예: 고평점 부티크 호텔이 "저가·호스텔" 클러스터에 속함).
- **이벤트는 외부로 전송하지 않는다.** GA4나 Amplitude를 붙일 때 `src/lib/analytics.js`의 `track()`만 바꾼다.

기록하는 이벤트: `search_submitted`, `category_selected`, `hotel_opened`, `booking_clicked`, `chat_opened`,
`chat_message_sent`, `chat_recommendation_clicked`.

## 데이터 다시 만들기

```bash
uv run python scripts/demo/build_frontend_data.py --reviews <hotelrec_geo_186338.json 경로>
```

`data/processed/`의 프로파일·샘플 리뷰, `artifacts/semantic_ids/rq_kmeans/`의 ID, 런던 원본 리뷰(최근 1년 평점 계산용)를 합쳐
`frontend/public/data/hotels.json`을 만든다. 원본 리뷰 경로를 생략하면 `data/raw/hotelrec_geo_186338.json`을 읽는다.

평점은 원본 리뷰 전체의 평균이다. `hotel_profiles.json`의 `avg_rating`은 평점 구간별로 균등하게 뽑은 샘플 20개의 평균이라
실제 평균과 다르므로 사용하지 않는다.

## 구조

```
frontend/
├── index.html
├── public/data/hotels.json     # 데모 데이터 (scripts/demo/build_frontend_data.py로 생성)
└── src/
    ├── App.jsx                 # 검색·목록·탭·정렬
    ├── components/
    │   ├── HotelCard.jsx
    │   ├── HotelModal.jsx      # 상세 화면
    │   ├── ChatWidget.jsx      # 에이전트 위젯
    │   └── common.jsx          # 썸네일, 평점, Semantic ID 배지 등
    ├── lib/
    │   ├── search.js           # 키워드 사전·검색
    │   ├── clusters.js         # C1 유형 이름·색
    │   ├── hotel.js            # 추천 점수, 예약 링크, 비슷한 호텔
    │   └── analytics.js        # 이벤트 기록
    └── styles.css
```
