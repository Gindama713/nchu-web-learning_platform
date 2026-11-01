"""C10 real installed Chrome/Edge + socket HTTP/SQLite/Vue, controlled accounts.

Run python -m scripts.verify_spec011_qa --output logs/spec-011-browsers.
Only build failure is injected (unittest.mock); all knowledge/membership mutations
use actual HTTP APIs. Threshold-edge doubles remain in test_qa, not browser claims.
"""

import argparse
import json
import re
import subprocess
import traceback
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

from backend.models import qa
from backend.shared.db import connect
from scripts.verify_spec006_papers import running, write
from scripts.verify_spec006_questions import ORIGIN, ROOT


def sign_in(page, number, password):
    # Finish initial session recovery before sending a new login.
    with page.expect_response(lambda response: response.url.endswith('/api/v1/auth/session')):
        page.goto(ORIGIN)
    page.get_by_label('学号', exact=True).fill(number)
    page.get_by_label('密码', exact=True).fill(password)
    page.get_by_role('button', name='登录', exact=True).click()
    bank = page.get_by_role('region', name='课程检索问答')
    expect(bank).to_be_visible()
    expect(bank).to_have_attribute('aria-busy', 'false')
    expect(bank.get_by_label('你的问题', exact=True)).to_be_enabled()
    return bank


def search(page, bank, question='PC 有什么作用', expected=200, retry=False):
    if not retry:
        bank.get_by_label('你的问题', exact=True).fill(question)
    with page.expect_response(lambda response: response.url.endswith('/qa') and response.request.method == 'POST') as info:
        bank.get_by_role('button', name='重试查询' if retry else '查询课程知识', exact=True).click()
    response = info.value
    assert response.status == expected, f'QA returned {response.status}'
    expect(bank).to_have_attribute('aria-busy', 'false')
    return response.json()


