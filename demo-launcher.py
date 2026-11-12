# -*- coding: utf-8 -*-
"""演示环境的启停器（Windows，纯标准库）。

用法（在 wt-demo 目录下双击 start-demo.bat，或手动执行）：
    python demo-launcher.py            启动后端 5000 + 前端 5173，等端口就绪后开浏览器
    python demo-launcher.py --stop     停掉占用 5000/5173 的进程
    python demo-launcher.py --status   只查状态，不启停

设计要点：
* 两个服务都用 DETACHED_PROCESS 拉起，父进程（这个脚本 / 黑色命令行窗口）退出后
  它们仍然活着，不会像挂在我会话里的后台任务那样被回收。
* 日志分别写 logs/backend.log、logs/frontend.log，出问题直接看文件。
* 启动前清空 HTTP(S)_PROXY 等变量，否则本机请求会被沙箱代理拦成 502。
"""
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = r"D:\Desktop\WebBigHomework(5)\WebBigHomework\.venv\Scripts\python.exe"
FRONTEND = os.path.join(HERE, "frontend")
LOGS = os.path.join(HERE, "logs")
BACKEND_PORT, FRONTEND_PORT = 5000, 5173
DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def log(msg):
    print(msg, flush=True)


def port_pids(port):
    """返回监听该端口的 PID 列表（用 netstat，避免依赖 psutil）。"""
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                             encoding="utf-8", errors="ignore", timeout=20).stdout
    except Exception as exc:  # noqa: BLE001
        log("netstat 失败: %s" % exc)
        return []
    pids = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        local, state, pid = parts[1], parts[-2].upper(), parts[-1]
        if state == "LISTENING" and local.endswith(":%d" % port) and pid.isdigit():
            if pid not in pids:
                pids.append(pid)
    return pids


def http_code(url, timeout=3):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as exc:
        return exc.code  # 401/403 也算服务活着
    except Exception:  # noqa: BLE001
        return 0


def stop():
    found = False
    for port in (BACKEND_PORT, FRONTEND_PORT):
        for pid in port_pids(port):
            found = True
            log("停止端口 %d 的进程 PID %s" % (port, pid))
            subprocess.run(["taskkill", "/PID", pid, "/F", "/T"],
                           capture_output=True, text=True)
    if not found:
        log("5000/5173 上没有监听进程，无需停止。")
    time.sleep(1)
    for port in (BACKEND_PORT, FRONTEND_PORT):
        left = port_pids(port)
        log("端口 %d：%s" % (port, "已释放" if not left else "仍被 %s 占用" % left))


def status():
    for port, path in ((BACKEND_PORT, "/api/v1/health"), (FRONTEND_PORT, "/")):
        code = http_code("http://127.0.0.1:%d%s" % (port, path))
        pids = port_pids(port)
        log("端口 %d: HTTP %s | PID %s" % (port, code or "无响应", ", ".join(pids) or "无"))


def clean_env():
    env = os.environ.copy()
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                "ALL_PROXY", "all_proxy", "FTP_PROXY", "ftp_proxy"):
        env.pop(key, None)
    env["NO_PROXY"] = "*"
    env["no_proxy"] = "*"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def spawn(label, argv, cwd, log_path, env):
    handle = open(log_path, "ab")
    handle.write(("\n===== %s 启动于 %s =====\n" % (
        label, time.strftime("%Y-%m-%d %H:%M:%S"))).encode("utf-8"))
    handle.flush()
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                            stdout=handle, stderr=subprocess.STDOUT,
                            creationflags=DETACHED)
    log("%s 已拉起，PID %d，日志 %s" % (label, proc.pid, log_path))
    return proc.pid


def wait_port(port, seconds=45):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if port_pids(port):
            return True
        time.sleep(0.6)
    return False


def start():
    os.makedirs(LOGS, exist_ok=True)
    env = clean_env()
    env["UPLOAD_ROOT"] = os.path.join(HERE, "instance", "uploads")
    env["DATABASE_PATH"] = os.path.join(HERE, "instance", "app.db")

    for port in (BACKEND_PORT, FRONTEND_PORT):
        busy = port_pids(port)
        if busy:
            log("端口 %d 已被 PID %s 占用，先执行 --stop 再启动。" % (port, ", ".join(busy)))
            return 1

    if not os.path.exists(VENV_PY):
        log("找不到虚拟环境解释器：%s" % VENV_PY)
        return 1

    spawn("后端", [VENV_PY, "-m", "backend.app"], HERE,
          os.path.join(LOGS, "backend.log"), env)
    npm = "npm.cmd" if os.name == "nt" else "npm"
    spawn("前端", ["cmd", "/c", npm, "run", "dev"], FRONTEND,
          os.path.join(LOGS, "frontend.log"), env)

    ok_back = wait_port(BACKEND_PORT)
    ok_front = wait_port(FRONTEND_PORT)
    log("后端 5000: %s" % ("就绪" if ok_back else "45 秒内没起来，看 logs/backend.log"))
    log("前端 5173: %s" % ("就绪" if ok_front else "45 秒内没起来，看 logs/frontend.log"))

    if ok_back and ok_front:
        for _ in range(20):
            if http_code("http://127.0.0.1:%d/" % FRONTEND_PORT) == 200:
                break
            time.sleep(0.5)
        status()
        url = "http://127.0.0.1:%d/" % FRONTEND_PORT
        log("打开浏览器：%s" % url)
        try:
            os.startfile(url)  # noqa: S606  Windows 专用
        except Exception as exc:  # noqa: BLE001
            log("自动打开浏览器失败（不影响使用）：%s" % exc)
        log("账号：学生 24201718 / 24201718，教师 teacher / teacher")
        return 0
    return 1


if __name__ == "__main__":
    arg = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if arg == "--stop":
        stop()
        sys.exit(0)
    if arg == "--status":
        status()
        sys.exit(0)
    sys.exit(start())
