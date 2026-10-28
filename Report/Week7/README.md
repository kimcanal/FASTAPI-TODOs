# 오픈소스를 이용한 SW 개발 실습 — 9주차 과제 (Week 7)

학과 : [본인 학과 입력]
학번 : [본인 학번 입력]
이름 : [본인 이름 입력]

| 항목 | 내용 |
|---|---|
| 대상 | http://163.239.77.80:5001 (본인 서버, `docker compose` 배포본, v6.0.0) |
| Prometheus | http://163.239.77.80:7070 (서버 자신에게만 공개) |
| Grafana | http://163.239.77.80:3000 |
| Jenkins Job | Jenkins Deploy Docker legacy (`jenkins/deploy-compose.groovy`) |

## 1. 시스템 모니터링 + 애플리케이션 모니터링 쿼리 추가

`docker-compose.yml`에 Prometheus/Grafana/Node Exporter/cAdvisor 모니터링 스택을 추가하고, FastAPI 앱에 `prometheus-fastapi-instrumentator`로 `/metrics` 엔드포인트를 붙였습니다. Grafana에서 Prometheus 데이터소스(`http://prometheus:9090`)를 연결한 뒤, 시스템 지표 5개(CPU·메모리·디스크 사용률, 네트워크 수신/전송 속도)와 애플리케이션 지표 6개(요청 비율, 전체 요청률, 요청 증가량, 2xx/4xx 비율, 95th percentile 응답 시간)를 한 대시보드에 패널로 추가했습니다.

![App & System 모니터링 대시보드](<(1)-1_App_System_모니터링_대시보드.png>)

## 2. 1번 사진에 관한 설명과 수치에 대한 분석

- **CPU/메모리 사용률**: CPU는 5~15% 구간에서 들쭉날쭉하게 움직이고, 메모리는 54%에서 58%까지 완만히 상승합니다. 두 지표 모두 node-exporter가 호스트 전체를 측정한 값이라, FastAPI·SonarQube·Grafana·Prometheus·cAdvisor가 동시에 떠 있는 상태의 전체 부하를 보여줍니다.
- **디스크/네트워크 그래프의 "시작 지점"**: 모든 그래프가 15:51~15:52 부근부터 데이터가 시작되는데, 이는 디스크 사용량이 그 시점에 갑자기 늘었다는 뜻이 아니라 **node-exporter/cadvisor 컨테이너를 그때 막 띄워서 그 이전 구간은 수집된 데이터 자체가 없기 때문**입니다. 데이터가 있는 구간만 보면 디스크 사용률은 45.6% 부근에서 거의 변화가 없습니다.
- **HTTP 요청 비율(최근 1분)**: 같은 시점부터 요청이 0 req/s에서 0.8 req/s까지 올라간 뒤 일정하게 유지됩니다. 이 구간은 `/health`, `/api/version`, `/login`, 존재하지 않는 경로를 2초 간격으로 반복 호출하는 트래픽 생성 스크립트를 실행해 확인했습니다 — To-do 사이트에 실제로 요청을 보내면 Prometheus/Grafana에 거의 실시간(스크레이프 주기 15초)으로 반영되는 것을 확인할 수 있었습니다.
- **2xx/4xx 응답 비율**: 2xx는 초당 약 1.5~2.5건, 4xx는 약 0.5~0.8건으로 나타나는데, 이는 트래픽 생성 스크립트가 호출한 4개 경로 중 3개(`/health`, `/api/version`, `/login`)는 정상 응답(2xx), 1개(존재하지 않는 경로)는 404(4xx)를 반환하도록 설계했기 때문입니다 — 쿼리가 상태 코드별로 정확히 구분해서 집계하고 있음을 확인했습니다.
- **95th Percentile 응답 시간**: 약 100ms 부근에서 평평하게 유지됩니다. 트래픽 양이 많지 않은 상태라 지연 시간 변동이 거의 없는 것으로 보입니다.

## 3. Node Exporter 사용해보기

Grafana 공식 커뮤니티 대시보드 **Node Exporter Full**(ID 1860, grafana.com)을 Import해서 사용했습니다. CPU Busy 6.5%, RAM Used 56.8%, 서버 가동 시간(Uptime) 6주 등 호스트 시스템 전반의 상태를 게이지와 시계열 그래프로 한눈에 볼 수 있었습니다.

![Node Exporter Full 대시보드](<(3)-1_Node_Exporter_대시보드.png>)

## 4. cAdvisor Exporter 사용해보기

