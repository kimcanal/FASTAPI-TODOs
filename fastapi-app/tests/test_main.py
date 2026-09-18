import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_FILE", tmp_path / "test.db")
    main.init_db()


def register(client: TestClient, username: str = "alice", password: str = "secret1") -> dict:
    response = client.post("/auth/register", json={"username": username, "password": password})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def client():
    return TestClient(main.app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_endpoint_matches_version_file(client):
    response = client.get("/api/version")
    assert response.status_code == 200
    assert response.json()["version"] == main.APP_VERSION


def test_release_notes_page_renders_html(client):
    response = client.get("/release-notes")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_todos_require_login(client):
    assert client.get("/todos").status_code == 401
    assert client.post("/todos", json={"title": "x"}).status_code == 401


def test_register_creates_session_and_me_reflects_it(client):
    register(client, "alice", "secret1")
    response = client.get("/auth/me")
    assert response.status_code == 200
    assert response.json() == {"username": "alice"}


def test_duplicate_username_is_rejected(client):
    register(client, "alice", "secret1")
    other = TestClient(main.app)
    response = other.post("/auth/register", json={"username": "alice", "password": "different1"})
    assert response.status_code == 409


def test_login_with_wrong_password_is_rejected(client):
    register(client, "alice", "secret1")
    fresh = TestClient(main.app)
    response = fresh.post("/auth/login", json={"username": "alice", "password": "wrongpass"})
    assert response.status_code == 401


def test_login_with_correct_password_succeeds(client):
    register(client, "alice", "secret1")
    fresh = TestClient(main.app)
    response = fresh.post("/auth/login", json={"username": "alice", "password": "secret1"})
    assert response.status_code == 200
    assert fresh.get("/auth/me").json() == {"username": "alice"}


def test_logout_clears_session(client):
    register(client, "alice", "secret1")
    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401


def test_todo_crud_roundtrip(client):
    register(client, "alice", "secret1")

    created = client.post("/todos", json={"title": "우유 사기"}).json()
    assert client.get("/todos").json() == [created]

    updated = client.put(
        f"/todos/{created['id']}",
        json={"title": "우유 사기", "description": "2%", "completed": True},
    ).json()
    assert updated["completed"] is True

    assert client.get("/todos", params={"completed": "true"}).json() == [updated]
    assert client.get("/todos", params={"completed": "false"}).json() == []

    assert client.delete(f"/todos/{created['id']}").status_code == 204
    assert client.get("/todos").json() == []


def test_blank_title_is_rejected(client):
    register(client, "alice", "secret1")
    response = client.post("/todos", json={"title": "   "})
    assert response.status_code == 422


def test_users_cannot_see_or_modify_each_others_todos(client):
    register(client, "alice", "secret1")
    todo = client.post("/todos", json={"title": "alice's secret"}).json()

    bob = TestClient(main.app)
    register(bob, "bob", "secret2")

    assert bob.get("/todos").json() == []
    assert bob.put(f"/todos/{todo['id']}", json={"title": "hijacked"}).status_code == 404
    assert bob.delete(f"/todos/{todo['id']}").status_code == 404

    # alice의 데이터는 그대로 남아 있어야 한다
    assert client.get("/todos").json() == [todo]