def verify(playwright, channel, output):
    checks, errors = [], []
    with running(False) as (app, password, course_id, _at):
        browser = playwright.chromium.launch(channel=channel, headless=True)
        try:
            context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(type(error).__name__))
            teacher_bank = sign_in(page, 'B006TEACH', password)
            chapter = write(context, 'POST', f'/courses/{course_id}/chapters', {'title': 'CPU寄存器'}, 201)['data']['id']
            point = write(context, 'POST', f'/chapters/{chapter}/knowledge-points', {
                'title': '程序计数器', 'content': '<p>程序计数器保存下一条指令的地址。</p>',
                'example': '取指后更新地址。', 'published': True}, 201)['data']['id']
            draft = write(context, 'POST', f'/chapters/{chapter}/knowledge-points', {
                'title': 'PC草稿', 'content': '草稿内容不可检索', 'published': False}, 201)['data']['id']
            practice = write(context, 'POST', f'/courses/{course_id}/questions', {
                'type': 'boolean', 'stem': 'PC保存下一条指令地址？', 'answer': True, 'options': [],
                'difficulty': 'easy', 'knowledge_ids': [point], 'practice_available': True}, 201)['data']
            student = browser.new_context(viewport={'width': 1440, 'height': 1000})
            student_page = student.new_page()
            student_page.on('pageerror', lambda error: errors.append(type(error).__name__))
            bank = sign_in(student_page, 'B006STUD1', password)
            data = search(student_page, bank)['data']
            assert data['found'] and data['reason'] == 'matched'
            assert [item['knowledge_id'] for item in data['matches']] == [point]
            assert draft not in [item['knowledge_id'] for item in data['matches']]
            expect(bank.get_by_text(re.compile(r'相似度 \d\.\d{6}$'))).to_be_visible()
            bank.get_by_role('button', name=f'打开知识出处 #{point}', exact=True).click()
            expect(bank.get_by_role('article', name='知识出处正文')).to_contain_text('程序计数器保存下一条指令的地址')
            bank.screenshot(path=str(output / f'{channel}-matched.png'))
            checks.append('real_001_login_005_publish_PC_alias_six_decimals_source_and_draft_excluded')

            for question in ('🦄', '<b></b>'):
                no_match = search(student_page, bank, question)['data']
                assert no_match['reason'] == 'no_match' and no_match['matches'] == []
                expect(bank.get_by_text('未找到相关知识，请调整问题或使用课程术语。', exact=True)).to_be_visible()
            checks.append('real_zero_vector_and_no_match_response_page')

            write(context, 'PATCH', f'/knowledge-points/{point}', {
                'title': '累加器', 'content': '<p>累加器保存运算结果。最新正文</p>'})
            changed = search(student_page, bank, 'ACC')['data']
            assert changed['index_version'] != data['index_version']
            assert '最新正文' in changed['matches'][0]['excerpt']
            assert '下一条指令' not in json.dumps(changed, ensure_ascii=False)
            checks.append('real_005_update_on_demand_revision_rebuild_without_old_excerpt')

            write(context, 'PATCH', f'/knowledge-points/{point}', {'content': '<p>累加器新修订用于失败恢复</p>'})
            with patch.object(qa, 'build_index', side_effect=RuntimeError('controlled rebuild fault')):
                failed = search(student_page, bank, 'ACC', expected=503)
                assert failed['error']['code'] == 'INDEX_UNAVAILABLE'
                expect(bank.get_by_role('alert')).to_contain_text('索引暂时不可用')
                expect(bank.locator('.qa-matches')).to_have_count(0)
                # A real independent learning operation remains usable while QA fails.
                write(student, 'PUT', f'/knowledge-points/{point}/progress', {'completed': True})
                session = student.request.get(ORIGIN + '/api/v1/auth/session').json()['data']
                submitted = student.request.post(ORIGIN + f"/api/v1/questions/{practice['id']}/practice-attempts", data={
                    'question_version_id': practice['version_id'], 'answer': True}, headers={
                    'Origin': ORIGIN, 'X-CSRF-Token': session['csrf_token'], 'Idempotency-Key': str(uuid4())})
                assert submitted.status == 201 and submitted.json()['data']['correct']
                bank.screenshot(path=str(output / f'{channel}-failure.png'))
            recovered = search(student_page, bank, retry=True)['data']
            assert recovered['found'] and '失败恢复' in recovered['matches'][0]['excerpt']
            checks.append('injected_build_failure_real_HTTP503_clears_UI_real_progress_and_practice_submit201_work_retry_recovers')

            write(context, 'PATCH', f'/knowledge-points/{point}', {'published': False})
            with patch.object(qa, 'build_index', side_effect=RuntimeError('controlled unpublish rebuild fault')):
                failed = search(student_page, bank, 'ACC', expected=503)
                assert failed['error']['code'] == 'INDEX_UNAVAILABLE'
                expect(bank.locator('.qa-matches')).to_have_count(0)
            empty = search(student_page, bank, retry=True)['data']
            assert empty['reason'] == 'empty_corpus' and not empty['found'] and empty['matches'] == []
            assert empty['index_version'] != recovered['index_version']
            expect(bank.get_by_text('本课程暂无已发布知识，请等待教师发布后重试。', exact=True)).to_be_visible()
            checks.append('real_unpublish_failed_rebuild_never_leaks_then_empty_corpus_revision')

            write(context, 'PATCH', f'/knowledge-points/{point}', {'published': True})
            search(student_page, bank, 'ACC')
            held = []

            def delay(route):
                held.append((route, route.fetch()))

            student_page.route('**/api/v1/courses/*/qa', delay, times=1)
            bank.get_by_role('button', name='查询课程知识', exact=True).click()
            expect(bank.get_by_text('正在查询或加载出处…', exact=True)).to_be_visible()
            for _ in range(100):
                if held:
                    break
                student_page.wait_for_timeout(20)
            assert held
            bank.get_by_label('你的问题', exact=True).fill('ALU')
            held[0][0].fulfill(response=held[0][1])
            expect(bank.locator('.qa-matches')).to_have_count(0)
            checks.append('delayed_real_HTTP_response_discarded_after_question_change')

            search(student_page, bank, 'ACC')
            student_page.set_viewport_size({'width': 390, 'height': 844})
            bank.scroll_into_view_if_needed()
            assert student_page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            bank.screenshot(path=str(output / f'{channel}-mobile.png'))
            checks.append('390px_mobile_no_document_overflow')

            student_session = student.request.get(ORIGIN + '/api/v1/auth/session').json()['data']
            student_id = student_session['user']['id']
            teacher_session = context.request.get(ORIGIN + '/api/v1/auth/session').json()['data']
            response = context.request.delete(ORIGIN + f'/api/v1/courses/{course_id}/members/{student_id}', headers={
                'Origin': ORIGIN, 'X-CSRF-Token': teacher_session['csrf_token']})
            assert response.status == 204
            denied = search(student_page, bank, 'ACC', expected=404)
            assert denied['error']['code'] == 'NOT_FOUND'
            expect(bank.locator('.qa-matches')).to_have_count(0)
            expect(bank.get_by_role('button', name='查询课程知识', exact=True)).to_be_disabled()
            checks.append('real_001_membership_revocation_HTTP404_clears_and_disables_query')

            # Assert actual records without exporting question text, cookies or credentials.
            with closing(connect(app.config['DATABASE_PATH'])) as db:
                records = db.execute('SELECT user_id,matched_ids_json,similarities_json,index_revision,algorithm_version FROM qa_query').fetchall()
                assert records and all(row['user_id'] == student_id for row in records)
                assert all(row['algorithm_version'] == qa.ALGORITHM for row in records)
                assert all(len(json.loads(row['matched_ids_json'])) == len(json.loads(row['similarities_json'])) for row in records)
                assert db.execute('PRAGMA foreign_key_check').fetchall() == []
            checks.append('SQLite_query_owner_raw_similarity_revision_algorithm_records_and_FK_integrity')
            expect(teacher_bank).to_be_visible()
            assert errors == []
            return {'channel': channel, 'version': browser.version, 'checks': checks,
                    'page_errors': errors, 'result': 'passed'}
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'logs/spec-011-browsers')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'date': datetime.now(UTC).isoformat(), 'executor': 'Codex, user-authorized automatic verification',
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'dirty_paths': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines(),
              'scope': 'controlled real 001/005/011 handlers plus socket HTTP/SQLite/Vue; only index-build faults injected; no production/target performance',
              'browsers': []}
    try:
        with sync_playwright() as playwright:
            for channel in ('chrome', 'msedge'):
                report['browsers'].append(verify(playwright, channel, args.output))
        report['result'] = 'passed'
    except Exception as error:
        report['result'] = 'failed'
        report['error_type'] = type(error).__name__
        traceback.print_exc()
        raise
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'result': report['result'], 'browsers': len(report['browsers']), 'output': str(args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
