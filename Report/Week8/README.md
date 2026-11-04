# 오픈소스를 이용한 SW 개발 실습 — 10주차 과제 (Week 8)

학과 : [본인 학과 입력]
학번 : [본인 학번 입력]
이름 : [본인 이름 입력]

| 항목 | 내용 |
|---|---|
| 팀 서버 배포 대상 | http://163.239.77.76:8022 (`FastApi-app-yunha`, v7.0.0) |
| 본인 서버 | http://163.239.77.80:5001 |
| InfluxDB | 내부 네트워크 전용 (JMeter → InfluxDB → Grafana) |
| Jenkins Job | Jenkins Deploy Docker legacy team (`jenkins/deploy-compose-team.groovy`) |

## 1. 성능 및 부하 테스트하는 스크립트 사용하여 팀서버에 배포

`docker-compose.yml`에 JMeter 서비스를 추가하고, 회원가입(`POST /auth/register`)으로 세션 쿠키를 만든 뒤 `GET /health`, `GET /todos`, `POST /todos`를 호출하는 테스트 플랜(`jmeter/fastapi_test_plan.jmx`)을 작성했습니다. 사용자 10명, 10초 램프업으로 구성했고, Jenkins 파이프라인(`Jenkins Deploy Docker legacy team`)이 팀 서버(163.239.77.76)에 배포한 직후 자동으로 부하 테스트를 실행하고 결과를 HTML 리포트로 게시하도록 구성했습니다.

**브라우저로 팀 서버 접속 확인**

![팀 서버 브라우저 접속](<(1)-1_팀서버_브라우저_접속.png>)

**Jenkins 빌드 내역**

![Jenkins 팀서버 빌드 내역](<(1)-2_Jenkins_팀서버_빌드내역.png>)

**JMeter HTML 리포트**

![JMeter HTML 리포트](<(1)-3_JMeter_HTML_리포트.png>)

전체 50건 요청(사용자 10명 × 5개 요청)에 실패 0건(Error 0.00%), APDEX 1.000(만족)으로 전부 집계됐습니다. 평균 응답 시간은 31.74ms였는데, `POST /auth/register`만 평균 136ms로 눈에 띄게 느렸습니다 — 이는 PBKDF2 20만 회 해시 반복으로 비밀번호를 암호화하기 때문으로, 보안을 위한 의도된 지연입니다. 반면 `GET /todos`류 조회 요청은 3~5ms 수준으로 빨랐습니다.

## 2. InfluxDB 사용해보기

JMeter 내장 백엔드 리스너(`InfluxdbBackendListenerClient`)가 테스트 중 실시간으로 메트릭을 InfluxDB(1.8)에 적재하도록 구성하고, Grafana에 InfluxDB 데이터소스를 연결한 뒤 grafana.com의 JMeter 전용 커뮤니티 대시보드(ID 5496, "Apache JMeter Dashboard using Core InfluxdbBackendListenerClient")를 Import했습니다.

![InfluxDB + Grafana JMeter 대시보드](<(2)-1_InfluxDB_Grafana_대시보드.png>)

Total Requests 50 / Failed Requests 0 / Error Rate 0.00%로 1번 항목의 JMeter HTML 리포트와 정확히 일치하는 수치를 확인했고, 트랜잭션별 응답 시간에서도 `POST /auth/register`가 143ms로 가장 느리고 나머지는 10ms 미만인 동일한 패턴이 나타났습니다 — JMeter의 정적 HTML 리포트와 InfluxDB/Grafana의 실시간 대시보드가 같은 테스트 결과를 서로 다른 방식(사후 집계 vs 시계열)으로 보여준다는 걸 비교해서 확인할 수 있었습니다.

### 겸사겸사 진행한 기능 개선 (v7.0.0)

- 할 일 **CSV 내보내기/가져오기** 추가 — `GET /todos/export`로 본인 할 일(휴지통 제외)을 CSV로 내려받고, `POST /todos/import`로 CSV 파일을 업로드해 일괄 추가
- 가져오기는 기존 항목을 건드리지 않고 유효한 행만 새로 추가하며, 제목이 빈 행 등 유효하지 않은 행은 건너뛰고 "N개 추가, M개 건너뜀"으로 결과를 안내
- 테스트 3개 추가(내보내기 범위 확인, 정상/일부실패 가져오기, 기존 데이터 보존)로 36개 → 39개

자세한 내용은 [`fastapi-app/CHANGELOG.md`](../../fastapi-app/CHANGELOG.md)의 `[7.0.0]` 항목 참고.

## 3. Claude Code를 어떻게 활용했는지와 소감 작성하기

> 아래 "소감"은 초안입니다. 본인 생각/표현으로 바꿔서 제출하세요.

### 활용 내역

