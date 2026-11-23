import contextlib
import csv
import hashlib
import hmac
import io
import logging
import os
import secrets
import sqlite3
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from markdown_it import MarkdownIt
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field, ValidationError, field_validator
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
TRASH_RETENTION_DAYS = 7                         # 휴지통 보관 기간 — 이 기간이 지나면 완전히 삭제
FRIEND_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # 0/O, 1/I/L 등 헷갈리는 글자 제외
REACTION_EMOJI = ("👍", "❤️", "🔥", "😂", "😮", "👏")


@contextlib.contextmanager
def get_db():
    # sqlite3.Connection을 `with`로만 쓰면 커밋/롤백만 하고 커넥션은 닫히지 않는다 (ResourceWarning).
    # 여기서 직접 열고 닫아서, 호출부의 `with get_db() as conn:` 모양은 그대로 유지한다.
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")      # 여러 프로세스가 동시에 읽고 써도 sqlite가 알아서 직렬화한다
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _assign_friend_code(conn: sqlite3.Connection, user_id: int) -> str:
    # 충돌 가능성은 희박하지만(6자리, 32종 알파벳), 유니크 인덱스 위반 시 다시 뽑는다
    for _ in range(5):
        code = "".join(secrets.choice(FRIEND_CODE_ALPHABET) for _ in range(6))
        try:
            conn.execute("UPDATE users SET friend_code = ? WHERE id = ?", (code, user_id))
            return code
        except sqlite3.IntegrityError:
            continue
    raise RuntimeError("친구 코드를 생성하지 못했습니다")


