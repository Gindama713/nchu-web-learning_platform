"""课堂部署：一键起后端 + 前端，打印局域网地址并自检。

课堂互测时别组要用你的局域网 IP 访问，本机 127.0.0.1 不算数。
这个脚本同时做三件事：

    1. 打印本机的局域网访问地址（其余组照这个填）
    2. 起后端（0.0.0.0:5000）与前端（0.0.0.0:5173），任一方退出会自动重启
    3. 逐个探测 /who、/help、74181 实验接口，给出能否被互测的结论

用法：
    python scripts/serve_lan.py            # 启动 + 自检，Ctrl+C 一起退出
    python scripts/serve_lan.py --check    # 只自检已经在跑的服务
    python scripts/serve_lan.py --check --base http://127.0.0.1:5173
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

API_PORT = 5000
WEB_PORT = 5173

CHECKS = [
    ("小组信息", "/who"),
    ("接口说明", "/help"),
    ("74181 加法", "/api/v1/alu74181/compute?a=15&b=1&op=add"),
    ("74181 减法", "/api/v1/alu74181/compute?a=1&b=15&op=sub"),
]


def lan_ip():
    """取本机对外网卡的 IPv4；纯本地环境会退化成 127.0.0.1。"""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(url, timeout=5):
    started = time.perf_counter()
    try:
        with OPENER.open(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
            return response.status, body, (time.perf_counter() - started) * 1000
    except urllib.error.HTTPError as failure:
        return failure.code, failure.read().decode("utf-8", "replace"), (time.perf_counter() - started) * 1000
    except Exception as failure:
        return 0, str(failure), (time.perf_counter() - started) * 1000


def wait_ready(url, seconds=40):
    deadline = time.time() + seconds
    while time.time() < deadline:
        status, _, _ = fetch(url, timeout=2)
        if status:
            return True
        time.sleep(0.5)
    return False


def run_checks(base):
    print("\n自检 %s" % base)
    print("-" * 68)
    ok = True
    for label, path in CHECKS:
        status, body, elapsed = fetch(base.rstrip("/") + path)
        detail = ""
        if status == 200:
            try:
                data = json.loads(body).get("data")
                if path == "/who" and isinstance(data, dict):
                    detail = "%s %s" % (data.get("class_name"), data.get("group_no"))
                elif path == "/help" and isinstance(data, dict):
                    detail = "%s 模块 / %s 接口" % (data.get("counts", {}).get("modules"),
                                                data.get("counts", {}).get("endpoints"))
                elif isinstance(data, dict):
                    detail = "%s = %s" % (data.get("expression"), data.get("decimal_result"))
            except json.JSONDecodeError:
                detail = "返回不是 JSON"
        else:
            ok = False
            detail = body[:60].replace("\n", " ")
        print("  %-10s %-42s %s  %5.0fms  %s" % (label, path, status or "连接失败", elapsed, detail))
    print("-" * 68)
    return ok


class Child:
    """带自动重启的子进程包装：进程意外退出就拉起来，课堂演示不至于中断。"""

    def __init__(self, name, command, cwd, shell=False, env=None):
        self.name = name
        self.command = command
        self.cwd = cwd
        self.shell = shell
        self.env = env
        self.process = None
        self.restarts = 0
        self.stopping = False

    def start(self):
        self.process = subprocess.Popen(self.command, cwd=self.cwd, shell=self.shell, env=self.env)
        return self

    def watch(self):
        while not self.stopping:
            if self.process and self.process.poll() is not None:
                self.restarts += 1
                print("[%s] 进程退出（码 %s），第 %d 次自动重启 …" % (self.name, self.process.returncode, self.restarts))
                time.sleep(1.5)
                if not self.stopping:
                    self.start()
            time.sleep(1)

    def stop(self):
        self.stopping = True
        if self.process and self.process.poll() is None:
            self.process.terminate()


def start_stack(ip):
    repo = Path(__file__).resolve().parents[1]
    python = sys.executable
    # 把 APP_ORIGIN 直接设成局域网地址：即使中间有代理改写 Host，
    # 后端的 CSRF 校验仍认可 http://<本机IP>:5173 这个来源。
    api_env = dict(os.environ)
    api_env["APP_ORIGIN"] = "http://%s:%d" % (ip, WEB_PORT)
    api = Child("后端", [python, "-c",
                         "from backend.app import app; app.run(host='0.0.0.0', port=%d, debug=False, use_reloader=False)"
                         % API_PORT], repo, env=api_env)
    web = Child("前端", "npm run dev", repo / "frontend", shell=True)
    api.start()
    web.start()
    for child in (api, web):
        threading.Thread(target=child.watch, daemon=True).start()
    return api, web


def main(argv=None):
    parser = argparse.ArgumentParser(description="课堂部署与可达性自检")
    parser.add_argument("--check", action="store_true", help="只自检，不启动服务")
    parser.add_argument("--base", default="", help="自检用的地址，默认用局域网 IP:5173")
    args = parser.parse_args(argv)

    ip = lan_ip()
    base = args.base or ("http://%s:%d" % (ip, WEB_PORT))

    print("本机局域网地址：%s" % ip)
    print("互测方填这个：%s" % base)
    print("后端：http://%s:%d  前端：http://%s:%d" % (ip, API_PORT, ip, WEB_PORT))

    if args.check:
        return 0 if run_checks(base) else 1

    api, web = start_stack(ip)
    try:
        if not wait_ready("http://127.0.0.1:%d/who" % API_PORT):
            print("后端 40 秒内没有起来，检查依赖是否装好（pip install -r backend/requirements.lock）")
            return 1
        if not wait_ready(base + "/"):
            print("前端 40 秒内没有起来，检查 frontend/node_modules 是否存在")
            return 1
        ok = run_checks(base)
        print("\nCtrl+C 结束服务。互测期间不要关这个窗口。")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止服务 …")
        return 0
    finally:
        api.stop()
        web.stop()
        time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
