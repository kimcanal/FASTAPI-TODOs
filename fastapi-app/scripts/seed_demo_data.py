"""발표/데모용 샘플 데이터를 실제 서버에 채워 넣는다.

데모 계정 2개(20260001, 20260002)를 만들고(비밀번호는 둘 다 0000), 각자 할 일을
몇 개 넣은 뒤 서로 친구로 연결하고 상대방 할 일에 이모지 반응까지 미리 남겨둔다.
친구/반응 기능을 빈 화면이 아니라 실제 데이터가 있는 상태로 바로 보여주기 위한 것.

사용법:
    python scripts/seed_demo_data.py [BASE_URL]   # 기본값 http://127.0.0.1:5001

같은 학번으로 다시 실행해도 안전하다(이미 있으면 로그인만 하고, 할 일이 이미 있으면
추가를 건너뜀) — 단, 반응은 "같은 이모지를 다시 누르면 취소"라서 두 번째 실행부터는
이미 남긴 반응이 꺼질 수 있다. 데모 직전에 한 번만 실행하는 걸 권장한다.
"""

import http.cookiejar
import json
import sys
import urllib.error
import urllib.request

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5001"
DEMO_PASSWORD = "0000"

DEMO_USERS = [
    {
        "username": "20260001",
        "todos": [
            {"title": "팀 발표 자료 준비", "description": "12/9 최종발표 슬라이드", "priority": "high", "due_date": "2026-12-08"},
            {"title": "4L 회고 작성", "description": "", "priority": "normal"},
            {"title": "장바구니 정리", "description": "", "priority": "normal", "completed": True},
        ],
    },
    {
        "username": "20260002",
        "todos": [
            {"title": "알고리즘 과제", "description": "DP 문제풀이", "priority": "high", "due_date": "2026-11-28"},
            {"title": "운동하기", "description": "", "priority": "normal"},
        ],
    },
]


def request(opener: urllib.request.OpenerDirector, method: str, path: str, payload: dict | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with opener.open(req) as res:
            body = res.read()
            return res.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        body = e.read()
        return e.code, (json.loads(body) if body else None)


def seed_user(user: dict) -> tuple[urllib.request.OpenerDirector, list[int]]:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    status, _ = request(opener, "POST", "/auth/register", {"username": user["username"]})
    if status == 409:
        status, _ = request(opener, "POST", "/auth/login", {"username": user["username"], "password": DEMO_PASSWORD})
    if status not in (200, 201):
        raise RuntimeError(f"{user['username']} 가입/로그인 실패 (status={status}) — 비밀번호를 이미 바꿨다면 수동 처리 필요")

    status, existing = request(opener, "GET", "/todos")
    if existing:
        print(f"  {user['username']}: 할 일이 이미 있어서 추가를 건너뜀 ({len(existing)}개)")
        return opener, [t["id"] for t in existing]

    todo_ids = []
    for todo in user["todos"]:
        status, body = request(opener, "POST", "/todos", todo)
        if status != 201:
            raise RuntimeError(f"할 일 추가 실패: {status} {body}")
        todo_ids.append(body["id"])
    print(f"  {user['username']}: 할 일 {len(todo_ids)}개 추가")
    return opener, todo_ids


def main() -> None:
    print(f"대상 서버: {BASE_URL}")
    opener_a, todos_a = seed_user(DEMO_USERS[0])
    opener_b, todos_b = seed_user(DEMO_USERS[1])

    request(opener_a, "POST", "/friends", {"username": DEMO_USERS[1]["username"]})
    print(f"  {DEMO_USERS[0]['username']} <-> {DEMO_USERS[1]['username']} 친구 연결")

    if todos_a:
        request(opener_b, "POST", f"/todos/{todos_a[0]}/reactions", {"emoji": "👍"})
        if len(todos_a) > 1:
            request(opener_b, "POST", f"/todos/{todos_a[1]}/reactions", {"emoji": "🔥"})
    if todos_b:
        request(opener_a, "POST", f"/todos/{todos_b[0]}/reactions", {"emoji": "😮"})
    print("  반응 미리 남겨둠")

    print("\n완료! 데모 계정 (비밀번호는 둘 다 0000):")
    for user in DEMO_USERS:
        print(f"  - {user['username']}")


if __name__ == "__main__":
    main()
