# Week 5 — 자동화 테스트 (pytest/coverage, 배포 환경 통합 테스트, Playwright UI 테스트)

| 항목 | 방식 | 대상 | Jenkins Job |
|---|---|---|---|
| (1) 테스트 게이트 + 팀 서버 배포 | pytest 통과해야 `docker compose` 빌드/배포 진행 | http://163.239.77.76:8022 | Jenkins Deploy Docker legacy team |
| (2) 배포 환경 API 통합 테스트 | pytest + httpx2, 실제 서버에 HTTP 요청 | http://163.239.77.76:8022 | - |
| (3) UI 테스트 | Playwright (Claude Code 연동) | http://163.239.77.80:5001 | - |

## (1) 테스트 후 Docker 빌드로 넘어가는 파이프라인 — 팀 서버 배포

`jenkins/deploy-compose-team.groovy`에 Install → Test 단계를 추가했습니다. pytest가 실패하면 이후 Docker 빌드/배포 단계가 실행되지 않습니다.

![브라우저 캡처](./(1)-1_팀서버_웹사이트_163.239.77.76-8022.png)
![젠킨스 빌드내역](./(1)-2_젠킨스_빌드내역.png)
![pytest html](./(1)-3_pytest_html.png)
![coverage html](./(1)-4_coverage_html.png)

## (2) 배포 환경에서 API 자동 테스트

`fastapi-app/tests/test_integration_deployed.py` — pytest + httpx2로 실제 배포된 서버(팀 서버)에 직접 HTTP 요청을 보내 회원가입/로그인/CRUD/권한 격리/로그아웃을 검증합니다.

```bash
API_BASE_URL=http://163.239.77.76:8022 pytest -m integration \
    tests/test_integration_deployed.py -v --html=integration-report.html --self-contained-html
```

![통합 테스트 html](./(2)-1_integration_report_html.png)

## (3) Claude Code로 Playwright 연동 — UI 테스트 수행 및 보고서

### 1. 목적

지금까지의 테스트(`test_main.py`, `test_integration_deployed.py`)는 전부 HTTP 요청/응답 레벨 검증입니다. 실제 사용자가 브라우저에서 클릭·입력하는 흐름까지는 보장하지 못하므로, **배포된 앱을 실제 브라우저로 조작하는 E2E(end-to-end) UI 테스트**를 Claude Code가 직접 작성·실행했습니다.

### 2. 도구 선택 — Playwright vs Selenium

Selenium 대신 **Playwright Test**(`@playwright/test`)를 선택했습니다.

| 비교 | Selenium | Playwright Test |
|---|---|---|
| 설치 | 브라우저 드라이버(ChromeDriver 등) 별도 관리 필요 | `npx playwright install`로 브라우저까지 한 번에 설치 |
| 대기 처리 | 명시적 `WebDriverWait` 작성 필요 | 자동 재시도(auto-waiting) — 엘리먼트가 준비될 때까지 알아서 기다림 |
| 리포트 | 별도 플러그인(pytest-html 등) 필요 | 테스트 러너에 HTML 리포트가 내장 |
| 테스트 격리 | 수동으로 세션/쿠키 관리 | 테스트마다 독립된 브라우저 컨텍스트 자동 생성 |

같은 서버(163.239.77.80)에 Node.js가 이미 있어 추가 설치 부담이 적고, 세션 쿠키 기반 로그인을 매 테스트마다 격리해서 검증하기 좋아 Playwright를 선택했습니다.

### 3. 테스트 대상 및 환경

- 대상: 배포된 실제 앱 — `http://163.239.77.80:5001` (본인 서버, `docker compose` 배포본)
- 도구: Playwright Test v1.63, Chromium(headless)
- 위치: 저장소 `ui-tests/` (`playwright.config.js`, `tests/todo-app.spec.js`)

### 4. 테스트 시나리오 (8개)

| # | 시나리오 | 검증 내용 |
| --- | --- | --- |
| 1 | 비로그인 접근 | `/` → `/login` 리다이렉트 |
| 2 | 회원가입 | 가입 즉시 로그인되어 할 일 목록으로 이동, 사용자명 표시 |
| 3 | 할 일 추가 | 목록에 제목·설명이 보임 |
| 4 | 완료 처리 | 체크박스 토글 → 완료/진행중 필터에 맞게 보이고 사라짐 |
| 5 | 인라인 수정 | 수정 버튼 → 입력창으로 전환 → 저장 후 반영 |
| 6 | 삭제 | 확인 다이얼로그 수락 → 목록에서 제거 |
| 7 | 로그아웃 | 로그인 화면으로 이동, 이후 `/` 재접근도 차단 |
| 8 | 릴리스 노트 | `/release-notes`에 변경 이력이 렌더링됨 |

### 5. 실행

