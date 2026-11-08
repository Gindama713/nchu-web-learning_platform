"""Repeatable T005 / NF-UI checks in installed Chrome and Edge.

Uses a temporary database, the real migration runner, HTTP API and Vue page.
Only initial admin/teacher accounts are bootstrapped; passwords stay in memory.
Requires backend dependencies, Playwright and frontend/node_modules. No browser
download is needed. Run from the repository root; ports 5000/5173 must be free.
"""

import argparse
import json
import platform
import secrets
import socket
import subprocess
import sys
import threading
import time
import traceback
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from http.cookiejar import CookieJar
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import expect, sync_playwright
from werkzeug.security import generate_password_hash
from werkzeug.serving import WSGIRequestHandler, make_server

from backend.app import create_app
from backend.shared.db import connect, migrate

ORIGIN = "http://127.0.0.1:5173"


class QuietHandler(WSGIRequestHandler):
    def log(self, *_args, **_kwargs):
        pass


class Api:
    def __init__(self):
        self.http = build_opener(HTTPCookieProcessor(CookieJar()))
        self.csrf = ""

    def call(self, method, path, data=None, status=200):
        headers = {"Origin": ORIGIN, "X-CSRF-Token": self.csrf}
        body = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data).encode()
        request = Request("http://127.0.0.1:5000/api/v1"+path, body, headers, method=method)
        with self.http.open(request, timeout=15) as response:
            assert response.status == status, f"Unexpected status for {method} {path}"
            return json.load(response)["data"] if status != 204 else None

    def login(self, number, password):
        data = self.call("POST", "/auth/login", {"student_no": number, "password": password})
        self.csrf = data["csrf_token"]
        return data["user"]["id"]


