"""Chrome/Edge consume the new handler scenarios through existing pages/socket APIs.

Fixture creation/submission/grading remains explicitly handler transport; UI reads,
restoration and CSV downloads use the real local server without request interception.
"""

import argparse
import hashlib
import json
import re
import shutil
import socket
import subprocess
import threading
import time
import traceback
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

from scripts.verify_spec006_questions import ORIGIN, ROOT, QuietHandler, login
from tests.test_mixed_consumption import MixedConsumptionTest, redact


@contextmanager
def serving(case):
    for port in (5000, 5173):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
    server = make_server('127.0.0.1', 5000, case.app, request_handler=QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with TemporaryDirectory(prefix='mixed-ui-') as temporary:
        process = None
        try:
            with (Path(temporary) / 'vite.log').open('wb') as log:
                process = subprocess.Popen([shutil.which('node') or 'node',
                    str(ROOT / 'frontend/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1',
                    '--port', '5173', '--strictPort'], cwd=ROOT / 'frontend', stdout=log,
                    stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError('Vite exited')
                    try:
                        with urlopen(ORIGIN, timeout=1) as response:
                            if response.status == 200:
                                break
                    except (URLError, TimeoutError):
                        time.sleep(.1)
                else:
                    raise RuntimeError('Vite readiness timeout')
                yield
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()


def verify(playwright, channel, output):
    browser = playwright.chromium.launch(channel=channel, headless=True)
    errors, sockets, checks, images = [], [], [], []

    def capture(response):
        if '/api/v1/' not in response.url:
            return
        raw = response.body()
        request = response.request
        sockets.append({'transport': 'browser socket', 'method': request.method,
            'path': response.url.split('/api/v1', 1)[1], 'status': response.status,
            'request': redact(json.loads(request.post_data)) if request.post_data else None,
            'response_sha256': hashlib.sha256(raw).hexdigest(),
            'response': redact(json.loads(raw)) if 'json' in response.headers.get('content-type', '')
            else raw.decode('utf-8-sig')})

    def photo(page, locator, name):
        page.set_viewport_size({'width': 390, 'height': 844})
        locator.scroll_into_view_if_needed()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        filename = f'{channel}-{name}.png'
        locator.screenshot(path=str(output / filename))
        images.append(filename)

    def restore(page, case, data, name=None, teacher=True):
        bank = page.locator('.analytics-bank')
        expect(bank).to_have_attribute('aria-busy', 'false')
        bank.get_by_label('原快照编号', exact=True).fill(str(data['analysis_run_id']))
        with page.expect_response(lambda r: '/analytics?analysis_run_id=' in r.url) as response:
            bank.get_by_role('button', name='恢复原快照', exact=True).click()
        assert response.value.json()['data'] == data
        expect(bank).to_have_attribute('aria-busy', 'false')
        expect(bank.locator('.analytics-report')).to_contain_text(f"有效样本 {data['sample_size']}")
        if teacher:
            with page.expect_download() as download:
                bank.get_by_role('button', name='导出当前快照 CSV', exact=True).click()
            assert download.value.failure() is None
            assert Path(download.value.path()).read_bytes() == case.export(data)
        if name:
            photo(page, bank, name)
        checks.append({'stage': name or 'restore', 'analysis_run_id': data['analysis_run_id'],
                       'dimension': data['dimension'], 'sample_size': data['sample_size']})

    def run_case(method):
        case = MixedConsumptionTest(method)
        case.output = output / (channel + '-handlers')
        case.setUp()

        def hook(stage, values):
            teacher = stage.startswith('a-')
            context = browser.new_context(viewport={'width': 1440, 'height': 1000},
                                          timezone_id='Asia/Shanghai', accept_downloads=True)
            try:
                page = context.new_page()
                page.on('response', capture)
                page.on('pageerror', lambda error: errors.append(type(error).__name__))
                login(page, 'T006TEACH' if teacher else 'T006STUD1', case.password)
                if stage in ('a-generated-drafts', 'a-published'):
                    bank = page.locator('.paper-bank').filter(has=page.get_by_role('heading', name='课程试卷', exact=True))
                    paper = values['generated'][0]
                    bank.get_by_role('button', name=re.compile(f"^#{paper['paper_id']} ·")).click()
                    expect(bank.locator('.paper-detail')).to_contain_text('组卷快照')
                    if stage == 'a-generated-drafts':
                        photo(page, bank.locator('.paper-detail'), 'a-fixed-generated-draft')
                    else:
                        expect(bank.locator('.paper-detail')).to_contain_text('发布冻结人数：3')
                elif stage == 'a-pending-scores':
                    restore(page, case, values['homework'], 'a-pending-homework')
                    restore(page, case, values['exam'])
                elif stage == 'a-new-scores':
                    restore(page, case, values['homework'], 'a-new-cross-homework')
                    restore(page, case, values['exam'], 'a-new-exam')
                    restore(page, case, values['single'])
                    restore(page, case, values['old_homework'], 'a-old-homework')
                    restore(page, case, values['old_exam'])
                elif stage == 'b-first-week':
                    restore(page, case, values['knowledge'], 'b-first-week', teacher=False)
                elif stage == 'b-second-week':
                    restore(page, case, values['knowledge'], 'b-two-week-knowledge', teacher=False)
                    recommendation = page.locator('.recommendation-bank')
                    recommendation.get_by_role('button', name='刷新推荐', exact=True).click()
                    expect(recommendation).to_have_attribute('aria-busy', 'false')
                    expect(recommendation).to_contain_text('样本 3 次')
                    expect(recommendation).to_contain_text('0.466667')
                    photo(page, recommendation, 'b-mixed-recommendation')
                    restore(page, case, values['old_knowledge'], 'b-old-knowledge', teacher=False)
                    page.reload()
                    expect(page.locator('.analytics-bank').get_by_label('原快照编号', exact=True)).to_have_value(
                        str(values['old_knowledge']['analysis_run_id']))
            finally:
                context.close()

        case.hook = hook
        try:
            with serving(case):
                getattr(case, method)()
        finally:
            case.doCleanups()

    try:
        for method in ('test_generated_homework_exam_cross_paper_scores_and_saved_snapshots',
                       'test_mixed_practice_quiz_versions_recommendation_and_weekly_knowledge'):
            run_case(method)
        assert not errors
        return {'channel': channel, 'version': browser.version, 'page_errors': errors,
                'checks': checks, 'screenshots': images, 'result': 'passed'}
    finally:
        (output / f'{channel}-socket-requests.json').write_text(
            json.dumps(sockets, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'logs/mixed-consumption/browsers')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'at': datetime.now(UTC).isoformat(),
        'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'dirty_paths': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines(),
        'scope': 'fixtures via real handlers; existing pages restore, display and download via real socket', 'browsers': []}
    try:
        with sync_playwright() as playwright:
            for channel in ('chrome', 'msedge'):
                report['browsers'].append(verify(playwright, channel, args.output))
        report['result'] = 'passed'
    except Exception as exc:  # Diagnostic boundary only; never turns failure into success.
        report.update(result='failed', error_type=type(exc).__name__)
        traceback.print_exc()
        raise
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'result': report['result'], 'browsers': len(report['browsers'])}))


if __name__ == '__main__':
    main()
