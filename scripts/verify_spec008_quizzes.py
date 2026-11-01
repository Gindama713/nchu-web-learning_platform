"""C05 real 001/005/006/008 Chrome/Edge flow on temporary databases.

Only initial teacher/admin accounts are bootstrapped. No secrets or student
answer payloads are saved. HTTP fault injection aborts real committed responses.
"""

import argparse
import json
import subprocess
import traceback
from contextlib import closing
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import expect, sync_playwright

from backend.shared.db import connect
from scripts.verify_spec006_papers import running, write
from scripts.verify_spec006_questions import ORIGIN, ROOT, login


def quiz_bank(page):
    return page.locator('.paper-bank').filter(has=page.get_by_role('heading', name='随堂测', exact=True))


def open_quiz(page, paper_id, state):
    bank = quiz_bank(page)
    bank.get_by_role('button', name='重新加载试卷', exact=True).click()
    bank.get_by_role('button', name=f'#{paper_id} · C05受控随堂测 · {state}', exact=True).click()
    return bank


def screenshot(page, locator, output, name):
    page.set_viewport_size({'width': 390, 'height': 844})
    locator.scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    locator.screenshot(path=str(output/name))
    page.set_viewport_size({'width': 1440, 'height': 1000})


def full(app, password, browser, page, context, course_id, at, output, channel, checks):
    extra = browser.new_context()
    try:
        response = extra.request.post(ORIGIN+'/api/v1/auth/register', data={
            'student_no': 'B008STUD2', 'name': 'B008STUD2', 'password': password}, headers={'Origin': ORIGIN})
        assert response.status == 201
        student_id = response.json()['data']['user']['id']
        write(context, 'POST', f'/courses/{course_id}/members', {'user_id': student_id, 'member_role': 'student'}, 201)
    finally:
        extra.close()
    values = [('single', 'A'), ('multiple', ['A', 'B']), ('boolean', False), ('numeric', 0.2), ('short', '教师参考')]
    questions = []
    for index, (kind, answer) in enumerate(values, 1):
        questions.append(write(context, 'POST', f'/courses/{course_id}/questions', {
            'type': kind, 'stem': f'C05第{index}题', 'answer': answer,
            'options': [{'key': 'A', 'text': '选项甲'}, {'key': 'B', 'text': '选项乙'}] if kind in {'single', 'multiple'} else [],
            'tolerance': 0.1 if kind == 'numeric' else 0, 'difficulty': 'easy', 'knowledge_ids': [1],
            'explanation': '讲评后解析'}, 201)['data'])
    bank = quiz_bank(page)
    bank.get_by_role('button', name='编排新试卷', exact=True).click()
    bank.get_by_label('试卷标题', exact=True).fill('C05受控随堂测')
    bank.get_by_label('要求保密（曾公开的题目不能发布）', exact=True).check()
    for q in questions:
        bank.get_by_label('选择题目版本', exact=True).select_option(str(q['id']))
        bank.get_by_role('button', name='加入试卷', exact=True).click()
    bank.get_by_role('button', name='保存试卷草稿', exact=True).click()
    expect(bank.get_by_role('heading', name='设置窗口并发布')).to_be_visible()
    paper_id = context.request.get(ORIGIN+f'/api/v1/courses/{course_id}/quizzes').json()['data'][0]['id']
    start, end = at+timedelta(minutes=1), at+timedelta(minutes=2)
    for value, label in ((start, '试卷开始'), (end, '试卷截止')):
        bank.get_by_label(label, exact=True).fill(value.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%dT%H:%M'))
    expect(bank.get_by_label('试卷讲评', exact=True)).to_have_count(0)
    bank.get_by_label('保密确认说明', exact=True).fill('确认未公开且非简单复制')
    bank.get_by_role('button', name='发布随堂测并冻结名单', exact=True).click()
    expect(bank.get_by_text('发布冻结人数：2', exact=True)).to_be_visible()
    bank.get_by_role('button', name='刷新逐题统计', exact=True).click()
    stats = bank.locator('.quiz-statistics')
    expect(stats.get_by_text('应交 2 · 已交 0 · 缺交 2 · 客观正确率 —', exact=True)).to_be_visible()
    expect(stats.get_by_role('button', name='发布讲评并开放答案')).to_be_disabled()
    expect(stats.get_by_text('A · 选项甲：0 人 · —', exact=True)).to_have_count(2)
    checks.append('real_knowledge_five_type_ui_draft_publication_zero_statistics_and_null_rates')
    write(context, 'PATCH', f"/questions/{questions[0]['id']}", {'stem': '后续题目新版', 'answer': 'B'})
    page.get_by_role('button', name='退出', exact=True).click()
    login(page, 'B006STUD1', password)
    assert context.request.get(ORIGIN+'/api/v1/notifications').json()['data'][0]['target_id'] == paper_id
    bank = open_quiz(page, paper_id, '未开始')
    expect(bank.get_by_text('试卷尚未开始，开始后可查看题目。')).to_be_visible()
    expect(bank.locator('.attempt-answer-form')).to_have_count(0)
    expect(bank.locator('.quiz-statistics')).to_have_count(0)
    checks.append('real_notification_original_quiz_prestart_metadata_no_questions_or_teacher_controls')
    app.config['TEST_NOW'] = start
    bank = open_quiz(page, paper_id, '进行中')
    form = bank.locator('.attempt-answer-form')
    expect(form).to_be_visible()
    expect(form.get_by_text('C05第1题', exact=True)).to_be_visible()
    expect(bank.get_by_text('后续题目新版', exact=True)).to_have_count(0)
    form.get_by_label('第 1 题作答 选项乙', exact=True).check()
    for option in ('选项甲', '选项乙'):
        form.get_by_label('第 2 题作答 '+option, exact=True).check()
    form.get_by_label('第 3 题作答 错误', exact=True).check()
    # Numeric is intentionally omitted; the short response remains pending.
    form.get_by_label('第 5 题作答', exact=True).fill('学生解释')
    form.get_by_label('确认交卷，接受漏答0分且提交后不可修改', exact=True).check()
    lost = {}

    def lose_attempt(route):
        response = route.fetch()
        assert response.status == 201
        lost['bytes'] = response.body()
        lost['key'] = route.request.headers['idempotency-key']
        app.config['TEST_NOW'] = end
        route.abort('failed')

    page.route(f'**/api/v1/quizzes/{paper_id}/attempts', lose_attempt, times=1)
    form.get_by_role('button', name='提交整份答卷', exact=True).click()
    expect(form.get_by_role('button', name='重试原交卷', exact=True)).to_be_visible()
    with page.expect_response(lambda r: r.url.endswith(f'/quizzes/{paper_id}/attempts')) as replay:
        form.get_by_role('button', name='重试原交卷', exact=True).click()
    assert replay.value.body() == lost['bytes'] and replay.value.request.headers['idempotency-key'] == lost['key']
    expect(bank.get_by_text('总分：待全部批阅 / 50', exact=True)).to_be_visible()
    expect(bank.get_by_text('已定分：20', exact=True)).to_be_visible()
    expect(bank.get_by_text('讲评后解析', exact=True)).to_have_count(0)
    screenshot(page, bank.locator('.attempt-result'), output, f'{channel}-student-pending.png')
    checks.append('fixed_versions_false_multiple_omitted_numeric_pending_short_and_deadline_original_key_byte_replay')
    wrong = context.request.get(ORIGIN+'/api/v1/users/me/wrong-questions').json()['data'][0]
    assert wrong['answer_visible'] is False and 'answer' not in wrong
    page.get_by_role('button', name='退出', exact=True).click()
    login(page, 'B006TEACH', password)
    bank = open_quiz(page, paper_id, '已截止')
    bank.get_by_role('button', name='刷新逐题统计', exact=True).click()
    stats = bank.locator('.quiz-statistics')
    expect(stats.get_by_text('应交 2 · 已交 1 · 缺交 1 · 客观正确率 50.0%', exact=True)).to_be_visible()
    expect(stats.get_by_text('已定分 0 · 待批 1 · 正确数 — · 正确率 — · 均分 —', exact=True)).to_be_visible()
    for key, text in (('A', '选项甲'), ('B', '选项乙')):
        expect(stats.get_by_text(f'{key} · {text}：1 人 · 100.0%', exact=True)).to_have_count(1 if key == 'A' else 2)
    checks.append('teacher_frozen_missing_omission_denominator_short_null_and_multiple_sum_200_percent')
    inline = bank.locator('.attempt-inline')
    inline.locator('.rows button').click()
    inline.get_by_label('批阅第 5 题', exact=True).check()
    inline.get_by_label('第 5 题评分', exact=True).fill('7.01')
    inline.get_by_role('button', name='保存本次批阅', exact=True).click()
    expect(inline.get_by_text('总分：27.01 / 50', exact=True)).to_be_visible()
    bank.get_by_role('button', name='刷新逐题统计', exact=True).click()
    expect(stats.get_by_text('已定分 1 · 待批 0 · 正确数 — · 正确率 — · 均分 7.01', exact=True)).to_be_visible()
    screenshot(page, stats, output, f'{channel}-teacher-statistics.png')
    checks.append('real_manual_grade_updates_mean_pending_and_390px_statistics')
    # Read fault clears stale statistics and detail, then actual retry reloads them.
    page.route(f'**/api/v1/quizzes/{paper_id}/statistics', lambda route: route.abort('failed'), times=1)
    bank.get_by_role('button', name='刷新逐题统计', exact=True).click()
    expect(bank.get_by_role('button', name='重试试卷', exact=True)).to_be_visible()
    expect(bank.locator('.quiz-statistics')).to_have_count(0)
    bank.get_by_role('button', name='重试试卷', exact=True).click()
    bank.get_by_role('button', name=f'#{paper_id} · C05受控随堂测 · 已截止', exact=True).click()
    checks.append('injected_statistics_failure_removes_stale_data_and_real_retry_recovers')
    bank.get_by_role('button', name='发布讲评并开放答案', exact=True).click()
    expect(bank.get_by_text('讲评已发布。学生重新加载后可查看答案与解析。', exact=True)).to_be_visible()
    expect(bank.get_by_role('button', name='发布讲评并开放答案')).to_have_count(0)
    review_at = write(context, 'POST', f'/quizzes/{paper_id}/review', {})['data']['review_published_at']
    assert review_at == end.isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    with closing(connect(app.config['DATABASE_PATH'])) as db:
        assert db.execute('SELECT count(*) FROM attempt').fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM audit_event WHERE action='quiz.review'").fetchone()[0] == 1
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    checks.append('explicit_review_exact_deadline_persists_once_and_repeat_keeps_original_timestamp')
    page.get_by_role('button', name='退出', exact=True).click()
    login(page, 'B006STUD1', password)
    bank = open_quiz(page, paper_id, '已截止')
    expect(bank.locator('.attempt-result').get_by_text('总分：27.01 / 50', exact=True)).to_be_visible()
    expect(bank.locator('.attempt-result').get_by_text('参考答案：教师参考', exact=True)).to_be_visible()
    expect(bank.locator('.attempt-result').get_by_text('解析：讲评后解析', exact=True)).to_have_count(5)
    expect(bank.locator('.quiz-statistics')).to_have_count(0)
    screenshot(page, bank.locator('.attempt-result'), output, f'{channel}-student-reviewed.png')
    page.reload()
    bank = open_quiz(page, paper_id, '已截止')
    expect(bank.locator('.attempt-result').get_by_text('参考答案：教师参考', exact=True)).to_be_visible()
    wrong = context.request.get(ORIGIN+'/api/v1/users/me/wrong-questions').json()['data'][0]
    assert wrong['answer_visible'] and wrong['answer'] == 'A'
    checks.append('student_relogin_refresh_latest_score_fixed_answers_and_wrong_entry_release_390px')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'logs/spec-008/browsers')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'started_at': datetime.now(UTC).isoformat(),
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'working_tree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
              'scope': 'real 001/005/006/008 controlled HTTP/UI; server clock and network faults injected',
              'browsers': [], 'page_errors': []}
    try:
        with sync_playwright() as playwright:
            for channel in ('chrome', 'msedge'):
                with running(True) as (app, password, course_id, at):
                    browser = playwright.chromium.launch(channel=channel, headless=True)
                    try:
                        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, timezone_id='Asia/Shanghai')
                        page = context.new_page()
                        page.on('pageerror', lambda error: report['page_errors'].append(type(error).__name__))
                        entry = {'channel': channel, 'version': browser.version, 'checks': []}
                        report['browsers'].append(entry)
                        login(page, 'B006TEACH', password)
                        full(app, password, browser, page, context, course_id, at, args.output, channel, entry['checks'])
                        assert not report['page_errors']
                        context.close()
                    finally:
                        browser.close()
        report['status'] = 'passed'
        print('C05 Chrome/Edge real quiz flow passed')
    except (AssertionError, OSError, RuntimeError, PlaywrightError) as error:
        report['status'] = 'failed'
        report['failure_type'] = type(error).__name__
        report['failure_location'] = [f'{frame.name}:{frame.lineno}' for frame in traceback.extract_tb(error.__traceback__)
                                      if frame.filename == __file__]
        raise RuntimeError('C05 browser verification failed; see redacted report') from None
    finally:
        report['finished_at'] = datetime.now(UTC).isoformat()
        (args.output/'browser-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
