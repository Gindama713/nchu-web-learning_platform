"""Focused C12a-UI-02 real HTTP/Chrome/Edge regression; no analytics rerun.

Only account bootstrap and TEST_NOW are controlled. No successful HTTP doubles.
"""

import argparse
import hashlib
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


def raw_write(context, path, payload, key):
    session = context.request.get(ORIGIN+'/api/v1/auth/session').json()['data']
    return context.request.post(ORIGIN+'/api/v1'+path, data=payload,
                                headers={'Origin': ORIGIN, 'X-CSRF-Token': session['csrf_token'],
                                         'Idempotency-Key': key})


def open_paper(page, paper_id, title, state, quiz):
    heading = '随堂测' if quiz else '课程试卷'
    bank = page.locator('.paper-bank').filter(has=page.get_by_role('heading', name=heading, exact=True))
    bank.get_by_role('button', name='重新加载试卷', exact=True).click()
    bank.get_by_role('button', name=f'#{paper_id} · {title} · {state}', exact=True).click()
    return bank


def capture(page, locator, output, filename):
    page.set_viewport_size({'width': 390, 'height': 844})
    locator.scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    locator.screenshot(path=str(output/filename))
    page.set_viewport_size({'width': 1440, 'height': 1000})


def full(app, password, browser, context, page, course_id, output, entry):
    late = browser.new_context()
    try:
        registered = late.request.post(ORIGIN+'/api/v1/auth/register', data={
            'student_no': 'C12BLATE', 'name': 'C12BLATE', 'password': password}, headers={'Origin': ORIGIN})
        assert registered.status == 201
        write(context, 'POST', f'/courses/{course_id}/members',
              {'user_id': registered.json()['data']['user']['id'], 'member_role': 'student'}, 201)
        chapter = write(context, 'POST', f'/courses/{course_id}/chapters', {'title': 'C12b时间'}, 201)['data']
        point = write(context, 'POST', f"/chapters/{chapter['id']}/knowledge-points",
                      {'title': '时区知识', 'content': '真实HTTP知识', 'published': True}, 201)['data']
        start = datetime(2026, 10, 18, 15, 59, tzinfo=UTC)
        end, submitted, review = start+timedelta(minutes=2), start+timedelta(minutes=1), start+timedelta(minutes=3)
        for quiz in (False, True):
            kind = 'quiz' if quiz else 'exam'
            title = f'C12b-{kind}'
            app.config['TEST_NOW'] = start-timedelta(minutes=1)
            if quiz:
                page.get_by_role('button', name='退出', exact=True).click()
                login(page, 'B006TEACH', password)
            question = write(context, 'POST', f'/courses/{course_id}/questions', {
                'type': 'boolean', 'stem': title+'题干', 'answer': True, 'options': [],
                'difficulty': 'easy', 'knowledge_ids': [point['id']], 'explanation': title+'解析'}, 201)['data']
            paper = write(context, 'POST', f'/courses/{course_id}/papers', {
                'title': title, 'kind': kind, 'confidential': True,
                'items': [{'question_version_id': question['version_id'], 'points': 10}]}, 201)['data']
            paper_id = paper['id']
            times = {'start_at': start.isoformat(), 'end_at': end.isoformat(), 'confidentiality_note': '未公开且非复制'}
            path = f'/courses/{course_id}/quizzes' if quiz else f'/papers/{paper_id}/publish'
            if quiz:
                times['paper_id'] = paper_id
            else:
                times['review_at'] = review.isoformat()
            write(context, 'POST', path, times, 201 if quiz else 200)
            teacher_raw = context.request.get(ORIGIN+f'/api/v1/papers/{paper_id}').json()['data']
            bank = open_paper(page, paper_id, title, '未开始', quiz)
            detail = bank.locator('.paper-detail')
            expect(detail.get_by_text('开始：2026-10-18 23:59:00 (Asia/Shanghai)', exact=False)).to_be_visible()
            expect(detail.get_by_text('截止：2026-10-19 00:01:00 (Asia/Shanghai)', exact=False)).to_be_visible()
            expect(detail.get_by_text('讲评：'+('待教师讲评' if quiz else '2026-10-19 00:02:00 (Asia/Shanghai)'), exact=False)).to_be_visible()
            assert context.request.get(ORIGIN+f'/api/v1/papers/{paper_id}').json()['data'] == teacher_raw
            entry['checks'].append(kind+': real window Sunday-to-Monday Shanghai, explicit zone, null review, UTC HTTP unchanged')
            page.get_by_role('button', name='退出', exact=True).click()
            login(page, 'B006STUD1', password)
            bank = open_paper(page, paper_id, title, '未开始', quiz)
            expect(bank.get_by_text('试卷尚未开始，开始后可查看题目。')).to_be_visible()
            payload = {'answers': [{'question_version_id': question['version_id'], 'value': False}]}
            target = f"/{'quizzes' if quiz else 'papers'}/{paper_id}/attempts"
            assert raw_write(context, target, payload, str(uuid4())).status == 409
            app.config['TEST_NOW'] = start
            bank = open_paper(page, paper_id, title, '进行中', quiz)
            form = bank.locator('.attempt-answer-form')
            expect(form).to_be_visible()
            if quiz:
                expect(form.get_by_text('截止：2026-10-19 00:01:00 (Asia/Shanghai)', exact=False)).to_be_visible()
                expect(form.get_by_text('收卷以服务器时间为准。', exact=False)).to_be_visible()
            capture(page, bank.locator('.paper-detail'), output, f"{entry['channel']}-{kind}-window.png")
            form.get_by_label('第 1 题作答 错误', exact=True).check()
            form.get_by_label('确认交卷，接受漏答0分且提交后不可修改', exact=True).check()
            app.config['TEST_NOW'] = submitted
            with page.expect_response(lambda r, target=target: r.url.endswith(target) and r.request.method == 'POST') as response:
                form.get_by_role('button', name='提交整份答卷', exact=True).click()
            success = response.value
            assert success.status == 201
            saved, key = success.body(), success.request.headers['idempotency-key']
            attempt_id = success.json()['data']['id']
            expect(bank.locator('.attempt-result').get_by_text('提交时间：2026-10-19 00:00:00 (Asia/Shanghai)', exact=True)).to_be_visible()
            expect(bank.get_by_text('解析：'+title+'解析', exact=True)).to_have_count(0)
            raw = context.request.get(ORIGIN+f'/api/v1/attempts/{attempt_id}').json()['data']
            bank.locator('.attempt-result').get_by_role('button', name='重新加载此答卷', exact=True).click()
            expect(bank.locator('.attempt-result').get_by_text('提交时间：2026-10-19 00:00:00 (Asia/Shanghai)', exact=True)).to_be_visible()
            assert context.request.get(ORIGIN+f'/api/v1/attempts/{attempt_id}').json()['data'] == raw
            with closing(connect(app.config['DATABASE_PATH'])) as db:
                original_stamp = db.execute('SELECT submitted_at FROM attempt WHERE id=?', (attempt_id,)).fetchone()[0]
            assert original_stamp == '2026-10-18T16:00:00.000Z'
            capture(page, bank.locator('.attempt-result'), output, f"{entry['channel']}-{kind}-submitted.png")
            app.config['TEST_NOW'] = end
            # New server submissions are closed; original successful key still replays exact UTC snapshot.
            if late.request.get(ORIGIN+'/api/v1/auth/session').status != 200:
                late_page = late.new_page()
                login(late_page, 'C12BLATE', password)
                late_page.close()
            assert raw_write(late, target, payload, str(uuid4())).status == 409
            replay = raw_write(context, target, payload, key)
            assert replay.status == 201 and replay.body() == saved
            bank = open_paper(page, paper_id, title, '已截止', quiz)
            expect(bank.get_by_text('解析：'+title+'解析', exact=True)).to_have_count(0)
            detail_data = context.request.get(ORIGIN+f'/api/v1/papers/{paper_id}').json()['data']
            attempt_data = context.request.get(ORIGIN+f'/api/v1/attempts/{attempt_id}').json()['data']
            assert 'answer' not in detail_data['items'][0] and 'answer' not in attempt_data['answers'][0]
            if quiz:
                page.get_by_role('button', name='退出', exact=True).click()
                login(page, 'B006TEACH', password)
                bank = open_paper(page, paper_id, title, '已截止', quiz)
                bank.get_by_role('button', name='发布讲评并开放答案', exact=True).click()
                expect(bank.get_by_text('讲评：2026-10-19 00:01:00 (Asia/Shanghai)', exact=False)).to_be_visible()
                page.get_by_role('button', name='退出', exact=True).click()
                login(page, 'B006STUD1', password)
            else:
                app.config['TEST_NOW'] = review
            bank = open_paper(page, paper_id, title, '已截止', quiz)
            expect(bank.locator('.attempt-result').get_by_text('解析：'+title+'解析', exact=True)).to_be_visible()
            replay = raw_write(context, target, payload, key)
            assert replay.status == 201 and replay.body() == saved
            with closing(connect(app.config['DATABASE_PATH'])) as db:
                assert db.execute('SELECT submitted_at FROM attempt WHERE id=?', (attempt_id,)).fetchone()[0] == original_stamp
            entry['checks'].append(kind+': UI submit Shanghai midnight; prestart/deadline 409; review protection/release; byte-exact UTC replay and DB unchanged')
            entry.setdefault('utc_facts', []).append({'kind': kind, 'submitted_at': original_stamp,
                                                     'success_snapshot_sha256': hashlib.sha256(saved).hexdigest()})
    finally:
        late.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'logs/c12b/paper-time')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'started_at': datetime.now(UTC).isoformat(),
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'dirty_paths': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines(),
              'scope': 'UI-02 only: real 001/005/006/008 HTTP/UI, account bootstrap and TEST_NOW; no successful response mocks',
              'browsers': [], 'page_errors': []}
    try:
        with sync_playwright() as playwright:
            for channel, zone in [('chrome', 'UTC'), ('msedge', 'America/Los_Angeles')]:
                with running(False) as (app, password, course_id, _at):
                    app.config['TEST_NOW'] = datetime(2026, 10, 18, 15, 58, tzinfo=UTC)
                    browser = playwright.chromium.launch(channel=channel, headless=True)
                    try:
                        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, timezone_id=zone)
                        page = context.new_page()
                        page.on('pageerror', lambda error: report['page_errors'].append(type(error).__name__))
                        entry = {'channel': channel, 'version': browser.version, 'browser_timezone': zone, 'checks': []}
                        report['browsers'].append(entry)
                        login(page, 'B006TEACH', password)
                        full(app, password, browser, context, page, course_id, args.output, entry)
                        assert not report['page_errors']
                        context.close()
                    finally:
                        browser.close()
        report['status'] = 'passed'
        print('C12b paper/attempt time and protection seams: Chrome/Edge passed')
    except (AssertionError, OSError, RuntimeError, PlaywrightError) as error:
        report['status'] = 'failed'
        report['failure_type'] = type(error).__name__
        report['failure_location'] = [f'{frame.name}:{frame.lineno}' for frame in traceback.extract_tb(error.__traceback__)
                                      if frame.filename == __file__]
        raise RuntimeError('C12b failed; see redacted report') from None
    finally:
        report['finished_at'] = datetime.now(UTC).isoformat()
        (args.output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