def init_db() -> None:
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                friend_code TEXT
            )
            """
        )
        # 기존 DB(볼륨)에 이미 users 테이블이 있던 경우를 위한 마이그레이션
        existing_user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        if "friend_code" not in existing_user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN friend_code TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_friend_code ON users (friend_code)")
        for row in conn.execute("SELECT id FROM users WHERE friend_code IS NULL"):
            _assign_friend_code(conn, row["id"])
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                completed INTEGER NOT NULL DEFAULT 0,
                priority TEXT NOT NULL DEFAULT 'normal',
                due_date TEXT,
                deleted_at TEXT
            )
            """
        )
        # 기존 DB(볼륨)에 이미 todos 테이블이 있던 경우를 위한 마이그레이션
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(todos)")}
        if "priority" not in existing_columns:
            conn.execute("ALTER TABLE todos ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'")
        if "due_date" not in existing_columns:
            conn.execute("ALTER TABLE todos ADD COLUMN due_date TEXT")
        if "deleted_at" not in existing_columns:
            conn.execute("ALTER TABLE todos ADD COLUMN deleted_at TEXT")
        # 휴지통 보관 기간이 지난 소프트 삭제 항목은 완전히 정리한다
        cutoff = (datetime.now(timezone.utc) - timedelta(days=TRASH_RETENTION_DAYS)).isoformat()
        conn.execute("DELETE FROM todos WHERE deleted_at IS NOT NULL AND deleted_at < ?", (cutoff,))
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                last_completed_date TEXT,
                streak INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS friendships (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                friend_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, friend_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todo_reactions (
                todo_id INTEGER NOT NULL REFERENCES todos(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                emoji TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (todo_id, user_id)
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
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

# 액세스 로그를 stdout으로 출력 (#9) — Docker가 컨테이너 로그로 저장하고 Alloy가 Loki로 전송한다
access_logger = logging.getLogger("custom.access")
access_logger.setLevel(logging.INFO)
access_logger.addHandler(logging.StreamHandler(sys.stdout))
access_logger.propagate = False                  # 상위 로거로 전파되어 두 번 찍히는 것을 방지

# uvicorn 기본 액세스 로그는 끈다 — 켜 두면 요청 1번에 로그가 2줄씩 남아 Loki 집계가 2배가 됨
logging.getLogger("uvicorn.access").disabled = True


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    client = request.client.host if request.client else "-"
    # 형식: IP - "METHOD PATH HTTP/1.1" 상태코드 응답시간 → Grafana LogQL pattern이 이 형식을 파싱
    access_logger.info(
        f'{client} - "{request.method} {request.url.path} HTTP/1.1" '
        f'{response.status_code} {duration:.3f}s'
    )
    return response


class TodoIn(BaseModel):                         # 클라이언트가 보내는 데이터 (id 없음)
    title: str = Field(min_length=1, max_length=100)
    description: str = ""
    completed: bool = False
    priority: Literal["high", "normal"] = "normal"
    due_date: date | None = None

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


class TrashedTodoItem(TodoItem):                 # 휴지통 목록용 — 삭제 시각 포함
    deleted_at: str


class AuthIn(BaseModel):
    username: str = Field(min_length=3, max_length=30, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=4, max_length=100)


class FriendCodeIn(BaseModel):
    friend_code: str = Field(min_length=6, max_length=6)


class FriendOut(BaseModel):
    id: int
    username: str


class FriendTodoItem(TodoItem):                  # 친구 할 일 목록용 — 이모지 반응 포함
    reaction_counts: dict[str, int]
    my_reaction: str | None


class ReactionIn(BaseModel):
    emoji: Literal["👍", "❤️", "🔥", "😂", "😮", "👏"]


def get_current_user(request: Request) -> sqlite3.Row:
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(401, "로그인이 필요합니다")
    with get_db() as conn:
        user = conn.execute("SELECT id, username, friend_code FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        request.session.clear()
        raise HTTPException(401, "로그인이 필요합니다")
    return user


def _row_to_todo(row: sqlite3.Row) -> TodoItem:
    return TodoItem(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        completed=bool(row["completed"]),
        priority=row["priority"],
        due_date=row["due_date"],
    )


def _recompute_streak(conn: sqlite3.Connection, user_id: int) -> int:
    # 오늘 할 일을 전부 끝냈으면 스트릭 +1 (단, 하루 한 번만), 하루 이상 비면 스트릭은 끊긴다
    todos = conn.execute("SELECT completed FROM todos WHERE user_id = ?", (user_id,)).fetchall()
    all_done_today = len(todos) > 0 and all(row["completed"] for row in todos)

    stats = conn.execute(
        "SELECT last_completed_date, streak FROM user_stats WHERE user_id = ?", (user_id,)
    ).fetchone()
    today = date.today()
    last_date = date.fromisoformat(stats["last_completed_date"]) if stats and stats["last_completed_date"] else None
    streak = stats["streak"] if stats else 0

    if all_done_today and last_date != today:
        if last_date == today - timedelta(days=1):
            streak += 1
        else:
            streak = 1
        last_date = today
    elif not all_done_today and last_date is not None and last_date < today - timedelta(days=1):
        streak = 0

    conn.execute(
        """
        INSERT INTO user_stats (user_id, last_completed_date, streak) VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET last_completed_date = excluded.last_completed_date, streak = excluded.streak
        """,
        (user_id, last_date.isoformat() if last_date else None, streak),
    )
    return streak


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
        _assign_friend_code(conn, user_id)
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
    return {"id": user["id"], "username": user["username"], "friend_code": user["friend_code"]}


@app.get("/todos")                               # 목록 조회 (completed/검색/정렬 가능, 본인 것만)
def get_todos(
    completed: bool | None = None,
    q: str | None = None,
    sort: Literal["due_date", "priority"] | None = None,
    user: sqlite3.Row = Depends(get_current_user),
) -> list[TodoItem]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, title, description, completed, priority, due_date FROM todos "
            "WHERE user_id = ? AND deleted_at IS NULL ORDER BY id",
            (user["id"],),
        ).fetchall()
    todos = [_row_to_todo(row) for row in rows]
    if completed is not None:
        todos = [t for t in todos if t.completed == completed]
    needle = q.strip().lower() if q else ""
    if needle:
        todos = [t for t in todos if needle in t.title.lower() or needle in t.description.lower()]
    if sort == "due_date":
        todos.sort(key=lambda t: (t.due_date is None, t.due_date))
    elif sort == "priority":
        order = {"high": 0, "normal": 1}
        todos.sort(key=lambda t: order[t.priority])
    return todos


@app.get("/todos/trash")                         # 휴지통 조회 (본인 것만, 삭제 최신순)
def get_trash(user: sqlite3.Row = Depends(get_current_user)) -> list[TrashedTodoItem]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, title, description, completed, priority, due_date, deleted_at FROM todos "
            "WHERE user_id = ? AND deleted_at IS NOT NULL ORDER BY deleted_at DESC",
            (user["id"],),
        ).fetchall()
    return [
        TrashedTodoItem(**_row_to_todo(row).model_dump(), deleted_at=row["deleted_at"])
        for row in rows
    ]


CSV_FIELDS = ["title", "description", "completed", "priority", "due_date"]


@app.get("/todos/export")                        # CSV로 내보내기 — 본인 것만, 휴지통 제외
def export_todos(user: sqlite3.Row = Depends(get_current_user)) -> StreamingResponse:
    todos = get_todos(user=user)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for todo in todos:
        writer.writerow({
            "title": todo.title,
            "description": todo.description,
            "completed": "true" if todo.completed else "false",
            "priority": todo.priority,
            "due_date": todo.due_date.isoformat() if todo.due_date else "",
        })
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=todos.csv"},
    )


@app.post("/todos/import", status_code=201)      # CSV 가져오기 — 유효한 행만 추가, 기존 항목은 그대로 둠
async def import_todos(file: UploadFile = File(...), user: sqlite3.Row = Depends(get_current_user)) -> dict:
    content = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    added = 0
    skipped = 0
    with get_db() as conn:
        for row in reader:
            completed_raw = str(row.get("completed") or "").strip().lower()
            due_date_raw = (row.get("due_date") or "").strip()
            try:
                payload = TodoIn(
                    title=row.get("title") or "",
                    description=row.get("description") or "",
                    completed=completed_raw in ("1", "true", "yes"),
                    priority=(row.get("priority") or "normal").strip().lower(),
                    due_date=due_date_raw or None,
                )
            except ValidationError:
                skipped += 1
                continue
            conn.execute(
                "INSERT INTO todos (user_id, title, description, completed, priority, due_date) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    user["id"], payload.title, payload.description, int(payload.completed),
                    payload.priority, payload.due_date.isoformat() if payload.due_date else None,
                ),
            )
            added += 1
    return {"added": added, "skipped": skipped}


