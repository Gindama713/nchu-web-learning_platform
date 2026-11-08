"""Real Chrome/Edge checks of existing 005/003/009 pages; 017 UI is blocked.

The request observer records actual server responses without replacing them.
No successful HTTP mocks, business SQL writes, injected UI or engine fixtures.
"""

import argparse
import json
import shutil
import socket
import subprocess
import threading
import time
import traceback
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from flask import request
from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

from scripts.verify_spec006_questions import QuietHandler
from tests.test_knowledge_i01_seams import (
    ORIGIN,
    PDF1,
    PDF2,
    PNG,
    KnowledgeI01SeamsTest,
    database_facts,
    redact,
)

ROOT = Path(__file__).resolve().parents[1]


def dump(path, value):
    path.write_text(json.dumps(redact(value), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@contextmanager
def runtime(output, channel):
    for port in (5000, 5173):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    case = KnowledgeI01SeamsTest()
    records = []
    transport = {"socket": False}

    def observe(response):
        if transport["socket"] and request.path.startswith("/api/v1/"):
            records.append({"layer": "real socket", "method": request.method,
                            "path": request.full_path.rstrip("?"),
                            "request": redact(request.get_json(silent=True) if request.is_json else dict(request.form)),
                            "files": [{"field": key, "name": value.filename, "mime": value.mimetype}
                                      for key, value in request.files.items()],
                            "status": response.status_code,
                            "response": redact(response.get_json()) if response.is_json else {
                                "content_type": response.content_type,
                                "content_length": response.content_length,
                                "disposition": response.headers.get("Content-Disposition")}})
        return response

    case.observe_app = lambda app: app.after_request(observe)
    case.setUp()
    app = case.app
    at = datetime.now(UTC).replace(microsecond=0)
    app.config["TEST_NOW"] = at
    transport["socket"] = True
    server = make_server("127.0.0.1", 5000, app, request_handler=QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    process = None
    try:
        process = subprocess.Popen([shutil.which("node") or "node",
            str(ROOT / "frontend/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1",
            "--port", "5173", "--strictPort"], cwd=ROOT / "frontend", stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError("Vite exited")
            try:
                with urlopen(ORIGIN, timeout=1) as response:
                    if response.status == 200:
                        break
            except (URLError, TimeoutError):
                time.sleep(0.1)
        else:
            raise RuntimeError("Vite readiness timeout")
        yield case, at, records
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()
        dump(output / f"{channel}-bootstrap.json", {"layer": "real handlers before socket observer",
             "fixtures": "only initial admin/teacher SQL bootstrap; TEST_NOW; panel definition is input, not result mock",
             "requests": case.records})
        dump(output / f"{channel}-requests.json", records)
        dump(output / f"{channel}-facts.json", database_facts(case.path))
        case.doCleanups()


def get(context, path, status=200):
    response = context.request.get(ORIGIN + "/api/v1" + path)
    assert response.status == status, (path, response.status, response.text())
    return response


def write(context, method, path, payload=None, status=200):
    session = get(context, "/auth/session").json()["data"]
    response = context.request.fetch(ORIGIN + "/api/v1" + path, method=method, data=payload,
        headers={"Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"]})
    assert response.status == status, (path, response.status, response.text())
    return response.json()["data"] if status != 204 else None


def login(page, number, password):
    page.goto(ORIGIN)
    expect(page.get_by_label("学号", exact=True)).to_be_visible()
    page.get_by_label("学号", exact=True).fill(number)
    page.get_by_label("密码", exact=True).fill(password)
    page.get_by_role("button", name="登录", exact=True).click()
    expect(page.locator(".knowledge-module:not(.qa-module)").get_by_role("button", name="重新加载", exact=True)).to_be_enabled()
    expect(page.locator(".experiment-center").get_by_label("实验课程")).to_be_enabled()


def screenshot(page, locator, output, channel, suffix):
    page.set_viewport_size({"width": 390, "height": 844})
    locator.scroll_into_view_if_needed()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    locator.screenshot(path=str(output / f"{channel}-{suffix}.png"))


def verify(playwright, channel, output):
    result = {"channel": channel, "checks": [], "page_errors": [], "blocked": []}
    with runtime(output, channel) as (case, at, records):
        browser = playwright.chromium.launch(channel=channel, headless=True)
        try:
            result["version"] = browser.version
            teacher = browser.new_context(viewport={"width": 1440, "height": 1000}, timezone_id="Asia/Shanghai")
            student = browser.new_context(viewport={"width": 1440, "height": 1000}, timezone_id="Asia/Shanghai")
            teacher.set_default_timeout(10000)
            student.set_default_timeout(10000)
            tp, sp = teacher.new_page(), student.new_page()
            for page in (tp, sp):
                page.on("pageerror", lambda error: result["page_errors"].append(type(error).__name__))
            login(tp, "I01TEACH", case.password)
            resources = tp.locator(".resource-module")
            upload = resources.locator("form").filter(has=tp.get_by_role("heading", name="上传资源", exact=True))
            upload.get_by_label("标题", exact=True).fill("I01 PNG现行入口")
            upload.locator("select").first.select_option("guide")
            upload.get_by_label("文件", exact=True).set_input_files({"name": "alu.png", "mimeType": "image/png", "buffer": PNG})
            with tp.expect_response(lambda r: r.url.endswith(case.base + "/resources") and r.request.method == "POST") as observed:
                upload.get_by_role("button", name="上传", exact=True).click()
            assert observed.value.status == 415
            expect(resources.locator("[role=alert]")).to_be_visible()
            screenshot(tp, resources, output, channel, "png-upload-415")
            assert get(teacher, case.base + "/resources").json()["total"] == 0
            result["checks"].append("B1_existing_resource_upload_real_PNG_415_no_image_object")
            upload.get_by_label("标题", exact=True).fill("I01合法文档对照")
            upload.get_by_label("文件", exact=True).set_input_files({"name": "control.pdf", "mimeType": "application/pdf", "buffer": PDF1})
            with tp.expect_response(lambda r: r.url.endswith(case.base + "/resources") and r.request.method == "POST") as observed:
                upload.get_by_role("button", name="上传", exact=True).click()
            assert observed.value.status == 201
            resource = observed.value.json()["data"]
            row = resources.locator("tbody > tr").filter(has_text="I01合法文档对照").first
            row.get_by_text("版本历史", exact=True).click()
            form = row.locator(".resource-version-form")
            form.locator("input[type=file]").set_input_files({"name": "v2.pdf", "mimeType": "application/pdf", "buffer": PDF2})
            with tp.expect_response(lambda r: r.url.endswith(f"/resources/{resource['resource_id']}/versions") and r.request.method == "POST") as observed:
                form.get_by_role("button", name="上传新版本", exact=True).click()
            assert observed.value.status == 201
            result["checks"].append("B2_existing_resource_UI_permitted_PDF_two_versions_control_only")
            knowledge = tp.locator(".knowledge-module:not(.qa-module)")
            knowledge.locator(".knowledge-results").get_by_role("button", name="I01 ALU", exact=True).click()
            knowledge.get_by_role("button", name="编辑知识", exact=True).click()
            editor = knowledge.locator(".knowledge-editor")
            url = f"/api/v1/resource-versions/{resource['id']}/content?intent=view&event_id=11111111-1111-4111-8111-111111111111"
            markup = f'<h2 class="x">I01图文边界</h2><p onclick="alert(1)">A<sup>2</sup><sub>i</sub><img src="{url}"><a href="{url}">原版资源</a></p>'
            editor.get_by_label("正文", exact=True).fill(markup)
            editor.get_by_label("例题", exact=True).fill('<p style="color:red"><b>例题</b><a href="https://example.com">链接文本</a></p>')
            expect(editor).to_contain_text("保存时移除图片、链接及标签属性")
            assert editor.locator("input[type=file]").count() == 0
            screenshot(tp, editor, output, channel, "markup-editor-policy")
            with tp.expect_response(lambda r: r.url.endswith(f"/knowledge-points/{case.points[0]['id']}") and r.request.method == "PATCH") as observed:
                editor.get_by_role("button", name="保存知识", exact=True).click()
            assert observed.value.status == 200
            assert observed.value.json()["data"]["content"] == '<h2>I01图文边界</h2><p>A<sup>2</sup><sub>i</sub>原版资源</p>'
            result["checks"].append("B3_existing_005_editor_saves_contract_sanitized_markup_without_reference_picker")
            login(sp, "I01STUD1", case.password)
            sk = sp.locator(".knowledge-module:not(.qa-module)")
            sk.locator(".knowledge-results").get_by_role("button", name="I01 ALU", exact=True).click()
            prose = sk.locator(".knowledge-prose")
            expect(prose.first).to_contain_text("原版资源")
            assert prose.locator("img,a,script,[onclick],[style],[class]").count() == 0
            expect(prose.locator("sup")).to_have_text("2")
            sk.get_by_role("button", name="标记完成", exact=True).click()
            expect(sk.get_by_role("button", name="取消完成", exact=True)).to_be_visible()
            screenshot(sp, sk, output, channel, "sanitized-reading-progress")
            sp.reload()
            sk.locator(".knowledge-results").get_by_role("button", name="I01 ALU", exact=True).click()
            expect(sk.get_by_role("button", name="取消完成", exact=True)).to_be_visible()
            assert not any(r["path"].startswith("/api/v1/resource-versions/") for r in records)
            result["checks"].append("A1_B4_real_student_005_reading_progress_refresh_no_embedded_resource_request")
            # The published experiment is created through the socket APIs, not business SQL.
            exp = write(teacher, "POST", case.base + "/experiments", {
                "code": "EXP-01", "title": "I01浏览器ALU实验", "description": "同课知识引用"}, 201)
            from backend.engines.wiring import _make_panel
            panel = _make_panel("EXP-01")
            panel["layout"] = {}
            version = write(teacher, "POST", f"/experiments/{exp['id']}/versions", {
                "title": "I01浏览器v1", "objectives": "理解算术和进位", "instructions": "连接并验证ALU",
                "knowledge_ids": [p["id"] for p in case.points[:2]], "submission_modes": ["wiring"],
                "panel": panel, "rules": {"require_required_inputs": True}}, 201)
            write(teacher, "POST", f"/experiment-versions/{version['id']}/publish", {
                "start_at": (at - timedelta(minutes=1)).isoformat(), "end_at": (at + timedelta(minutes=10)).isoformat()})
            experiment = sp.locator(".experiment-center")
            experiment.get_by_role("button", name="重新加载", exact=True).click()
            experiment.locator("li").filter(has_text="EXP-01 · I01浏览器ALU实验").get_by_role("button", name="查看指导", exact=True).click()
            expect(experiment.locator(".experiment-guidance")).to_contain_text("I01 ALU")
            sp.evaluate("window.i01Entries=[]; document.addEventListener('cpu-experiment-open', event => window.i01Entries.push(event.detail))")
            before = len(records)
            experiment.get_by_role("button", name="进入实验箱连线（SPEC-017）", exact=True).click()
            expect(experiment).to_contain_text("已请求打开实验箱连线工作台")
            assert sp.evaluate("window.i01Entries") == [{"mode": "wiring", "version_id": version["id"], "experiment_id": exp["id"]}]
            assert not any("wiring-attempts" in r["path"] for r in records[before:])
            result["headings"] = sp.get_by_role("heading").all_text_contents()
            assert not any("工作台" in heading or "连线模拟" in heading for heading in result["headings"])
            screenshot(sp, experiment, output, channel, "experiment-entry-blocked")
            result["checks"].append("A2_real_009_list_guidance_knowledge_labels_and_entry_event_observed")
            result["blocked"].extend(["I01-017-01: no mounted 017 workbench; no UI wiring/save/refresh/submit pass",
                                      "I01-010C-01: no existing wiring analytics page; handler consumption only",
                                      "B image preview/download blocked: PNG upload rejects every defined kind; knowledge reference contract absent"])
            # Real resource UI download remains an independent document control.
            sr = sp.locator(".resource-module")
            sr.get_by_role("button", name="检索", exact=True).click()
            rrow = sr.locator("tbody > tr").filter(has_text="I01合法文档对照").first
            rrow.get_by_text("版本历史", exact=True).click()
            v1row = rrow.locator("details table tbody > tr").filter(has=sp.get_by_role("cell", name="v1", exact=True))
            with sp.expect_download() as download:
                v1row.get_by_role("button", name="下载", exact=True).click()
            assert Path(download.value.path()).read_bytes() == PDF1
            result["download"] = {"control": "PDF v1 only", "bytes_match": True, "size": len(PDF1)}
            write(teacher, "PATCH", f"/resources/{resource['resource_id']}", {"visibility": "teacher_only"})
            get(student, f"/resources/{resource['resource_id']}/versions", 404)
            sr.get_by_role("button", name="检索", exact=True).click()
            expect(sr.get_by_text("暂无资源。", exact=True)).to_be_visible()
            screenshot(sp, sr, output, channel, "resource-permission-reread")
            result["checks"].append("B5_independent_PDF_old_version_UI_download_and_permission_reread_not_image_proof")
            write(teacher, "PATCH", f"/knowledge-points/{case.points[0]['id']}", {"published": False})
            sk.locator(".knowledge-results").get_by_role("button", name="I01 ALU", exact=True).click()
            expect(sk.locator("[role=alert]")).to_be_visible()
            expect(sk.locator(".knowledge-detail")).to_have_count(0)
            student_id = get(student, "/auth/session").json()["data"]["user"]["id"]
            write(teacher, "DELETE", case.base + f"/members/{student_id}", status=204)
            experiment.get_by_role("button", name="重新加载", exact=True).click()
            expect(experiment.locator(".experiment-guidance")).to_have_count(0)
            get(student, f"/experiment-versions/{version['id']}", 404)
            screenshot(sp, experiment, output, channel, "revoked-entry-cleared")
            result["checks"].append("A3_005_unpublish_clears_old_detail_009_member_revocation_clears_entry")
            assert not result["page_errors"]
            result["status"] = "passed_existing_pages_with_explicit_blockers"
            return result
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "logs/i01/browsers")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"started_at": datetime.now(UTC).isoformat(), "browsers": [],
              "tested_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "dirty_paths": subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines()}
    try:
        with sync_playwright() as playwright:
            for channel in ("chrome", "msedge"):
                report["browsers"].append(verify(playwright, channel, args.output))
        report["status"] = "passed_existing_pages_with_explicit_blockers"
    except Exception as error:
        report["status"] = "failed"
        report["failure_type"] = type(error).__name__
        report["failure"] = redact(str(error))
        report["trace"] = traceback.format_exc()
        raise
    finally:
        dump(args.output / "report.json", report)
        print(json.dumps({"status": report["status"], "browsers": len(report["browsers"])}))


if __name__ == "__main__":
    main()