@contextmanager
def servers():
    for port in (5000, 5173):
        with closing(socket.socket()) as probe:
            probe.bind(("127.0.0.1", port))
    with TemporaryDirectory(prefix="t005-browser-") as directory:
        database = Path(directory)/"course.db"
        password = secrets.token_urlsafe(24)
        migrate(database)
        with closing(connect(database)) as db:
            now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            for number, role in (("T005ADMIN", "admin"), ("T005TEACH", "teacher")):
                db.execute("INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) "
                           "VALUES(?,?,?,?,1,?,?)", (number, number, generate_password_hash(password), role, now, now))
        app = create_app({"DATABASE_PATH": str(database), "APP_ORIGIN": ORIGIN,
                          "APP_ENV": "development", "SECRET_KEY": secrets.token_hex(32)})
        server = make_server("127.0.0.1", 5000, app, threaded=True, request_handler=QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        vite = None
        try:
            with (Path(directory)/"vite.log").open("w", encoding="utf-8") as log:
                vite = subprocess.Popen(["node", str(ROOT/"frontend/node_modules/vite/bin/vite.js"),
                                         "--host", "127.0.0.1", "--port", "5173", "--strictPort"],
                                        cwd=ROOT/"frontend", stdout=log, stderr=subprocess.STDOUT,
                                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
                deadline = time.monotonic()+30
                while True:
                    if vite.poll() is not None:
                        raise RuntimeError("Vite failed to start; install frontend dependencies and free port 5173")
                    try:
                        with urlopen(ORIGIN, timeout=1) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError("Vite startup timed out") from None
                        time.sleep(0.1)
                yield password
        finally:
            if vite is not None and vite.poll() is None:
                vite.terminate()
                vite.wait(timeout=10)
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()


def login(page, number, password):
    page.goto(ORIGIN)
    page.get_by_label("学号", exact=True).fill(number)
    page.get_by_label("密码", exact=True).fill(password)
    page.get_by_role("button", name="登录", exact=True).click()
    expect(page.locator(".knowledge-module")).to_have_attribute("aria-busy", "false")
    expect(page.locator(".knowledge-module .knowledge-course")).to_be_visible()
    return page.locator(".knowledge-module")


def verify_browser(playwright, channel, password, output):
    checks = []
    admin, teacher, student = Api(), Api(), Api()
    admin.login("T005ADMIN", password)
    teacher_id = teacher.login("T005TEACH", password)
    number = "T005CHROME" if channel == "chrome" else "T005EDGE1"
    student.call("POST", "/auth/register", {"student_no": number, "name": number, "password": password}, 201)
    student_id = student.login(number, password)
    course_id = admin.call("POST", "/courses", {"title": "T005 "+channel, "teacher_id": teacher_id}, 201)["id"]
    teacher.call("POST", f"/courses/{course_id}/members", {"user_id": student_id, "member_role": "student"}, 201)
    browser = playwright.chromium.launch(channel=channel, headless=True)
    contexts = []
    try:
        errors = []
        for _ in range(2):
            contexts.append(browser.new_context(viewport={"width": 1440, "height": 1000}))
        teacher_page, student_page = [context.new_page() for context in contexts]
        for page in (teacher_page, student_page):
            page.on("pageerror", lambda error: errors.append(str(error)))
        t = login(teacher_page, "T005TEACH", password)
        t.get_by_label("当前课程").select_option(str(course_id))
        t.get_by_label("新章节名称").fill("CPU")
        t.get_by_role("button", name="新增章节", exact=True).click()
        expect(t.get_by_role("button", name="CPU", exact=True)).to_be_visible()
        t.get_by_label("新章节名称").fill("ALU")
        t.get_by_role("button", name="新增章节", exact=True).click()
        alu = t.locator(".knowledge-chapters li").nth(1)
        alu.locator("summary").click()
        alu.get_by_label("章节名称", exact=True).fill("算术逻辑单元")
        alu.get_by_role("button", name="保存名称", exact=True).click()
        expect(alu.get_by_role("button", name="算术逻辑单元", exact=True)).to_be_visible()
        alu.get_by_role("button", name="上移", exact=True).click()
        expect(t.locator(".knowledge-chapters li > button").first).to_have_text("算术逻辑单元")
        checks.append("teacher_add_rename_atomic_reorder")

        t.get_by_role("button", name="新增知识", exact=True).click()
        t.get_by_label("标题", exact=True).fill("程序计数器")
        t.get_by_label("正文", exact=True).fill(
            '<p onclick="window.__t005_xss=1">PC<sub>n</sub> 指向下一条指令，2<sup>4</sup>=16。</p>'
            '<img src="/invalid-image" onerror="window.__t005_xss=1">'
            '<script>window.__t005_xss=1</script><pre>&lt;CPU&gt;</pre>')
        t.get_by_label("例题", exact=True).fill("<p>0x13、0x22、0xF0：第3拍 ACC=3，第6拍 ACC=5，第9拍停止。</p>")
        t.get_by_label("标记为基础知识").check()
        t.get_by_role("button", name="保存知识", exact=True).click()
        expect(t.locator(".knowledge-detail h3")).to_have_text("程序计数器")
        point_id = teacher.call("GET", f"/courses/{course_id}/knowledge-points")[0]["id"]
        s = login(student_page, number, password)
        expect(s.get_by_text("暂无知识点。", exact=True)).to_be_visible()
        assert student_page.request.get(ORIGIN+f"/api/v1/knowledge-points/{point_id}").status == 404
        t.get_by_role("button", name="发布知识", exact=True).click()
        expect(t.locator(".knowledge-detail .knowledge-status").first).to_have_text("已发布")
        checks.append("draft_hidden_publish_real_api")

        s.get_by_role("button", name="重新加载", exact=True).click()
        s.get_by_label("检索知识").fill("程序计数器")
        s.get_by_role("button", name="检索", exact=True).click()
        s.get_by_role("button", name="程序计数器", exact=True).click()
        expect(s.locator(".knowledge-detail h3")).to_have_text("程序计数器")
        expect(s.locator(".knowledge-prose sub")).to_have_text("n")
        expect(s.locator(".knowledge-prose sup")).to_have_text("4")
        expect(s.locator(".knowledge-prose pre")).to_have_text("<CPU>")
        expect(s.locator(".knowledge-prose img, .knowledge-prose script, .knowledge-prose [onclick]")).to_have_count(0)
        assert student_page.evaluate("window.__t005_xss === undefined")
        expect(s.get_by_role("button", name="编辑知识", exact=True)).to_have_count(0)
        checks.append("search_formula_example_xss_escape_student_controls")
        s.get_by_role("button", name="收藏知识点", exact=True).click()
        expect(s.get_by_role("button", name="取消收藏", exact=True)).to_have_attribute("aria-pressed", "true")
        s.get_by_role("button", name="标记完成", exact=True).click()
        expect(s.get_by_role("button", name="取消完成", exact=True)).to_have_attribute("aria-pressed", "true")
        student_page.reload()
        s.get_by_role("button", name="程序计数器", exact=True).click()
        expect(s.get_by_role("button", name="取消完成", exact=True)).to_be_visible()
        student_page.get_by_role("button", name="退出", exact=True).click()
        expect(student_page.get_by_role("button", name="登录", exact=True)).to_be_visible()
        s = login(student_page, number, password)
        s.get_by_role("button", name="程序计数器", exact=True).click()
        expect(s.get_by_role("button", name="取消收藏", exact=True)).to_have_attribute("aria-pressed", "true")
        expect(s.get_by_role("button", name="取消完成", exact=True)).to_have_attribute("aria-pressed", "true")
        checks.append("bookmark_progress_refresh_logout_relogin")
        student_page.screenshot(path=str(output/f"{channel}-desktop.jpg"), full_page=True, quality=70)
        student_page.set_viewport_size({"width": 390, "height": 844})
        assert student_page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        expect(s.get_by_role("button", name="取消完成", exact=True)).to_be_visible()
        student_page.screenshot(path=str(output/f"{channel}-mobile.jpg"), full_page=True, quality=70)
        student_page.set_viewport_size({"width": 1440, "height": 1000})
        checks.append("390px_no_horizontal_overflow")

        s.get_by_label("检索知识").fill("没有这样的知识点")
        s.get_by_role("button", name="检索", exact=True).click()
        expect(s.get_by_text("没有匹配知识，请调整关键词。", exact=True)).to_be_visible()
        expect(s.locator(".knowledge-detail")).to_have_count(0)
        checks.append("empty_search_clears_detail")
        # Fault injection only: hold/abort the network, never substitute API data.
        pattern = "**/api/v1/courses/*/knowledge-points?*"
        held = []
        student_page.route(pattern, lambda route: held.append(route))
        s.get_by_role("button", name="检索", exact=True).click()
        expect(s).to_have_attribute("aria-busy", "true")
        expect(s.get_by_role("button", name="检索", exact=True)).to_be_disabled()
        expect(s.get_by_text("正在加载或保存…", exact=True)).to_be_visible()
        assert held, "Expected the list request to be held"
        held.pop().abort("internetdisconnected")
        student_page.unroute(pattern)
        expect(s.get_by_role("alert")).to_be_visible()
        expect(s.get_by_role("button", name="重试加载", exact=True)).to_be_enabled()
        expect(s.locator(".knowledge-results > button")).to_have_count(0)
        s.get_by_role("button", name="重试加载", exact=True).click()
        expect(s.get_by_role("alert")).to_have_count(0)
        s.get_by_role("button", name="程序计数器", exact=True).click()
        checks.append("injected_network_loading_failure_retry")

        t.get_by_role("button", name="下架知识", exact=True).click()
        expect(t.get_by_role("button", name="发布知识", exact=True)).to_be_visible()
        assert student_page.request.get(ORIGIN+f"/api/v1/knowledge-points/{point_id}").status == 404
        s.get_by_role("button", name="重新加载", exact=True).click()
        expect(s.locator(".knowledge-detail")).to_have_count(0)
        expect(s.get_by_text("暂无知识点。", exact=True)).to_be_visible()
        t.get_by_role("button", name="发布知识", exact=True).click()
        expect(t.get_by_role("button", name="下架知识", exact=True)).to_be_visible()
        s.get_by_role("button", name="重新加载", exact=True).click()
        s.get_by_role("button", name="程序计数器", exact=True).click()
        expect(s.get_by_role("button", name="取消收藏", exact=True)).to_have_attribute("aria-pressed", "true")
        expect(s.get_by_role("button", name="取消完成", exact=True)).to_have_attribute("aria-pressed", "true")
        s.get_by_role("button", name="取消收藏", exact=True).click()
        expect(s.get_by_role("button", name="收藏知识点", exact=True)).to_be_visible()
        s.get_by_role("button", name="取消完成", exact=True).click()
        expect(s.get_by_role("button", name="标记完成", exact=True)).to_be_visible()
        checks.append("unpublish_hides_republish_preserves_cancel_states")
        assert not errors, "Browser JavaScript errors occurred"
        return {"channel": channel, "version": browser.version, "status": "passed", "checks": checks,
                "page_errors": errors, "screenshots": [f"{channel}-desktop.jpg", f"{channel}-mobile.jpg"]}
    finally:
        for context in contexts:
            context.close()
        browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"logs/spec-005-browsers")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"started_at": datetime.now(UTC).isoformat(), "os": platform.platform(),
              "python": platform.python_version(), "playwright": version("playwright"),
              "tested_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "scope": "controlled real HTTP/UI; headless installed browsers; not classroom or performance acceptance",
              "fault_injection": "list network held then aborted; retry uses real HTTP; no mocked API responses",
              "browsers": []}
    try:
        with servers() as password, sync_playwright() as playwright:
            for channel in ("chrome", "msedge"):
                result = verify_browser(playwright, channel, password, args.output)
                report["browsers"].append(result)
                print(f"{channel} {result['version']}: {len(result['checks'])} checks passed", flush=True)
        report["status"] = "passed"
    except Exception as error:  # noqa: BLE001 - sanitized CLI failure boundary prevents credential-bearing exception output
        report["status"] = "failed"
        # Never serialize requests, cookies, passwords, tokens or browser storage.
        report["failure_type"] = type(error).__name__
        report["failure_locations"] = [f"{frame.name}:{frame.lineno}" for frame in traceback.extract_tb(error.__traceback__)
                                       if Path(frame.filename) == Path(__file__)]
        print(f"FAILED: {report['failure_type']} at {report['failure_locations']}", file=sys.stderr)
        return 1
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        (args.output/"browser-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
