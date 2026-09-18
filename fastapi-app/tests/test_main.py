import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture(autouse=True)
def isolated_todo_file(tmp_path, monkeypatch):
    todo_file = tmp_path / "todo.json"
    todo_file.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(main, "TODO_FILE", todo_file)


client = TestClient(main.app)


def test_version_endpoint_matches_version_file():
    response = client.get("/api/version")
    assert response.status_code == 200
    assert response.json()["version"] == main.APP_VERSION


def test_release_notes_page_renders_html():
    response = client.get("/release-notes")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_todo_crud_roundtrip():
    created = client.post("/todos", json={"title": "우유 사기"}).json()
    assert created["id"] == 1
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


def test_blank_title_is_rejected():
    response = client.post("/todos", json={"title": "   "})
    assert response.status_code == 422
