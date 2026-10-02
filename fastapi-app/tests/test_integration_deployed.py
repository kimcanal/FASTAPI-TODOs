"""실제로 배포된 환경(컨테이너로 떠 있는 API)에 HTTP 요청을 보내 확인하는 통합 테스트.

단위 테스트(test_main.py)와 달리 TestClient를 쓰지 않고, 네트워크 너머의 진짜 서버를
때린다. 기본 CI(`pytest`)에서는 제외되고(`pyproject.toml`의 `not integration` 기본값),
배포 후 별도로 아래처럼 실행한다:

    API_BASE_URL=http://163.239.77.76:8022 pytest -m integration \
        tests/test_integration_deployed.py -v --html=integration-report.html --self-contained-html
"""

import os
import time

import httpx2
import pytest

pytestmark = pytest.mark.integration

BASE_URL = os.environ.get("API_BASE_URL", "http://163.239.77.76:8022")
TEST_USERNAME = f"it_{int(time.time())}"
TEST_PASSWORD = "integration1"


@pytest.fixture(scope="module")
def anon_client():
    with httpx2.Client(base_url=BASE_URL, timeout=10) as client:
        yield client


@pytest.fixture(scope="module")
def auth_client():
    with httpx2.Client(base_url=BASE_URL, timeout=10) as client:
        response = client.post(
            "/auth/register",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        )
        assert response.status_code == 201, response.text
        yield client


def test_health_check_is_ok(anon_client):
    response = anon_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_endpoint_reports_build_info(anon_client):
    response = anon_client.get("/api/version")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"version", "commit", "build"}


def test_todos_require_login(anon_client):
    assert anon_client.get("/todos").status_code == 401


def test_register_then_me_reflects_new_user(auth_client):
    response = auth_client.get("/auth/me")
    assert response.status_code == 200
    assert response.json() == {"username": TEST_USERNAME}


def test_todo_crud_roundtrip_against_live_deployment(auth_client):
    created = auth_client.post("/todos", json={"title": "통합테스트 할 일"}).json()
    assert auth_client.get("/todos").json() == [created]

    updated = auth_client.put(
        f"/todos/{created['id']}",
        json={"title": "통합테스트 할 일", "description": "배포 환경에서 생성됨", "completed": True},
    ).json()
    assert updated["completed"] is True

    assert auth_client.get("/todos", params={"completed": "true"}).json() == [updated]

    assert auth_client.delete(f"/todos/{created['id']}").status_code == 204
    assert auth_client.get("/todos").json() == []


def test_logout_then_me_is_rejected(auth_client):
    assert auth_client.post("/auth/logout").status_code == 200
    assert auth_client.get("/auth/me").status_code == 401
