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

## (3) Claude Code + Playwright UI 테스트

`ui-tests/`에 Playwright Test 기반 UI 테스트 8개를 작성했습니다 (로그인 리다이렉트, 회원가입, 할 일 추가, 완료 처리, 인라인 수정, 삭제, 로그아웃, 릴리스 노트). 배포된 앱(본인 서버)을 실제 헤드리스 브라우저로 조작하며 검증합니다.

```bash
cd ui-tests && BASE_URL=http://163.239.77.80:5001 npx playwright test
```

![Playwright 테스트 결과](./(3)-1_playwright_report.png)

### 결과 요약

- 8개 시나리오 전부 통과 (`playwright-report/index.html`)
- 발견한 이슈: 인라인 수정 모드로 전환되면 `<li>`의 텍스트 콘텐츠가 더 이상 입력값을 포함하지 않아(`input value`는 텍스트 노드가 아님) 기존 `hasText` 로케이터가 깨짐 → 편집 중인 행을 `li.editing`으로 직접 찾도록 테스트를 수정해 해결
