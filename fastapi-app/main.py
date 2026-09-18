import json
import os
import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from markdown_it import MarkdownIt
from pydantic import BaseModel, Field, field_validator

BASE_DIR = Path(__file__).resolve().parent       # main.py 가 있는 폴더
TODO_FILE = BASE_DIR / "todo.json"
INDEX_FILE = BASE_DIR / "templates" / "index.html"
VERSION_FILE = BASE_DIR / "VERSION"
CHANGELOG_FILE = BASE_DIR / "CHANGELOG.md"
RELEASE_NOTES_TEMPLATE = BASE_DIR / "templates" / "release_notes.html"

if not TODO_FILE.exists():                       # 없으면 빈 목록으로 만들어 둔다
    TODO_FILE.write_text("[]", encoding="utf-8")


def _detect_git_commit() -> str:
    commit = os.environ.get("GIT_COMMIT")        # Jenkins가 자동으로 채워주는 환경변수
    if commit:
        return commit[:7]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=BASE_DIR, capture_output=True, text=True, timeout=2, check=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


APP_VERSION = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.exists() else "0.0.0"
GIT_COMMIT = _detect_git_commit()
BUILD_NUMBER = os.environ.get("BUILD_NUMBER", "local")   # Jenkins가 자동으로 채워주는 환경변수

app = FastAPI(title="To-Do List API")


class TodoIn(BaseModel):                         # 클라이언트가 보내는 데이터 (id 없음)
    title: str = Field(min_length=1, max_length=100)
    description: str = ""
    completed: bool = False

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        # [수정] "   " 처럼 공백만 있는 제목이 min_length 검사를 통과해 저장되던 결함
        stripped = value.strip()
        if not stripped:
            raise ValueError("제목은 공백만으로 이루어질 수 없습니다")
        return stripped


class TodoItem(TodoIn):                          # 서버가 돌려주는 데이터 (id 있음)
    id: int


def load_todos() -> list[TodoItem]:
    raw = TODO_FILE.read_text(encoding="utf-8") if TODO_FILE.exists() else "[]"
    return [TodoItem(**t) for t in json.loads(raw)]


def save_todos(todos: list[TodoItem]) -> None:
    data = json.dumps([t.model_dump() for t in todos], indent=2, ensure_ascii=False)
    TODO_FILE.write_text(data, encoding="utf-8")


def find_index(todos: list[TodoItem], todo_id: int) -> int:
    for i, todo in enumerate(todos):
        if todo.id == todo_id:
            return i
    raise HTTPException(404, "To-Do item not found")


@app.get("/todos")                               # 목록 조회 (completed로 필터링 가능)
def get_todos(completed: bool | None = None) -> list[TodoItem]:
    todos = load_todos()
    if completed is None:
        return todos
    return [t for t in todos if t.completed == completed]


@app.post("/todos", status_code=201)             # 추가 — id 는 서버가 매긴다
def create_todo(payload: TodoIn) -> TodoItem:
    todos = load_todos()
    new_id = max((t.id for t in todos), default=0) + 1
    todo = TodoItem(id=new_id, **payload.model_dump())
    save_todos(todos + [todo])
    return todo


@app.put("/todos/{todo_id}")                     # 수정
def update_todo(todo_id: int, payload: TodoIn) -> TodoItem:
    todos = load_todos()
    todo = TodoItem(id=todo_id, **payload.model_dump())
    todos[find_index(todos, todo_id)] = todo
    save_todos(todos)
    return todo


@app.delete("/todos/{todo_id}", status_code=204)  # 삭제
def delete_todo(todo_id: int) -> None:
    todos = load_todos()
    del todos[find_index(todos, todo_id)]
    save_todos(todos)


@app.get("/api/version")                         # 현재 버전/빌드 정보 조회
def get_version() -> dict:
    return {"version": APP_VERSION, "commit": GIT_COMMIT, "build": BUILD_NUMBER}


@app.get("/release-notes", include_in_schema=False)  # 릴리스 노트 화면
def read_release_notes() -> HTMLResponse:
    changelog_md = (
        CHANGELOG_FILE.read_text(encoding="utf-8")
        if CHANGELOG_FILE.exists()
        else "# Changelog\n\n(작성된 릴리스 노트가 없습니다.)"
    )
    content_html = MarkdownIt().render(changelog_md)
    page = RELEASE_NOTES_TEMPLATE.read_text(encoding="utf-8").replace("<!--CONTENT-->", content_html)
    return HTMLResponse(page)


@app.get("/", include_in_schema=False)           # 화면 서빙
def read_root() -> FileResponse:
    return FileResponse(INDEX_FILE, media_type="text/html")