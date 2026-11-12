"""并发读写下的 SQLITE_BUSY 频率探测（2026-11-12）。

背景：UI 深测时 `/api/v1/courses` 与 `/api/v1/courses/16/knowledge-graph` 偶发 503，
返回体 code=DB_BUSY。`backend/shared/db.py:16-19` 设了 busy_timeout=5000，
但库是 `journal_mode=delete`（回滚日志）：读事务持 SHARED 锁时，写事务从
BEGIN IMMEDIATE 提升到 EXCLUSIVE 会立刻拿到 SQLITE_BUSY，busy handler 不重试。
本脚本用「只读流量 + 空写事务」把这件事量化，默认不做任何数据改动。

写侧刻意用 `PUT /courses/16/me/seat` 传本人当前座位：`seat_swap.py:200` 命中
`mine.group_no/seat_no` 相同就提前返回，只取写锁、不写行、不落审计。

用法：
    python scripts/db_busy_probe_20261112.py            # 默认 12 秒
    python scripts/db_busy_probe_20261112.py --seconds 30 --readers 8 --writers 2
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter

BASE = "http://127.0.0.1:5000"


def _opener():
    # 明确绕开系统代理：本机 HTTP_PROXY 指向沙箱代理，会把 127.0.0.1 也劫持掉
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))

def _request(opener, path, method="GET", payload=None, cookie=None, csrf=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    req.add_header("Origin", "http://127.0.0.1:5173")
    if cookie:
        req.add_header("Cookie", cookie)
    if csrf:
        req.add_header("X-CSRF-Token", csrf)
    try:
        with opener.open(req, timeout=20) as response:
            body = response.read().decode("utf-8", "replace")
            return response.status, body, response.headers.get_all("Set-Cookie") or []
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace"), error.headers.get_all("Set-Cookie") or []
    except Exception as error:  # 网络层失败也算一次观测
        return 0, f"{type(error).__name__}: {error}", []


def login(opener, number, password):
    status, body, cookies = _request(opener, "/api/v1/auth/login", "POST",
                                     {"student_no": number, "password": password})
    if status != 200:
        raise SystemExit(f"登录失败 {number}: {status} {body[:200]}")
    cookie = "; ".join(item.split(";", 1)[0] for item in cookies)
    csrf = json.loads(body)["data"]["csrf_token"]
    return cookie, csrf


def main() -> int:
    global BASE
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=12.0)
    parser.add_argument("--readers", type=int, default=6)
    parser.add_argument("--writers", type=int, default=2)
    parser.add_argument("--course", type=int, default=16)
    parser.add_argument("--seat", default="10,8", help="写侧用的本人座位 group_no,seat_no")
    parser.add_argument("--base", default=BASE, help="后端地址，默认 http://127.0.0.1:5000")
    parser.add_argument("--write-interval", type=float, default=0.0,
                        help="每个写线程两次写之间的间隔秒数；0 表示不歇（压满）")
    parser.add_argument("--read-interval", type=float, default=0.0,
                        help="每个读线程两次请求之间的间隔秒数，用来模拟学生的操作间隔")
    args = parser.parse_args()

    BASE = args.base.rstrip("/")

    opener = _opener()
    teacher_cookie, _ = login(opener, "teacher", "teacher")
    student_cookie, student_csrf = login(opener, "24201718", "24201718")
    group_no, seat_no = (int(x) for x in args.seat.split(","))

    read_paths = [
        f"/api/v1/courses?page=1&page_size=100",
        f"/api/v1/courses/{args.course}/knowledge-graph",
        f"/api/v1/attendance-tasks/53/seats",
        f"/api/v1/courses/{args.course}/attendance-tasks",
    ]
    counts = Counter()
    busy_bodies = Counter()
    latencies = []
    lock = threading.Lock()
    stop = threading.Event()
    errors: list[str] = []

    def reader(index: int):
        local = Counter()
        local_lat = []
        opts = _opener()
        path = read_paths[index % len(read_paths)]
        while not stop.is_set():
            started = time.perf_counter()
            status, body, _ = _request(opts, path, cookie=teacher_cookie)
            local_lat.append((time.perf_counter() - started) * 1000)
            local[f"GET {status}"] += 1
            if status == 503:
                try:
                    code = json.loads(body).get("error", {}).get("code", "?")
                except Exception:
                    code = "unparsable"
                local[f"503 {code} {path}"] += 1
                with lock:
                    busy_bodies[f"{code} {path}"] += 1
            elif status >= 400 and status != 401:
                with lock:
                    errors.append(f"{status} {path} {body[:120]}")
            if args.read_interval > 0:
                time.sleep(args.read_interval)
        with lock:
            counts.update(local)
            latencies.extend(local_lat)

    def writer():
        local = Counter()
        opts = _opener()
        while not stop.is_set():
            status, body, _ = _request(
                opts, f"/api/v1/courses/{args.course}/me/seat", "PUT",
                {"group_no": group_no, "seat_no": seat_no},
                cookie=student_cookie, csrf=student_csrf)
            local[f"PUT {status}"] += 1
            if status >= 400:
                try:
                    code = json.loads(body).get("error", {}).get("code", "?")
                except Exception:
                    code = "unparsable"
                with lock:
                    busy_bodies[f"PUT {status} {code}"] += 1
            if args.write_interval > 0:
                time.sleep(args.write_interval)
        with lock:
            counts.update(local)

    threads = [threading.Thread(target=reader, args=(i,), daemon=True) for i in range(args.readers)]
    threads += [threading.Thread(target=writer, daemon=True) for _ in range(args.writers)]
    for thread in threads:
        thread.start()
    time.sleep(args.seconds)
    stop.set()
    for thread in threads:
        thread.join(timeout=20)

    total = sum(counts.values())
    bad = sum(value for key, value in counts.items()
              if key.split()[1].isdigit() and int(key.split()[1]) >= 400)
    latencies.sort()

    def pct(p):
        if not latencies:
            return 0.0
        k = min(len(latencies) - 1, int(len(latencies) * p))
        return latencies[k]

    print(f"时长 {args.seconds}s  读 {args.readers} 线程 / 写 {args.writers} 线程")
    print(f"总请求 {total}，失败(≥400) {bad}，失败率 {bad / total * 100:.2f}%" if total else "无请求")
    print(f"延迟 p50 {pct(0.50):.1f}ms  p95 {pct(0.95):.1f}ms  p99 {pct(0.99):.1f}ms  max {pct(0.999):.1f}ms")
    print("状态分布：")
    for key, value in sorted(counts.items()):
        print(f"  {key}: {value}")
    if busy_bodies:
        print("失败明细：")
        for key, value in busy_bodies.most_common():
            print(f"  {key}: {value}")
    if errors:
        print("其它 4xx/5xx 样例：")
        for line in errors[:5]:
            print("  " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
