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

        stage('Deploy') {
            steps {
                sshagent(credentials: ['deploy-key']) {
                    sh '''
ssh ${REMOTE_USER}@${REMOTE_HOST} \
  "REMOTE_PATH='${REMOTE_PATH}' REPO_URL='${REPO_URL}' BRANCH_NAME='${BRANCH_NAME}' REPO_DIR='${REPO_DIR}' APP_DIR='${APP_DIR}' BUILD_NUMBER='${BUILD_NUMBER}' GIT_COMMIT='${GIT_COMMIT}' CONTAINER_NAME='${CONTAINER_NAME}' HOST_PORT='${HOST_PORT}' bash -se" <<'ENDSSH'
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
export CONTAINER_NAME HOST_PORT
docker compose up -d --build --remove-orphans
docker compose ps
ENDSSH
'''
                }
            }
        }
    }
}
