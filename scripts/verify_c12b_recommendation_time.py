"""Focused UI-03 real HTTP/Chrome/Edge cutoff rendering; no C11 algorithm rerun."""

import argparse
import hashlib
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
from scripts.verify_spec006_questions import ORIGIN, ROOT, login


def refresh(panel, page):
    with page.expect_response(lambda r: '/recommendations?' in r.url) as response:
        panel.get_by_role('button', name='刷新推荐', exact=True).click()
    assert response.value.status == 200
    expect(panel).to_have_attribute('aria-busy', 'false')
    return response.value.json()['data']


def full(app, password, context, page, course_id, output, entry):
    chapter = write(context, 'POST', f'/courses/{course_id}/chapters', {'title': 'C12b推荐时间'}, 201)['data']
    point = write(context, 'POST', f"/chapters/{chapter['id']}/knowledge-points", {
        'title': '跨日知识', 'content': '真实HTTP内容', 'published': True}, 201)['data']
    write(context, 'PATCH', f"/knowledge-points/{point['id']}", {'is_foundational': True})
    question = write(context, 'POST', f'/courses/{course_id}/questions', {
        'type': 'boolean', 'stem': 'C12b公开练习', 'options': [], 'answer': True, 'difficulty': 'easy',
        'knowledge_ids': [point['id']], 'practice_available': True, 'explanation': '固定版本解析'}, 201)['data']
    page.get_by_role('button', name='退出', exact=True).click()
    login(page, 'B006STUD1', password)
    panel = page.locator('.recommendation-bank')
    for at, expected in [(datetime(2026, 10, 18, 15, 59, 59, tzinfo=UTC), '2026-10-18 23:59:59'),
                         (datetime(2026, 10, 18, 16, 0, 0, tzinfo=UTC), '2026-10-19 00:00:00')]:
        app.config['TEST_NOW'] = at
        data = refresh(panel, page)
        raw_until = at.isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        assert data['source_until'] == raw_until
        assert data['items'][0]['question_version_id'] == question['version_id']
        expect(panel.locator('.recommendation-meta')).to_have_text(
            f'依据截止 {expected} (Asia/Shanghai) · 算法 recommend-v1')
        again = context.request.get(ORIGIN+f'/api/v1/courses/{course_id}/recommendations?limit=5').json()['data']
        assert again == data
        entry['checks'].append({'utc_source_until': raw_until, 'displayed': expected+' (Asia/Shanghai)',
                                'http_data_unchanged_after_render': True})
    # Keep this complete card inside the viewport for Edge's headless capture.
    page.set_viewport_size({'width': 390, 'height': 1200})
    panel.scroll_into_view_if_needed()
    expect(panel.locator('.recommendation-meta')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    panel.screenshot(path=str(output/f"{entry['channel']}-recommendation-390.png"), animations='disabled')
    page.set_viewport_size({'width': 1440, 'height': 1000})
    # The existing recommendation entry still uses the original practice component.
    panel.get_by_role('button', name=f"去练习 · 版本 #{question['version_id']}", exact=True).click()
    bank = page.locator('.practice-bank')
    expect(bank.locator('.practice-form')).to_be_visible()
    bank.get_by_label('练习作答 错误', exact=True).check()
    app.config['TEST_NOW'] = at+timedelta(seconds=1)
    with page.expect_response(lambda r: '/practice-attempts' in r.url and r.request.method == 'POST') as submitted:
        bank.get_by_role('button', name='提交本次练习', exact=True).click()
    response = submitted.value
    assert response.status == 201
    saved, key = response.body(), response.request.headers['idempotency-key']
    expect(bank.locator('.practice-result')).to_be_visible()
    app.config['TEST_NOW'] = at+timedelta(seconds=2)
    data = refresh(panel, page)
    assert data['source_until'] == '2026-10-18T16:00:02.000Z'
    assert data['items'][0]['sample_size'] == 1 and data['items'][0]['mastery'] == 0
    session = context.request.get(ORIGIN+'/api/v1/auth/session').json()['data']
    replay = context.request.post(ORIGIN+f"/api/v1/questions/{question['id']}/practice-attempts",
                                  data={'question_version_id': question['version_id'], 'answer': False},
                                  headers={'Origin': ORIGIN, 'X-CSRF-Token': session['csrf_token'], 'Idempotency-Key': key})
    assert replay.status == 201 and replay.body() == saved
    assert refresh(panel, page)['items'][0]['sample_size'] == 1
    with closing(connect(app.config['DATABASE_PATH'])) as db:
        stamp = db.execute('SELECT created_at FROM practice_attempt').fetchone()[0]
    assert stamp == '2026-10-18T16:00:01.000Z'
    entry['checks'].append({'real_practice_http': 201, 'replay_bytes_equal': True, 'sample_size': 1,
                            'db_created_at_utc': stamp, 'success_snapshot_sha256': hashlib.sha256(saved).hexdigest()})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'logs/c12b/recommendation-time')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'started_at': datetime.now(UTC).isoformat(),
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'dirty_paths': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines(),
              'scope': 'UI-03 only: real HTTP/UI; account bootstrap and TEST_NOW controlled; no response mocks',
              'browsers': [], 'page_errors': []}
    try:
        with sync_playwright() as playwright:
            for channel, zone in [('chrome', 'UTC'), ('msedge', 'America/Los_Angeles')]:
                with running(False) as (app, password, course_id, _at):
                    app.config['TEST_NOW'] = datetime(2026, 10, 18, 15, 59, 59, tzinfo=UTC)
                    browser = playwright.chromium.launch(channel=channel, headless=True)
                    try:
                        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, timezone_id=zone)
                        page = context.new_page()
                        page.on('pageerror', lambda error: report['page_errors'].append(type(error).__name__))
                        entry = {'channel': channel, 'version': browser.version, 'browser_timezone': zone, 'checks': []}
                        report['browsers'].append(entry)
                        login(page, 'B006TEACH', password)
                        full(app, password, context, page, course_id, args.output, entry)
                        assert not report['page_errors']
                        context.close()
                    finally:
                        browser.close()
        report['status'] = 'passed'
        print('C12b recommendation Shanghai cutoff and UTC facts: Chrome/Edge passed')
    except (AssertionError, OSError, RuntimeError, PlaywrightError) as error:
        report['status'] = 'failed'
        report['failure_type'] = type(error).__name__
        report['failure_location'] = [f'{frame.name}:{frame.lineno}' for frame in traceback.extract_tb(error.__traceback__)
                                      if frame.filename == __file__]
        raise RuntimeError('C12b recommendation failed; see redacted report') from None
    finally:
        report['finished_at'] = datetime.now(UTC).isoformat()
        (args.output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
