# Changelog

이 프로젝트의 주요 변경 사항을 기록합니다.
형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따릅니다.

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