@app.get("/stats")                               # 연속 완료 스트릭 조회 (본인 것만)
def get_stats(user: sqlite3.Row = Depends(get_current_user)) -> dict:
    with get_db() as conn:
        streak = _recompute_streak(conn, user["id"])
    return {"streak": streak}


@app.get("/friends")                             # 친구 목록 조회
def list_friends(user: sqlite3.Row = Depends(get_current_user)) -> list[FriendOut]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT u.id, u.username FROM friendships f JOIN users u ON u.id = f.friend_id "
            "WHERE f.user_id = ? ORDER BY u.username",
            (user["id"],),
        ).fetchall()
    return [FriendOut(id=row["id"], username=row["username"]) for row in rows]


@app.post("/friends", status_code=201)           # 친구 코드로 추가 — 요청/수락 없이 바로 양방향 연결
def add_friend(payload: FriendCodeIn, user: sqlite3.Row = Depends(get_current_user)) -> FriendOut:
    code = payload.friend_code.strip().upper()
    with get_db() as conn:
        friend = conn.execute("SELECT id, username FROM users WHERE friend_code = ?", (code,)).fetchone()
        if friend is None:
            raise HTTPException(404, "친구 코드를 찾을 수 없습니다")
        if friend["id"] == user["id"]:
            raise HTTPException(400, "본인을 친구로 추가할 수 없습니다")
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO friendships (user_id, friend_id, created_at) VALUES (?, ?, ?)",
            (user["id"], friend["id"], now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO friendships (user_id, friend_id, created_at) VALUES (?, ?, ?)",
            (friend["id"], user["id"], now),
        )
    return FriendOut(id=friend["id"], username=friend["username"])


@app.delete("/friends/{friend_id}", status_code=204)   # 친구 삭제 — 양방향 모두 해제
def remove_friend(friend_id: int, user: sqlite3.Row = Depends(get_current_user)) -> None:
    with get_db() as conn:
        conn.execute("DELETE FROM friendships WHERE user_id = ? AND friend_id = ?", (user["id"], friend_id))
        conn.execute("DELETE FROM friendships WHERE user_id = ? AND friend_id = ?", (friend_id, user["id"]))


@app.get("/friends/{friend_id}/todos")            # 친구의 할 일 조회 (읽기 전용, 친구가 아니면 403)
def get_friend_todos(friend_id: int, user: sqlite3.Row = Depends(get_current_user)) -> list[FriendTodoItem]:
    with get_db() as conn:
        is_friend = conn.execute(
            "SELECT 1 FROM friendships WHERE user_id = ? AND friend_id = ?", (user["id"], friend_id)
        ).fetchone()
        if is_friend is None:
            raise HTTPException(403, "친구가 아닙니다")
        todo_rows = conn.execute(
            "SELECT id, title, description, completed, priority, due_date FROM todos "
            "WHERE user_id = ? AND deleted_at IS NULL ORDER BY id",
            (friend_id,),
        ).fetchall()
        items = []
        for row in todo_rows:
            reaction_rows = conn.execute(
                "SELECT emoji, user_id FROM todo_reactions WHERE todo_id = ?", (row["id"],)
            ).fetchall()
            counts: dict[str, int] = {}
            my_reaction = None
            for reaction in reaction_rows:
                counts[reaction["emoji"]] = counts.get(reaction["emoji"], 0) + 1
                if reaction["user_id"] == user["id"]:
                    my_reaction = reaction["emoji"]
            items.append(FriendTodoItem(
                **_row_to_todo(row).model_dump(), reaction_counts=counts, my_reaction=my_reaction,
            ))
    return items


