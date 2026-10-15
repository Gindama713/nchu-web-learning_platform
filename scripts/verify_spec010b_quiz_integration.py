"""Real merged 008 -> 010B Chrome/Edge HTTP/UI evidence on controlled databases."""

import argparse
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from scripts.verify_spec006_papers import running, write
from scripts.verify_spec006_questions import ORIGIN, ROOT, login
from scripts.verify_spec010b_analytics import download, read, submit


def verify(playwright, channel, output):
    checks, errors = [], []
    with running(True) as (app, password, course_id, at):
        browser = playwright.chromium.launch(channel=channel, headless=True)
        try:
            context = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(type(error).__name__))
            login(page, 'B006TEACH', password)
            for number in ('B010BQUIZ2', 'B010BQUIZ3'):
                response = context.request.post(ORIGIN + '/api/v1/auth/register', data={
                    'student_no': number, 'name': number, 'password': password}, headers={'Origin': ORIGIN})
                assert response.status == 201
                write(context, 'POST', f'/courses/{course_id}/members', {
                    'user_id': response.json()['data']['user']['id'], 'member_role': 'student'}, 201)
            questions = []
            for i in range(4):
                questions.append(write(context, 'POST', f'/courses/{course_id}/questions', {
                    'type': 'short' if i == 3 else 'single', 'stem': f'010B联测第{i + 1}题',
                    'answer': '参考' if i == 3 else 'A', 'explanation': '联测讲评',
                    'options': [] if i == 3 else [{'key': 'A', 'text': '甲'}, {'key': 'B', 'text': '乙'}],
                    'difficulty': 'easy', 'knowledge_ids': [1]}, 201)['data'])
            quiz_id = write(context, 'POST', f'/courses/{course_id}/papers', {
                'title': '010B联测', 'kind': 'quiz', 'confidential': True, 'items': [
                    {'question_version_id': q['version_id'], 'points': 10} for q in questions]}, 201)['data']['id']
            write(context, 'POST', f'/courses/{course_id}/quizzes', {
                'paper_id': quiz_id, 'start_at': at.isoformat(), 'end_at': (at + timedelta(hours=1)).isoformat(),
                'confidentiality_note': '未公开确认'}, 201)
            student = browser.new_context()
            student_page = student.new_page()
            student_page.on('pageerror', lambda error: errors.append(type(error).__name__))
            login(student_page, 'B006STUD1', password)
            pending = submit(student, f'/quizzes/{quiz_id}/attempts', {'answers': [
                {'question_version_id': questions[i]['version_id'], 'value': v}
                for i, v in ((0, 'A'), (1, 'B'), (3, '受控回答'))]})
            blank = browser.new_context()
            blank_page = blank.new_page()
            login(blank_page, 'B010BQUIZ2', password)
            submit(blank, f'/quizzes/{quiz_id}/attempts', {'answers': []})
            blank.close()
            app.config['TEST_NOW'] = at + timedelta(hours=1, minutes=1)
            stats = read(context, f'/quizzes/{quiz_id}/statistics').json()['data']
            assert [stats[k] for k in ('expected_count', 'submitted_count', 'missing_count')] == [3, 2, 1]
            assert stats['objective_correct_rate'] == 1 / 6 and stats['questions'][3]['pending_count'] == 1
            quiz = page.locator('.paper-bank').filter(has=page.get_by_role('heading', name='随堂测', exact=True))
            quiz.get_by_role('button', name='重新加载试卷', exact=True).click()
            quiz.get_by_role('button', name=f'#{quiz_id} · 010B联测 · 已截止', exact=True).click()
            quiz.get_by_role('button', name='刷新逐题统计', exact=True).click()
            expect(quiz.locator('.quiz-statistics').get_by_text('应交 3 · 已交 2 · 缺交 1 · 客观正确率 16.7%', exact=True)).to_be_visible()
            checks.append('dedicated_publish_submit_partial_blank_missing_and_real_statistics_ui_omission_denominator')
            bank = page.locator('.analytics-bank')
            bank.get_by_role('button', name='查询统计', exact=True).click()
            expect(bank.locator('dd').filter(has_text='50.00%')).to_have_count(1)
            knowledge_id = bank.get_by_label('原快照编号', exact=True).input_value()
            knowledge = read(context, f'/courses/{course_id}/analytics?analysis_run_id={knowledge_id}').json()['data']
            assert knowledge['sample_size'] == 2 and knowledge['metrics']['mastery'] == 0.5
            knowledge_csv = download(page, bank)
            student_bank = student_page.locator('.analytics-bank')
            student_bank.get_by_role('button', name='查询统计', exact=True).click()
            expect(student_bank.locator('dd').filter(has_text='50.00%')).to_have_count(1)
            read(student, f'/quizzes/{quiz_id}/statistics', 403)
            assert 'answer' not in read(student, f'/papers/{quiz_id}').json()['data']['items'][0]
            checks.append('teacher_student_knowledge50_actual_answer_denominator_differs_from_quiz16_7_and_statistics403')
            bank.get_by_label('统计维度', exact=True).select_option('scores')
            bank.get_by_label('成绩类别', exact=True).select_option('quiz')
            bank.get_by_role('button', name='查询统计', exact=True).click()
            expect(bank.locator('.analytics-report')).to_contain_text('分类成绩 / quiz')
            score_id = bank.get_by_label('原快照编号', exact=True).input_value()
            old = read(context, f'/courses/{course_id}/analytics?analysis_run_id={score_id}').json()['data']
            assert [old['metrics'][k] for k in ('expected_count', 'submitted_count', 'missing_count',
                    'graded_count', 'partial_count', 'mean_percentage')] == [3, 2, 1, 1, 1, 0]
            score_csv = download(page, bank)
            checks.append('quiz_scores_frozen3_2_1_partial_excluded_graded_zero_and_csv')
            write(context, 'PATCH', f"/attempts/{pending['id']}/manual-scores", {'revision': 0, 'items': [
                {'question_version_id': questions[3]['version_id'], 'score': 8, 'comment': ''}]})
            quiz.get_by_role('button', name='发布讲评并开放答案', exact=True).click()
            expect(quiz.get_by_text('讲评已发布。学生重新加载后可查看答案与解析。', exact=True)).to_be_visible()
            assert 'answer' in read(student, f'/papers/{quiz_id}').json()['data']['items'][0]
            assert read(student, '/users/me/wrong-questions').json()['data'][0]['answer_visible']
            checks.append('real_manual_grade_and_explicit_review_ui_release_fixed_answers_wrong_entry')
            page.reload()
            bank = page.locator('.analytics-bank')
            expect(bank.get_by_label('原快照编号', exact=True)).to_have_value(score_id)
            assert read(context, f'/courses/{course_id}/analytics?analysis_run_id={score_id}').json()['data'] == old
            assert download(page, bank) == score_csv
            bank.get_by_label('原快照编号', exact=True).fill(knowledge_id)
            bank.get_by_role('button', name='恢复原快照', exact=True).click()
            expect(bank.locator('dd').filter(has_text='50.00%')).to_have_count(1)
            assert download(page, bank) == knowledge_csv
            page.set_viewport_size({'width': 390, 'height': 844})
            bank.scroll_into_view_if_needed()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            bank.screenshot(path=str(output / f'{channel}-quiz-knowledge.png'))
            checks.append('original_score_id_reload_and_knowledge_id_restore_keep_json_csv_after_grade_review_390px')
            bank.get_by_label('统计维度', exact=True).select_option('scores')
            bank.get_by_label('成绩类别', exact=True).select_option('quiz')
            bank.get_by_role('button', name='查询统计', exact=True).click()
            expect(bank.locator('dd').filter(has_text='22.50%')).to_have_count(1)
            bank.screenshot(path=str(output / f'{channel}-quiz-scores.png'))
            page.get_by_role('button', name='退出', exact=True).click()
            login(page, 'B006TEACH', password)
            bank.get_by_label('原快照编号', exact=True).fill(score_id)
            bank.get_by_role('button', name='恢复原快照', exact=True).click()
            assert download(page, bank) == score_csv
            checks.append('new_quiz_query22_5_percent_and_relogin_original_score_id_csv')
            assert not errors
            return {'channel': channel, 'version': browser.version, 'checks': checks, 'page_errors': errors, 'result': 'passed'}
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'logs/spec-010b-quiz-browsers')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'date': datetime.now(UTC).isoformat(), 'executor': 'Codex, user-authorized automatic verification',
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'dirty_paths': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines(),
              'scope': 'real merged 001/005/006/008 -> 010B controlled HTTP/UI; no target production/performance', 'browsers': []}
    try:
        with sync_playwright() as playwright:
            for channel in ('chrome', 'msedge'):
                report['browsers'].append(verify(playwright, channel, args.output))
        report['result'] = 'passed'
    except Exception as exc:
        report['result'] = 'failed'
        report['error_type'] = type(exc).__name__
        raise
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'result': report['result'], 'browsers': len(report['browsers']), 'output': str(args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
