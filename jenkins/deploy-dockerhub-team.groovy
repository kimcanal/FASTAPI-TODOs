pipeline {
    agent any

    environment {
        DOCKERHUB_CREDENTIALS = 'dockerhub-credentials'
        IMAGE_NAME     = 'lucatonikroos/fastapi-app'
        IMAGE_TAG      = "team-${env.BUILD_NUMBER}"   // 본인 서버 작업과 태그가 겹치지 않게
        REMOTE_USER    = 'sogang003'
        REMOTE_HOST    = '163.239.77.76'
        REPO_URL       = 'https://github.com/kimcanal/FASTAPI-TODOs.git'
        BRANCH_NAME    = 'main'
        CONTAINER_NAME = 'fastapi-app2-yunha'
        HOST_PORT      = '8023'
        CONTAINER_PORT = '8000'
    }

    options {
        timeout(time: 20, unit: 'MINUTES')
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                git url: "${REPO_URL}", branch: "${BRANCH_NAME}"
            }
        }

        stage('Build') {
            steps {
                dir('fastapi-app') {
                    script {
                        docker.build("${IMAGE_NAME}:${IMAGE_TAG}", "--pull .")
                    }
                }
            }
        }

        stage('Push') {
            steps {
                script {
                    docker.withRegistry('https://index.docker.io/v1/', DOCKERHUB_CREDENTIALS) {
                        def img = docker.image("${IMAGE_NAME}:${IMAGE_TAG}")
                        img.push()
                        img.push('latest')
                    }
                }
            }
        }

        stage('Deploy') {
            steps {
                sshagent(credentials: ['deploy-key']) {
                    sh '''
ssh ${REMOTE_USER}@${REMOTE_HOST} \
  "IMAGE='${IMAGE_NAME}:${IMAGE_TAG}' CONTAINER_NAME='${CONTAINER_NAME}' HOST_PORT='${HOST_PORT}' CONTAINER_PORT='${CONTAINER_PORT}' BUILD_NUMBER='${BUILD_NUMBER}' GIT_COMMIT='${GIT_COMMIT}' bash -se" <<'ENDSSH'
set -euo pipefail

docker pull "$IMAGE"
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
docker run -d --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  --security-opt no-new-privileges:true \
  --cap-drop ALL \
  -e BUILD_NUMBER="$BUILD_NUMBER" \
  -e GIT_COMMIT="$GIT_COMMIT" \
  -p "$HOST_PORT:$CONTAINER_PORT" \
  -v "$CONTAINER_NAME-data:/app/data" \
  "$IMAGE"
docker ps --filter "name=$CONTAINER_NAME"
ENDSSH
'''
                }
            }
        }
    }

    post {
        always {
            sh 'docker image prune -f || true'
            echo 'Docker Hub 기반 배포 파이프라인 실행 완료.'
        }
    }
}
