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


def test_root_redirects_to_login_when_logged_out(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/login"


def test_root_serves_app_when_logged_in(client):
    register(client, "alice", "secret1")
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_login_page_redirects_to_root_when_already_logged_in(client):
    register(client, "alice", "secret1")
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/"


def test_login_page_renders_when_logged_out(client):
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_stale_session_for_deleted_user_is_rejected(client):
    user = register(client, "alice", "secret1")
    with main.get_db() as conn:
        conn.execute("DELETE FROM users WHERE username = ?", (user["username"],))

    response = client.get("/auth/me")
    assert response.status_code == 401
    # 세션도 함께 지워졌어야, 다음 요청에서도 계속 401이어야 한다
    assert client.get("/auth/me").status_code == 401


def test_detect_git_commit_prefers_env_var(monkeypatch):
    monkeypatch.setenv("GIT_COMMIT", "abcdef1234567890")
    assert main._detect_git_commit() == "abcdef1"


def test_detect_git_commit_falls_back_when_git_fails(monkeypatch):
    monkeypatch.delenv("GIT_COMMIT", raising=False)

    def boom(*args, **kwargs):
        raise FileNotFoundError("git not installed")

    monkeypatch.setattr(main.subprocess, "run", boom)
    assert main._detect_git_commit() == "unknown"


def test_get_or_create_session_secret_prefers_env_var(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "env-secret")
    assert main._get_or_create_session_secret() == "env-secret"


def test_get_or_create_session_secret_reuses_existing_file(tmp_path, monkeypatch):
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    secret_file = tmp_path / ".session_secret"
    secret_file.write_text("file-secret", encoding="utf-8")
    monkeypatch.setattr(main, "SESSION_SECRET_FILE", secret_file)
    assert main._get_or_create_session_secret() == "file-secret"


def test_get_or_create_session_secret_creates_file_when_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    secret_file = tmp_path / ".session_secret"
    monkeypatch.setattr(main, "SESSION_SECRET_FILE", secret_file)

    secret = main._get_or_create_session_secret()
    assert secret_file.read_text(encoding="utf-8").strip() == secret


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


def test_todo_defaults_to_normal_priority_and_no_due_date(client):
    register(client, "alice", "secret1")
    created = client.post("/todos", json={"title": "우유 사기"}).json()
    assert created["priority"] == "normal"
    assert created["due_date"] is None


def test_todo_priority_and_due_date_roundtrip(client):
    register(client, "alice", "secret1")
    created = client.post(
        "/todos",
        json={"title": "발표 준비", "priority": "high", "due_date": "2026-12-25"},
    ).json()
    assert created["priority"] == "high"
    assert created["due_date"] == "2026-12-25"

    updated = client.put(
        f"/todos/{created['id']}",
        json={"title": "발표 준비", "priority": "normal", "due_date": None},
    ).json()
    assert updated["priority"] == "normal"
    assert updated["due_date"] is None


def test_todo_search_filters_by_title_and_description(client):
    register(client, "alice", "secret1")
    client.post("/todos", json={"title": "우유 사기", "description": "2%"})
    client.post("/todos", json={"title": "운동하기", "description": "헬스장"})

    response = client.get("/todos", params={"q": "우유"})
    assert [t["title"] for t in response.json()] == ["우유 사기"]

    response = client.get("/todos", params={"q": "헬스"})
    assert [t["title"] for t in response.json()] == ["운동하기"]


def test_todo_sort_by_priority_puts_high_first(client):
    register(client, "alice", "secret1")
    client.post("/todos", json={"title": "일반 할 일", "priority": "normal"})
    client.post("/todos", json={"title": "중요한 할 일", "priority": "high"})

    response = client.get("/todos", params={"sort": "priority"})
    assert [t["title"] for t in response.json()] == ["중요한 할 일", "일반 할 일"]


def test_todo_sort_by_due_date_puts_items_without_due_date_last(client):
    register(client, "alice", "secret1")
    client.post("/todos", json={"title": "날짜 없음"})
    client.post("/todos", json={"title": "먼 미래", "due_date": "2026-12-31"})
    client.post("/todos", json={"title": "가까운 미래", "due_date": "2026-11-01"})

    response = client.get("/todos", params={"sort": "due_date"})
    assert [t["title"] for t in response.json()] == ["가까운 미래", "먼 미래", "날짜 없음"]


def test_stats_streak_increments_once_per_day_when_all_done(client):
    register(client, "alice", "secret1")
    created = client.post("/todos", json={"title": "할 일"}).json()

    assert client.get("/stats").json()["streak"] == 0

    client.put(f"/todos/{created['id']}", json={"title": "할 일", "completed": True})
    assert client.get("/stats").json()["streak"] == 1
    # 같은 날 다시 조회해도 중복으로 올라가지 않는다
    assert client.get("/stats").json()["streak"] == 1


def test_data_dir_env_moves_db_and_secret(tmp_path, monkeypatch):
    import importlib

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    reloaded = importlib.reload(main)
    try:
        assert reloaded.DB_FILE == tmp_path / "data" / "todo.db"
        assert reloaded.DB_FILE.exists()
        assert (tmp_path / "data" / ".session_secret").exists()
    finally:
        monkeypatch.delenv("DATA_DIR")
        importlib.reload(main)