@app.post("/todos/{todo_id}/reactions")          # 친구 할 일에 이모지 반응 토글 (같은 이모지 다시 누르면 취소)
def react_to_todo(todo_id: int, payload: ReactionIn, user: sqlite3.Row = Depends(get_current_user)) -> dict:
    with get_db() as conn:
        todo = conn.execute(
            "SELECT user_id FROM todos WHERE id = ? AND deleted_at IS NULL", (todo_id,)
        ).fetchone()
        if todo is None:
            raise HTTPException(404, "할 일을 찾을 수 없습니다")
        owner_id = todo["user_id"]
        if owner_id == user["id"]:
            raise HTTPException(400, "본인 할 일에는 반응을 남길 수 없습니다")
        is_friend = conn.execute(
            "SELECT 1 FROM friendships WHERE user_id = ? AND friend_id = ?", (user["id"], owner_id)
        ).fetchone()
        if is_friend is None:
            raise HTTPException(403, "친구가 아닙니다")
        existing = conn.execute(
            "SELECT emoji FROM todo_reactions WHERE todo_id = ? AND user_id = ?", (todo_id, user["id"])
        ).fetchone()
        if existing is not None and existing["emoji"] == payload.emoji:
            conn.execute(
                "DELETE FROM todo_reactions WHERE todo_id = ? AND user_id = ?", (todo_id, user["id"])
            )
            reacted = None
        else:
            conn.execute(
                "INSERT INTO todo_reactions (todo_id, user_id, emoji, created_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(todo_id, user_id) DO UPDATE SET emoji = excluded.emoji, created_at = excluded.created_at",
                (todo_id, user["id"], payload.emoji, datetime.now(timezone.utc).isoformat()),
            )
            reacted = payload.emoji
    return {"reaction": reacted}


@app.post("/todos", status_code=201)             # 추가 — id 는 DB가 매긴다
def create_todo(payload: TodoIn, user: sqlite3.Row = Depends(get_current_user)) -> TodoItem:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO todos (user_id, title, description, completed, priority, due_date) VALUES (?, ?, ?, ?, ?, ?)",
            (
                user["id"], payload.title, payload.description, int(payload.completed),
                payload.priority, payload.due_date.isoformat() if payload.due_date else None,
            ),
        )
        todo_id = cur.lastrowid
    return TodoItem(id=todo_id, **payload.model_dump())


@app.put("/todos/{todo_id}")                     # 수정 — 본인 소유가 아니면 404
def update_todo(todo_id: int, payload: TodoIn, user: sqlite3.Row = Depends(get_current_user)) -> TodoItem:
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE todos SET title = ?, description = ?, completed = ?, priority = ?, due_date = ? "
            "WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (
                payload.title, payload.description, int(payload.completed), payload.priority,
                payload.due_date.isoformat() if payload.due_date else None, todo_id, user["id"],
            ),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "To-Do item not found")
    return TodoItem(id=todo_id, **payload.model_dump())


@app.delete("/todos/{todo_id}", status_code=204)  # 휴지통으로 이동(소프트 삭제) — 본인 소유가 아니면 404
def delete_todo(todo_id: int, user: sqlite3.Row = Depends(get_current_user)) -> None:
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE todos SET deleted_at = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (datetime.now(timezone.utc).isoformat(), todo_id, user["id"]),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "To-Do item not found")


@app.post("/todos/{todo_id}/restore")         # 휴지통에서 복원 — 완료 여부는 미완료로 초기화됨
def restore_todo(todo_id: int, user: sqlite3.Row = Depends(get_current_user)) -> TodoItem:
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE todos SET deleted_at = NULL, completed = 0 WHERE id = ? AND user_id = ? AND deleted_at IS NOT NULL",
            (todo_id, user["id"]),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "복원할 수 있는 삭제된 할 일을 찾을 수 없습니다")
        row = conn.execute(
            "SELECT id, title, description, completed, priority, due_date FROM todos WHERE id = ?",
            (todo_id,),
        ).fetchone()
    return _row_to_todo(row)


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
