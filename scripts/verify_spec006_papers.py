"""C02b real HTTP/UI checks. --knowledge-fixture is explicitly NOT SPEC-005 integration.

Paper/identity/migrations/publication are always the actual implementation.
Requires free 5000/5173 ports, installed Chrome/Edge and requirements-browser.txt.
"""

import argparse
import json
import secrets
import shutil
import socket
import subprocess
import threading
import time
import traceback
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

from backend.shared.db import connect
from scripts.verify_spec006_questions import ORIGIN, ROOT, QuietHandler, login, prepare


@contextmanager
def running(knowledge_fixture):
    for port in (5000, 5173):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
    with TemporaryDirectory(prefix='c02b-browser-') as temporary:
        path = Path(temporary) / 'controlled.db'
        password = secrets.token_urlsafe(24)
        app, course_id = prepare(path, password)
        # Keep deterministic windows while all login/member/paper operations use actual APIs.
        at = datetime.now(UTC).replace(second=0, microsecond=0)
        app.config['TEST_NOW'] = at
        if knowledge_fixture:
            with closing(connect(path)) as db:
                db.executescript('CREATE TABLE chapter(id INTEGER PRIMARY KEY,course_id INTEGER REFERENCES course(id));'
                                 'CREATE TABLE knowledge_point(id INTEGER PRIMARY KEY,chapter_id INTEGER REFERENCES chapter(id));')
                db.execute('INSERT INTO chapter VALUES(1,?)', (course_id,))
                db.execute('INSERT INTO knowledge_point VALUES(1,1)')
        server = make_server('127.0.0.1', 5000, app, request_handler=QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        process = None
        try:
            with (Path(temporary)/'vite.log').open('wb') as log:
                process = subprocess.Popen([shutil.which('node') or 'node',
                                            str(ROOT/'frontend/node_modules/vite/bin/vite.js'),
                                            '--host', '127.0.0.1', '--port', '5173', '--strictPort'],
                                           cwd=ROOT/'frontend', stdout=log, stderr=subprocess.STDOUT,
                                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError('Vite exited before readiness')
                    try:
                        with urlopen(ORIGIN, timeout=1) as response:
                            if response.status == 200:
                                break
                    except (URLError, TimeoutError):
                        time.sleep(0.1)
                else:
                    raise RuntimeError('Vite readiness timed out')
                yield app, password, course_id, at
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()


def write(context, method, path, body, expected=200):
    session = context.request.get(ORIGIN+'/api/v1/auth/session').json()['data']
    response = context.request.fetch(ORIGIN+'/api/v1'+path, method=method, data=body,
                                     headers={'Origin': ORIGIN, 'X-CSRF-Token': session['csrf_token']})
    assert response.status == expected, f'{method} {path} returned unexpected status'
    return response.json()


def check_empty(page, context, bank, course_id, checks):
    expect(bank.get_by_text('共 0 份试卷')).to_be_visible()
    bank.get_by_role('button', name='编排新试卷', exact=True).click()
    expect(bank.get_by_text('暂无可用题目。请先在课程题库创建带知识标签的题目。')).to_be_visible()
    expect(bank.get_by_role('button', name='保存试卷草稿')).to_be_disabled()
    checks.append('real_teacher_empty_list_and_empty_draft_disabled_without_dependency_fixtures')
    result = write(context, 'POST', f'/courses/{course_id}/questions',
                   {'type': 'boolean', 'stem': 'PC保存指令地址？', 'options': [], 'answer': True,
                    'difficulty': 'easy', 'knowledge_ids': [1]}, 503)
    assert result['error']['code'] == 'DEPENDENCY_UNAVAILABLE'
    assert context.request.get(ORIGIN+f'/api/v1/courses/{course_id}/papers').json()['total'] == 0
    checks.append('real_missing_knowledge_503_and_no_partial_paper')
    page.set_viewport_size({'width': 390, 'height': 844})
    bank.scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    checks.append('390px_empty_editor_without_horizontal_overflow')


def check_publication(app, password, page, context, bank, course_id, at, checks, output, channel):
    # Only the minimal knowledge schema above is a fixture; create/edit questions through 006 API.
    q = write(context, 'POST', f'/courses/{course_id}/questions',
              {'type': 'boolean', 'stem': 'PC保存指令地址？', 'options': [], 'answer': True,
               'difficulty': 'easy', 'knowledge_ids': [1]}, 201)['data']
    bank.get_by_role('button', name='编排新试卷', exact=True).click()
    page.get_by_label('试卷标题', exact=True).fill('C02b保密考试')
    page.get_by_label('试卷类型', exact=True).select_option('exam')
    page.get_by_label('选择题目版本', exact=True).select_option(str(q['id']))
    bank.get_by_role('button', name='加入试卷', exact=True).click()
    page.get_by_label('第 1 题配分', exact=True).fill('10.01')
    bank.get_by_role('button', name='保存试卷草稿', exact=True).click()
    expect(bank.get_by_role('heading', name='设置窗口并发布')).to_be_visible()
    papers = context.request.get(ORIGIN+f'/api/v1/courses/{course_id}/papers').json()['data']
    paper = next(item for item in papers if item['title'] == 'C02b保密考试' and item['status'] == 'draft')
    updated = write(context, 'PATCH', f"/questions/{q['id']}", {'stem': '后续版本的新题干', 'answer': False})['data']
    detail = context.request.get(ORIGIN+f"/api/v1/papers/{paper['id']}").json()['data']
    assert detail['items'][0]['question_version_id'] == q['version_id'] != updated['version_id']
    assert detail['items'][0]['answer'] is True
    checks.append('teacher_ui_draft_exact_points_and_api_edit_retains_original_version')
    window = {'start_at': at+timedelta(minutes=1), 'end_at': at+timedelta(minutes=2), 'review_at': at+timedelta(minutes=3)}
    for field, label in (('start_at', '试卷开始'), ('end_at', '试卷截止'), ('review_at', '试卷讲评')):
        # Browser datetime-local expects its local time; timezone conversion is exercised by UI.
        page.get_by_label(label, exact=True).fill(window[field].astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%dT%H:%M'))
    page.get_by_label('保密确认说明', exact=True).fill('确认题目未公开且并非对公开题的简单复制')
    bank.get_by_role('button', name='发布试卷并冻结名单', exact=True).click()
    expect(bank.get_by_text('发布冻结人数：1')).to_be_visible()
    checks.append('teacher_ui_confidential_publication_freezes_real_active_roster')
    page.set_viewport_size({'width': 390, 'height': 844})
    bank.scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    bank.screenshot(path=str(output/f'{channel}-teacher-published.png'))
    checks.append('390px_published_paper_without_horizontal_overflow')
    page.get_by_role('button', name='退出', exact=True).click()
    login(page, 'B006STUD1', password)
    expect(bank.get_by_text('共 1 份试卷')).to_be_visible()
    bank.get_by_role('button', name=f"#{paper['id']} · C02b保密考试 · 未开始", exact=True).click()
    expect(bank.get_by_text('试卷尚未开始，开始后可查看题目。')).to_be_visible()
    assert 'items' not in context.request.get(ORIGIN+f"/api/v1/papers/{paper['id']}").json()['data']
    checks.append('student_real_roster_list_prestart_metadata_without_items')
    for field in ('start_at', 'end_at'):
        app.config['TEST_NOW'] = window[field]
        bank.get_by_role('button', name='重新加载试卷', exact=True).click()
        label = '进行中' if field == 'start_at' else '已截止'
        bank.get_by_role('button', name=f"#{paper['id']} · C02b保密考试 · {label}", exact=True).click()
        expect(bank.get_by_text('PC保存指令地址？', exact=True)).to_be_visible()
        expect(bank.get_by_text('参考答案：true', exact=True)).to_have_count(0)
        detail = context.request.get(ORIGIN+f"/api/v1/papers/{paper['id']}").json()['data']
        assert 'answer' not in detail['items'][0] and 'explanation' not in detail['items'][0]
    checks.append('student_exact_start_and_end_boundaries_no_answers_before_review')
    bank.screenshot(path=str(output/f'{channel}-student-protected.png'))
    app.config['TEST_NOW'] = window['review_at']
    bank.get_by_role('button', name='重新加载试卷', exact=True).click()
    bank.get_by_role('button', name=f"#{paper['id']} · C02b保密考试 · 已截止", exact=True).click()
    expect(bank.get_by_text('参考答案：true', exact=True)).to_be_visible()
    checks.append('student_exact_review_boundary_releases_fixed_original_answer')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'logs/spec-006-papers')
    parser.add_argument('--knowledge-fixture', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'started_at': datetime.now(UTC).isoformat(),
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'scope': 'real paper/001 migrations and HTTP/UI; knowledge ONLY fixture' if args.knowledge_fixture
                       else 'real empty paper/001 HTTP/UI and missing knowledge failure; NO dependency fixtures',
              'knowledge_fixture': args.knowledge_fixture, 'browsers': [], 'page_errors': []}
    try:
        with sync_playwright() as playwright:
            for channel in ('chrome', 'msedge'):
                with running(args.knowledge_fixture) as (app, password, course_id, at):
                    browser = playwright.chromium.launch(channel=channel, headless=True)
                    try:
                        entry = {'channel': channel, 'version': browser.version, 'checks': []}
                        report['browsers'].append(entry)
                        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, timezone_id='Asia/Shanghai')
                        page = context.new_page()
                        page.on('pageerror', lambda error: report['page_errors'].append(type(error).__name__))
                        login(page, 'B006TEACH', password)
                        bank = page.locator('.paper-bank')
                        expect(bank.get_by_text('正在加载或保存试卷…')).to_have_count(0)
                        if args.knowledge_fixture:
                            check_publication(app, password, page, context, bank, course_id, at, entry['checks'], args.output, channel)
                        else:
                            check_empty(page, context, bank, course_id, entry['checks'])
                            bank.screenshot(path=str(args.output/f'{channel}-teacher-empty.png'))
                            page.get_by_role('button', name='退出', exact=True).click()
                            login(page, 'B006STUD1', password)
                            expect(bank.get_by_text('共 0 份试卷')).to_be_visible()
                        expect(bank.get_by_role('button', name='编排新试卷')).to_have_count(0)
                        expect(bank.get_by_role('button', name='发布试卷并冻结名单')).to_have_count(0)
                        entry['checks'].append('student_without_teacher_controls')
                        assert not report['page_errors']
                        context.close()
                    finally:
                        browser.close()
        report['status'] = 'passed'
        print('C02b Chrome/Edge checks passed; scope:', report['scope'])
    except (AssertionError, OSError, RuntimeError, PlaywrightError) as error:
        report['status'] = 'failed'
        report['failure_type'] = type(error).__name__
        report['failure_location'] = [f'{frame.name}:{frame.lineno}' for frame in traceback.extract_tb(error.__traceback__)
                                      if frame.filename == __file__]
        raise RuntimeError('C02b browser verification failed; see redacted report') from None
    finally:
        report['finished_at'] = datetime.now(UTC).isoformat()
        (args.output/'browser-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
