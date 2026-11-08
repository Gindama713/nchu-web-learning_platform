"""R37 linked quiz socket/UI checks; preparation UI is absent, never fabricated."""

import argparse
import json
import subprocess
import traceback
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from backend.shared.db import connect
from scripts.verify_spec006_papers import running
from scripts.verify_spec006_questions import ORIGIN, ROOT, login


def request(context, method, path, data=None, status=200, *, trace):
    session = context.request.get(ORIGIN+'/api/v1/auth/session').json()['data']
    response = context.request.fetch(ORIGIN+'/api/v1'+path, method=method, data=data,
                                     headers={'Origin': ORIGIN, 'X-CSRF-Token': session['csrf_token']})
    value = response.json() if response.status != 204 else None
    trace.append({'method': method, 'path': path, 'status': response.status, 'response': value})
    assert response.status == status, trace[-1]
    return value.get('data', value) if value else None


def bank(page):
    return page.locator('.paper-bank').filter(has=page.get_by_role('heading', name='随堂测', exact=True))


def open_quiz(page, quiz_id, state):
    view = bank(page)
    view.get_by_role('button', name='重新加载试卷', exact=True).click()
    view.get_by_role('button', name=f'#{quiz_id} · R37关联测验 · {state}', exact=True).click()
    return view


def screenshot(page, locator, output, name):
    page.set_viewport_size({'width': 390, 'height': 1200})
    locator.scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    locator.screenshot(path=str(output/name))
    page.set_viewport_size({'width': 1440, 'height': 1000})


