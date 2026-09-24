import hashlib
import hmac
import os
import secrets
import sqlite3
import subprocess
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from markdown_it import MarkdownIt
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.sessions import SessionMiddleware

BASE_DIR = Path(__file__).resolve().parent       # main.py 가 있는 폴더
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR))   # DB·세션 키 저장 위치 (Docker에서는 볼륨 경로)
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = DATA_DIR / "todo.db"
SESSION_SECRET_FILE = DATA_DIR / ".session_secret"
INDEX_FILE = BASE_DIR / "templates" / "index.html"
LOGIN_FILE = BASE_DIR / "templates" / "login.html"
VERSION_FILE = BASE_DIR / "VERSION"
CHANGELOG_FILE = BASE_DIR / "CHANGELOG.md"
RELEASE_NOTES_TEMPLATE = BASE_DIR / "templates" / "release_notes.html"

PBKDF2_ITERATIONS = 200_000


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")      # 여러 프로세스가 동시에 읽고 써도 sqlite가 알아서 직렬화한다
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                completed INTEGER NOT NULL DEFAULT 0
            )
            """
        )


init_db()


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return digest.hex(), salt.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), PBKDF2_ITERATIONS)
    return hmac.compare_digest(digest.hex(), hash_hex)


def _get_or_create_session_secret() -> str:
    env_secret = os.environ.get("SESSION_SECRET")
    if env_secret:
        return env_secret
    if SESSION_SECRET_FILE.exists():
        return SESSION_SECRET_FILE.read_text(encoding="utf-8").strip()
    secret = secrets.token_hex(32)
    SESSION_SECRET_FILE.write_text(secret, encoding="utf-8")
    return secret


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
app.add_middleware(SessionMiddleware, secret_key=_get_or_create_session_secret(), max_age=14 * 24 * 3600)


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


class AuthIn(BaseModel):
    username: str = Field(min_length=3, max_length=30, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=4, max_length=100)


def get_current_user(request: Request) -> sqlite3.Row:
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(401, "로그인이 필요합니다")
    with get_db() as conn:
        user = conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        request.session.clear()
        raise HTTPException(401, "로그인이 필요합니다")
    return user


def _row_to_todo(row: sqlite3.Row) -> TodoItem:
    return TodoItem(id=row["id"], title=row["title"], description=row["description"], completed=bool(row["completed"]))


@app.post("/auth/register", status_code=201)     # 회원가입 — 성공 시 바로 로그인 처리
def register(payload: AuthIn, request: Request) -> dict:
    password_hash, password_salt = hash_password(payload.password)
    with get_db() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, password_salt) VALUES (?, ?, ?)",
                (payload.username, password_hash, password_salt),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "이미 사용 중인 아이디입니다")
        user_id = cur.lastrowid
    request.session["user_id"] = user_id
    return {"username": payload.username}


@app.post("/auth/login")                         # 로그인
def login(payload: AuthIn, request: Request) -> dict:
    with get_db() as conn:
        user = conn.execute(
            "SELECT id, username, password_hash, password_salt FROM users WHERE username = ?",
            (payload.username,),
        ).fetchone()
    if user is None or not verify_password(payload.password, user["password_salt"], user["password_hash"]):
        raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다")
    request.session["user_id"] = user["id"]
    return {"username": user["username"]}


@app.post("/auth/logout")                        # 로그아웃
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@app.get("/auth/me")                             # 현재 로그인한 사용자 확인
def me(user: sqlite3.Row = Depends(get_current_user)) -> dict:
    return {"username": user["username"]}


@app.get("/todos")                               # 목록 조회 (completed로 필터링 가능, 본인 것만)
def get_todos(completed: bool | None = None, user: sqlite3.Row = Depends(get_current_user)) -> list[TodoItem]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, title, description, completed FROM todos WHERE user_id = ? ORDER BY id",
            (user["id"],),
        ).fetchall()
    todos = [_row_to_todo(row) for row in rows]
    if completed is None:
        return todos
    return [t for t in todos if t.completed == completed]


@app.post("/todos", status_code=201)             # 추가 — id 는 DB가 매긴다
def create_todo(payload: TodoIn, user: sqlite3.Row = Depends(get_current_user)) -> TodoItem:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO todos (user_id, title, description, completed) VALUES (?, ?, ?, ?)",
            (user["id"], payload.title, payload.description, int(payload.completed)),
        )
        todo_id = cur.lastrowid
    return TodoItem(id=todo_id, **payload.model_dump())


@app.put("/todos/{todo_id}")                     # 수정 — 본인 소유가 아니면 404
def update_todo(todo_id: int, payload: TodoIn, user: sqlite3.Row = Depends(get_current_user)) -> TodoItem:
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE todos SET title = ?, description = ?, completed = ? WHERE id = ? AND user_id = ?",
            (payload.title, payload.description, int(payload.completed), todo_id, user["id"]),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "To-Do item not found")
    return TodoItem(id=todo_id, **payload.model_dump())


@app.delete("/todos/{todo_id}", status_code=204)  # 삭제 — 본인 소유가 아니면 404
def delete_todo(todo_id: int, user: sqlite3.Row = Depends(get_current_user)) -> None:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM todos WHERE id = ? AND user_id = ?", (todo_id, user["id"]))
        if cur.rowcount == 0:
            raise HTTPException(404, "To-Do item not found")


@app.get("/health", include_in_schema=False)     # 배포/모니터링용 헬스체크 (로그인 불필요)
def health_check() -> dict:
    return {"status": "ok"}


@app.get("/api/version")                         # 현재 버전/빌드 정보 조회 (로그인 불필요)
def get_version() -> dict:
    return {"version": APP_VERSION, "commit": GIT_COMMIT, "build": BUILD_NUMBER}


@app.get("/release-notes", include_in_schema=False)  # 릴리스 노트 화면 (로그인 불필요)
def read_release_notes() -> HTMLResponse:
    changelog_md = (
        CHANGELOG_FILE.read_text(encoding="utf-8")
        if CHANGELOG_FILE.exists()
        else "# Changelog\n\n(작성된 릴리스 노트가 없습니다.)"
    )
    content_html = MarkdownIt().render(changelog_md)
    page = RELEASE_NOTES_TEMPLATE.read_text(encoding="utf-8").replace("<!--CONTENT-->", content_html)
    return HTMLResponse(page)


@app.get("/login", include_in_schema=False)      # 로그인/회원가입 화면
def read_login(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/")
    return FileResponse(LOGIN_FILE, media_type="text/html")


@app.get("/", include_in_schema=False)           # 화면 서빙 — 로그인 안 했으면 로그인 화면으로
def read_root(request: Request):
    if not request.session.get("user_id"):
        return RedirectResponse("/login")
    return FileResponse(INDEX_FILE, media_type="text/html")
