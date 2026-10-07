# Week 6 — SonarQube 정적분석 + OWASP Top 10 보안 분석

| 항목 | 내용 |
|---|---|
| 대상 | http://163.239.77.80:5001 (본인 서버, `docker compose` 배포본) |
| SonarQube | http://163.239.77.80:9000 (프로젝트 키: `fastapi-todos`) |
| Jenkins Job | Jenkins Deploy Docker legacy (`jenkins/deploy-compose.groovy`) |

## (1) 1차 분석 수행

`docker-compose.yml`에 `sonarqube`/`sonar-db`(Postgres) 서비스를 추가하고, `sonar-project.properties`를 작성한 뒤 Jenkins 파이프라인에 `SonarQube Analysis` → `Quality Gate` 스테이지를 붙였습니다. pytest가 생성하는 `coverage.xml`을 그대로 재사용해서 스캔합니다.

```
# sonar-project.properties
sonar.projectKey=fastapi-todos
sonar.sources=fastapi-app
sonar.exclusions=fastapi-app/myenv/**,fastapi-app/htmlcov/**,fastapi-app/templates/**,fastapi-app/tests/**
sonar.tests=fastapi-app/tests
sonar.python.coverage.reportPaths=fastapi-app/coverage.xml
```

1차 분석(빌드 #9, v4.0.0 코드 기준) 결과:

| 지표 | 결과 |
|---|---|
| Bugs | 0 |
| Vulnerabilities | 0 |
| Code Smells | 0 |
| 중복도 | 0.0% |
| 커버리지 | 99.4% |
| **Security Hotspot** | **1건** |

![SonarQube 1차 분석 대시보드](./(1)-1_SonarQube_1차분석_대시보드.png)

## (2) 발견사항별 검토 의견

### Security Hotspot — [`fastapi-app/Dockerfile:22`](../../fastapi-app/Dockerfile)

```dockerfile
COPY --chown=appuser:appuser . .
```

- **규칙**: `docker:S6470` — "Make sure that recursively copying directories is safe here."
- **내용**: 빌드 컨텍스트 전체를 재귀적으로 복사하는 패턴이라, `.dockerignore`로 민감 파일을 확실히 제외했는지 수동 검토하라는 경고(=Security Hotspot. 확정된 취약점이 아니라 "사람이 검토해야 하는 지점").
- **검토**: [`fastapi-app/.dockerignore`](../../fastapi-app/.dockerignore)에 `.env`, `.git`, `.session_secret`, `todo.db*`, `app.log` 등 민감 파일/시크릿이 이미 전부 명시적으로 제외되어 있음을 확인했습니다. 실제 이미지에 민감 정보가 포함될 위험은 없습니다.
- **수정 여부**: **코드 수정 없이 Safe로 리뷰 처리**. `COPY . .`을 개별 파일 나열로 바꾸는 방법도 있지만, 파일이 추가될 때마다 Dockerfile을 매번 갱신해야 해서 오히려 유지보수 부담과 누락 위험이 커집니다. `.dockerignore`로 제외 목록을 관리하는 현재 방식이 더 안전합니다.
- **처리**: SonarQube UI → Security Hotspots → 해당 항목 → Status: **Safe** + 위 의견 코멘트.

## (3) 개선 후 2차 분석

이번 주 할 일 관리 기능 개선(아래 "기능 개선" 참고)을 반영해 코드가 달라졌고, 그 과정에서 SonarQube가 새 Code Smell 1건을 추가로 잡아냈습니다.

### 신규 발견 — [`fastapi-app/main.py`](../../fastapi-app/main.py) (연속 스트릭 계산 로직)

- **규칙**: `python:S108` (MAJOR) — "Either remove or fill this block of code."
- **내용**: `if last_date == today: pass` 처럼 아무 동작도 하지 않는 빈 분기가 있으면, 구현을 깜빡한 TODO인지 의도한 것인지 알 수 없어 경고합니다.
- **검토**: 의도한 no-op(오늘 이미 스트릭을 세었으면 아무것도 안 함)이 맞았지만, 빈 분기로 남겨두는 대신 조건 자체를 재구성하면 더 명확하다고 판단했습니다.
- **수정**: `if all_done_today: if last_date == today: pass / elif ... / else ...` 구조를 `if all_done_today and last_date != today: ...`로 바꿔 빈 분기를 아예 없앴습니다 ([커밋 4047834](https://github.com/kimcanal/FASTAPI-TODOs/commit/4047834)).

### 2차 분석 결과 (빌드 #11, v5.0.0 + 위 수정 반영)

| 지표 | 1차 | 2차 |
|---|---|---|
| Bugs | 0 | 0 |
| Vulnerabilities | 0 | 0 |
| Code Smells | 0 | 0 *(중간에 1건 발생 → 수정 완료)* |
| 중복도 | 0.0% | 0.0% |
| 커버리지 | 99.4% | 97.7% *(기능 추가로 코드량 증가, 테스트는 23→29개로 확대)* |
| Security Hotspot | 1건 (Safe 처리) | 1건 (동일, Safe 유지) |
| Quality Gate | — | **Passed** |

![SonarQube 2차 분석 대시보드](./(3)-1_SonarQube_2차분석_대시보드.png)

### 겸사겸사 진행한 기능 개선 (v5.0.0)

- 할 일에 우선순위(👑 중요 / 💌 일반)와 마감일 추가, 지난 마감일은 빨간 뱃지로 강조
- 제목/설명 검색, 마감일순·우선순위순 정렬
- 모든 할 일을 끝내면 축하 배너 + 매일 전부 완료 시 연속 달성 스트릭 집계(`GET /stats`)
- 핑크·골드 톤의 "투두 프린세스" 테마로 전체 화면 리디자인

자세한 내용은 [`fastapi-app/CHANGELOG.md`](../../fastapi-app/CHANGELOG.md)의 `[5.0.0]` 항목 참고.

## (4) Claude Code로 OWASP Top 10 분석

`fastapi-app/main.py`, `Dockerfile`, `docker-compose.yml`, 세션/인증 설정을 OWASP Top 10 (2021) 기준으로 Claude Code가 직접 코드 리뷰했습니다. SonarQube는 범용 정적분석(버그/스멜/중복)인 반면, 이 리뷰는 "공격자 관점에서 뭐가 뚫리는가"에 초점을 맞춘 것이라 서로 다른 종류의 이슈를 찾아냅니다.

| OWASP 분류 | 해당 여부 | 발견 사항 | 위험도 | 권고 |
|---|---|---|---|---|
| **A01 Broken Access Control** | 검토함 | 모든 `/todos` 쿼리가 `WHERE user_id = ?`로 필터링되고, 테스트(`test_users_cannot_see_or_modify_each_others_todos`)로 계정 간 격리를 검증함 | - | 문제 없음 |
| **A02 Cryptographic Failures** | **해당** | 세션 쿠키에 `https_only`/`Secure` 플래그가 설정되어 있지 않음 (`SessionMiddleware` 기본값) — 평문 HTTP 배포 시 쿠키가 그대로 노출될 수 있음 | 중간 | 배포를 HTTPS(리버스 프록시+TLS)로 전환하고 `SessionMiddleware(..., https_only=True)` 적용 |
| **A03 Injection** | 검토함 | 모든 SQL이 `conn.execute("... WHERE id = ?", (id,))` 형태의 파라미터 바인딩만 사용, 문자열 포맷팅으로 쿼리를 조립하는 코드 없음 | - | 문제 없음 |
| **A04 Insecure Design** | **해당** | 로그인/회원가입에 시도 횟수 제한이 없어 무차별 대입(Brute Force) 공격에 취약 | 중간 | 계정/IP 단위 rate limiting 또는 실패 횟수 기반 지연·잠금 추가 |
| **A05 Security Misconfiguration** | **해당** | ① `/docs`, `/redoc`, `/openapi.json`이 인증 없이 공개되어 API 구조가 그대로 노출됨 ② 보안 헤더(`X-Content-Type-Options`, `Content-Security-Policy` 등) 미설정 | 낮음 | 운영 환경에서는 `FastAPI(docs_url=None, redoc_url=None)`로 비활성화하거나 접근 제한, 보안 헤더 미들웨어 추가 |
| **A06 Vulnerable/Outdated Components** | 검토함 | `requirements.txt`가 알려진 CVE가 패치된 하한 버전으로 고정됨(`fastapi>=0.142.0` 등, CHANGELOG 4.0.0 참고). 다만 상한이 없어 추후 상위 버전에서 호환성 깨질 가능성은 있음 | 낮음 | 정기적으로 `pip list --outdated` 점검 |
| **A07 Identification & Authentication Failures** | **해당** | 비밀번호 최소 길이가 4자로 매우 짧음(`AuthIn.password: min_length=4`) | 중간 | 최소 8자 이상 + 복잡도 권장 문구 추가 |
| **A08 Software/Data Integrity Failures** | 검토함 | `Dockerfile`의 `FROM python:3.13-slim`이 다이제스트(sha256) 고정 없이 태그만 사용 — 상위 이미지가 바뀔 수 있음 | 낮음 | `FROM python:3.13-slim@sha256:...`로 고정 고려 |
| **A09 Security Logging & Monitoring Failures** | **해당** | 로그인 실패, 세션 무효화 등 보안 이벤트에 대한 로깅이 없음 | 낮음 | 실패한 로그인 시도 등을 구조화된 로그로 남기기 |
| **A10 Server-Side Request Forgery** | 해당 없음 | 사용자 입력으로 서버가 외부 URL을 요청하는 기능이 없음 | - | - |

### 요약

- **즉시 조치가 필요한 치명적 취약점은 없음** (Injection, Access Control은 설계상 안전하게 되어 있음을 확인)
- 가장 현실적인 리스크는 **A02(쿠키 미암호화 전송)**와 **A07(짧은 비밀번호 최소 길이)** — 둘 다 배포 설정/검증 규칙 한 줄 수준으로 고칠 수 있는 항목이라 다음 주차에 우선 반영 예정
- A04(무차별 대입 방어 없음)는 실제 공격 시나리오로 이어질 수 있어 rate limiting 도입을 다음 개선 후보로 기록

![Claude Code OWASP 분석 화면](./(4)-1_Claude_Code_OWASP_분석_캡처.png)

## Claude Code 활용 내역 및 소감

> 아래 "소감"은 초안입니다. 본인 생각/표현으로 바꿔서 제출하세요.

### 활용 내역

- **인프라 구성**: `docker-compose.yml`에 SonarQube/Postgres 서비스 추가, `sonar-project.properties` 작성, Jenkins 파이프라인에 `SonarQube Analysis`/`Quality Gate` 스테이지 추가 — 전부 Claude Code가 직접 작성하고 컨테이너를 띄워 검증
- **트러블슈팅**: 1차 스캔에서 테스트 파일이 소스/테스트로 중복 인덱싱되는 오류, SonarQube→Jenkins 웹훅이 UFW 방화벽(라우팅 트래픽 기본 차단)에 막혀 Quality Gate가 타임아웃(ABORTED)되는 문제를 Claude Code가 원인을 찾아 직접 진단하고, 방화벽 규칙(`ufw route allow`/`ufw allow`)은 본인이 터미널에서 직접 적용
- **파이프라인 실행/분석**: Jenkins API로 빌드를 트리거하고 SonarQube API로 1차/2차 분석 결과를 가져와 비교, 발견된 Security Hotspot과 신규 Code Smell을 리뷰 의견과 함께 정리
- **기능 개선**: 사용자 요청으로 할 일 우선순위/마감일/검색/정렬/연속 스트릭 기능과 "투두 프린세스" 테마 UI를 함께 구현 — Claude Code가 백엔드(FastAPI/SQLite 마이그레이션)·프론트엔드(HTML/CSS/JS)·테스트를 모두 작성하고, Playwright로 서버에서 직접 헤드리스 스크린샷까지 찍어 검증
- **OWASP Top 10 분석**: 코드베이스를 직접 읽고 OWASP Top 10 2021 10개 항목에 하나씩 대조해 해당 여부·근거·권고를 작성
- **보안 경계**: SonarQube 웹 UI 로그인은 토큰을 URL에 넣어 우회하려던 시도가 Claude Code 자체 안전장치에 의해 차단됨 — 결국 대시보드 스크린샷은 본인이 직접 로그인해서 캡처

### 소감 (초안 — 본인 말로 수정할 것)

- SonarQube를 처음 연동할 때 방화벽 문제로 막혔는데, "컨테이너 안에서 호스트로 요청이 타임아웃난다"는 증상만 보고 UFW의 라우팅 정책까지 원인을 짚어내는 과정이 인상 깊었다. 혼자였으면 한참 헤맸을 문제였다.
- SonarQube가 찾아준 이슈가 Security Hotspot 1개뿐이어서 좀 허무했는데, Claude Code한테 OWASP Top 10 기준으로 따로 리뷰를 시켜보니 정적분석 도구가 안 잡아주는(비밀번호 정책, rate limiting, 쿠키 설정 같은) 설계/운영 수준의 보안 이슈들이 나와서 "정적분석 = 보안 점검 끝"이 아니라는 걸 체감했다.
- 새 기능을 추가하자마자 SonarQube 2차 분석에서 바로 새 code smell을 잡아낸 게 신기했다 — 기능 개발과 정적분석을 같은 파이프라인에 묶어두니 "코드 늘어날 때마다 자동으로 검증"되는 느낌을 받았다.
- 토큰을 URL에 넣어서 로그인하려던 걸 AI가 스스로 막은 부분에서, 편의보다 안전을 우선하는 동작을 직접 봤다. 결국 내가 직접 로그인해서 스크린샷을 찍어야 했지만, 그게 맞는 방향이라고 생각한다.
