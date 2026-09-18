pipeline {
    agent any

    environment {
        APP_DIR = 'fastapi-app'
        DEPLOY_PORT = '8000'
    }

    stages {
        stage('Install') {
            steps {
                sh '''
                    python3 -m venv "$APP_DIR/myenv"
                    "$APP_DIR/myenv/bin/pip" install --upgrade pip
                    "$APP_DIR/myenv/bin/pip" install -r "$APP_DIR/requirements.txt" -r "$APP_DIR/requirements-dev.txt"
                '''
            }
        }

        stage('Test') {
            steps {
                sh '"$APP_DIR/myenv/bin/pytest" "$APP_DIR" -v'
            }
        }

        // 이 머신(163.239.77.80)의 DEPLOY_PORT에서 uvicorn을 재기동합니다.
        // Jenkins 프로세스(jenkins 사용자)가 기존 uvicorn(sogang007 소유)을
        // kill할 수 있는 권한이 있어야 합니다 (필요 시 sudoers/agent 사용자 설정 확인).
        stage('Deploy') {
            steps {
                sh '''
                    PID=$(lsof -ti tcp:${DEPLOY_PORT} || true)
                    if [ -n "$PID" ]; then
                        kill "$PID"
                        sleep 2
                    fi
                    cd "$APP_DIR"
                    nohup ./myenv/bin/uvicorn main:app --host 0.0.0.0 --port "${DEPLOY_PORT}" > app.log 2>&1 &
                    disown
                    sleep 2
                    curl -sf "http://localhost:${DEPLOY_PORT}/health"
                '''
            }
        }
    }

    post {
        success {
            echo "빌드 성공: #${env.BUILD_NUMBER} (commit ${env.GIT_COMMIT})"
        }
        failure {
            echo "빌드 실패: #${env.BUILD_NUMBER}"
        }
    }
}
