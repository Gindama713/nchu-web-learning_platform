"""C03b Chrome/Edge actual API/SQLite/UI regression with real SPEC-005 knowledge.

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

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import expect, sync_playwright

from backend.shared.db import connect
from scripts.verify_spec006_papers import running, write
from scripts.verify_spec006_questions import ROOT, login


def empty(page, context, checks):
    history = page.locator('.attempt-bank.card')
    expect(history.get_by_text('共 0 份答卷', exact=True)).to_be_visible()
    expect(history.get_by_text('暂无符合条件的答卷。学生交卷后可在这里批阅。')).to_be_visible()
    checks.append('real_teacher_empty_history_without_dependency_fixtures')
    page.get_by_role('button', name='退出', exact=True).click()
    checks.append('real_logout_removes_teacher_history')


def create_paper(context, course_id, at):
    values = [('single', 'A', 0.1), ('multiple', ['A', 'B'], 0.2), ('boolean', False, 1.01),
              ('numeric', 0.2, 2.02), ('short', '教师参考一', 3.03), ('short', '教师参考二', 4.04)]
    questions = []
    for index, (kind, answer, points) in enumerate(values, 1):
        q = write(context, 'POST', f'/courses/{course_id}/questions', {
            'type': kind, 'stem': f'C03b第{index}题', 'answer': answer,
            'options': [{'key': 'A', 'text': '选项甲'}, {'key': 'B', 'text': '选项乙'}] if kind in {'single', 'multiple'} else [],
            'tolerance': 0.1 if kind == 'numeric' else 0, 'difficulty': 'easy', 'knowledge_ids': [1],
            'explanation': '仅讲评后可见的解析'}, 201)['data']
        questions.append({**q, 'points': points})
    paper = write(context, 'POST', f'/courses/{course_id}/papers', {'title': 'C03b受控考试', 'kind': 'exam',
                  'items': [{'question_version_id': q['version_id'], 'points': q['points']} for q in questions]}, 201)['data']
    times = {'start_at': at+timedelta(minutes=1), 'end_at': at+timedelta(minutes=2), 'review_at': at+timedelta(minutes=3)}
    write(context, 'POST', f"/papers/{paper['id']}/publish", {
        **{k: v.isoformat() for k, v in times.items()}, 'confidentiality_note': '确认未公开且非简单复制'})
    write(context, 'PATCH', f"/questions/{questions[0]['id']}", {'stem': '后续题目版本', 'answer': 'B'})
    return paper['id'], times


def open_history(page):
    history = page.locator('.attempt-bank.card')
    history.get_by_role('button', name='重新加载答卷', exact=True).click()
    expect(history.get_by_text('共 1 份答卷', exact=True)).to_be_visible()
    history.locator('.rows button').click()
    expect(history.locator('.attempt-result')).to_be_visible()
    return history


def mobile(page, bank, path):
    page.set_viewport_size({'width': 390, 'height': 844})
    bank.scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    bank.screenshot(path=str(path))


def full(app, password, browser, page, context, course_id, at, output, channel, checks, page_errors):
    paper_id, times = create_paper(context, course_id, at)
    page.get_by_role('button', name='退出', exact=True).click()
    login(page, 'B006STUD1', password)
    bank = page.locator('.paper-bank')
    bank.get_by_role('button', name=f'#{paper_id} · C03b受控考试 · 未开始', exact=True).click()
    expect(bank.get_by_text('试卷尚未开始，开始后可查看题目。')).to_be_visible()
    expect(bank.get_by_role('button', name='提交整份答卷')).to_have_count(0)
    checks.append('prestart_has_metadata_and_no_answer_form')
    app.config['TEST_NOW'] = times['start_at']
    bank.get_by_role('button', name='重新加载试卷', exact=True).click()
    bank.get_by_role('button', name=f'#{paper_id} · C03b受控考试 · 进行中', exact=True).click()
    form = bank.locator('.attempt-answer-form')
    expect(form).to_be_visible()
    form.get_by_label('第 1 题作答 选项甲', exact=True).check()
    for option in ('选项甲', '选项乙'):
        form.get_by_label('第 2 题作答 '+option, exact=True).check()
    form.get_by_label('第 3 题作答 错误', exact=True).check()
    form.get_by_label('第 4 题作答', exact=True).fill('0.3')
    form.get_by_label('第 5 题作答', exact=True).fill('学生解释一')
    form.get_by_label('第 6 题作答', exact=True).fill('学生解释二')
    expect(form.get_by_role('button', name='提交整份答卷')).to_be_disabled()
    form.get_by_label('确认交卷，接受漏答0分且提交后不可修改', exact=True).check()
    expect(bank.get_by_text('教师参考一', exact=True)).to_have_count(0)
    mobile(page, form, output/f'{channel}-student-answer.png')
    checks.append('five_type_form_fixed_old_version_confirmation_and_390px_layout')
    lost = {}
    route_path = f'**/api/v1/papers/{paper_id}/attempts'

    def lose_response(route):
        response = route.fetch()
        assert response.status == 201
        lost['response'] = response.body()
        lost['key'] = route.request.headers['idempotency-key']
        route.abort('failed')

    page.route(route_path, lose_response, times=1)
    form.get_by_role('button', name='提交整份答卷', exact=True).click()
    expect(form.get_by_role('button', name='重试原交卷', exact=True)).to_be_visible()
    expect(form.get_by_label('第 5 题作答', exact=True)).to_be_disabled()
    with page.expect_response(lambda response: response.url.endswith(f'/papers/{paper_id}/attempts')) as response_info:
        form.get_by_role('button', name='重试原交卷', exact=True).click()
    replay = response_info.value
    assert replay.status == 201 and replay.body() == lost['response']
    assert replay.request.headers['idempotency-key'] == lost['key']
    result = bank.locator('.attempt-result')
    expect(result.get_by_text('总分：待全部批阅 / 10.4', exact=True)).to_be_visible()
    expect(result.get_by_text('已定分：3.33', exact=True)).to_be_visible()
    expect(result.get_by_text('后续题目版本', exact=True)).to_have_count(0)
    checks.append('real_committed_response_loss_retry_preserves_key_and_original_201_bytes')
    checks.append('pending_short_answers_null_total_and_fixed_objective_score')
    mobile(page, result, output/f'{channel}-student-pending.png')
    page.get_by_role('button', name='退出', exact=True).click()
    login(page, 'B006TEACH', password)
    first = open_history(page)
    other = browser.new_context(viewport={'width': 1440, 'height': 1000}, timezone_id='Asia/Shanghai')
    try:
        second_page = other.new_page()
        second_page.on('pageerror', lambda error: page_errors.append(type(error).__name__))
        login(second_page, 'B006TEACH', password)
        second = open_history(second_page)
        first.get_by_label('批阅第 5 题', exact=True).check()
        first.get_by_label('第 5 题评分', exact=True).fill('1.01')
        first.get_by_label('第 5 题评语', exact=True).fill('保留原作答，部分得分')
        first.get_by_role('button', name='保存本次批阅', exact=True).click()
        expect(first.get_by_text('已定分：4.34', exact=True)).to_be_visible()
        expect(first.get_by_text('总分：待全部批阅 / 10.4', exact=True)).to_be_visible()
        checks.append('teacher_history_partial_manual_batch_keeps_null_total')
        second.get_by_label('批阅第 6 题', exact=True).check()
        second.get_by_label('第 6 题评分', exact=True).fill('2.02')
        second.get_by_role('button', name='保存本次批阅', exact=True).click()
        expect(second.get_by_text('评分已被其他会话修改。请重新加载此答卷，再填写批阅。')).to_be_visible()
        expect(second.get_by_role('button', name='保存本次批阅', exact=True)).to_be_disabled()
        checks.append('two_actual_teacher_sessions_stale_revision_conflict_locks_form')
        second.get_by_role('button', name='重新加载此答卷', exact=True).click()
        expect(second.get_by_text('正在加载或保存答卷…', exact=True)).to_have_count(0)
        second.get_by_label('批阅第 6 题', exact=True).check()
        second.get_by_label('第 6 题评分', exact=True).fill('2.02')
        second.get_by_role('button', name='保存本次批阅', exact=True).click()
        try:
            expect(second.get_by_text('总分：6.36 / 10.4', exact=True)).to_be_visible()
        except AssertionError:
            second.screenshot(path=str(output/f'{channel}-failure.png'))
            (output/f'{channel}-diagnostics.json').write_text(json.dumps({
                'alerts': second.locator('[role="alert"]').all_text_contents(),
                'summary': second.locator('.attempt-summary').all_text_contents(),
            }, ensure_ascii=False), encoding='utf-8')
            raise
        first.get_by_role('button', name='重新加载此答卷', exact=True).click()
        expect(first.get_by_text('正在加载或保存答卷…', exact=True)).to_have_count(0)
        first.get_by_label('批阅第 5 题', exact=True).check()
        first.get_by_label('第 5 题评分', exact=True).fill('0')
        first.get_by_label('第 5 题评语', exact=True).fill('更正为零分')
        first.get_by_role('button', name='保存本次批阅', exact=True).click()
        expect(first.get_by_text('总分：5.35 / 10.4', exact=True)).to_be_visible()
        mobile(page, first.locator('.attempt-result'), output/f'{channel}-teacher-correction.png')
        checks.append('reload_then_complete_and_correct_zero_grade_with_390px_layout')
    finally:
        other.close()
    with closing(connect(app.config['DATABASE_PATH'])) as db:
        row = db.execute('SELECT * FROM attempt').fetchone()
        assert row['revision'] == 3 and row['score_hundredths'] == 535
        assert db.execute('SELECT count(*) FROM attempt').fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM audit_event WHERE action='attempt.manual_scores'").fetchone()[0] == 3
    checks.append('persisted_single_attempt_revision_three_exact_score_and_three_audits')
    app.config['TEST_NOW'] = times['end_at']
    page.get_by_role('button', name='退出', exact=True).click()
    login(page, 'B006STUD1', password)
    history = open_history(page)
    expect(history.get_by_text('总分：5.35 / 10.4', exact=True)).to_be_visible()
    expect(history.get_by_text('评语：更正为零分', exact=True)).to_be_visible()
    expect(history.get_by_text('参考答案：教师参考一', exact=True)).to_have_count(0)
    expect(history.get_by_role('button', name='保存本次批阅', exact=True)).to_have_count(0)
    checks.append('student_relogin_latest_correction_and_no_answers_at_deadline')
    app.config['TEST_NOW'] = times['review_at']
    history.get_by_role('button', name='重新加载此答卷', exact=True).click()
    expect(history.get_by_text('参考答案：教师参考一', exact=True)).to_be_visible()
    mobile(page, history.locator('.attempt-result'), output/f'{channel}-student-reviewed.png')
    checks.append('exact_review_boundary_reveals_fixed_answer_and_390px_result')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'logs/spec-006-attempts')
    parser.add_argument('--knowledge-fixture', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'started_at': datetime.now(UTC).isoformat(),
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'knowledge_fixture': args.knowledge_fixture,
              'scope': 'real 001/005/006 knowledge, paper, attempt and manual-score HTTP/UI' if args.knowledge_fixture
                       else 'real empty attempt HTTP/UI without dependency fixtures', 'browsers': [], 'page_errors': []}
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
                        if args.knowledge_fixture:
                            full(app, password, browser, page, context, course_id, at, args.output, channel,
                                 entry['checks'], report['page_errors'])
                        else:
                            empty(page, context, entry['checks'])
                            login(page, 'B006STUD1', password)
                            history = page.locator('.attempt-bank.card')
                            expect(history.get_by_text('共 0 份答卷', exact=True)).to_be_visible()
                            expect(history.get_by_role('button', name='保存本次批阅')).to_have_count(0)
                            mobile(page, history, args.output/f'{channel}-student-empty.png')
                            entry['checks'].append('real_student_empty_history_no_teacher_controls_390px')
                        assert not report['page_errors']
                        context.close()
                    finally:
                        browser.close()
        report['status'] = 'passed'
        print('C03b Chrome/Edge regression passed; scope:', report['scope'])
    except (AssertionError, OSError, RuntimeError, PlaywrightError) as error:
        report['status'] = 'failed'
        report['failure_type'] = type(error).__name__
        report['failure_location'] = [f'{frame.name}:{frame.lineno}' for frame in traceback.extract_tb(error.__traceback__)
                                      if frame.filename == __file__]
        raise RuntimeError('C03b browser regression failed; see redacted report') from None
    finally:
        report['finished_at'] = datetime.now(UTC).isoformat()
        (args.output/'browser-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
