pipeline {
    agent any

    environment {
        REMOTE_USER = 'sogang003'
        REMOTE_HOST = '163.239.77.76'
        REMOTE_PATH = '/home/sogang003@SGVDI.local'
        REPO_URL    = 'https://github.com/kimcanal/FASTAPI-TODOs.git'
        BRANCH_NAME = 'main'
        REPO_DIR    = 'FastApi_Todos-deploy-yunha'
        APP_DIR     = '.'
        CONTAINER_NAME = 'FastApi-app-yunha'   // 팀 서버에서 겹치지 않는 이름
        HOST_PORT   = '8022'                   // 팀 서버에 배정된 포트
        // influxdb/jmeter도 container_name이 고정값이라, 팀원들이 같은 docker-compose.yml을
        // 각자 올리면 이름이 겹친다. fastapi-app과 같은 방식으로 이름을 분리한다.
        INFLUXDB_CONTAINER_NAME = 'influxdb-yunha'
        JMETER_CONTAINER_NAME   = 'jmeter-yunha'
    }

    options {
        timeout(time: 30, unit: 'MINUTES')   // jmeter 이미지 빌드(JMeter tarball 다운로드)가 추가되어 넉넉히 잡음
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                git url: "${REPO_URL}", branch: "${BRANCH_NAME}"
            }
        }

        stage('Install') {
            steps {
                sh '''
                    python3 -m venv fastapi-app/myenv
                    fastapi-app/myenv/bin/pip install --upgrade pip
                    fastapi-app/myenv/bin/pip install -r fastapi-app/requirements.txt -r fastapi-app/requirements-dev.txt
                '''
            }
        }

        stage('Test') {
            steps {
                sh '''
                    fastapi-app/myenv/bin/pytest fastapi-app -v \
                        --cov=main --cov-report=term --cov-report=html:fastapi-app/htmlcov \
                        --html=fastapi-app/report.html --self-contained-html \
                        --junitxml=fastapi-app/junit.xml
                '''
            }
            post {
                always {
                    junit 'fastapi-app/junit.xml'
                    archiveArtifacts artifacts: 'fastapi-app/htmlcov/**, fastapi-app/report.html', allowEmptyArchive: true
                }
            }
        }

        // 테스트를 통과해야만 여기(팀 서버 Docker 빌드/배포)로 넘어온다
        stage('Deploy') {
            steps {
                sshagent(credentials: ['deploy-key']) {
                    sh '''
ssh ${REMOTE_USER}@${REMOTE_HOST} \
  "REMOTE_PATH='${REMOTE_PATH}' REPO_URL='${REPO_URL}' BRANCH_NAME='${BRANCH_NAME}' REPO_DIR='${REPO_DIR}' APP_DIR='${APP_DIR}' BUILD_NUMBER='${BUILD_NUMBER}' GIT_COMMIT='${GIT_COMMIT}' CONTAINER_NAME='${CONTAINER_NAME}' HOST_PORT='${HOST_PORT}' INFLUXDB_CONTAINER_NAME='${INFLUXDB_CONTAINER_NAME}' JMETER_CONTAINER_NAME='${JMETER_CONTAINER_NAME}' bash -se" <<'ENDSSH'
set -euo pipefail
cd "$REMOTE_PATH"

if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" fetch --prune origin
  git -C "$REPO_DIR" checkout "$BRANCH_NAME"
  git -C "$REPO_DIR" reset --hard "origin/$BRANCH_NAME"
else
  git clone --branch "$BRANCH_NAME" "$REPO_URL" "$REPO_DIR"
fi

cd "$REPO_DIR/$APP_DIR"
export CONTAINER_NAME HOST_PORT INFLUXDB_CONTAINER_NAME JMETER_CONTAINER_NAME
# jmeter 컨테이너(uid 1000)가 호스트 바인드 마운트에 결과를 쓸 수 있도록.
mkdir -p jmeter && chmod 777 jmeter
# Grafana는 팀 서버에서 쓰지 않지만, docker-compose.yml 전체가 파싱되면서
# 필수값(:?) 검증에 걸리므로 자리만 채워둔다.
[ -f .env ] || echo "GRAFANA_ADMIN_PASSWORD=unused-on-team-server-Aa1!" > .env
docker compose up -d --build --remove-orphans
docker compose ps
ENDSSH
'''
                }
            }
        }

        // JMeter는 compose 의존성(healthy)이 갖춰지는 대로 백그라운드로 시작되므로,
        // Deploy 단계가 끝난 시점엔 아직 실행 중일 수 있다 — 끝날 때까지 기다렸다가 리포트를 가져온다.
        stage('Wait for JMeter & Collect Report') {
            steps {
                sshagent(credentials: ['deploy-key']) {
                    sh '''
ssh ${REMOTE_USER}@${REMOTE_HOST} "REMOTE_PATH='${REMOTE_PATH}' REPO_DIR='${REPO_DIR}' APP_DIR='${APP_DIR}' JMETER_CONTAINER_NAME='${JMETER_CONTAINER_NAME}' bash -se" <<'ENDSSH'
set -euo pipefail
cd "$REMOTE_PATH/$REPO_DIR/$APP_DIR"
docker wait "$JMETER_CONTAINER_NAME" >/dev/null
ENDSSH

rm -rf jmeter-report results.jtl
mkdir -p jmeter-report
scp -o StrictHostKeyChecking=yes -r \
  "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/${REPO_DIR}/${APP_DIR}/jmeter/report/." jmeter-report/ || true
scp -o StrictHostKeyChecking=yes \
  "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/${REPO_DIR}/${APP_DIR}/jmeter/results.jtl" . || true
'''
                }
            }
            post {
                always {
                    publishHTML(target: [
                        reportName           : 'JMeter HTML Report (Team Server)',
                        reportDir            : 'jmeter-report',
                        reportFiles          : 'index.html',
                        keepAll              : true,
                        alwaysLinkToLastBuild: true,
                        allowMissing         : true
                    ])
                    archiveArtifacts artifacts: 'results.jtl', allowEmptyArchive: true
                }
            }
        }
    }
}