- **인프라 구성**: `jmeter/Dockerfile`, `jmeter/fastapi_test_plan.jmx`, `docker-compose.yml`의 jmeter/influxdb 서비스, `.env`/`.env.example`, Jenkins 파이프라인 수정까지 전부 Claude Code가 작성
- **과제 자료의 오류를 직접 발견하고 수정**: 제공된 JMeter 테스트 플랜 예시가 존재하지 않는 `/users` 엔드포인트를 호출하고 있었고, InfluxDB 백엔드 리스너 설정도 과제 문서 자체에 없었음 — 실제 앱 엔드포인트(`/health`, `/auth/register`, `/todos`)로 교체하고 InfluxDB 연동을 추가로 설계·구현
- **실제 배포 트러블슈팅 (3건)**:
  1. **JMeter 유니크 사용자명 생성 버그**: 스레드마다 다른 계정을 만들려고 "User Defined Variables" 설정 요소를 썼는데, 이 방식이 스레드 시작 전에 딱 한 번만 평가되는 바람에 10개 스레드가 전부 같은 아이디로 가입을 시도해 9개가 409(중복)로 실패. 샘플러 안에 `${__threadNum}_${__time(,)}`를 직접 집어넣는 방식으로 바꿔서 해결
  2. **팀 서버의 느린/막힌 외부 네트워크**: JMeter 이미지를 `Dockerfile`로 직접 빌드하면 `archive.apache.org`에서 설치 파일을 받는데, 팀 서버에서 이 다운로드가 6분 넘게 멈춰 있었음. 반면 Docker Hub pull은 이미 잘 되고 있었기 때문에(기존 dockerhub 배포 파이프라인), 네트워크가 되는 본인 서버에서 미리 이미지를 빌드해 Docker Hub에 올려두고 모든 서버는 pull만 하도록 구조를 바꿈
  3. **SonarQube LTS 건너뛰기 업그레이드 실패**: 과제 문서의 권장대로 SonarQube를 최신 버전(26.10)으로 고정했더니 "너무 오래된 버전이라 바로 업그레이드할 수 없다"는 에러로 아예 기동이 안 됨. DB를 직접 조회해서 실제 설치된 버전이 9.9.8이라는 걸 확인하고, 여러 LTS를 한 번에 건너뛸 수 없다는 SonarQube 정책 때문임을 파악 — 지금 당장 단계별로 다 올리는 대신 기존에 멀쩡히 동작하던 버전으로 되돌려 배포가 막히지 않게 하고, 다음 과제로 남김
- **Jenkins HTML 리포트가 빈 화면으로 뜨는 문제 해결**: Jenkins가 발행한 JMeter HTML 리포트를 열면 그래프/통계 영역이 전부 비어 있었음 — 과제 문서가 경고한 바로 그 CSP(Content-Security-Policy) 문제였고, 문서가 제시한 해결책만으로는 부족해서(스크립트 실행은 허용되지만 데이터 요청이 origin 문제로 또 막힘) `allow-same-origin`과 `connect-src 'self'`를 추가로 조합해서 완전히 해결
- **배포 자동화**: Jenkins REST API로 빌드를 트리거하고 완료까지 폴링, 실패 시 콘솔 로그를 직접 읽어 원인을 진단 → 수정 → 재배포를 여러 차례 반복
- **보안 경계**: `git push`(일반)는 승인 후 바로 처리됐지만, 기존에 올라간 태그를 옮기는 `git push --force`는 Claude Code 자동 모드 정책상 항상 차단되어 사용자가 직접 실행해야 했음 — 일반 푸시와 히스토리를 덮어쓰는 force 푸시를 다르게 취급하는 걸 확인

### 소감 (초안 — 본인 말로 수정할 것)

- 과제 문서에 적힌 예제 코드를 그대로 베껴 쓰는 게 아니라, "이 코드가 실제로 우리 앱에 맞는가"를 Claude Code가 먼저 검증하고 틀린 부분(존재하지 않는 엔드포인트 등)을 스스로 고쳐서 진행하는 걸 보고, 과제 자료도 100% 신뢰하면 안 되는구나 싶었다.
- 이번 주는 유독 "진짜 장애"를 많이 만났다 — JMeter 변수 평가 시점 버그, 팀 서버 네트워크 제약, SonarQube 버전 호환성, Jenkins CSP까지. 그런데 매번 에러 메시지를 그냥 재시도하는 게 아니라 로그를 읽고, 필요하면 DB까지 직접 조회해서 근본 원인을 찾아내는 과정이 인상 깊었다. 특히 SonarQube 문제는 "버전을 최신으로 고정하라"는 보안 모범사례를 그대로 따랐다가 오히려 배포를 깨뜨린 경우라, 모범사례도 현재 상태를 먼저 확인하고 적용해야 한다는 걸 배웠다.
- 팀 서버는 나 혼자 쓰는 게 아니라서, 기존에 다른 주차에 이미 떠 있던 SonarQube/Grafana 컨테이너랑 이름이 겹치지 않게 새로 추가한 InfluxDB/JMeter 컨테이너 이름도 전부 구분해야 한다고 짚어준 부분이 좋았다 — 내가 먼저 생각 못 했던 부분이었다.
- 문제가 생길 때마다 "일단 되게만 만들자"가 아니라 왜 안 되는지 설명하고, 고치는 과정과 이유를 전부 커밋 메시지/CHANGELOG에 남겨서 나중에 다시 봐도 이해할 수 있게 해준 점이 좋았다.
