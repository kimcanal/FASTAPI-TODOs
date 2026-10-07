# OWASP Top 10 (2021) 보안 분석 보고서

**대상**: FastApi Todos (`fastapi-app/main.py`, `Dockerfile`, `docker-compose.yml`, 세션/인증 설정)
**분석 도구**: Claude Code (코드 직접 리뷰)
**분석일**: 2026-10-08
**버전**: v5.0.0

## 1. 목적 및 방법

SonarQube는 버그·코드 스멜·중복 등 범용 정적분석에 강하지만, "공격자 관점에서 이 코드가 어떻게 뚫릴 수 있는가"는 별도의 보안 리뷰가 필요합니다. 이 보고서는 OWASP Top 10 (2021) 10개 분류를 기준으로 `fastapi-app` 코드베이스 전체(인증, 세션, SQL 접근, 의존성, 컨테이너 설정)를 Claude Code가 직접 읽고 대조한 결과입니다.

## 2. 분류별 분석 결과

| OWASP 분류 | 해당 여부 | 발견 사항 | 위험도 | 권고 |
|---|---|---|---|---|
| A01 Broken Access Control | 검토함 | 모든 `/todos` 쿼리가 `WHERE user_id = ?`로 필터링되고, 테스트(`test_users_cannot_see_or_modify_each_others_todos`)로 계정 간 격리를 검증함 | - | 문제 없음 |
| **A02 Cryptographic Failures** | **해당** | 세션 쿠키에 `https_only`/`Secure` 플래그가 설정되어 있지 않음 (`SessionMiddleware` 기본값) — 평문 HTTP 배포 시 쿠키가 그대로 노출될 수 있음 | 중간 | 배포를 HTTPS(리버스 프록시+TLS)로 전환하고 `SessionMiddleware(..., https_only=True)` 적용 |
| A03 Injection | 검토함 | 모든 SQL이 `conn.execute("... WHERE id = ?", (id,))` 형태의 파라미터 바인딩만 사용, 문자열 포맷팅으로 쿼리를 조립하는 코드 없음 | - | 문제 없음 |
| **A04 Insecure Design** | **해당** | 로그인/회원가입에 시도 횟수 제한이 없어 무차별 대입(Brute Force) 공격에 취약 | 중간 | 계정/IP 단위 rate limiting 또는 실패 횟수 기반 지연·잠금 추가 |
| **A05 Security Misconfiguration** | **해당** | ① `/docs`, `/redoc`, `/openapi.json`이 인증 없이 공개되어 API 구조가 그대로 노출됨 ② 보안 헤더(`X-Content-Type-Options`, `Content-Security-Policy` 등) 미설정 | 낮음 | 운영 환경에서는 `FastAPI(docs_url=None, redoc_url=None)`로 비활성화하거나 접근 제한, 보안 헤더 미들웨어 추가 |
| A06 Vulnerable/Outdated Components | 검토함 | `requirements.txt`가 알려진 CVE가 패치된 하한 버전으로 고정됨(`fastapi>=0.142.0` 등). 다만 상한이 없어 추후 상위 버전에서 호환성이 깨질 가능성은 있음 | 낮음 | 정기적으로 `pip list --outdated` 점검 |
| **A07 Identification & Authentication Failures** | **해당** | 비밀번호 최소 길이가 4자로 매우 짧음(`AuthIn.password: min_length=4`) | 중간 | 최소 8자 이상 + 복잡도 권장 문구 추가 |
| A08 Software/Data Integrity Failures | 검토함 | `Dockerfile`의 `FROM python:3.13-slim`이 다이제스트(sha256) 고정 없이 태그만 사용 — 상위 이미지가 바뀔 수 있음 | 낮음 | `FROM python:3.13-slim@sha256:...`로 고정 고려 |
| **A09 Security Logging & Monitoring Failures** | **해당** | 로그인 실패, 세션 무효화 등 보안 이벤트에 대한 로깅이 없음 | 낮음 | 실패한 로그인 시도 등을 구조화된 로그로 남기기 |
| A10 Server-Side Request Forgery | 해당 없음 | 사용자 입력으로 서버가 외부 URL을 요청하는 기능이 없음 | - | - |

## 3. 코드 근거

```python
# A03 — 전부 파라미터 바인딩 (main.py:170 등)
conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,))

# A07 — 비밀번호 최소 길이 4자 (main.py:162)
password: str = Field(min_length=4, max_length=100)

# A02 — https_only 미설정 (main.py:136)
app.add_middleware(SessionMiddleware, secret_key=..., max_age=14 * 24 * 3600)

# A05 — docs_url 미설정, /docs가 기본 공개 (main.py:135)
app = FastAPI(title="To-Do List API")
```

## 4. 종합 평가

- **치명적(Critical) 취약점 없음** — Injection, Access Control처럼 가장 흔한 고위험 항목은 설계 단계에서부터 안전하게 처리되어 있었습니다 (파라미터 바인딩, `user_id` 필터링 + 전용 테스트).
- **현실적인 우선순위**:
  1. **A02 / A07** — 둘 다 설정값 한 줄 수준으로 고칠 수 있는 항목이라 가장 먼저 반영할 가치가 있습니다.
  2. **A04** — rate limiting 부재는 실제 공격 시나리오(크리덴셜 스터핑)로 이어질 수 있어 다음으로 우선순위가 높습니다.
  3. A05/A06/A08/A09는 낮은 위험도지만, 운영 전환 전 체크리스트로 남겨둘 가치가 있습니다.
- SonarQube(범용 정적분석)가 잡아낸 이슈는 Security Hotspot 1건(Dockerfile)뿐이었던 반면, 이 OWASP 기반 리뷰는 설정·운영 수준의 보안 이슈 5건을 추가로 발견했습니다. **정적분석 도구 통과 ≠ 보안 점검 완료**라는 것을 보여주는 사례입니다.