def verify(playwright, channel, output, report):
    with running(False) as (app, password, course_id, at):
        browser = playwright.chromium.launch(channel=channel, headless=True)
        entry = {'channel': channel, 'version': browser.version, 'checks': [], 'page_errors': [], 'http': []}
        report['browsers'].append(entry)
        try:
            teacher = browser.new_context(viewport={'width': 1440, 'height': 1000})
            teacher_page = teacher.new_page()
            teacher_page.on('pageerror', lambda error: entry['page_errors'].append(str(error)))
            login(teacher_page, 'B006TEACH', password)

            def call(context, method, path, data=None, status=200):
                return request(context, method, path, data, status, trace=entry['http'])

            chapter = call(teacher, 'POST', f'/courses/{course_id}/chapters', {'title': 'R37'}, 201)
            knowledge = call(teacher, 'POST', f"/chapters/{chapter['id']}/knowledge-points",
                             {'title': 'R37知识', 'content': '正文', 'published': True}, 201)
            q = call(teacher, 'POST', f'/courses/{course_id}/questions', {
                'type': 'boolean', 'stem': 'R37 PC保存下一条指令地址？', 'options': [], 'answer': True,
                'difficulty': 'easy', 'knowledge_ids': [knowledge['id']], 'explanation': 'R37受保护解析'}, 201)
            quiz = call(teacher, 'POST', f'/courses/{course_id}/papers', {
                'title': 'R37关联测验', 'kind': 'quiz', 'confidential': True,
                'items': [{'question_version_id': q['version_id'], 'points': 10}]}, 201)
            prep = call(teacher, 'POST', f'/courses/{course_id}/preparations', {
                'title': 'R37关联备课', 'knowledge_ids': [knowledge['id']], 'resource_version_ids': [],
                'question_version_ids': [], 'quiz_ids': [quiz['id']]}, 201)
            call(teacher, 'POST', f"/preparations/{prep['id']}/publish", {}, 404)
            start, end = at+timedelta(minutes=1), at+timedelta(minutes=2)
            call(teacher, 'POST', f'/courses/{course_id}/quizzes', {
                'paper_id': quiz['id'], 'start_at': start.isoformat(), 'end_at': end.isoformat(),
                'confidentiality_note': '确认未公开且非简单复制'}, 201)
            late = browser.new_context()
            registered = late.request.post(ORIGIN+'/api/v1/auth/register', data={
                'student_no': 'R37LATE01', 'name': 'R37 late', 'password': password}, headers={'Origin': ORIGIN})
            assert registered.status == 201
            late_id = registered.json()['data']['user']['id']
            late.request.post(ORIGIN+'/api/v1/auth/login', data={
                'student_no': 'R37LATE01', 'password': password}, headers={'Origin': ORIGIN})
            call(teacher, 'POST', f'/courses/{course_id}/members', {'user_id': late_id, 'member_role': 'student'}, 201)
            call(teacher, 'POST', f"/preparations/{prep['id']}/publish", {})
            copied = call(teacher, 'POST', f"/preparations/{prep['id']}/copy", {'title': 'R37副本'}, 201)
            assert copied['quiz_ids'] == [quiz['id']] and copied['status'] == 'draft'
            call(teacher, 'PATCH', f"/preparations/{prep['id']}", {'quiz_ids': []}, 409)
            entry['checks'].append('socket_real_knowledge_question_quiz_preparation_copy_and_publish_freeze')

            student = browser.new_context(viewport={'width': 1440, 'height': 1000})
            page = student.new_page()
            page.on('pageerror', lambda error: entry['page_errors'].append(str(error)))
            login(page, 'B006STUD1', password)
            detail = call(student, 'GET', f"/preparations/{prep['id']}")
            assert detail['quiz_ids'] == [quiz['id']]
            assert set(detail['quizzes'][0]) == {'id', 'title', 'start_at', 'end_at'}
            entry['known_contract_failures'] = ['R37-004-01: 404 NOT_FOUND instead of 409 QUIZ_NOT_PUBLISHED',
                                                 'R37-004-02: preparation metadata missing window_state']
            view = open_quiz(page, detail['quiz_ids'][0], '未开始')
            expect(view.get_by_text('试卷尚未开始，开始后可查看题目。')).to_be_visible()
            expect(view.locator('.attempt-answer-form')).to_have_count(0)
            assert 'items' not in call(student, 'GET', f"/papers/{quiz['id']}")
            screenshot(page, view, output, f'{channel}-prestart.png')
            entry['checks'].append('linked_original_id_existing_quiz_ui_prestart_no_questions')

            app.config['TEST_NOW'] = start
            view = open_quiz(page, quiz['id'], '进行中')
            form = view.locator('.attempt-answer-form')
            expect(form.get_by_text(q['stem'], exact=True)).to_be_visible()
            form.get_by_label('第 1 题作答 错误', exact=True).check()
            form.get_by_label('确认交卷，接受漏答0分且提交后不可修改', exact=True).check()
            with page.expect_response(lambda response: response.url.endswith(f"/quizzes/{quiz['id']}/attempts")) as submitted:
                form.get_by_role('button', name='提交整份答卷', exact=True).click()
            assert submitted.value.status == 201
            attempt_id = submitted.value.json()['data']['id']
            app.config['TEST_NOW'] = end
            view = open_quiz(page, quiz['id'], '已截止')
            expect(view.locator('.attempt-reference')).to_have_count(0)
            expect(view.get_by_text('解析：R37受保护解析', exact=True)).to_have_count(0)
            closed = call(student, 'GET', f"/papers/{quiz['id']}")
            assert closed['review_at'] is None and 'answer' not in closed['items'][0]
            attempt = call(student, 'GET', f'/attempts/{attempt_id}')
            assert 'answer' not in attempt['answers'][0]
            screenshot(page, view, output, f'{channel}-unreviewed.png')
            entry['checks'].append('real_ui_submission_closed_unreviewed_paper_and_attempt_protected')

            teacher_view = open_quiz(teacher_page, quiz['id'], '已截止')
            teacher_view.get_by_role('button', name='发布讲评并开放答案', exact=True).click()
            expect(teacher_view.get_by_text('讲评已发布。学生重新加载后可查看答案与解析。', exact=True)).to_be_visible()
            view = open_quiz(page, quiz['id'], '已截止')
            expect(view.locator('.attempt-reference').get_by_text('解析：R37受保护解析', exact=True)).to_be_visible()
            assert call(student, 'GET', f"/papers/{quiz['id']}")['items'][0]['answer'] is True
            screenshot(page, view, output, f'{channel}-reviewed.png')
            entry['checks'].append('real_teacher_ui_review_releases_original_answers')

            late_page = late.new_page()
            late_page.on('pageerror', lambda error: entry['page_errors'].append(str(error)))
            late_page.goto(ORIGIN)
            late_detail = call(late, 'GET', f"/preparations/{prep['id']}")
            assert late_detail['quiz_ids'] == [] and late_detail['quizzes'] == []
            expect(bank(late_page).get_by_text('共 0 份试卷', exact=True)).to_be_visible()
            call(late, 'GET', f"/papers/{quiz['id']}", status=404)
            student_id = student.request.get(ORIGIN+'/api/v1/auth/session').json()['data']['user']['id']
            call(teacher, 'DELETE', f'/courses/{course_id}/members/{student_id}', status=204)
            for path in (f"/preparations/{prep['id']}", f"/papers/{quiz['id']}", f'/attempts/{attempt_id}'):
                call(student, 'GET', path, status=404)
            page.reload()
            expect(bank(page).get_by_text('R37 PC保存下一条指令地址？', exact=True)).to_have_count(0)
            entry['checks'].append('late_member_filtered_from_preparation_and_quiz_ui_revocation_rechecked')
            with closing(connect(app.config['DATABASE_PATH'])) as db:
                entry['database'] = {
                    'links': [dict(r) for r in db.execute('SELECT * FROM preparation_quiz ORDER BY preparation_id')],
                    'papers': [dict(r) for r in db.execute('SELECT id,status,start_at,end_at,review_at FROM paper')],
                    'roster': [dict(r) for r in db.execute('SELECT * FROM paper_participant')],
                    'attempt_count': db.execute('SELECT count(*) FROM attempt').fetchone()[0],
                    'foreign_key_check': [list(r) for r in db.execute('PRAGMA foreign_key_check')],
                }
            assert len(entry['database']['papers']) == len(entry['database']['roster']) == 1
            assert len(entry['database']['links']) == 2 and entry['database']['attempt_count'] == 1
            assert entry['database']['foreign_key_check'] == [] and entry['page_errors'] == []
            entry['result'] = 'covered checks passed; complete R37 remains blocked'
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {
        'at_utc': datetime.now(UTC).isoformat(),
        'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'dirty_paths': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines(),
        'scope': 'real socket HTTP + existing 008 UI; preparation UI absent in frontend/js/main.js',
        'fixtures': 'initial admin/teacher bootstrap and TEST_NOW; course/member helper uses actual handlers; business setup uses socket HTTP',
        'preparation_ui': 'blocked: no preparation component or route; no teammate UI written',
        'browsers': [],
    }
    try:
        with sync_playwright() as playwright:
            for channel in ('chrome', 'msedge'):
                verify(playwright, channel, args.output, report)
    except Exception:
        report['failure'] = traceback.format_exc()
        raise
    finally:
        (args.output/'browsers.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps([{'channel': x['channel'], 'checks': len(x['checks']), 'page_errors': x['page_errors']}
                      for x in report['browsers']]))


if __name__ == '__main__':
    main()
