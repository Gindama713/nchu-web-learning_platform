"""C02a real Chrome/HTTP check on develop's baseline: no knowledge/paper fixtures.

Run from the repository root: python -m scripts.verify_spec006_questions
Requires installed Chrome, optional requirements-browser.txt, and free 5000/5173 ports.
"""

import argparse
import json
import secrets
import shutil
import socket
import subprocess
import threading
import time
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


@contextmanager
def running():
    for port in (5000, 5173):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
    with TemporaryDirectory(prefix='c02a-browser-') as temporary:
        password = secrets.token_urlsafe(24)
        app, course_id = prepare(Path(temporary)/'controlled.db', password)
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
                yield password, course_id
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'logs/spec-006-questions')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'started_at': datetime.now(UTC).isoformat(),
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'scope': 'real SPEC-001/006 HTTP/UI; missing knowledge/paper remain blocked; no dependency fixtures',
              'checks': [], 'page_errors': []}
    try:
        with running() as (password, course_id), sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            try:
                report['browser'] = {'channel': 'chrome', 'version': browser.version}
                context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                page = context.new_page()
                page.on('pageerror', lambda error: report['page_errors'].append(type(error).__name__))
                login(page, 'B006TEACH', password)
                bank = page.locator('.question-bank')
                expect(bank.get_by_text('共 0 道题目')).to_be_visible()
                expect(bank.get_by_text('知识标签暂不可用，请等待知识模块接入后重新加载。')).to_be_visible()
                expect(bank.get_by_role('button', name='新增题目')).to_be_disabled()
                report['checks'].append('teacher_real_login_empty_list_missing_knowledge_disables_creation')
                session = context.request.get(ORIGIN+'/api/v1/auth/session').json()['data']
                response = context.request.post(ORIGIN+f'/api/v1/courses/{course_id}/questions',
                                                headers={'Origin': ORIGIN, 'X-CSRF-Token': session['csrf_token']},
                                                data={'type': 'boolean', 'stem': 'PC保存指令地址？', 'options': [],
                                                      'answer': True, 'difficulty': 'easy', 'knowledge_ids': [1]})
                assert response.status == 503
                assert response.json()['error']['code'] == 'DEPENDENCY_UNAVAILABLE'
                assert context.request.get(ORIGIN+f'/api/v1/courses/{course_id}/questions').json()['total'] == 0
                report['checks'].append('real_http_missing_knowledge_rejects_without_partial_question')
                page.set_viewport_size({'width': 390, 'height': 844})
                bank.scroll_into_view_if_needed()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                bank.screenshot(path=str(args.output/'chrome-teacher-blocked.png'))
                report['checks'].append('390px_teacher_bank_no_horizontal_overflow')
                page.get_by_role('button', name='退出', exact=True).click()
                login(page, 'B006STUD1', password)
                expect(bank.get_by_role('button', name='新增题目')).to_have_count(0)
                expect(bank.get_by_text('共 0 道题目')).to_be_visible()
                bank.screenshot(path=str(args.output/'chrome-student-empty.png'))
                report['checks'].append('student_real_login_empty_bank_without_teacher_controls')
                assert not report['page_errors']
                context.close()
            finally:
                browser.close()
        report['status'] = 'passed'
        print(f"Chrome {report['browser']['version']}: {len(report['checks'])} C02a checks passed")
    except (AssertionError, OSError, RuntimeError, PlaywrightError) as error:
        report['status'] = 'failed'
        report['failure_type'] = type(error).__name__
        raise RuntimeError('C02a browser verification failed; report contains only redacted failure type') from None
    finally:
        report['finished_at'] = datetime.now(UTC).isoformat()
        (args.output/'browser-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
