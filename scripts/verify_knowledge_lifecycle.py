"""Run only the finite knowledge lifecycle, optionally observing existing pages."""

import argparse
import json
import shutil
import socket
import subprocess
import threading
import time
import unittest
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from scripts.verify_spec005_browsers import QuietHandler
from tests.test_knowledge_lifecycle import KnowledgeLifecycleTest, sanitized

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'http://127.0.0.1:5173'
METHOD = 'test_current_projection_retains_history_and_old_snapshots_through_005_lifecycle'


@contextmanager
def serving(case, output):
    from werkzeug.serving import make_server
    for port in (5000, 5173):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
    server = make_server('127.0.0.1', 5000, case.app, threaded=True, request_handler=QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    process = None
    try:
        with (output / 'vite.txt').open('w', encoding='utf-8') as stream:
            process = subprocess.Popen([shutil.which('node') or 'node',
                str(ROOT / 'frontend/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1',
                '--port', '5173', '--strictPort'], cwd=ROOT / 'frontend', stdout=stream,
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


def browser_check(playwright, channel, output):
    from playwright.sync_api import expect

    from scripts.verify_spec010b_analytics import download

    folder = output / channel
    folder.mkdir(parents=True, exist_ok=True)
    case = KnowledgeLifecycleTest(METHOD)
    case.output = folder
    errors, requests, checks = [], [], []
    case.setUp()
    # Browser cookies honor wall time; the handler suite's Oct 13 clock is historical.
    case.app.config['TEST_NOW'] = datetime.now(UTC)
    for role, number in (('admin', 'T006ADMIN'), ('teacher', 'T006TEACH'),
                         ('student', 'T006STUD1'), ('outsider', 'T006STUD2')):
        case.login(getattr(case, role), number)
    try:
        with serving(case, folder):
            browser = playwright.chromium.launch(channel=channel, headless=True)
            try:
                teacher = browser.new_context(viewport={'width': 390, 'height': 1200}, accept_downloads=True)
                student = browser.new_context(viewport={'width': 390, 'height': 1200})
                pages = [teacher.new_page(), student.new_page()]
                for page, number in zip(pages, ('T006TEACH', 'T006STUD1'), strict=True):
                    page.on('pageerror', lambda error: errors.append(type(error).__name__))
                    with page.expect_response(lambda r: r.url.endswith('/auth/session')) as initial:
                        page.goto(ORIGIN)
                    initial.value.body()
                    page.get_by_label('学号', exact=True).fill(number)
                    page.get_by_label('密码', exact=True).fill(case.password)
                    with page.expect_response(lambda r: r.url.endswith('/auth/login')) as signed:
                        page.get_by_role('button', name='登录', exact=True).click()
                    assert signed.value.status == 200
                    expect(page.locator('.analytics-bank').get_by_label('统计课程', exact=True)).to_be_enabled()

                def observe(name, values):
                    if name not in {'original', 'renamed', 'all-hidden', 'both-restored'}:
                        return
                    for page, role in zip(pages, ('teacher', 'student'), strict=True):
                        bank = page.locator('.analytics-bank')
                        value = values[role]
                        bank.get_by_label('原快照编号', exact=True).fill(str(value['analysis_run_id']))
                        with page.expect_response(lambda r: '/analytics?analysis_run_id=' in r.url) as pending:
                            bank.get_by_role('button', name='恢复原快照', exact=True).click()
                        pending.value.body()
                        assert pending.value.json()['data'] == value
                        requests.append({'actor': role, 'transport': 'real socket UI restore', 'stage': name,
                                         'status': pending.value.status, 'response': sanitized(pending.value.json())})
                        expect(bank).to_have_attribute('aria-busy', 'false')
                        expect(bank.locator('.analytics-report')).to_contain_text('有效样本 2')
                        if name == 'renamed':
                            expect(bank.locator('.analytics-report')).to_contain_text('程序计数器新名')
                        if name == 'all-hidden':
                            expect(bank.locator('.analytics-report')).not_to_contain_text('程序计数器新名')
                        if role == 'teacher':
                            # Actual UI download of both current and original selected-student snapshots.
                            assert download(page, bank) == case.export(value)
                        if role == 'teacher':
                            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                            bank.screenshot(path=str(folder / f'{name}.png'))
                        checks.append(f'{name}:{role}:restore_exact_data')
                    if name == 'both-restored':
                        for page, role, old in zip(pages, ('teacher', 'student'),
                                                  (case.old_teacher, case.old_student), strict=True):
                            bank = page.locator('.analytics-bank')
                            bank.get_by_label('原快照编号', exact=True).fill(str(old['analysis_run_id']))
                            bank.get_by_role('button', name='恢复原快照', exact=True).click()
                            expect(bank).to_have_attribute('aria-busy', 'false')
                            expect(bank.locator('.analytics-report')).to_contain_text('程序计数器原名')
                            page.reload()
                            expect(bank).to_have_attribute('aria-busy', 'false')
                            expect(bank.get_by_label('原快照编号', exact=True)).to_have_value(str(old['analysis_run_id']))
                            expect(bank.locator('.analytics-report')).to_contain_text('程序计数器原名')
                            if role == 'teacher':
                                assert download(page, bank) == case.old_csv
                                bank.screenshot(path=str(folder / 'old-after-refresh.png'))
                            checks.append(f'{role}:original_id_survives_changes_and_reload')

                case.observer = observe
                getattr(case, METHOD)()
                assert errors == []
                return {'channel': channel, 'version': browser.version, 'checks': checks,
                        'page_errors': errors, 'result': 'passed'}
            finally:
                browser.close()
    finally:
        case.doCleanups()
        (folder / 'socket.json').write_text(json.dumps(requests, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--browsers', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'at': datetime.now(UTC).isoformat(), 'tested_head': subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), 'dirty_paths': subprocess.check_output(
        ['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines(), 'result': 'failed'}
    try:
        if args.browsers:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                report['browsers'] = [browser_check(playwright, channel, args.output) for channel in ('chrome', 'msedge')]
            report['result'] = 'passed'
        else:
            case = KnowledgeLifecycleTest(METHOD)
            case.output = args.output
            with (args.output / 'tests.txt').open('w', encoding='utf-8') as stream:
                result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.TestSuite([case]))
            report.update(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                          expected_failures=len(result.expectedFailures), result='passed' if result.wasSuccessful() else 'failed')
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(report['result'] != 'passed')


if __name__ == '__main__':
    main()
