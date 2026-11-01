"""R01 installed Chrome/Edge: real resource UI, socket APIs and imported quiz UI.

Only reuses the existing server/login helpers, never either C12b script main.
"""

import argparse
import hashlib
import json
import subprocess
import traceback
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import expect, sync_playwright

from scripts.verify_spec006_papers import running
from scripts.verify_spec006_questions import ORIGIN, ROOT, login
from tests.test_resource_question_integration import bank, facts


def verify(playwright, channel, output, report):
    with running(False) as (app, password, cid, at):
        app.config['UPLOAD_ROOT'] = str(Path(app.config['DATABASE_PATH']).parent/'uploads')
        browser = playwright.chromium.launch(channel=channel, headless=True)
        entry = {'channel': channel, 'version': browser.version, 'requests': [], 'checkpoints': [], 'checks': []}
        report['browsers'].append(entry)
        teacher = browser.new_context(viewport={'width': 1440, 'height': 1000})
        student = browser.new_context(viewport={'width': 1440, 'height': 1000})
        try:
            tp, sp = teacher.new_page(), student.new_page()
            for page in (tp, sp):
                page.on('pageerror', lambda error: report['page_errors'].append(type(error).__name__))
            login(tp, 'B006TEACH', password)
            login(sp, 'B006STUD1', password)

            def record(response):
                raw = response.body()
                try:
                    body = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    body = None
                entry['requests'].append({'path': response.url.split('/api/v1')[-1],
                    'status': response.status, 'body': body, 'bytes': len(raw),
                    'sha256': hashlib.sha256(raw).hexdigest()})
                return response

            def request(context, method, path, data=None, status=200, key=None):
                session = context.request.get(ORIGIN+'/api/v1/auth/session').json()['data']
                headers = {'Origin': ORIGIN, 'X-CSRF-Token': session['csrf_token']}
                if key:
                    headers['Idempotency-Key'] = key
                response = record(context.request.fetch(ORIGIN+'/api/v1'+path, method=method,
                                                        data=data, headers=headers))
                assert response.status == status, f'{method} {path}: {response.status}'
                return response

            def checkpoint(label):
                value = facts(app.config['DATABASE_PATH'])
                assert value['foreign_key_check'] == []
                entry['checkpoints'].append({'label': label, 'db': value})
                return value

            def capture(locator, name):
                sp.set_viewport_size({'width': 390, 'height': 844})
                locator.scroll_into_view_if_needed()
                assert sp.evaluate('document.documentElement.scrollWidth <= innerWidth')
                locator.screenshot(path=str(output/f'{channel}-{name}.png'))
                sp.set_viewport_size({'width': 1440, 'height': 1000})

            def no_secrets(value):
                if isinstance(value, dict):
                    assert 'answer' not in value and 'explanation' not in value
                    for child in value.values():
                        no_secrets(child)
                elif isinstance(value, list):
                    for child in value:
                        no_secrets(child)

            ch = request(teacher, 'POST', f'/courses/{cid}/chapters', {'title': 'R01'}, 201).json()['data']['id']
            kid = request(teacher, 'POST', f'/chapters/{ch}/knowledge-points',
                {'title': 'R01知识', 'content': '真实知识', 'published': True}, 201).json()['data']['id']
            tr = tp.locator('.resource-module')
            expect(tr).to_have_attribute('aria-busy', 'false')
            upload = tr.locator('.resource-upload')
            upload.get_by_label('标题', exact=True).fill('R01题库源文件')
            upload.locator('select').first.select_option('question_bank')
            bad = json.dumps([bank(kid), bank(kid, answer='invalid')], ensure_ascii=False).encode()
            upload.get_by_label('文件', exact=True).set_input_files(
                {'name': 'r01-bad.json', 'mimeType': 'application/json', 'buffer': bad})
            with tp.expect_response(lambda r: r.url.endswith('/resources') and r.request.method == 'POST') as pending:
                upload.get_by_role('button', name='上传', exact=True).click()
            created = record(pending.value).json()['data']
            rid = created['resource_id']
            row = tr.locator('tbody > tr').filter(has=tp.get_by_text('R01题库源文件', exact=True)).first
            row.get_by_text('版本历史', exact=True).click()
            expect(row.get_by_role('button', name='导入题库', exact=True)).to_have_count(1)
            before = checkpoint('before invalid UI import')
            with tp.expect_response(lambda r: '/question-imports' in r.url) as pending:
                row.get_by_role('button', name='导入题库', exact=True).click()
            assert record(pending.value).status == 400
            expect(tr.get_by_role('alert')).to_contain_text('题目[1]')
            assert checkpoint('after invalid UI import') == before
            good = json.dumps([bank(kid)], ensure_ascii=False).encode()
            version_form = row.locator('.resource-version-form')
            version_form.locator('input[type=file]').set_input_files(
                {'name': 'r01-good.json', 'mimeType': 'application/json', 'buffer': good})
            with tp.expect_response(lambda r: r.url.endswith('/versions') and r.request.method == 'POST') as pending:
                version_form.get_by_role('button', name='上传新版本', exact=True).click()
            valid = record(pending.value).json()['data']
            expect(tr).to_have_attribute('aria-busy', 'false')
            row.get_by_text('版本历史', exact=True).click()
            expect(row.get_by_role('button', name='导入题库', exact=True)).to_have_count(2)
            with tp.expect_response(lambda r: '/question-imports' in r.url) as pending:
                row.get_by_role('button', name='导入题库', exact=True).first.click()
            imported = record(pending.value)
            assert imported.status == 201
            key = imported.request.headers['idempotency-key']
            expected_bytes = imported.body()
            after = checkpoint('after valid UI import')
            replay = request(teacher, 'POST', f'/resources/{rid}/question-imports',
                             {'resource_version_id': valid['id']}, 201, key)
            assert replay.body() == expected_bytes
            assert checkpoint('same UI key replay exact bytes') == after
            request(teacher, 'POST', f'/resources/{rid}/question-imports',
                    {'resource_version_id': created['id']}, 409, key)
            entry['checks'].append('real resource UI multipart bad v1/good v2; invalid batch no writes; UI import; exact key replay/conflict')

            sr = sp.locator('.resource-module')
            sr.get_by_role('button', name='检索', exact=True).click()
            expect(sr).to_have_attribute('aria-busy', 'false')
            expect(sr.get_by_text('暂无资源。', exact=True)).to_be_visible()
            expect(sr.get_by_text('R01题库源文件', exact=True)).to_have_count(0)
            capture(sr, 'student-resources')
            assert request(student, 'GET', f'/courses/{cid}/resources?kind=question_bank').json()['data'] == []
            request(student, 'GET', f'/resources/{rid}/versions', status=404)
            for version, content in ((created, bad), (valid, good)):
                path = f"/resource-versions/{version['id']}/content?intent=download&event_id={uuid4()}"
                assert request(teacher, 'GET', path).body() == content
                request(student, 'GET', path, status=404)
                blocked = request(teacher, 'POST', f'/courses/{cid}/preparations',
                    {'title': 'R01源备课', 'knowledge_ids': [], 'resource_version_ids': [version['id']],
                     'question_version_ids': [], 'quiz_ids': []}, 201).json()['data']['id']
                before = checkpoint('before source preparation publish')
                request(teacher, 'POST', f'/preparations/{blocked}/publish', {}, 404)
                assert checkpoint('source publication rejection atomic') == before
                request(student, 'GET', f'/preparations/{blocked}', status=404)
            entry['checks'].append('student resource UI hides source; both source downloads404; teacher byte equality; both source preparation publications rejected')

            vid = imported.json()['data']['question_version_ids'][0]
            q = request(teacher, 'GET', f'/courses/{cid}/questions').json()['data'][0]
            request(teacher, 'PATCH', f"/questions/{q['id']}", {'stem': 'R01题目新版'})
            pid = request(teacher, 'POST', f'/courses/{cid}/papers',
                {'title': 'R01导入随堂测', 'kind': 'quiz', 'confidential': True,
                 'items': [{'question_version_id': vid, 'points': 10}]}, 201).json()['data']['id']
            request(teacher, 'POST', f'/courses/{cid}/quizzes',
                {'paper_id': pid, 'start_at': (at+timedelta(minutes=1)).isoformat(),
                 'end_at': (at+timedelta(minutes=3)).isoformat(), 'confidentiality_note': '未公开非简单复制'}, 201)
            prep = request(teacher, 'POST', f'/courses/{cid}/preparations',
                {'title': 'R01真实测验备课', 'knowledge_ids': [], 'resource_version_ids': [],
                 'question_version_ids': [], 'quiz_ids': [pid]}, 201).json()['data']['id']
            request(teacher, 'POST', f'/preparations/{prep}/publish', {})
            metadata = request(student, 'GET', f'/preparations/{prep}').json()['data']
            no_secrets(metadata)
            assert metadata['quiz_ids'] == [pid]
            entry['r37_metadata_missing_window_state'] = 'window_state' not in metadata['quizzes'][0]
            quiz = sp.locator('.paper-bank').filter(has=sp.get_by_role('heading', name='随堂测', exact=True))

            def open_quiz(state):
                quiz.get_by_role('button', name='重新加载试卷', exact=True).click()
                quiz.get_by_role('button', name=f'#{pid} · R01导入随堂测 · {state}', exact=True).click()
                expect(quiz).to_have_attribute('aria-busy', 'false')

            open_quiz('未开始')
            expect(quiz.get_by_text('R01 PC保存指令地址？', exact=True)).to_have_count(0)
            assert 'items' not in request(student, 'GET', f'/papers/{pid}').json()['data']
            capture(quiz, 'prestart')
            app.config['TEST_NOW'] = at+timedelta(minutes=2)
            open_quiz('进行中')
            form = quiz.locator('.attempt-answer-form')
            form.get_by_label('第 1 题作答 错误', exact=True).check()
            form.get_by_label('确认交卷，接受漏答0分且提交后不可修改', exact=True).check()
            with sp.expect_response(lambda r: r.url.endswith('/attempts') and r.request.method == 'POST') as pending:
                form.get_by_role('button', name='提交整份答卷', exact=True).click()
            submitted = record(pending.value)
            assert submitted.status == 201
            aid = submitted.json()['data']['id']
            app.config['TEST_NOW'] = at+timedelta(minutes=4)
            open_quiz('已截止')
            for path in (f'/papers/{pid}', f'/attempts/{aid}', '/users/me/wrong-questions',
                         f'/preparations/{prep}', f'/courses/{cid}/preparations'):
                no_secrets(request(student, 'GET', path).json()['data'])
            expect(quiz.get_by_text('解析：R01_SECRET_EXPLANATION', exact=True)).to_have_count(0)
            capture(quiz, 'unreviewed')
            request(teacher, 'PATCH', f"/questions/{q['id']}", {'practice_available': True}, 409)
            entry['checks'].append('imported original question version -> quiz/real preparation; UI prestart no stem; actual UI answer; closed unreviewed paper/attempt/wrong/preparation no secrets')
            request(teacher, 'POST', f'/quizzes/{pid}/review', {})
            open_quiz('已截止')
            expect(quiz.locator('.attempt-result').get_by_text('解析：R01_SECRET_EXPLANATION', exact=True)).to_be_visible()
            capture(quiz, 'reviewed')
            final = checkpoint('review releases only original imported question version')
            assert final['counts']['question'] == 1 and final['counts']['question_import'] == 1
            assert final['counts']['attempt'] == 1 and final['counts']['paper_participant'] == 1
            assert not report['page_errors']
            entry['checks'].append('explicit real review -> existing quiz UI answer release; DB one import/question/attempt/frozen participant; 390px screenshots')
        finally:
            teacher.close()
            student.close()
            browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'logs/r01/browsers')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'dirty_paths': subprocess.check_output(['git', 'status', '--porcelain'], text=True).splitlines(),
              'layer': 'real socket HTTP + resource/quiz UI; helper bootstrap via handlers, TEST_NOW only',
              'browsers': [], 'page_errors': []}
    try:
        with sync_playwright() as playwright:
            for channel in ('chrome', 'msedge'):
                verify(playwright, channel, args.output, report)
        report['status'] = 'passed'
    except (AssertionError, OSError, RuntimeError, ValueError, PlaywrightError) as error:
        report.update(status='failed', error_type=type(error).__name__,
                      locations=[f'{f.name}:{f.lineno}' for f in traceback.extract_tb(error.__traceback__)])
        raise RuntimeError('R01 browser check failed; see report') from None
    finally:
        (args.output/'browsers.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('R01 Chrome/Edge socket + UI passed')


if __name__ == '__main__':
    main()
