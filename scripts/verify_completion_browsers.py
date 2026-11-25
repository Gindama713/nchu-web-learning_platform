"""Optional installed Chrome/Edge UI checks, invoked by verify_grading_live.py."""

import json
import re

import cv2
import numpy as np


def verify(base, fixture, output):
    from playwright.sync_api import expect, sync_playwright

    fixture.create_version(("circuit",), title="浏览器表单草稿")
    results = []
    with sync_playwright() as playwright:
        for channel in ("chrome", "msedge"):
            browser = playwright.chromium.launch(channel=channel, headless=True)
            context = browser.new_context(base_url=base, viewport={"width": 1280, "height": 900})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error, target=errors: target.append(str(error)))

            def login(target, account):
                target.goto(base)
                target.locator("#username").fill(account)
                target.locator("#password").fill(fixture.password)
                target.locator("#login").click()
                expect(target.get_by_role("tab", name="课程与通知", exact=True)).to_be_visible()

            def open_knowledge(target):
                target.get_by_role("tab", name="教学内容", exact=True).click()
                module = target.locator('.knowledge-module[aria-labelledby="knowledge-title"]')
                expect(module).to_have_attribute("aria-busy", "false")
                module.locator(".knowledge-results button").first.click()
                return module

            login(page, "T018TEACH")
            page.get_by_role("tab", name="实验与演示", exact=True).click()
            grading = page.locator(".grading-center")
            grading.locator("li").filter(has_text="浏览器表单草稿").get_by_role("button", name="配置评测", exact=True).click()
            grading.get_by_role("button", name="载入本实验公开模板（替换当前草稿）", exact=True).click()
            expect(grading.get_by_label("顶层电路名", exact=True)).to_have_value("ALU8")
            width = grading.get_by_label("位宽（1—8）", exact=True).first
            width.fill("7")
            width.press("Tab")
            value = grading.get_by_label("端口 port_schema JSON", exact=True).input_value()
            assert json.loads(value)["inputs"]["A"] == 7
            width.fill("8")
            width.press("Tab")
            grading.get_by_role("button", name="保存判分配置", exact=True).click()
            expect(grading.get_by_text("判分配置已保存；配置变更会使旧验证失效。", exact=True)).to_be_visible()
            grading.get_by_label("用例名称", exact=True).first.fill("浏览器编辑 add")
            grading.get_by_label("用例名称", exact=True).first.press("Tab")
            with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/test-suites")) as response:
                grading.get_by_role("button", name="新建测试集", exact=True).click()
            assert response.value.status == 201
            assert response.value.json()["data"]["cases"][0]["label"] == "浏览器编辑 add"
            grading.screenshot(path=str(output / f"{channel}-grading.png"))
            page.set_viewport_size({"width": 390, "height": 844})
            grading.scroll_into_view_if_needed()
            assert grading.evaluate("node => node.scrollWidth <= node.clientWidth + 1"), "Grading overflows at 390px"
            size = grading.evaluate("node => ({width:node.getBoundingClientRect().width, viewport:innerWidth, document:document.documentElement.scrollWidth})")
            if size["document"] > size["viewport"] + 1:
                size["overflow"] = page.evaluate("[...document.querySelectorAll('body *')].filter(n=>n.getBoundingClientRect().right>innerWidth+1).slice(0,18).map(n=>({tag:n.tagName,cls:n.className,right:n.getBoundingClientRect().right,width:n.getBoundingClientRect().width}))")
            assert size["width"] <= size["viewport"] and size["document"] <= size["viewport"] + 1, size
            grading.screenshot(path=str(output / f"{channel}-grading-390.png"))
            page.set_viewport_size({"width": 1280, "height": 900})
            knowledge = open_knowledge(page)
            knowledge.get_by_role("button", name="编辑知识", exact=True).click()
            knowledge.get_by_label("正文", exact=True).fill("<p>浏览器配图：CPU数据通路</p>")
            image = np.full((100, 240, 3), 255, dtype=np.uint8)
            cv2.rectangle(image, (20, 20), (100, 75), (0, 0, 0), 2)
            cv2.line(image, (100, 48), (220, 48), (0, 0, 0), 2)
            _, encoded = cv2.imencode(".png", image)
            knowledge.locator('input[type="file"]').set_input_files({"name": "cpu-diagram.png", "mimeType": "image/png", "buffer": encoded.tobytes()})
            expect(knowledge.get_by_label("正文", exact=True)).to_have_value(re.compile(r"\[\[image:\d+\]\]"))
            knowledge.get_by_role("button", name="保存知识", exact=True).click()
            picture = knowledge.locator(".knowledge-prose img")
            expect(picture).to_be_visible()
            assert picture.evaluate("node => node.complete && node.naturalWidth === 240")
            url = picture.get_attribute("src")
            knowledge.screenshot(path=str(output / f"{channel}-knowledge.png"))
            student_context = browser.new_context(base_url=base, viewport={"width": 390, "height": 844})
            student = student_context.new_page()
            student.on("pageerror", lambda error, target=errors: target.append(str(error)))
            login(student, "T018STUD1")
            student_knowledge = open_knowledge(student)
            expect(student_knowledge.locator(".knowledge-prose img")).to_be_visible()
            assert student_knowledge.locator(".knowledge-prose img").evaluate("node => node.complete && node.naturalWidth === 240")
            assert student_knowledge.evaluate("node => node.scrollWidth <= node.clientWidth + 1"), "Knowledge overflows at 390px"
            assert student.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "Page overflows at 390px"
            student_knowledge.screenshot(path=str(output / f"{channel}-knowledge-390.png"))
            with page.expect_response(lambda response: response.request.method == "PATCH" and "/knowledge-points/" in response.url) as saved:
                knowledge.get_by_role("button", name="下架知识", exact=True).click()
            assert saved.value.status == 200 and not saved.value.json()["data"]["published"]
            expect(knowledge.get_by_role("button", name="发布知识", exact=True)).to_be_visible()
            response = student.request.get(url)
            assert response.status == 404, (channel, response.status, response.text()[:200])
            with page.expect_response(lambda response: response.request.method == "PATCH" and "/knowledge-points/" in response.url) as saved:
                knowledge.get_by_role("button", name="发布知识", exact=True).click()
            assert saved.value.status == 200 and saved.value.json()["data"]["published"]
            expect(knowledge.get_by_role("button", name="下架知识", exact=True)).to_be_visible()
            response = student.request.get(url)
            assert response.status == 200, (channel, response.status, response.text()[:200])
            assert not errors, errors
            results.append({"channel": channel, "template_form_json_sync": True, "suite_saved": True,
                            "knowledge_upload_and_student_view": True, "unpublish_revokes_image": True,
                            "viewport_390": True, "page_errors": errors})
            student_context.close()
            context.close()
            browser.close()
    return results
