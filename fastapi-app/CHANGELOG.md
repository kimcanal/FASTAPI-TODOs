# Changelog

이 프로젝트의 주요 변경 사항을 기록합니다.
형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따릅니다.

## [7.0.0] - 2026-11-04

### Added

- JMeter 부하 테스트를 `docker-compose.yml`에 추가 (`jmeter` 서비스) — 회원가입으로 세션을 만든 뒤 `/health`, `/todos`(조회·생성)를 호출하는 테스트 플랜(`jmeter/fastapi_test_plan.jmx`), 사용자 10명·10초 램프업. 이미지는 Jenkins가 미리 빌드해 Docker Hub(`lucatonikroos/jmeter-fastapi-todos`)로 올려두고, 각 서버는 pull만 한다 (archive.apache.org 다운로드가 느리거나 막히는 네트워크 대응)
- InfluxDB(1.8)를 추가해 JMeter 백엔드 리스너(`InfluxdbBackendListenerClient`)가 테스트 중 실시간으로 메트릭을 적재하도록 구성, Grafana에 InfluxDB 데이터소스 + JMeter 전용 대시보드(grafana.com ID 5496) 연결
- 할 일 CSV 내보내기/가져오기 추가 — `GET /todos/export`로 본인 할 일을 CSV로 내려받고, `POST /todos/import`로 CSV 파일을 업로드해 일괄 추가 (기존 항목은 그대로 둠, 유효하지 않은 행은 건너뛰고 개수 안내)

### Changed

- 이미지 버전 고정/갱신: `prom/prometheus:v3.15.1`, `grafana/grafana:13.3.0`
- SonarQube/Prometheus/Grafana 포트를 `127.0.0.1`에만 바인딩 (기존엔 전체 공개) — 접속은 SSH 터널 또는 Tailscale로. node-exporter/cadvisor는 원래부터 외부 미공개
- Grafana 관리자 비밀번호를 `.env`(git 미포함) 참조로 전환, 회원가입/익명 접근 비활성화(`GF_USERS_ALLOW_SIGN_UP`, `GF_AUTH_ANONYMOUS_ENABLED`)
- 모든 서비스를 전용 네트워크(`loadtest-net`)로 묶음 — JMeter가 내부 네트워크로 앱/InfluxDB에 접근
- Jenkins 파이프라인에 JMeter 결과 대기/수집 단계 추가, SonarQube 분석 단계는 (아래 Fixed 참고) 맨 뒤로 옮기고 실패해도 빌드를 막지 않게 변경

### Fixed

- SonarQube 버전을 `26.10.0-community`로 고정하려다 배포가 깨짐 — 실제 저장된 데이터는 v9.9.8이었는데 SonarQube는 LTS를 건너뛰고 업그레이드할 수 없어("upgrade to the 24.12 version first" 등) 기동 자체가 실패했다. `lts-community`(9.9.x, 기존과 동일 버전)로 되돌려 복구. **9.9 → 최신 LTS까지 단계별 업그레이드는 다음 주차 이후 과제로 남김**
- Jenkins가 발행하는 JMeter HTML 리포트가 빈 화면으로 보이던 문제 수정 — 기본 `DirectoryBrowserSupport.CSP`가 리포트의 스크립트 실행 자체를 막고 있었음. `sandbox allow-scripts allow-same-origin` + `connect-src 'self'`를 포함한 CSP로 교체

## [6.0.0] - 2026-10-28

### Added

- Prometheus/Grafana/Node Exporter/cAdvisor 모니터링 스택을 `docker-compose.yml`에 추가 — 애플리케이션 메트릭(`/metrics`, `prometheus-fastapi-instrumentator`)과 시스템/컨테이너 메트릭(CPU·메모리·디스크·네트워크)을 수집해 Grafana 대시보드로 시각화
- Prometheus는 서버 자신에게만 공개(`127.0.0.1:7070`), node-exporter/cadvisor는 외부 포트 없이 내부 네트워크로만 수집하도록 구성, Grafana는 비밀번호 정책(`GF_AUTH_BASIC_PASSWORD_POLICY`) 적용
- 할 일 삭제를 **휴지통** 방식으로 변경 — 삭제는 소프트 삭제(`deleted_at`)로 처리되어 7일간 보관되며, `GET /todos/trash`로 목록 확인 후 `POST /todos/{id}/restore`로 복원 가능 (7일이 지나면 서버 기동 시 자동으로 완전히 삭제됨)
- 화면에 "🗑 휴지통" 패널 추가 — 삭제 직후 5초간 뜨는 "실행취소" 토스트와, 언제든 열어서 보관 중인 항목을 확인·복원할 수 있는 휴지통 버튼 모두 제공
- 복원된 할 일은 완료 여부와 관계없이 항상 **미완료 상태**로 돌아옴

### Changed

- 이미지 버전 고정: `prom/prometheus:v3.15.0`, `grafana/grafana:13.2.4`(2026-10-13 보안 패치), `prom/node-exporter:v1.12.1`, `ghcr.io/google/cadvisor:v0.60.6`

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
