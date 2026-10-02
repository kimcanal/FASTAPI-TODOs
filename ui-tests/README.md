# UI Tests (Playwright)

배포된 To-Do List 앱을 실제 브라우저로 조작하며 검증하는 UI 테스트입니다. Claude Code가 Playwright Test 러너를 연동해 작성/실행했습니다.

## 실행

```bash
cd ui-tests
npm install
npx playwright install chromium   # 최초 1회
BASE_URL=http://163.239.77.80:5001 npx playwright test
```

`BASE_URL`을 생략하면 기본값(`http://163.239.77.80:5001`, 본인 서버 compose 배포)을 테스트합니다.

## 테스트 범위 (`tests/todo-app.spec.js`)

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

## 리포트

`npx playwright test` 실행 후 `playwright-report/index.html`에 결과 리포트가 생성됩니다:

```bash
npx playwright show-report
```
