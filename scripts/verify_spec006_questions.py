"""C02a real Chrome/Edge checks; --with-knowledge seeds tags through the real SPEC-005 API.

Run from the repository root: python -m scripts.verify_spec006_questions
Requires installed Chrome/Edge, optional requirements-browser.txt, and free 5000/5173 ports.
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
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import expect, sync_playwright
from werkzeug.security import generate_password_hash
from werkzeug.serving import WSGIRequestHandler, make_server

from backend.app import create_app
from backend.shared.db import connect, migrate

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'http://127.0.0.1:5173'


class QuietHandler(WSGIRequestHandler):
    def log(self, *_args, **_kwargs):
        pass


def prepare(path, password):
    migrate(path)
    app = create_app({'TESTING': True, 'DATABASE_PATH': str(path), 'APP_ORIGIN': ORIGIN,
                      'SECRET_KEY': secrets.token_hex(32)})
    with closing(connect(path)) as db:
        for number, role in (('B006ADMIN', 'admin'), ('B006TEACH', 'teacher')):
            db.execute('INSERT INTO user(student_no,name,password_hash,role,active,created_at,updated_at) '
                       'VALUES(?,?,?,?,1,?,?)', (number, number, generate_password_hash(password), role,
                                                datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat()))
    admin, teacher, student = [app.test_client() for _ in range(3)]
    def call(client, method, path, body=None, status=200):
        response = client.open('/api/v1'+path, method=method, json=body,
                               headers={'Origin': ORIGIN, 'X-CSRF-Token': getattr(client, 'csrf', '')})
        assert response.status_code == status, f'Unexpected HTTP status: {method} {path}'
        return response.json['data'] if response.status_code != 204 else None
    for client, number in ((admin, 'B006ADMIN'), (teacher, 'B006TEACH')):
        client.csrf = call(client, 'POST', '/auth/login', {'student_no': number, 'password': password})['csrf_token']
    user = call(student, 'POST', '/auth/register', {'student_no': 'B006STUD1', 'name': 'B006STUD1', 'password': password}, 201)
    teacher_id = call(teacher, 'GET', '/auth/session')['user']['id']
    course = call(admin, 'POST', '/courses', {'title': 'C02a受控CPU课程', 'teacher_id': teacher_id}, 201)
    call(teacher, 'POST', f"/courses/{course['id']}/members", {'user_id': user['user']['id'], 'member_role': 'student'}, 201)
    return app, course['id']


def seed_knowledge(app, course_id, password):
    teacher = app.test_client()
    response = teacher.post('/api/v1/auth/login', json={'student_no': 'B006TEACH', 'password': password},
                            headers={'Origin': ORIGIN})
    assert response.status_code == 200
    headers = {'Origin': ORIGIN, 'X-CSRF-Token': response.json['data']['csrf_token']}
    chapter = teacher.post(f'/api/v1/courses/{course_id}/chapters', json={'title': 'CPU'}, headers=headers)
    assert chapter.status_code == 201
    point = teacher.post(f"/api/v1/chapters/{chapter.json['data']['id']}/knowledge-points",
                         json={'title': 'CPU基础', 'content': '教学正文', 'published': True}, headers=headers)
    assert point.status_code == 201 and point.json['data']['id'] == 1


@contextmanager
def running(with_knowledge=False):
    for port in (5000, 5173):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
    with TemporaryDirectory(prefix='c02a-browser-') as temporary:
        password = secrets.token_urlsafe(24)
        app, course_id = prepare(Path(temporary)/'controlled.db', password)
        if with_knowledge:
            seed_knowledge(app, course_id, password)
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
                yield app, password, course_id
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()


def login(page, number, password):
    page.goto(ORIGIN)
    page.get_by_label('学号', exact=True).fill(number)
    page.get_by_label('密码', exact=True).fill(password)
    page.get_by_role('button', name='登录', exact=True).click()
    expect(page.locator('.question-bank')).to_be_visible()
    expect(page.locator('.question-bank').get_by_text('正在加载或保存…')).to_have_count(0)


def api(context, method, path, body=None, expected=200):
    session = context.request.get(ORIGIN+'/api/v1/auth/session').json()['data']
    headers = {'Origin': ORIGIN, 'X-CSRF-Token': session['csrf_token']}
    if method == 'GET':
        response = context.request.get(ORIGIN+'/api/v1'+path, headers=headers)
    else:
        response = context.request.fetch(ORIGIN+'/api/v1'+path, method=method, data=body, headers=headers)
    assert response.status == expected, f'{method} {path} returned unexpected status'
    return response.json()['data']


def select_field(form, label):
    # Select labels include their option text, so get_by_label(exact) cannot match them.
    return form.locator(f'label:has(> span:text-is("{label}")) select')


def check_bank(app, password, page, context, bank, course_id, output, channel, checks):
    expect(bank.get_by_text('共 0 道题目', exact=True)).to_be_visible()
    bank.get_by_role('button', name='新增题目', exact=True).click()
    form = bank.locator('.question-editor')
    select_field(form, '题型').select_option('boolean')
    form.get_by_label('题干', exact=True).fill('PC保存指令地址？')
    select_field(form, '难度').select_option('easy')
    select_field(form, '正确答案').select_option('true')
    form.get_by_label('CPU基础', exact=True).check()
    form.get_by_label('开放为公开练习（曾公开后不再具备保密资格）', exact=True).check()
    form.get_by_role('button', name='保存新版本', exact=True).click()
    expect(bank.get_by_text('新版本已保存，旧版本保留。', exact=True)).to_be_visible()
    expect(bank.get_by_text('共 1 道题目', exact=True)).to_be_visible()
    expect(bank.get_by_role('button', name='#1 · v1 · PC保存指令地址？', exact=True)).to_be_visible()
    checks.append('teacher_ui_creates_public_boolean_question_with_real_knowledge_tag')
    first_version = api(context, 'GET', f'/courses/{course_id}/questions')[0]
    bank.get_by_role('button', name='新增题目', exact=True).click()
    form = bank.locator('.question-editor')
    form.get_by_label('题干', exact=True).fill('C02保密单选')
    form.get_by_label('选项 1 内容', exact=True).fill('选项甲')
    form.get_by_label('选项 2 内容', exact=True).fill('选项乙')
    select_field(form, '正确答案').select_option('A')
    form.get_by_label('CPU基础', exact=True).check()
    form.get_by_role('button', name='保存新版本', exact=True).click()
    expect(bank.get_by_text('共 2 道题目', exact=True)).to_be_visible()
    checks.append('teacher_ui_creates_private_single_choice_with_default_off_practice')
    bank.get_by_role('button', name='#1 · v1 · PC保存指令地址？', exact=True).click()
    expect(bank.get_by_text('题目 #1 · 版本 1', exact=True)).to_be_visible()
    expect(bank.get_by_text('参考答案：true', exact=True)).to_be_visible()
    bank.get_by_role('button', name='编辑为新版本', exact=True).click()
    form = bank.locator('.question-editor')
    form.get_by_label('题干', exact=True).fill('PC保存指令地址？（修订）')
    form.get_by_role('button', name='保存新版本', exact=True).click()
    expect(bank.get_by_text('题目 #1 · 版本 2', exact=True)).to_be_visible()
    checks.append('teacher_ui_edit_appends_version_two_and_keeps_teacher_answer')
    paper = api(context, 'POST', f'/courses/{course_id}/papers', {
        'title': 'C02a固定版本卷', 'kind': 'homework',
        'items': [{'question_version_id': first_version['version_id'], 'points': 5}]}, 201)
    detail = api(context, 'GET', f"/papers/{paper['id']}")
    assert detail['items'][0]['version_id'] == first_version['version_id']
    assert detail['items'][0]['stem'] == 'PC保存指令地址？'
    assert detail['items'][0]['answer'] is True
    checks.append('paper_created_after_edit_keeps_fixed_old_version_and_answer')
    page.set_viewport_size({'width': 390, 'height': 844})
    bank.scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    bank.screenshot(path=str(output/f'{channel}-teacher-versions.png'))
    checks.append('390px_teacher_question_detail_without_horizontal_overflow')
    page.get_by_role('button', name='退出', exact=True).click()
    login(page, 'B006STUD1', password)
    expect(bank.get_by_text('共 1 道题目', exact=True)).to_be_visible()
    expect(bank.get_by_text('C02保密单选')).to_have_count(0)
    expect(bank.get_by_role('button', name='新增题目')).to_have_count(0)
    bank.get_by_role('button', name='#1 · v2 · PC保存指令地址？（修订）', exact=True).click()
    expect(bank.get_by_text('PC保存指令地址？（修订）', exact=True)).to_be_visible()
    expect(bank.get_by_text('参考答案：', exact=False)).to_have_count(0)
    expect(bank.get_by_text('解析：', exact=False)).to_have_count(0)
    listed = api(context, 'GET', f'/courses/{course_id}/questions')
    assert len(listed) == 1 and 'answer' not in listed[0] and 'explanation' not in listed[0]
    bank.screenshot(path=str(output/f'{channel}-student-public.png'))
    checks.append('student_real_login_sees_only_latest_public_version_without_answers')
    with closing(connect(app.config['DATABASE_PATH'])) as db:
        assert db.execute('SELECT count(*) FROM question').fetchone()[0] == 2
        assert db.execute('SELECT count(*) FROM question_version').fetchone()[0] == 3
        versions = [row[0] for row in db.execute(
            'SELECT version FROM question_version WHERE question_id=1 ORDER BY version')]
        assert versions == [1, 2]
        public = [row[0] for row in db.execute('SELECT ever_public FROM question ORDER BY id')]
        assert public == [1, 0]
    checks.append('database_keeps_two_identities_three_versions_and_public_history')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'logs/spec-006-questions')
    parser.add_argument('--with-knowledge', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'started_at': datetime.now(UTC).isoformat(),
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'with_knowledge': args.with_knowledge,
              'scope': 'real 001/005/006 knowledge, question versions and fixed-version paper HTTP/UI'
                       if args.with_knowledge
                       else 'real SPEC-001/006 HTTP/UI; missing knowledge/paper remain blocked; '
                            'no dependency fixtures',
              'browsers': [], 'page_errors': []}
    try:
        with sync_playwright() as playwright:
            for channel in (('chrome', 'msedge') if args.with_knowledge else ('chrome',)):
                with running(args.with_knowledge) as (app, password, course_id):
                    browser = playwright.chromium.launch(channel=channel, headless=True)
                    try:
                        entry = {'channel': channel, 'version': browser.version, 'checks': []}
                        report['browsers'].append(entry)
                        report.setdefault('browser', {'channel': channel, 'version': browser.version})
                        context = browser.new_context(viewport={'width': 1440, 'height': 1000},
                                                      timezone_id='Asia/Shanghai')
                        page = context.new_page()
                        page.on('pageerror', lambda error: report['page_errors'].append(type(error).__name__))
                        login(page, 'B006TEACH', password)
                        bank = page.locator('.question-bank')
                        if args.with_knowledge:
                            check_bank(app, password, page, context, bank, course_id, args.output, channel,
                                       entry['checks'])
                        else:
                            expect(bank.get_by_text('共 0 道题目')).to_be_visible()
                            expect(bank.get_by_text('请先在课程中创建知识点，再添加题目。')).to_be_visible()
                            expect(bank.get_by_role('button', name='新增题目')).to_be_disabled()
                            entry['checks'].append('teacher_real_login_empty_list_missing_tag_disables_creation')
                            session = context.request.get(ORIGIN+'/api/v1/auth/session').json()['data']
                            response = context.request.post(
                                ORIGIN+f'/api/v1/courses/{course_id}/questions',
                                headers={'Origin': ORIGIN, 'X-CSRF-Token': session['csrf_token']},
                                data={'type': 'boolean', 'stem': 'PC保存指令地址？', 'options': [],
                                      'answer': True, 'difficulty': 'easy', 'knowledge_ids': [1]})
                            assert response.status == 400
                            assert response.json()['error']['code'] == 'VALIDATION_ERROR'
                            assert context.request.get(
                                ORIGIN+f'/api/v1/courses/{course_id}/questions').json()['total'] == 0
                            entry['checks'].append(
                                'real_http_missing_knowledge_rejects_without_partial_question')
                            page.set_viewport_size({'width': 390, 'height': 844})
                            bank.scroll_into_view_if_needed()
                            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                            bank.screenshot(path=str(args.output/f'{channel}-teacher-blocked.png'))
                            entry['checks'].append('390px_teacher_bank_no_horizontal_overflow')
                            page.get_by_role('button', name='退出', exact=True).click()
                            login(page, 'B006STUD1', password)
                            expect(bank.get_by_role('button', name='新增题目')).to_have_count(0)
                            expect(bank.get_by_text('共 0 道题目')).to_be_visible()
                            bank.screenshot(path=str(args.output/f'{channel}-student-empty.png'))
                            entry['checks'].append(
                                'student_real_login_empty_bank_without_teacher_controls')
                        assert not report['page_errors']
                        context.close()
                    finally:
                        browser.close()
        report['status'] = 'passed'
        print(f"Chrome/Edge {len(report['browsers'])} channel(s): "
              f"{sum(len(item['checks']) for item in report['browsers'])} C02a checks passed")
    except (AssertionError, OSError, RuntimeError, PlaywrightError) as error:
        report['status'] = 'failed'
        report['failure_type'] = type(error).__name__
        report['failure_location'] = [f'{frame.name}:{frame.lineno}'
                                      for frame in traceback.extract_tb(error.__traceback__)
                                      if frame.filename == __file__]
        raise RuntimeError('C02a browser verification failed; report contains only redacted failure type') from None
    finally:
        report['finished_at'] = datetime.now(UTC).isoformat()
        (args.output/'browser-results.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
