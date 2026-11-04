pipeline {
    agent any

    environment {
        REMOTE_USER = 'sogang007'
        REMOTE_HOST = '163.239.77.80'
        REMOTE_PATH = '/home/sogang007@SGVDI.local'
        REPO_URL    = 'https://github.com/kimcanal/FASTAPI-TODOs.git'
        BRANCH_NAME = 'main'
        REPO_DIR    = 'FastApi_Todos-deploy'
        APP_DIR     = '.'
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
                        --cov-report=xml:fastapi-app/coverage.xml \
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

        stage('SonarQube Analysis') {
            steps {
                withSonarQubeEnv('sonarqube') {
                    sh "${tool 'sonar'}/bin/sonar-scanner"
                }
            }
        }

        stage('Quality Gate') {
            steps {
                timeout(time: 5, unit: 'MINUTES') {
                    waitForQualityGate abortPipeline: true
                }
            }
        }

        // 팀 서버가 archive.apache.org 접근이 느리거나 막혀 있어, jmeter 이미지를
        // Dockerfile로 직접 빌드하지 못한다(JMeter tarball 다운로드 단계에서 멈춤).
        // Docker Hub pull은 팀 서버에서 이미 정상 동작하므로(기존 dockerhub 배포 파이프라인),
        // 네트워크가 되는 이 서버(Jenkins 에이전트)에서 미리 빌드해 올려두고 팀 서버는 pull만 한다.
        stage('Build & Push JMeter Image') {
            steps {
                script {
                    def jmImg = docker.build('lucatonikroos/jmeter-fastapi-todos:' + env.BUILD_NUMBER, '--pull jmeter')
                    docker.withRegistry('https://index.docker.io/v1/', 'dockerhub-credentials') {
                        jmImg.push()
                        jmImg.push('latest')
                    }
                }
            }
        }

        // 테스트를 통과해야만 여기(Docker 빌드/배포)로 넘어온다
        stage('Deploy') {
            steps {
                sshagent(credentials: ['deploy-key']) {
                    sh '''
ssh ${REMOTE_USER}@${REMOTE_HOST} \
  "REMOTE_PATH='${REMOTE_PATH}' REPO_URL='${REPO_URL}' BRANCH_NAME='${BRANCH_NAME}' REPO_DIR='${REPO_DIR}' APP_DIR='${APP_DIR}' BUILD_NUMBER='${BUILD_NUMBER}' GIT_COMMIT='${GIT_COMMIT}' bash -se" <<'ENDSSH'
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
# jmeter 컨테이너(uid 1000)가 호스트 바인드 마운트에 결과를 쓸 수 있도록.
# 이 서버 계정의 uid가 1000이 아니라서 (AD 계정) 기본 권한(755)으로는 쓰기가 막힌다.
mkdir -p jmeter && chmod 777 jmeter
[ -f .env ] || echo "GRAFANA_ADMIN_PASSWORD=change-me-12chars-Aa1!" > .env
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
ssh ${REMOTE_USER}@${REMOTE_HOST} "REMOTE_PATH='${REMOTE_PATH}' REPO_DIR='${REPO_DIR}' APP_DIR='${APP_DIR}' bash -se" <<'ENDSSH'
set -euo pipefail
cd "$REMOTE_PATH/$REPO_DIR/$APP_DIR"
docker wait jmeter >/dev/null
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
                        reportName           : 'JMeter HTML Report',
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

    post {
        failure {
            emailext(
                to: 'kenny31@sogang.ac.kr',
                subject: "[Jenkins] 빌드 실패: ${env.JOB_NAME} #${env.BUILD_NUMBER}",
                mimeType: 'text/html',
                attachLog: true,
                body: """<h2>❌ 빌드 실패</h2>
<p><b>Job:</b> ${env.JOB_NAME}<br><b>Build:</b> #${env.BUILD_NUMBER}<br><b>Commit:</b> ${env.GIT_COMMIT}</p>
<p><a href="${env.BUILD_URL}console">Console Output 보기</a> (전체 로그는 첨부파일 참고)</p>"""
            )
        }
        fixed {
            emailext(
                to: 'kenny31@sogang.ac.kr',
                subject: "[Jenkins] 빌드 복구: ${env.JOB_NAME} #${env.BUILD_NUMBER}",
                mimeType: 'text/html',
                body: """<h2>✅ 빌드 복구</h2>
<p>${env.JOB_NAME} #${env.BUILD_NUMBER} 빌드가 다시 성공했습니다.</p>
<p><a href="${env.BUILD_URL}">빌드 보기</a></p>"""
            )
        }
    }
}
