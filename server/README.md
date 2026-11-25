# 서버 공동 개발

FastAPI + PostgreSQL 17 + Redis 7.4 개발 환경이다. Docker Desktop의 Linux 컨테이너 및 Docker Compose v2가 필요하다. Windows는 WSL 2 기반 Docker Desktop을 사용한다.

## 실행

저장소 루트에서 실행한다 (Windows PowerShell / macOS 터미널 공통).

```sh
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

- API 문서: http://localhost:8000/docs
- 프로세스 상태: http://localhost:8000/health
- PostgreSQL / Redis 연결 확인: http://localhost:8000/health/ready
- React 개발 서버 실행은 [프런트엔드 안내](../frontend/README.md)를 참고한다. Vite는 `/api` 요청을 FastAPI로 프록시한다.

`server/app/` 수정은 자동 반영된다. 서버 의존성을 변경하면 다시 `docker compose up --build -d`를 실행한다. 서버 requirements는 버전 범위이므로 빌드 시점에 따라 세부 버전이 달라질 수 있다.

```sh
docker compose logs -f api
docker compose exec db psql -U graduation -d graduation
docker compose exec redis redis-cli ping
docker compose down
```

DB 사용자나 DB명을 변경했다면 psql 명령에도 같은 값을 사용한다. `down` 후에도 PostgreSQL 데이터는 named volume에 남는다. `docker compose down -v`는 DB 데이터를 삭제하므로 초기화할 때만 사용한다. Redis는 재생성 가능한 캐시로 사용하며 영구 보존하지 않는다.

## 환경 변수

루트 `.env.example`에 있는 변수 중 필요한 값만 루트 `.env`에 추가한다. 대화 추천에 필요한 `LUXIA_API_KEY`는 서버 컨테이너에 전달된다. 키를 나중에 추가한 경우 루트에서 `docker compose up -d api`로 설정을 반영한다. 키가 비어 있으면 카탈로그 탐색과 상태 확인을 사용할 수 있고, 대화 API는 `503 llm_not_configured`를 반환한다.

API_PORT로 API 포트를 바꿀 수 있다. PostgreSQL과 Redis는 컨테이너 내부 네트워크에서만 접근한다. API도 호스트의 127.0.0.1에만 공개한다. 이 구성과 기본 비밀번호는 로컬 개발용이며 외부 배포 전 인증, 비밀값, TLS 등을 별도로 설정해야 한다.

## 대화 추천

`POST /api/chat`에는 메시지와 요청마다 고유한 UUID v4인 `request_id`를 보낸다. 다음 턴부터는 응답의 `conversation_id`도 보낸다. 응답에는 적용된 조건, 답변, 호텔 카드 최대 3개가 들어 있다. 네트워크 실패 후에는 같은 요청 ID와 본문으로 재시도한다. 만료된 대화는 `404 conversation_expired`, 동시에 갱신된 대화는 `409 conversation_conflict`로 응답한다.

서버는 최근 12개 대화 메시지와 현재 조건을 Redis에 보관한다. 대화는 마지막 성공 요청 이후 24시간에 만료되며, 각 성공 요청은 24시간 동안 재전송할 수 있다. Luxia Cloud에는 조건 해석용 메시지와 최근 문맥, 추천 이유에 필요한 호텔 프로파일을 전송한다.

최근 추천 목록 6개의 순서와 카드 ID도 저장한다. “첫 번째 호텔 빼줘”는 직전 추천의 1번 카드를, “처음 추천한 첫 번째 호텔”은 아직 보관 중인 첫 목록의 1번 카드를 가리킨다. 지칭 대상이나 변경할 조건이 불명확하면 확인 질문을 하고 기존 조건을 유지한다. 대화에서 검색을 명시적으로 초기화하면 기존 조건, 제외 호텔, 추천 목록과 이전 대화 문맥을 비운다.

기존 호텔 JSON을 읽기 전용으로 마운트한다. 추천 서비스는 BM25로 후보를 찾은 다음 K-means Semantic ID의 공통 접두사로 재정렬한다. 호텔 정보와 외부 링크는 카탈로그에서 구성한다.

## 테스트와 모델 학습

저장소 루트에서 서버 의존성을 설치한 Python 환경으로 `python -m unittest discover -s server/tests -v`를 실행한다. 테스트용 Redis가 있으면 `TEST_REDIS_URL`을 지정하여 API·Redis 통합 테스트도 실행한다. 테스트는 모의 LLM을 사용한다.

모델 학습은 루트에서 기존 `uv sync --locked`, `uv run python scripts/...` 흐름을 사용한다. 서버 이미지에는 학습용 torch 의존성을 설치하지 않는다. `artifacts/`는 API의 `/app/artifacts`에 읽기 전용으로 연결한다.

## 동료와 작업

설정 파일을 Git으로 공유하고 각자 `git pull` 후 동일한 Compose 명령으로 실행한다. 컨테이너와 DB 데이터는 각자의 PC에 독립적으로 생성된다. 의존성 변경 시 재빌드하고, 모델 파일과 DB 데이터의 공유 방식은 별도로 합의한다.