`docker-compose.yml`에 cAdvisor(`ghcr.io/google/cadvisor:v0.60.6`)를 외부 포트 없이 내부 네트워크로만 추가하고, Prometheus가 `cadvisor:8080`에서 컨테이너별 메트릭을 수집하도록 구성했습니다. 직접 작성한 PromQL로 컨테이너별 CPU 사용률·메모리 사용량·네트워크 수신/전송 속도를 `name` 라벨 기준으로 분리해서 대시보드를 만들었습니다. cAdvisor 자신이 모든 컨테이너의 cgroup을 지속적으로 읽어야 해서 CPU 사용률이 다른 컨테이너보다 눈에 띄게 높게(8~9%) 나오는 점이 흥미로웠습니다.

![cAdvisor 컨테이너별 메트릭 대시보드](<(4)-1_cAdvisor_대시보드.png>)

## 5. Claude Code를 어떻게 활용했는지와 소감 작성하기

> 아래 "소감"은 초안입니다. 본인 생각/표현으로 바꿔서 제출하세요.

### 활용 내역

- **인프라 구성**: `prometheus/prometheus.yml` 작성, `docker-compose.yml`에 prometheus/grafana/node-exporter/cadvisor 4개 서비스와 볼륨 2개 추가, `main.py`에 `Instrumentator` 계측 코드 삽입, `requirements.txt`에 관련 의존성 추가까지 전부 Claude Code가 직접 작성
- **검증**: 변경 전/후로 pytest 29개 테스트와 `docker compose config` 문법 검사를 돌려 기존 기능에 영향이 없는지 확인한 뒤 배포
- **배포 및 자동화**: 현재 작업 환경이 실제 배포 서버(163.239.77.80) 자체였기 때문에, Claude Code가 `docker compose up -d --build`로 직접 스택을 띄우고 Prometheus Targets API로 3개 타깃(fastapi/node/cadvisor)이 모두 `up` 상태인지 확인
- **Grafana 설정 자동화**: 헤드리스 브라우저(Playwright)로 Grafana 초기 로그인(admin/admin) 후 비밀번호 정책을 만족하는 새 비밀번호로 교체, Prometheus 데이터소스 연결까지 자동화
- **대시보드 생성**: Grafana HTTP API로 애플리케이션+시스템 모니터링 대시보드(패널 11개)를 직접 만들고, grafana.com에서 Node Exporter Full(ID 1860) 커뮤니티 대시보드를 내려받아 Import, cAdvisor용 커스텀 대시보드(패널 4개)도 추가로 구성
- **트래픽 생성 및 스크린샷**: 그래프에 실제 데이터가 보이도록 백그라운드에서 테스트 트래픽을 생성한 뒤, 헤드리스 브라우저로 3개 대시보드를 스크린샷으로 캡처해 보고서에 바로 쓸 수 있는 형태로 저장
- **보안 경계**: `git push`·`git tag` 원격 반영은 Claude Code의 자동 모드 정책상 외부 시스템에 쓰기 작업으로 분류되어 자동 실행이 차단되었고, 본인이 직접 승인한 뒤에야 진행됨 — 로컬 커밋/배포까지는 자동으로 처리하되, 공유 저장소에 반영되는 작업은 항상 확인을 거치는 구조를 직접 경험

### 소감 (초안 — 본인 말로 수정할 것)

- 이번 주는 유독 "눈에 보이는 결과물"이 많아서 좋았다. 코드 몇 줄 추가했을 뿐인데 Grafana 대시보드에 실시간으로 그래프가 그려지는 걸 보니 모니터링이 왜 필요한지 체감이 됐다.
- Grafana 로그인부터 데이터소스 연결, 대시보드 생성, 스크린샷 캡처까지 브라우저 조작이 필요한 작업을 Claude Code가 헤드리스 브라우저로 전부 자동화해준 게 인상 깊었다 — 평소였으면 직접 클릭하면서 캡처했을 작업인데, 반복 가능한 스크립트로 처리되니 다음에 대시보드를 다시 만들어야 할 때도 훨씬 수월할 것 같다.
- 그래프 초반 구간이 비어 있는 걸 보고 "디스크 사용량이 갑자기 늘었나?" 싶었는데, 알고 보니 그냥 컨테이너를 그 시점에 막 띄워서 그 전 데이터가 없는 것뿐이었다. 모니터링 그래프를 읽을 때 "데이터가 없는 구간"과 "값이 0인 구간"을 구분해야 한다는 걸 배웠다.
- `git push`가 자동 모드 정책으로 막혔을 때, AI가 알아서 우회하지 않고 "여기까지는 했고, 이 부분은 승인이 필요하다"고 멈춰 선 게 인상적이었다. 로컬 작업과 공유 저장소에 영향을 주는 작업을 구분해서 다루는 게 맞는 방향이라고 생각한다.
