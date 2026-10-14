"""C07 installed Chrome/Edge, real 001/005/006 HTTP + SQLite + Vue + CSV.

Dedicated 008 is deliberately excluded until PR #9 merges. Controlled accounts only;
no passwords, cookies, CSRF, student answers or database files enter the report.
Run: .venv/Scripts/python.exe -m scripts.verify_spec010b_analytics
"""

import argparse
import csv
import io
import json
import subprocess
import traceback
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

from scripts.verify_spec006_papers import running, write
from scripts.verify_spec006_questions import ORIGIN, ROOT, login


def read(context, path, expected=200):
    response = context.request.get(ORIGIN + '/api/v1' + path)
    assert response.status == expected, f'GET {path} returned {response.status}'
    return response


def submit(context, path, payload):
    session = read(context, '/auth/session').json()['data']
    response = context.request.post(ORIGIN + '/api/v1' + path, data=payload, headers={
        'Origin': ORIGIN, 'X-CSRF-Token': session['csrf_token'], 'Idempotency-Key': str(uuid4())})
    assert response.status == 201
    return response.json()['data']


def download(page, bank):
    with page.expect_download() as info:
        bank.get_by_role('button', name='导出当前快照 CSV', exact=True).click()
    item = info.value
    assert item.failure() is None
    return Path(item.path()).read_bytes()


