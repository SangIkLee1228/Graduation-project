# server/

추천 결과를 제공하는 API 서버다. 현재는 FastAPI + PostgreSQL 기본 구성과 `/health` 엔드포인트만 있다.

- 학습·실험은 프로젝트 루트의 uv 환경에서 수행하고, 서버는 이 폴더 안에서 Docker로 빌드한다.
- 서버 의존성은 이 폴더의 `pyproject.toml`·`uv.lock`으로 루트와 분리한다. 루트의 uv workspace에 넣지 않는다.
- 서버가 `artifacts/`의 학습 산출물을 쓰게 되면 compose에 읽기 전용 볼륨으로 연결한다.
  서버가 사용할 산출물 목록과 형식을 먼저 문서화한다.

## 구성

| 파일 | 역할 |
|---|---|
| `compose.yaml` | 배포·공통 설정: `api`(FastAPI), `db`(PostgreSQL 17) |
| `compose.override.yaml` | 로컬 개발용: 코드 마운트 + `--reload`, DB 포트 5432 노출 |
| `Dockerfile` | `python:3.12-slim` + uv로 의존성 설치 |
| `.env.example` | DB 계정·접속 정보 예시. 복사해서 `.env`로 사용 (Git 제외) |
| `app/main.py` | FastAPI 앱. `GET /health`가 DB 연결까지 확인 |

Redis, 모델 추론 서비스는 필요해질 때 `compose.yaml`에 서비스로 추가한다.

## 로컬 실행

```bash
cd server
cp .env.example .env              # 최초 1회
docker compose up --build         # http://localhost:8000/health, 문서: /docs
docker compose down               # 종료 (DB 데이터는 pgdata 볼륨에 유지)
docker compose down -v            # DB 데이터까지 삭제
```

`app/` 코드를 수정하면 컨테이너가 자동으로 다시 시작된다.
의존성 추가는 `server/`에서 `uv add <패키지>` 후 `docker compose up --build`로 이미지를 다시 만든다.

Windows에서는 저장소를 WSL2 리눅스 파일시스템(`~/...`) 안에 클론해서 실행한다.
`C:\` 아래에서 실행하면 파일 마운트가 느리고 `--reload`가 변경을 감지하지 못할 수 있다.

## 배포 (AWS)

```bash
docker compose -f compose.yaml up -d --build    # 개발용 override 제외
```

- Apple Silicon 맥에서 만든 이미지는 기본적으로 arm64다. x86 인스턴스에 올릴 이미지는
  `docker build --platform linux/amd64`로 빌드하거나 서버에서 직접 빌드한다.
- 배포 환경의 `.env`에는 `.env.example`과 다른 비밀번호를 사용한다.
