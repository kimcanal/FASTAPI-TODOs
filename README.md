# To-Do List (FastAPI)

계정별로 할 일을 관리하는 간단한 To-Do List 웹앱입니다. FastAPI + SQLite로 만들었고, Jenkins로 배포합니다.

| 로그인 | 할 일 목록 | 릴리스 노트 |
| --- | --- | --- |
| ![로그인 화면](docs/screenshots/login.png) | ![할 일 목록 화면](docs/screenshots/todos.png) | ![릴리스 노트 화면](docs/screenshots/release-notes.png) |

## 주요 기능

- 회원가입 / 로그인 / 로그아웃 — 세션 쿠키 기반, 계정별로 할 일이 완전히 분리됩니다
- 할 일 추가 / 목록 조회(전체·진행중·완료 필터) / 인라인 수정 / 삭제
- 모바일 화면 대응 (iOS 자동 확대 방지, 좁은 화면 레이아웃)
- 현재 버전 및 릴리스 노트 확인 (`GET /api/version`, `GET /release-notes`)
- 배포/모니터링용 헬스체크 (`GET /health`)

## 기술 스택

- **FastAPI** + **Uvicorn**
- **SQLite** — 계정(`users`)과 할 일(`todos`) 저장, WAL 모드로 다중 프로세스 동시 접근 처리
- **세션 인증** — `itsdangerous` 서명 쿠키, 비밀번호는 PBKDF2(+salt)로 해시 저장
- **pytest** — 인증 플로우, 계정 간 데이터 격리 포함 테스트
- **Jenkins** — CI/CD 파이프라인

## 프로젝트 구조

```
fastapi-app/
├── main.py                  # FastAPI 앱 — 인증 API, 할 일 API
├── requirements.txt         # 운영 의존성
├── requirements-dev.txt     # 테스트 의존성 (pytest)
├── VERSION                  # 현재 버전
├── CHANGELOG.md             # 버전별 변경 이력 (Keep a Changelog 형식)
├── conftest.py
├── templates/
│   ├── index.html           # 할 일 목록 화면
│   ├── login.html           # 로그인 / 회원가입 화면
│   └── release_notes.html   # 릴리스 노트 화면
└── tests/
    └── test_main.py
Jenkinsfile                  # CI 파이프라인 (Install → Test → Deploy)
```

## 로컬에서 실행하기

```bash
cd fastapi-app
python3 -m venv myenv
source myenv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn main:app --reload
```

`http://localhost:8000` 접속 → 로그인 화면으로 이동합니다. 회원가입 후 바로 이용할 수 있습니다.

## 테스트

```bash
cd fastapi-app
pytest -v
```

## 버전 관리 & 릴리스

- 현재 버전은 `fastapi-app/VERSION`, 변경 이력은 `fastapi-app/CHANGELOG.md`에서 관리합니다.
- 배포마다 `vX.Y.Z` 형태의 git tag를 남기고, 제출/배포 버전은 GitHub Release로 등록합니다.
- 앱이 떠 있는 동안에는 `/api/version`(현재 버전·커밋·빌드 번호)과 `/release-notes`(변경 이력)에서 바로 확인할 수 있습니다.

## 배포 (Jenkins)

저장소 루트의 `Jenkinsfile`이 Install(의존성 설치) → Test(pytest) → Deploy(uvicorn 재기동) 파이프라인을 정의합니다. Jenkins Pipeline job에서 "Pipeline script from SCM"으로 이 저장소를 연결해서 사용합니다.