```bash
cd ui-tests
npm install && npx playwright install chromium
BASE_URL=http://163.239.77.80:5001 npx playwright test
npx playwright show-report
```

### 6. 결과

**8개 시나리오 전부 통과** (`playwright-report/index.html`, 총 소요 4.9초).

![Playwright 테스트 결과](./(3)-1_playwright_report.png)

### 7. 테스트 작성 중 발견한 이슈

최초 작성한 시나리오 5(인라인 수정) 테스트가 30초 타임아웃으로 실패했습니다.

- **원인**: `page.locator('#todo-list li', { hasText: '...' })`로 찾은 `<li>`를 수정 버튼 클릭 후에도 그대로 재사용했는데, 수정 모드로 전환되면 `<li>` 내부가 `<input value="...">`로 바뀌면서 **`textContent`에는 input의 value가 포함되지 않음** — `hasText` 필터가 더 이상 그 요소를 찾지 못해 타임아웃이 난 것이었습니다.
- **해결**: 수정 모드로 전환한 뒤에는 `hasText`로 과거의 `item`을 재사용하지 않고, CSS 클래스(`li.editing`)로 "현재 편집 중인 행"을 새로 찾도록 테스트를 수정했습니다.
- **의미**: 이건 테스트 코드만의 문제가 아니라, **실제 사용자 조작 흐름(수정 버튼 클릭 → 입력 → 저장)을 브라우저 레벨에서 그대로 재현했기 때문에 걸러진 문제**입니다. HTTP 레벨 테스트(`test_main.py`)만으로는 발견할 수 없는, UI 테스트의 존재 이유를 보여주는 사례입니다.

### 8. 결론

Playwright로 배포된 앱의 8가지 핵심 사용자 흐름(인증, CRUD, 권한 분리, 릴리스 노트)을 실제 브라우저 레벨에서 검증했고, 전부 정상 동작함을 확인했습니다. 테스트 작성 과정에서 찾은 로케이터 이슈는 테스트 스크립트 버그였을 뿐 앱 자체의 결함은 아니었습니다.

## Claude Code 활용 내역 및 소감

> 아래 "소감"은 초안입니다. 본인 생각/표현으로 바꿔서 제출하세요.

### 활용 내역

이번 주차 과제 전체(테스트 작성, Jenkins 파이프라인 수정, 배포, 통합·UI 테스트, 스크린샷 캡처, 릴리스 노트/버전 관리)를 Claude Code와 함께 진행했습니다.

- **코드 작성**: `pyproject.toml` 설정, pytest 테스트 10여 개 추가(라인 커버리지 91%→100%), 배포 환경 통합 테스트(`test_integration_deployed.py`), Playwright UI 테스트(`ui-tests/`) 전부 Claude Code가 작성
- **버그 발견**: 테스트를 작성/실행하는 과정에서 실제 버그 2개를 찾아 수정함 — `sqlite3` 커넥션이 닫히지 않던 리소스 누수, 인라인 수정 UI 테스트에서 드러난 로케이터 이슈
- **Jenkins 자동화**: 4개 Docker 배포 파이프라인에 Install→Test 단계 추가, 실제 Job 설정(Pipeline script)까지 Claude Code가 브라우저 자동화로 직접 수정하고 빌드를 트리거해서 결과 확인
- **문서/버전 관리**: CHANGELOG, README, 버전 태그(`v4.0.0`), GitHub Release까지 전체 사이클을 Claude Code가 처리

### 소감 (초안 — 본인 말로 수정할 것)

- 테스트 코드 자체를 처음부터 다 짜달라고 하면 금방 끝나긴 하는데, 그 과정에서 실제로 내가 몰랐던 버그(DB 커넥션 안 닫히는 것)를 찾아줘서 신기했다. 테스트를 "숙제라서 쓰는 것"이 아니라 "진짜로 버그를 잡는 도구"로 체감한 계기였다.
- UI 테스트(Playwright)를 만드는 과정에서 테스트 스크립트 자체의 버그(로케이터 문제)가 나왔는데, 이걸 Claude Code가 원인을 분석하고 고치는 과정을 보면서 "UI 테스트가 왜 HTTP 테스트만으로는 부족한지"를 체감했다.
- Jenkins Job 설정을 자동으로 바꾸는 부분에서는 안전장치 때문에 한 번 막혔다 — AI가 공유 서버(팀 서버 배포)에 영향을 주는 작업은 스스로 조심한다는 걸 직접 겪어봤다. 결국 내가 "진행해도 된다"고 명확히 확인해준 뒤에 처리됐다.
- 혼자 할 때보다 확실히 반복 작업(스크린샷 캡처, 리포트 생성, 버전 태깅 등)에 드는 시간이 크게 줄었다. 다만 요구사항을 정확히 전달하고, 중간중간 결과를 검증하는 건 여전히 내 몫이라는 걸 느꼈다.
