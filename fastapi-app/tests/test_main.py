import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_FILE", tmp_path / "test.db")
    main.init_db()


ALICE = "20231001"
BOB = "20231002"


def register(client: TestClient, username: str = ALICE) -> dict:
    response = client.post("/auth/register", json={"username": username})
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
    register(client)
    response = client.get("/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == ALICE


def test_duplicate_username_is_rejected(client):
    register(client)
    other = TestClient(main.app)
    response = other.post("/auth/register", json={"username": ALICE})
    assert response.status_code == 409


def test_register_rejects_non_numeric_username(client):
    response = client.post("/auth/register", json={"username": "alice"})
    assert response.status_code == 422


def test_login_with_wrong_password_is_rejected(client):
    register(client)
    fresh = TestClient(main.app)
    response = fresh.post("/auth/login", json={"username": ALICE, "password": "9999"})
    assert response.status_code == 401


def test_login_with_correct_password_succeeds(client):
    register(client)
    fresh = TestClient(main.app)
    response = fresh.post("/auth/login", json={"username": ALICE, "password": main.DEFAULT_PASSWORD})
    assert response.status_code == 200
    assert fresh.get("/auth/me").json()["username"] == ALICE


def test_logout_clears_session(client):
    register(client)
    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401


def test_change_password_then_login_requires_new_password(client):
    register(client)
    response = client.post("/auth/password", json={"old_password": main.DEFAULT_PASSWORD, "new_password": "1234"})
    assert response.status_code == 200

    fresh = TestClient(main.app)
    assert fresh.post("/auth/login", json={"username": ALICE, "password": main.DEFAULT_PASSWORD}).status_code == 401
    assert fresh.post("/auth/login", json={"username": ALICE, "password": "1234"}).status_code == 200


def test_change_password_with_wrong_old_password_is_rejected(client):
    register(client)
    response = client.post("/auth/password", json={"old_password": "9999", "new_password": "1234"})
    assert response.status_code == 400


def test_change_password_requires_login(client):
    response = client.post("/auth/password", json={"old_password": main.DEFAULT_PASSWORD, "new_password": "1234"})
    assert response.status_code == 401


def test_change_password_rejects_non_numeric_new_password(client):
    register(client)
    response = client.post("/auth/password", json={"old_password": main.DEFAULT_PASSWORD, "new_password": "abcd"})
    assert response.status_code == 422


def test_todo_crud_roundtrip(client):
    register(client)

    created = client.post("/todos", json={"title": "우유 사기"}).json()
    assert client.get("/todos").json() == [{**created, "reaction_counts": {}}]

    updated = client.put(
        f"/todos/{created['id']}",
        json={"title": "우유 사기", "description": "2%", "completed": True},
    ).json()
    assert updated["completed"] is True

    assert client.get("/todos", params={"completed": "true"}).json() == [{**updated, "reaction_counts": {}}]
    assert client.get("/todos", params={"completed": "false"}).json() == []

    assert client.delete(f"/todos/{created['id']}").status_code == 204
    assert client.get("/todos").json() == []


def test_deleted_todo_can_be_restored(client):
    register(client)
    created = client.post("/todos", json={"title": "우유 사기"}).json()

    assert client.delete(f"/todos/{created['id']}").status_code == 204
    assert client.get("/todos").json() == []

    restored = client.post(f"/todos/{created['id']}/restore")
    assert restored.status_code == 200
    assert restored.json() == created
    assert client.get("/todos").json() == [{**created, "reaction_counts": {}}]


def test_restoring_a_todo_that_was_never_deleted_returns_404(client):
    register(client)
    created = client.post("/todos", json={"title": "우유 사기"}).json()
    assert client.post(f"/todos/{created['id']}/restore").status_code == 404


def test_restoring_someone_elses_deleted_todo_returns_404(client):
    register(client)
    todo = client.post("/todos", json={"title": "alice's secret"}).json()
    client.delete(f"/todos/{todo['id']}")

    bob = TestClient(main.app)
    register(bob, BOB)
    assert bob.post(f"/todos/{todo['id']}/restore").status_code == 404


def test_restoring_a_completed_todo_marks_it_incomplete(client):
    register(client)
    created = client.post("/todos", json={"title": "우유 사기"}).json()
    client.put(f"/todos/{created['id']}", json={"title": "우유 사기", "completed": True})

    client.delete(f"/todos/{created['id']}")
    restored = client.post(f"/todos/{created['id']}/restore").json()

    assert restored["completed"] is False


def test_deleted_todo_appears_in_trash_until_restored(client):
    register(client)
    created = client.post("/todos", json={"title": "우유 사기"}).json()

    assert client.get("/todos/trash").json() == []

    client.delete(f"/todos/{created['id']}")
    trash = client.get("/todos/trash").json()
    assert len(trash) == 1
    assert trash[0]["id"] == created["id"]
    assert "deleted_at" in trash[0]

    client.post(f"/todos/{created['id']}/restore")
    assert client.get("/todos/trash").json() == []


def test_trash_is_scoped_to_owner(client):
    register(client)
    todo = client.post("/todos", json={"title": "alice's secret"}).json()
    client.delete(f"/todos/{todo['id']}")

    bob = TestClient(main.app)
    register(bob, BOB)
    assert bob.get("/todos/trash").json() == []


def test_trash_older_than_retention_period_is_purged_on_startup(client):
    from datetime import datetime, timedelta, timezone

    register(client)
    recent = client.post("/todos", json={"title": "최근 삭제"}).json()
    stale = client.post("/todos", json={"title": "오래된 삭제"}).json()
    client.delete(f"/todos/{recent['id']}")
    client.delete(f"/todos/{stale['id']}")

    just_inside = datetime.now(timezone.utc) - timedelta(days=main.TRASH_RETENTION_DAYS) + timedelta(hours=1)
    just_outside = datetime.now(timezone.utc) - timedelta(days=main.TRASH_RETENTION_DAYS) - timedelta(hours=1)
    with main.get_db() as conn:
        conn.execute("UPDATE todos SET deleted_at = ? WHERE id = ?", (just_inside.isoformat(), recent["id"]))
        conn.execute("UPDATE todos SET deleted_at = ? WHERE id = ?", (just_outside.isoformat(), stale["id"]))

    main.init_db()  # 배포/재시작 시 실행되는 정리 로직

    trash_ids = {t["id"] for t in client.get("/todos/trash").json()}
    assert trash_ids == {recent["id"]}


def test_export_returns_csv_of_own_todos_only(client):
    register(client)
    client.post("/todos", json={"title": "우유 사기", "priority": "high", "due_date": "2026-12-25"})
    deleted = client.post("/todos", json={"title": "휴지통행"}).json()
    client.delete(f"/todos/{deleted['id']}")

    bob = TestClient(main.app)
    register(bob, BOB)
    bob.post("/todos", json={"title": "bob's todo"})

    response = client.get("/todos/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    body = response.text
    assert "우유 사기" in body
    assert "high" in body
    assert "2026-12-25" in body
    assert "휴지통행" not in body   # 삭제(휴지통)된 항목은 내보내지 않음
    assert "bob's todo" not in body  # 본인 것만


def test_import_adds_valid_rows_and_skips_invalid_ones(client):
    register(client)
    csv_body = (
        "title,description,completed,priority,due_date\n"
        "할 일 1,설명1,true,high,2026-12-31\n"
        "할 일 2,,false,normal,\n"
        ",빈 제목은 거부됨,false,normal,\n"
    )
    files = {"file": ("todos.csv", csv_body, "text/csv")}
    response = client.post("/todos/import", files=files)

    assert response.status_code == 201
    assert response.json() == {"added": 2, "skipped": 1}

    todos = client.get("/todos").json()
    assert len(todos) == 2
    first = next(t for t in todos if t["title"] == "할 일 1")
    assert first["completed"] is True
    assert first["priority"] == "high"
    assert first["due_date"] == "2026-12-31"


def test_import_does_not_touch_existing_todos(client):
    register(client)
    existing = client.post("/todos", json={"title": "기존 할 일"}).json()
    files = {"file": ("todos.csv", "title,description,completed,priority,due_date\n새 할 일,,false,normal,\n", "text/csv")}
    client.post("/todos/import", files=files)

    todos = client.get("/todos").json()
    assert {**existing, "reaction_counts": {}} in todos
    assert any(t["title"] == "새 할 일" for t in todos)
    assert len(todos) == 2


def test_blank_title_is_rejected(client):
    register(client)
    response = client.post("/todos", json={"title": "   "})
    assert response.status_code == 422


def test_root_redirects_to_login_when_logged_out(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/login"


def test_root_serves_app_when_logged_in(client):
    register(client)
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_login_page_redirects_to_root_when_already_logged_in(client):
    register(client)
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/"


def test_login_page_renders_when_logged_out(client):
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_stale_session_for_deleted_user_is_rejected(client):
    user = register(client)
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
    register(client)
    todo = client.post("/todos", json={"title": "alice's secret"}).json()

    bob = TestClient(main.app)
    register(bob, BOB)

    assert bob.get("/todos").json() == []
    assert bob.put(f"/todos/{todo['id']}", json={"title": "hijacked"}).status_code == 404
    assert bob.delete(f"/todos/{todo['id']}").status_code == 404

    # alice의 데이터는 그대로 남아 있어야 한다
    assert client.get("/todos").json() == [{**todo, "reaction_counts": {}}]


def test_todo_defaults_to_normal_priority_and_no_due_date(client):
    register(client)
    created = client.post("/todos", json={"title": "우유 사기"}).json()
    assert created["priority"] == "normal"
    assert created["due_date"] is None


def test_todo_priority_and_due_date_roundtrip(client):
    register(client)
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
    register(client)
    client.post("/todos", json={"title": "우유 사기", "description": "2%"})
    client.post("/todos", json={"title": "운동하기", "description": "헬스장"})

    response = client.get("/todos", params={"q": "우유"})
    assert [t["title"] for t in response.json()] == ["우유 사기"]

    response = client.get("/todos", params={"q": "헬스"})
    assert [t["title"] for t in response.json()] == ["운동하기"]


def test_todo_sort_by_priority_puts_high_first(client):
    register(client)
    client.post("/todos", json={"title": "일반 할 일", "priority": "normal"})
    client.post("/todos", json={"title": "중요한 할 일", "priority": "high"})

    response = client.get("/todos", params={"sort": "priority"})
    assert [t["title"] for t in response.json()] == ["중요한 할 일", "일반 할 일"]


def test_todo_sort_by_due_date_puts_items_without_due_date_last(client):
    register(client)
    client.post("/todos", json={"title": "날짜 없음"})
    client.post("/todos", json={"title": "먼 미래", "due_date": "2026-12-31"})
    client.post("/todos", json={"title": "가까운 미래", "due_date": "2026-11-01"})

    response = client.get("/todos", params={"sort": "due_date"})
    assert [t["title"] for t in response.json()] == ["가까운 미래", "먼 미래", "날짜 없음"]


def test_stats_streak_increments_once_per_day_when_all_done(client):
    register(client)
    created = client.post("/todos", json={"title": "할 일"}).json()

    assert client.get("/stats").json()["streak"] == 0

    client.put(f"/todos/{created['id']}", json={"title": "할 일", "completed": True})
    assert client.get("/stats").json()["streak"] == 1
    # 같은 날 다시 조회해도 중복으로 올라가지 않는다
    assert client.get("/stats").json()["streak"] == 1


def test_add_friend_by_username_links_both_directions(client):
    register(client)

    bob = TestClient(main.app)
    register(bob, BOB)

    response = bob.post("/friends", json={"username": ALICE})
    assert response.status_code == 201
    assert response.json()["username"] == ALICE
    assert [f["username"] for f in bob.get("/friends").json()] == [ALICE]
    assert [f["username"] for f in client.get("/friends").json()] == [BOB]


def test_add_friend_with_unknown_username_is_404(client):
    register(client)
    assert client.post("/friends", json={"username": "99999999"}).status_code == 404


def test_add_self_as_friend_is_rejected(client):
    register(client)
    assert client.post("/friends", json={"username": ALICE}).status_code == 400


def test_remove_friend_unlinks_both_directions(client):
    register(client)
    bob = TestClient(main.app)
    register(bob, BOB)
    bob.post("/friends", json={"username": ALICE})
    bob_id = client.get("/friends").json()[0]["id"]

    assert client.delete(f"/friends/{bob_id}").status_code == 204
    assert client.get("/friends").json() == []
    assert bob.get("/friends").json() == []


def test_friend_can_view_and_toggle_reaction(client):
    register(client)
    created = client.post("/todos", json={"title": "밥 먹기"}).json()
    alice_id = client.get("/auth/me").json()["id"]

    bob = TestClient(main.app)
    register(bob, BOB)
    bob.post("/friends", json={"username": ALICE})

    friend_todos = bob.get(f"/friends/{alice_id}/todos").json()
    assert friend_todos[0]["title"] == "밥 먹기"
    assert friend_todos[0]["my_reaction"] is None
    assert friend_todos[0]["reaction_counts"] == {}

    react = bob.post(f"/todos/{created['id']}/reactions", json={"emoji": "👍"})
    assert react.status_code == 200
    assert react.json() == {"reaction": "👍"}
    friend_todos = bob.get(f"/friends/{alice_id}/todos").json()
    assert friend_todos[0]["my_reaction"] == "👍"
    assert friend_todos[0]["reaction_counts"] == {"👍": 1}

    # 같은 이모지를 다시 누르면 반응이 취소된다
    toggled_off = bob.post(f"/todos/{created['id']}/reactions", json={"emoji": "👍"})
    assert toggled_off.json() == {"reaction": None}
    assert bob.get(f"/friends/{alice_id}/todos").json()[0]["reaction_counts"] == {}


def test_own_todo_list_shows_reactions_left_by_friends(client):
    register(client)
    created = client.post("/todos", json={"title": "밥 먹기"}).json()

    bob = TestClient(main.app)
    register(bob, BOB)
    bob.post("/friends", json={"username": ALICE})

    assert client.get("/todos").json()[0]["reaction_counts"] == {}

    bob.post(f"/todos/{created['id']}/reactions", json={"emoji": "🔥"})
    assert client.get("/todos").json()[0]["reaction_counts"] == {"🔥": 1}


def test_cannot_react_to_own_todo(client):
    register(client)
    created = client.post("/todos", json={"title": "할 일"}).json()
    assert client.post(f"/todos/{created['id']}/reactions", json={"emoji": "👍"}).status_code == 400


def test_non_friend_cannot_view_or_react(client):
    register(client)
    created = client.post("/todos", json={"title": "할 일"}).json()
    alice_id = client.get("/auth/me").json()["id"]

    bob = TestClient(main.app)
    register(bob, BOB)

    assert bob.get(f"/friends/{alice_id}/todos").status_code == 403
    assert bob.post(f"/todos/{created['id']}/reactions", json={"emoji": "👍"}).status_code == 403


def test_invalid_reaction_emoji_is_rejected(client):
    register(client)
    created = client.post("/todos", json={"title": "할 일"}).json()

    bob = TestClient(main.app)
    register(bob, BOB)
    bob.post("/friends", json={"username": ALICE})

    response = bob.post(f"/todos/{created['id']}/reactions", json={"emoji": "🙂"})
    assert response.status_code == 422


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
