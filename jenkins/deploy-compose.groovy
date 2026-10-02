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
        timeout(time: 15, unit: 'MINUTES')
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
docker compose up -d --build --remove-orphans
docker compose ps
ENDSSH
'''
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