def verify(playwright, channel, output):
    checks, errors = [], []
    with running(True) as (app, password, course_id, at):
        browser = playwright.chromium.launch(channel=channel, headless=True)
        try:
            context = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(type(error).__name__))
            login(page, 'B006TEACH', password)
            bank = page.locator('.analytics-bank')
            expect(bank).to_have_attribute('aria-busy', 'false')
            title = '=SUM(1),换行\nCPU基础'
            write(context, 'PATCH', '/knowledge-points/1', {'title': title})
            practice = write(context, 'POST', f'/courses/{course_id}/questions', {
                'type': 'boolean', 'stem': 'C07公开客观题', 'answer': True, 'options': [],
                'difficulty': 'easy', 'knowledge_ids': [1], 'practice_available': True}, 201)['data']
            short = write(context, 'POST', f'/courses/{course_id}/questions', {
                'type': 'short', 'stem': 'C07作业简答题', 'answer': '教学参考', 'options': [],
                'difficulty': 'easy', 'knowledge_ids': [1]}, 201)['data']
            papers = []
            for name in ('缺交', '待批', '真实0分'):
                paper = write(context, 'POST', f'/courses/{course_id}/papers', {
                    'title': 'C07' + name, 'kind': 'homework', 'items': [
                        {'question_version_id': short['version_id'], 'points': 10}]}, 201)['data']
                write(context, 'POST', f"/papers/{paper['id']}/publish", {
                    'start_at': at.isoformat(), 'end_at': (at + timedelta(hours=1)).isoformat(),
                    'review_at': (at + timedelta(hours=2)).isoformat()})
                papers.append(paper['id'])
            student = browser.new_context(viewport={'width': 1440, 'height': 1000})
            student_page = student.new_page()
            student_page.on('pageerror', lambda error: errors.append(type(error).__name__))
            login(student_page, 'B006STUD1', password)
            student_id = read(student, '/auth/session').json()['data']['user']['id']
            for value in (True, True, True, False):
                submit(student, f"/questions/{practice['id']}/practice-attempts", {
                    'question_version_id': practice['version_id'], 'answer': value})
            write(student, 'PUT', '/knowledge-points/1/progress', {'completed': True})
            pending = submit(student, f'/papers/{papers[1]}/attempts', {'answers': [
                {'question_version_id': short['version_id'], 'value': '受控回答'}]})
            submit(student, f'/papers/{papers[2]}/attempts', {'answers': []})
            app.config['TEST_NOW'] = at + timedelta(minutes=1)
            student_bank = student_page.locator('.analytics-bank')
            student_bank.get_by_role('button', name='查询统计', exact=True).click()
            expect(student_bank.locator('dd').filter(has_text='75.00%')).to_have_count(1)
            expect(student_bank.get_by_role('button', name='导出当前快照 CSV')).to_have_count(0)
            student_run = student_bank.get_by_label('原快照编号', exact=True).input_value()
            read(student, f'/courses/{course_id}/analytics/export?analysis_run_id={student_run}&format=csv', 403)
            checks.append('real_student_4_answers_3_correct_75_percent_progress_and_export403')
            student_page.reload()
            expect(student_bank.get_by_label('原快照编号', exact=True)).to_have_value(student_run)
            expect(student_bank.locator('dd').filter(has_text='75.00%')).to_have_count(1)
            checks.append('reload_restores_exact_student_snapshot_id')
            bank.get_by_label('学生编号（留空全班）', exact=True).fill(str(student_id))
            bank.get_by_role('button', name='查询统计', exact=True).click()
            expect(bank.locator('dd').filter(has_text='75.00%')).to_have_count(1)
            knowledge_run = bank.get_by_label('原快照编号', exact=True).input_value()
            knowledge_csv = download(page, bank)
            rows = list(csv.reader(io.StringIO(knowledge_csv.decode('utf-8-sig'))))
            assert ['item', '1', "'" + title, '4', '3', '1', '0.75'] in rows
            checks.append('teacher_selected_student_matches_page_and_real_csv_formula_escape')
            bank.get_by_label('统计维度', exact=True).select_option('scores')
            bank.get_by_label('学生编号（留空全班）', exact=True).fill('')
            bank.get_by_role('button', name='查询统计', exact=True).click()
            expect(bank.locator('dt').filter(has_text='应交人卷次')).to_be_visible()
            run = bank.get_by_label('原快照编号', exact=True).input_value()
            old = read(context, f'/courses/{course_id}/analytics?analysis_run_id={run}').json()['data']
            assert [old['metrics'][key] for key in ('expected_count', 'submitted_count', 'missing_count',
                    'graded_count', 'partial_count', 'mean_percentage')] == [3, 2, 1, 1, 1, 0]
            before = download(page, bank)
            write(context, 'PATCH', f"/attempts/{pending['id']}/manual-scores", {'revision': 0, 'items': [
                {'question_version_id': short['version_id'], 'score': 8, 'comment': ''}]})
            page.reload()
            expect(bank.get_by_label('原快照编号', exact=True)).to_have_value(run)
            expect(bank.get_by_text('原快照 #' + run + ' · 分类成绩 / homework', exact=True)).to_be_visible()
            assert read(context, f'/courses/{course_id}/analytics?analysis_run_id={run}').json()['data'] == old
            assert download(page, bank) == before
            checks.append('frozen_3_expected_2_submitted_1_missing_1_partial_graded_zero_old_json_csv_survive_grade_and_reload')
            bank.get_by_label('统计维度', exact=True).select_option('scores')
            bank.get_by_role('button', name='查询统计', exact=True).click()
            expect(bank.locator('dd').filter(has_text='40.00%')).to_have_count(1)
            bank.get_by_label('试卷编号（留空本类别全部）', exact=True).fill(str(papers[1]))
            bank.get_by_role('button', name='查询统计', exact=True).click()
            expect(bank.locator('dd').filter(has_text='8.00 分')).to_have_count(1)
            expect(bank.locator('dd').filter(has_text='80.00%')).to_have_count(1)
            checks.append('new_query_reflects_grade40_percent_single_paper8_points_80_percent')
            # Real delayed HTTP response: changing a filter invalidates it before delivery.
            held = []

            def delay(route):
                held.append((route, route.fetch()))

            page.route('**/api/v1/courses/*/analytics?dimension=*', delay, times=1)
            bank.get_by_role('button', name='查询统计', exact=True).click()
            expect(bank.get_by_text('正在读取统计…', exact=True)).to_be_visible()
            for _ in range(100):
                if held:
                    break
                page.wait_for_timeout(20)
            assert held
            bank.get_by_label('成绩类别', exact=True).select_option('exam')
            held[0][0].fulfill(response=held[0][1])
            expect(bank.locator('.analytics-report')).to_have_count(0)
            bank.get_by_role('button', name='查询统计', exact=True).click()
            expect(bank.get_by_text('无有效样本，均分或掌握度显示无数据。', exact=True)).to_be_visible()
            checks.append('delayed_real_http_dropped_after_filter_change_exam_empty_unknown')
            bank.get_by_label('原快照编号', exact=True).fill('999999')
            bank.get_by_role('button', name='恢复原快照', exact=True).click()
            expect(bank.get_by_role('alert')).to_be_visible()
            expect(bank.locator('.analytics-report')).to_have_count(0)
            bank.get_by_label('原快照编号', exact=True).fill(knowledge_run)
            bank.get_by_role('button', name='恢复原快照', exact=True).click()
            expect(bank.locator('dd').filter(has_text='75.00%')).to_have_count(1)
            checks.append('unavailable_old_id_clears_report_explicit_restore_original_id_only')
            page.set_viewport_size({'width': 390, 'height': 844})
            bank.scroll_into_view_if_needed()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            bank.screenshot(path=str(output / f'{channel}-knowledge-mobile.png'))
            bank.get_by_label('原快照编号', exact=True).fill(run)
            bank.get_by_role('button', name='恢复原快照', exact=True).click()
            expect(bank.get_by_text('原快照 #' + run + ' · 分类成绩 / homework', exact=True)).to_be_visible()
            bank.screenshot(path=str(output / f'{channel}-scores-mobile.png'))
            checks.append('390px_knowledge_and_scores_tables_scroll_without_document_overflow')
            page.get_by_role('button', name='退出', exact=True).click()
            login(page, 'B006TEACH', password)
            expect(bank.get_by_label('原快照编号', exact=True)).to_have_value(run)
            checks.append('logout_login_restores_creator_original_score_snapshot')
            # Selected-student revocation must affect teacher restoration/export too.
            session = read(context, '/auth/session').json()['data']
            removed = context.request.delete(ORIGIN + f'/api/v1/courses/{course_id}/members/{student_id}',
                                              headers={'Origin': ORIGIN, 'X-CSRF-Token': session['csrf_token']})
            assert removed.status == 204
            bank.get_by_label('原快照编号', exact=True).fill(knowledge_run)
            bank.get_by_role('button', name='恢复原快照', exact=True).click()
            expect(bank.get_by_role('alert')).to_be_visible()
            expect(bank.locator('.analytics-report')).to_have_count(0)
            read(context, f'/courses/{course_id}/analytics/export?analysis_run_id={knowledge_run}&format=csv', 404)
            checks.append('real_member_revocation_blocks_old_selected_snapshot_and_csv404')
            assert errors == []
            return {'channel': channel, 'version': browser.version, 'checks': checks, 'page_errors': errors, 'result': 'passed'}
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'logs/spec-010b-browsers')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'date': datetime.now(UTC).isoformat(), 'executor': 'Codex, user-authorized automatic verification',
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'dirty_paths': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines(),
              'scope': 'controlled real 001/005/006 HTTP + SQLite + Vue; no dedicated008 or target Linux performance', 'browsers': []}
    try:
        with sync_playwright() as playwright:
            for channel in ('chrome', 'msedge'):
                report['browsers'].append(verify(playwright, channel, args.output))
        report['result'] = 'passed'
    except Exception as exc:
        report['result'] = 'failed'
        report['error_type'] = type(exc).__name__
        traceback.print_exc()
        raise
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'result': report['result'], 'browsers': len(report['browsers']), 'output': str(args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
