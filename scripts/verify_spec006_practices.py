"""C04 Chrome/Edge actual API/SQLite/UI regression with real SPEC-005 knowledge.

Run twice, with and without --knowledge-fixture. New contexts/services are closed on exit.
No passwords, cookies, CSRF tokens, answers or request payloads are written to reports.
"""

import argparse
import json
import subprocess
import traceback
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import expect, sync_playwright

from backend.shared.db import connect
from scripts.verify_spec006_papers import running, write
from scripts.verify_spec006_questions import ORIGIN, ROOT, login


def mobile(page, bank, path):
    page.set_viewport_size({'width': 390, 'height': 844})
    bank.scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    bank.screenshot(path=str(path))


def practice(context, question_id, version_id, answer):
    session = context.request.get(ORIGIN+'/api/v1/auth/session').json()['data']
    return context.request.fetch(
        ORIGIN+f'/api/v1/questions/{question_id}/practice-attempts', method='POST',
        data={'question_version_id': version_id, 'answer': answer},
        headers={'Origin': ORIGIN, 'X-CSRF-Token': session['csrf_token'], 'Idempotency-Key': str(uuid4())})


def full(app, password, page, context, course_id, at, output, channel, checks):
    questions = []
    for kind, expected in (('single', 'A'), ('multiple', ['A', 'B']), ('boolean', False), ('numeric', 0.2)):
        questions.append(write(context, 'POST', f'/courses/{course_id}/questions', {
            'type': kind, 'stem': f'C04公开{kind}题', 'answer': expected,
            'options': [{'key': 'A', 'text': '选项甲'}, {'key': 'B', 'text': '选项乙'}] if kind in ('single', 'multiple') else [],
            'tolerance': 0.1 if kind == 'numeric' else 0, 'difficulty': 'easy', 'knowledge_ids': [1],
            'practice_available': True, 'explanation': '固定公开版本的练习解析'}, 201)['data'])
    secret = write(context, 'POST', f'/courses/{course_id}/questions', {
        'type': 'boolean', 'stem': 'C04保密题', 'answer': True, 'options': [], 'difficulty': 'easy',
        'knowledge_ids': [1], 'explanation': '保密卷的讲评解析'}, 201)['data']
    short = write(context, 'POST', f'/courses/{course_id}/questions', {
        'type': 'short', 'stem': 'C04简答题', 'answer': '参考文本', 'options': [], 'difficulty': 'easy',
        'knowledge_ids': [1], 'explanation': '简答不开放单题练习'}, 201)['data']
    rejected = write(context, 'PATCH', f"/questions/{short['id']}", {'practice_available': True}, 400)
    assert rejected['error']['code'] == 'VALIDATION_ERROR'
    checks.append('short_question_cannot_be_opened_for_single_practice')
    paper = write(context, 'POST', f'/courses/{course_id}/papers', {'title': 'C04保护回归考试', 'kind': 'exam',
                  'items': [{'question_version_id': secret['version_id'], 'points': 10}]}, 201)['data']
    times = {'start_at': at, 'end_at': at+timedelta(minutes=1), 'review_at': at+timedelta(minutes=2)}
    write(context, 'POST', f"/papers/{paper['id']}/publish", {
        **{k: v.isoformat() for k, v in times.items()}, 'confidentiality_note': '确认未公开且非简单复制'})
    page.get_by_role('button', name='退出', exact=True).click()
    login(page, 'B006STUD1', password)
    bank = page.locator('.practice-bank')
    expect(bank.get_by_text('共 4 道公开练习题', exact=True)).to_be_visible()
    assert 'answer' not in context.request.get(ORIGIN+f'/api/v1/courses/{course_id}/questions').json()['data'][0]
    checks.append('student_public_list_has_no_reference_or_private_exam_question')
    first = questions[0]
    bank.get_by_role('button', name=f"#{first['id']} · v1 · {first['stem']}", exact=True).click()
    expect(bank.get_by_text('本次解析：固定公开版本的练习解析', exact=True)).to_have_count(0)
    bank.get_by_label('练习作答 选项乙', exact=True).check()
    lost = {}

    def lose_response(route):
        response = route.fetch()
        assert response.status == 201
        lost['bytes'] = response.body()
        lost['key'] = route.request.headers['idempotency-key']
        route.abort('failed')

    endpoint = f"/questions/{first['id']}/practice-attempts"
    page.route('**/api/v1'+endpoint, lose_response, times=1)
    bank.get_by_role('button', name='提交本次练习', exact=True).click()
    expect(bank.get_by_role('button', name='重试原练习', exact=True)).to_be_visible()
    expect(bank.get_by_label('练习作答 选项乙', exact=True)).to_be_disabled()
    expect(bank.get_by_role('button', name='我的错题', exact=True)).to_be_disabled()
    with page.expect_response(lambda response: response.url.endswith(endpoint)) as info:
        bank.get_by_role('button', name='重试原练习', exact=True).click()
    assert info.value.body() == lost['bytes'] and info.value.request.headers['idempotency-key'] == lost['key']
    expect(bank.get_by_text('错误 / 未答 · 0 分', exact=True)).to_be_visible()
    checks.append('real_commit_lost_response_locks_form_and_retries_exact_201_bytes_and_key')
    bank.get_by_role('button', name='我的错题', exact=True).click()
    expect(bank.get_by_text('累计错答 1 次 · 待重练 · 来源 练习', exact=True)).to_be_visible()
    bank.get_by_label('筛选错题或练习知识标签').select_option('1')
    expect(bank.get_by_text('共 1 道错题', exact=True)).to_be_visible()
    bank.get_by_role('button', name=f"#{first['id']} · v1 · {first['stem']}", exact=True).click()
    # Teacher API edits while the student's old version remains selected.
    teacher = app.test_client()
    token = teacher.post('/api/v1/auth/login', json={'student_no': 'B006TEACH', 'password': password},
                         headers={'Origin': ORIGIN}).json['data']['csrf_token']
    updated = teacher.patch(f"/api/v1/questions/{first['id']}", json={'answer': 'B', 'practice_available': False},
                            headers={'Origin': ORIGIN, 'X-CSRF-Token': token})
    assert updated.status_code == 200
    bank.get_by_label('练习作答 选项甲', exact=True).check()
    bank.get_by_role('button', name='提交本次练习', exact=True).click()
    expect(bank.get_by_text('累计错答 1 次 · 已掌握 · 来源 练习', exact=True)).to_be_visible()
    expect(bank.get_by_text('正确 · 100 分', exact=True)).to_be_visible()
    checks.append('source_tag_filter_old_public_version_remains_exact_after_private_latest_edit_and_resolves')
    bank.get_by_role('button', name='再次练习此版本', exact=True).click()
    bank.get_by_label('练习作答 选项乙', exact=True).check()
    bank.get_by_role('button', name='提交本次练习', exact=True).click()
    expect(bank.get_by_text('累计错答 2 次 · 待重练 · 来源 练习', exact=True)).to_be_visible()
    checks.append('new_actual_error_reopens_same_wrong_identity_without_deleting_history')
    mobile(page, bank, output/f'{channel}-wrong-repractice.png')
    bank.get_by_role('button', name='公开客观练习', exact=True).click()
    expect(bank.get_by_text('共 3 道公开练习题', exact=True)).to_be_visible()
    for q in questions[1:]:
        bank.get_by_role('button', name=f"#{q['id']} · v1 · {q['stem']}", exact=True).click()
        if q['type'] == 'multiple':
            bank.get_by_label('练习作答 选项甲', exact=True).check()
            bank.get_by_label('练习作答 选项乙', exact=True).check()
        elif q['type'] == 'boolean':
            bank.get_by_label('练习作答 错误', exact=True).check()
        else:
            bank.get_by_label('练习作答', exact=True).fill('0.3')
        bank.get_by_role('button', name='提交本次练习', exact=True).click()
        expect(bank.get_by_text('正确 · 100 分', exact=True)).to_be_visible()
        expect(bank.get_by_text('正在加载或保存练习…', exact=True)).to_have_count(0)
    checks.append('multiple_full_set_boolean_false_numeric_exact_tolerance_actual_ui_grading')
    # Actual exam submission via the existing paper UI creates a second wrong question.
    paper_bank = page.locator('.paper-bank').filter(has=page.get_by_role('heading', name='课程试卷', exact=True))
    paper_bank.get_by_role('button', name='重新加载试卷', exact=True).click()
    paper_bank.get_by_role('button', name=f"#{paper['id']} · C04保护回归考试 · 进行中", exact=True).click()
    form = paper_bank.locator('.attempt-answer-form')
    form.get_by_label('第 1 题作答 错误', exact=True).check()
    form.get_by_label('确认交卷，接受漏答0分且提交后不可修改', exact=True).check()
    form.get_by_role('button', name='提交整份答卷', exact=True).click()
    expect(paper_bank.locator('.attempt-result')).to_be_visible()
    secret_new = teacher.patch(f"/api/v1/questions/{secret['id']}", json={'stem': 'C04保密题新版'},
                               headers={'Origin': ORIGIN, 'X-CSRF-Token': token})
    assert secret_new.status_code == 200 and secret_new.json['data']['version'] == 2
    secret_new = secret_new.json['data']
    # Explicitly anomalous legacy-open flags, not a successful business opening.
    with closing(connect(app.config['DATABASE_PATH'])) as db:
        db.execute('DROP TRIGGER question_version_no_update')
        db.execute('UPDATE question_version SET practice_available=1 WHERE question_id=?', (secret['id'],))
    for version in (secret, secret_new):
        blocked = practice(context, secret['id'], version['version_id'], True)
        assert blocked.status == 409 and blocked.json()['error']['code'] == 'QUESTION_RESERVED'
    wrong_row = next(row for row in context.request.get(ORIGIN+'/api/v1/users/me/wrong-questions').json()['data']
                     if row['id'] == secret['id'])
    assert (wrong_row['answer_visible'], wrong_row['can_practice']) == (False, False)
    assert 'answer' not in wrong_row and 'explanation' not in wrong_row
    submitted = context.request.get(ORIGIN+f"/api/v1/attempts/{wrong_row['last_attempt_id']}").json()['data']
    secret_answer = next(a for a in submitted['answers'] if a['question_version_id'] == secret['version_id'])
    assert 'answer' not in secret_answer and 'explanation' not in secret_answer
    checks.append('protected_identity_all_versions_and_wrong_attempt_reads_409_or_redacted_even_if_legacy_open')
    app.config['TEST_NOW'] = times['end_at']
    bank.get_by_role('button', name='我的错题', exact=True).click()
    expect(bank.get_by_text('共 2 道错题', exact=True)).to_be_visible()
    bank.get_by_role('button', name=f"#{secret['id']} · v1 · {secret['stem']}", exact=True).click()
    expect(bank.get_by_text('答案与解析尚受保护，请等待允许讲评。')).to_be_visible()
    expect(bank.locator('.practice-form')).to_have_count(0)
    expect(bank.get_by_text('解析：保密卷的讲评解析', exact=True)).to_have_count(0)
    checks.append('actual_paper_objective_error_enters_wrong_list_without_pre_review_answers_or_practice')
    mobile(page, bank, output/f'{channel}-protected-wrong.png')
    app.config['TEST_NOW'] = times['review_at']
    bank.get_by_role('button', name='重新加载练习与错题', exact=True).click()
    bank.get_by_role('button', name=f"#{secret['id']} · v1 · {secret['stem']}", exact=True).click()
    expect(bank.get_by_text('解析：保密卷的讲评解析', exact=True)).to_be_visible()
    checks.append('server_exact_timed_review_boundary_reveals_exam_wrong_reference')
    page.get_by_role('button', name='退出', exact=True).click()
    login(page, 'B006STUD1', password)
    bank.get_by_role('button', name='我的错题', exact=True).click()
    expect(bank.get_by_text('共 2 道错题', exact=True)).to_be_visible()
    expect(bank.get_by_text('累计错答 2 次 · 待重练 · 来源 练习', exact=True)).to_be_visible()
    with closing(connect(app.config['DATABASE_PATH'])) as db:
        assert db.execute('SELECT count(*) FROM practice_attempt').fetchone()[0] == 6
        assert db.execute('SELECT count(*) FROM wrong_question').fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM audit_event WHERE action='practice.submit'").fetchone()[0] == 6
    checks.append('relogin_retains_real_wrong_count_sources_and_six_practice_facts_audits')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'logs/spec-006-practices')
    parser.add_argument('--knowledge-fixture', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'started_at': datetime.now(UTC).isoformat(),
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'knowledge_fixture': args.knowledge_fixture,
              'scope': 'actual 001/005/006 knowledge, identity, practice and wrong-question HTTP/UI'
                       if args.knowledge_fixture else 'actual empty practice/wrong HTTP/UI with migrated 005',
              'browsers': [], 'page_errors': []}
    try:
        with sync_playwright() as playwright:
            for channel in ('chrome', 'msedge'):
                with running(args.knowledge_fixture) as (app, password, course_id, at):
                    browser = playwright.chromium.launch(channel=channel, headless=True)
                    try:
                        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, timezone_id='Asia/Shanghai')
                        page = context.new_page()
                        page.on('pageerror', lambda error: report['page_errors'].append(type(error).__name__))
                        entry = {'channel': channel, 'version': browser.version, 'checks': []}
                        report['browsers'].append(entry)
                        login(page, 'B006TEACH', password)
                        expect(page.locator('.practice-bank')).to_have_count(0)
                        entry['checks'].append('teacher_has_no_student_practice_or_personal_wrong_controls')
                        if args.knowledge_fixture:
                            full(app, password, page, context, course_id, at, args.output, channel, entry['checks'])
                        else:
                            page.get_by_role('button', name='退出', exact=True).click()
                            login(page, 'B006STUD1', password)
                            bank = page.locator('.practice-bank')
                            expect(bank.get_by_text('共 0 道公开练习题', exact=True)).to_be_visible()
                            bank.get_by_role('button', name='我的错题', exact=True).click()
                            expect(bank.get_by_text('暂无符合条件的错题。')).to_be_visible()
                            mobile(page, bank, args.output/f'{channel}-empty.png')
                            entry['checks'].append('student_real_empty_lists_without_dependency_fixtures_390px')
                        assert not report['page_errors']
                        context.close()
                    finally:
                        browser.close()
        report['status'] = 'passed'
        print('C04 Chrome/Edge regression passed; scope:', report['scope'])
    except (AssertionError, OSError, RuntimeError, PlaywrightError) as error:
        report['status'] = 'failed'
        report['failure_type'] = type(error).__name__
        report['failure_location'] = [f'{frame.name}:{frame.lineno}' for frame in traceback.extract_tb(error.__traceback__)
                                      if frame.filename == __file__]
        raise RuntimeError('C04 browser regression failed; see redacted report') from None
    finally:
        report['finished_at'] = datetime.now(UTC).isoformat()
        (args.output/'browser-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
