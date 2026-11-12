"""验证 2026-11-12 两处并发修复的行为没有退化。

1) 访问日志：请求后不再立刻落库，但导出前必须把缓冲刷进去，导出结果要包含刚发生的访问。
2) 会话心跳：只在距上次续期超过 60 秒时才写 session；连续请求不会每次都写。

用法：
    python scripts/verify_session_log_20261112.py
    python scripts/verify_session_log_20261112.py --base http://127.0.0.1:5001 --db <库路径>
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

DEFAULT_BASE = "http://127.0.0.1:5000"
DEFAULT_DB = r"D:/Desktop/WebBigHomework/wt-demo/instance/app.db"

failures: list[str] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  {detail}" if detail != "" else ""))
    if not ok:
        failures.append(name)


def opener() -> urllib.request.OpenerDirector:
    # 明确绕开系统代理，否则 127.0.0.1 也会走沙箱代理
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(opener_, base, path, method="GET", payload=None, cookie=None, csrf=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(base + path, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    request.add_header("Origin", "http://127.0.0.1:5173")
    if cookie:
        request.add_header("Cookie", cookie)
    if csrf:
        request.add_header("X-CSRF-Token", csrf)
    try:
        with opener_.open(request, timeout=20) as response:
            return response.status, response.read().decode("utf-8", "replace"), response.headers.get_all("Set-Cookie") or []
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace"), []


def session_row(db_path, token):
    import hashlib

    digest = hashlib.sha256(token.encode()).hexdigest()
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return db.execute("SELECT id,last_seen_at,expires_at FROM session WHERE token_hash=?",
                          (digest,)).fetchone()
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--db", default=DEFAULT_DB)
    args = parser.parse_args()

    op = opener()
    status, body, cookies = call(op, args.base, "/api/v1/auth/login", "POST",
                                 {"student_no": "teacher", "password": "teacher"})
    if status != 200:
        print(f"登录失败：{status} {body[:200]}")
        return 1
    cookie_header = "; ".join(item.split(";", 1)[0] for item in cookies)
    token = [item for item in cookie_header.split("; ") if item.startswith("cpu_session=")][0].split("=", 1)[1]
    csrf = json.loads(body)["data"]["csrf_token"]
    row = session_row(args.db, token)
    check("登录后能查到本次会话", row is not None, f"session id={row[0] if row else None}")

    # ---- 会话心跳限频 ----
    db = sqlite3.connect(args.db, timeout=10)
    stale = (datetime.now(UTC) - timedelta(hours=1)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    db.execute("UPDATE session SET last_seen_at=? WHERE id=?", (stale, row[0]))
    db.commit()
    db.close()
    call(op, args.base, "/api/v1/courses?page=1&page_size=5", cookie=cookie_header)
    after_first = session_row(args.db, token)[1]
    check("心跳过期后，一次请求会把 last_seen_at 续上", after_first > stale, after_first)
    time.sleep(0.3)
    call(op, args.base, "/api/v1/courses?page=1&page_size=5", cookie=cookie_header)
    after_second = session_row(args.db, token)[1]
    check("60 秒内的下一次请求不再写 session（限频生效）", after_second == after_first,
          f"{after_first} -> {after_second}")

    # ---- 访问日志攒批 + 导出前刷盘 ----
    for _ in range(3):
        call(op, args.base, "/api/v1/courses?page=1&page_size=5", cookie=cookie_header)
    status, body, _ = call(op, args.base, "/api/v1/logs/access?page=1&page_size=5",
                           cookie=cookie_header)
    check("教师可导出访问日志", status == 200, f"status={status}")
    rows = json.loads(body)["data"] if status == 200 else []
    check("导出结果包含刚发生的访问（缓冲已刷盘）",
          any("/api/v1/courses" in (item.get("path") or "") for item in rows),
          f"最新 {len(rows)} 条：{[item.get('path') for item in rows][:3]}")
    newest = rows[0]["at"] if rows else None
    if newest:
        age = (datetime.now(UTC) - datetime.fromisoformat(newest.replace("Z", "+00:00"))).total_seconds()
        check("最新一条访问日志是刚刚写入的", age < 60, f"{age:.0f} 秒前")

    # 导出接口自身不该被记进日志，否则越导出越多
    check("导出接口自身不写入访问日志",
          not any("/api/v1/logs/" in (item.get("path") or "") for item in rows), "")

    print(f"\n汇总：失败 {len(failures)} 项" + (f" -> {failures}" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
