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
- React 개발 서버는 localhost:5173 또는 localhost:3000에서 별도 실행한다. 프론트엔드 코드는 아직 포함하지 않는다.

`server/app/` 수정은 자동 반영된다. 서버 의존성을 변경하면 다시 `docker compose up --build -d`를 실행한다. 서버 requirements는 버전 범위이므로 빌드 시점에 따라 세부 버전이 달라질 수 있다.

```sh
docker compose logs -f api
docker compose exec db psql -U graduation -d graduation
docker compose exec redis redis-cli ping
docker compose down
```

DB 사용자나 DB명을 변경했다면 psql 명령에도 같은 값을 사용한다. `down` 후에도 PostgreSQL 데이터는 named volume에 남는다. `docker compose down -v`는 DB 데이터를 삭제하므로 초기화할 때만 사용한다. Redis는 재생성 가능한 캐시로 사용하며 영구 보존하지 않는다.

## 환경 변수

루트 `.env.example`의 Docker 설정을 참고해 각자 루트 `.env`에 필요한 값만 추가한다. 기존 `.env`를 덮어쓰지 않는다. 기본값만으로 로컬 실행할 수 있다. `.env`와 API 키는 Git에 커밋하지 않는다. 루트 `.env` 전체를 API 컨테이너에 전달하지 않는다.

API_PORT로 API 포트를 바꿀 수 있다. PostgreSQL과 Redis는 컨테이너 내부 네트워크에서만 접근한다. API도 호스트의 127.0.0.1에만 공개한다. 이 구성과 기본 비밀번호는 로컬 개발용이며 외부 배포 전 인증, 비밀값, TLS 등을 별도로 설정해야 한다.

## 모델 학습과 연동

모델 학습은 루트에서 기존 `uv sync --locked`, `uv run python scripts/...` 흐름을 사용한다. 서버 이미지에는 학습용 torch 의존성을 설치하지 않는다. `artifacts/`는 API의 `/app/artifacts`에 읽기 전용으로 연결한다. 추천 추론, 모델 로딩, DB 스키마 및 사용자 기능은 이후 구현한다.

## 동료와 작업

설정 파일을 Git으로 공유하고 각자 `git pull` 후 동일한 Compose 명령으로 실행한다. 컨테이너와 DB 데이터는 각자의 PC에 독립적으로 생성된다. 의존성 변경 시 재빌드하고, 모델 파일과 DB 데이터의 공유 방식은 별도로 합의한다.
