# Week 4 — Docker + Jenkins 배포

| 항목 | 방식 | 주소 | Jenkins Job |
|---|---|---|---|
| (1) 본인 서버 배포 | GitHub clone + `docker compose` | http://163.239.77.80:5001 | Jenkins Deploy Docker legacy |
| (2) 팀 서버 배포 (깃허브) | GitHub clone + `docker compose` | http://163.239.77.76:8022 | Jenkins Deploy Docker legacy team |
| (3) 팀 서버 배포 (바로 pull) | DockerHub push → `docker pull` / `docker run` | http://163.239.77.76:8023 | Jenkins Deploy Docker direct team |

## (1) 본인 서버 배포
![](./(1)-1_본인서버_웹사이트_163.239.77.80-5001.png)
![](./(1)-2_본인서버_젠킨스빌드.png)

## (2) 팀 서버 배포 — 깃허브
![](./(2)-1_팀서버_깃허브배포_웹사이트_163.239.77.76-8022.png)
![](./(2)-2_팀서버_깃허브배포_젠킨스빌드.png)

## (3) 팀 서버 배포 — 바로 pull
![](./(3)-1_팀서버_pull배포_웹사이트_163.239.77.76-8023.png)
![](./(3)-2_팀서버_pull배포_젠킨스빌드.png)

## (4) 빌드 오류 시 이메일 발송
`requirements.txt`를 `fastapi==9999.0.0`으로 바꿔 빌드 오류를 낸 뒤(`32e2ed3`) Jenkins가 kenny31@sogang.ac.kr로 실패 메일을 발송, 이후 되돌려(`471481f`) 복구 확인.

![](./(4)-1_빌드실패_젠킨스빌드.png)
![](./(4)-2_빌드실패_콘솔_메일발송.png)
