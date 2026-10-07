# Changelog

이 프로젝트의 주요 변경 사항을 기록합니다.
형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따릅니다.

## [5.0.0] - 2026-10-08

### Added

- SonarQube 정적분석을 CI에 통합 (`docker-compose.yml`에 `sonarqube`/`sonar-db` 서비스, `sonar-project.properties`, Jenkins 파이프라인에 `SonarQube Analysis`/`Quality Gate` 스테이지) — pytest 커버리지(`coverage.xml`)를 그대로 재사용해 스캔
- 할 일에 우선순위(`priority`: 👑 중요 / 💌 일반)와 마감일(`due_date`) 필드 추가, 지난 마감일은 목록에서 빨간 뱃지로 강조
- 할 일 목록 검색(제목·설명)과 정렬(마감일순/우선순위순) 추가
- 할 일을 모두 끝내면 축하 배너가 뜨고, 매일 전부 완료하면 연속 달성 스트릭을 집계해 보여주는 `GET /stats` API 추가
- 핑크·골드 톤의 "투두 프린세스" 테마로 전체 화면(로그인/목록/릴리스노트) 리디자인 — 커스텀 커서, 구글 폰트(Jua) 적용

### Changed

- `todos` 테이블에 `priority`/`due_date` 컬럼 추가, 기존 DB(볼륨)도 자동 마이그레이션되도록 처리

## [4.0.0] - 2026-10-02

### Added

- `pyproject.toml`에 pytest/coverage 설정 추가 (`pythonpath`로 `conftest.py`의 `sys.path` 조작 대체)
- 테스트를 13개 → **23개**로 확장, `main.py` 라인 커버리지 **100%** 달성 (`pytest-cov`)
- `pytest-html`/`pytest-cov` HTML 리포트를 Jenkins Docker 배포 파이프라인 4종(`jenkins/*.groovy`) 모두에 연결 — **테스트를 통과해야만 Docker 빌드/배포 단계로 진행**, JUnit 결과와 커버리지 리포트를 빌드 아티팩트로 보관
- 배포된 실제 환경(팀 서버)에 직접 HTTP로 붙어 검증하는 통합 테스트 추가 (`tests/test_integration_deployed.py`, `pytest -m integration`)
- Playwright 기반 UI 테스트 추가 (`ui-tests/`) — 배포된 앱을 헤드리스 브라우저로 조작해 로그인/가입/CRUD/인라인수정/삭제/로그아웃/릴리스노트 8개 시나리오 검증, HTML 리포트 생성

### Fixed

- `sqlite3.Connection`을 `with get_db() as conn:`으로만 써서 커넥션이 닫히지 않던 리소스 누수(ResourceWarning) 수정

### Changed

- 의존성 버전을 보안 패치가 적용된 하한선으로 고정: `fastapi>=0.142.0`, `starlette>=1.7.0`(CVE-2026-48710), `uvicorn[standard]>=0.54.0`, `pytest>=9.0.3`(CVE-2025-71176)
- 테스트 클라이언트를 `httpx`에서 `httpx2`로 교체 (Starlette TestClient 권장 사항)
- 사용하지 않는 `jinja2` 의존성 제거

## [3.0.0] - 2026-09-25

### Added

- Docker 배포 지원: `Dockerfile`(root가 아닌 `appuser`로 실행), `.dockerignore`, `docker-compose.yml`
- Jenkins 배포 파이프라인 2종 — GitHub clone 후 `docker compose` 배포 / DockerHub push 후 `docker pull` 배포 (본인 서버·팀 서버)
- 컨테이너 헬스체크(`HEALTHCHECK`, `/health`) — `docker ps`에 `healthy` 표시
- Jenkins 빌드 실패 시 이메일 알림, 복구 시 복구 알림

### Changed

- **[BREAKING]** DB(`todo.db`)와 세션 키(`.session_secret`)를 `DATA_DIR` 환경변수 경로에 저장 (기본값은 기존과 같은 앱 폴더, Docker에서는 `/app/data` 볼륨). 기존 컨테이너의 데이터는 새 볼륨으로 옮겨지지 않음
- 의존성 버전 고정 (`requirements.txt`, `requirements-dev.txt`)
- compose 배포에서도 화면 하단에 Jenkins 빌드 번호·커밋이 표시되도록 `BUILD_NUMBER`/`GIT_COMMIT` 전달
- `docker-compose.yml`의 컨테이너 이름·포트를 `CONTAINER_NAME`/`HOST_PORT`로 바꿀 수 있게 함 (공용 팀 서버에서 충돌 방지)

### Fixed

- 재배포(컨테이너 재생성)할 때마다 계정과 할 일이 모두 지워지던 문제 — Docker 볼륨으로 데이터 유지

## [2.0.0] - 2026-09-18

### Added

- 회원가입/로그인/로그아웃 (`/auth/register`, `/auth/login`, `/auth/logout`, `/auth/me`), 세션 쿠키 기반
- 할 일 데이터를 SQLite(`todo.db`)로 이전, 계정별로 완전히 분리해서 저장
- 로그인하지 않으면 `/`가 `/login` 화면으로 리다이렉트됨

### Changed

- **[BREAKING]** `/todos` API 전체가 로그인을 요구하도록 변경됨 (비로그인 요청은 401)
- 기존 `todo.json`의 데이터는 더 이상 자동으로 불러오지 않음 (파일은 참고용으로 남겨둠). 동시성 문제도 SQLite가 직접 처리하므로 수동 파일 락(`flock`) 코드를 제거함

## [1.3.0] - 2026-09-18

### Added

- `GET /health` 헬스체크 엔드포인트 추가 (배포 스크립트/모니터링용)
- 파비콘 추가로 `/favicon.ico` 404 로그 제거

### Changed

- 할 일 수정을 브라우저 `prompt()` 대신 목록에서 바로 편집하는 인라인 편집 방식으로 변경
- 모바일 화면에서 입력창이 자동 확대되던 문제 수정 (입력 폰트 16px 이상으로 조정), 좁은 화면 여백/줄바꿈 개선

### Fixed

- 여러 요청(및 여러 uvicorn 프로세스)이 동시에 `todo.json`을 읽고 덮어써서 변경 사항이 유실될 수 있던 경쟁 조건을 스레드 락 + 파일 락(`flock`)으로 방지

## [1.2.0] - 2026-09-18

### Added

- 현재 버전과 빌드 정보를 확인할 수 있는 `/api/version` API 추가
- 릴리스 노트를 볼 수 있는 `/release-notes` 페이지 추가 (이 문서를 렌더링해서 보여줍니다)
- 화면 하단 푸터에 현재 버전 및 릴리스 노트 링크 표시
- `pytest` 기반 자동 테스트와 Jenkins 파이프라인(`Jenkinsfile`) 추가

## [1.1.0] - 2026-09-17

### Added

- `GET /todos?completed=true|false` 로 진행중/완료 항목 필터링 지원

### Fixed

- 공백만 입력한 제목이 `min_length` 검사를 통과해 저장되던 결함 수정

## [1.0.0] - 2026-09-10

### Added

- 할 일 목록 CRUD API (`GET/POST/PUT/DELETE /todos`)
- 기본 웹 UI 화면
