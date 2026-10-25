"""C11 installed Chrome/Edge: real socket HTTP + existing 001/005/006 business UI.

Synthetic accounts/course facts are created through real APIs after the shared
temporary server's admin/teacher bootstrap. Calculation faults/delays are explicit
server-side fixtures; never replace recommendation HTTP responses in the browser.
"""

import argparse
import json
import platform
import subprocess
import sys
import threading
import traceback
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import expect, sync_playwright

from backend.models import recommendation
from scripts.verify_spec005_browsers import ORIGIN, Api, servers
from tests.test_question_validation import question


def login(page, number, password):
    with page.expect_response(lambda r: r.url.endswith('/auth/session')) as initial:
        page.goto(ORIGIN)
    initial.value.body()
    page.get_by_label('学号', exact=True).fill(number)
    page.get_by_label('密码', exact=True).fill(password)
    with page.expect_response(lambda r: r.url.endswith('/auth/login')) as pending:
        page.get_by_role('button', name='登录', exact=True).click()
    assert pending.value.status == 200
    expect(page.locator('.recommendation-bank')).to_have_attribute('aria-busy', 'false', timeout=15000)


def refresh(page, panel, status=200):
    with page.expect_response(lambda r: '/recommendations?' in r.url) as response:
        panel.get_by_role('button', name='刷新推荐', exact=True).click()
    assert response.value.status == status
    expect(panel).to_have_attribute('aria-busy', 'false')
    body = response.value.json()
    if status == 200:
        assert response.value.headers['cache-control'] == 'no-store'
        assert {'items', 'reason', 'source_until', 'algorithm_version'} == body['data'].keys()
        assert body['data']['algorithm_version'] == 'recommend-v1'
    return body


def practice(page, q, answer='B', key=None):
    session = page.request.get(ORIGIN+'/api/v1/auth/session').json()['data']
    response = page.request.post(ORIGIN+f"/api/v1/questions/{q['id']}/practice-attempts",
        data={'question_version_id': q['version_id'], 'answer': answer}, headers={'Origin': ORIGIN,
        'X-CSRF-Token': session['csrf_token'], 'Idempotency-Key': key or str(uuid4())})
    assert response.status == 201
    return response.json()['data']


def verify(playwright, channel, password, output):
    admin, teacher, student = Api(), Api(), Api()
    admin.login('T005ADMIN', password)
    tid = teacher.login('T005TEACH', password)
    number = 'T012CHROME' if channel == 'chrome' else 'T012EDGE01'
    student.call('POST', '/auth/register', {'student_no': number, 'name': 'C11学生', 'password': password}, 201)
    sid = student.login(number, password)
    cid = admin.call('POST', '/courses', {'title': f'C11 CPU {channel}', 'teacher_id': tid}, 201)['id']
    teacher.call('POST', f'/courses/{cid}/members', {'user_id': sid, 'member_role': 'student'}, 201)
    chapter = teacher.call('POST', f'/courses/{cid}/chapters', {'title': 'CPU基础'}, 201)['id']
    browser = playwright.chromium.launch(channel=channel, headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    errors, checks = [], []
    try:
        page = context.new_page()
        page.set_default_timeout(10000)
        page.on('pageerror', lambda error: errors.append(type(error).__name__))
        login(page, number, password)
        panel = page.locator('.recommendation-bank')
        panel.get_by_label('推荐课程', exact=True).select_option(str(cid))
        expect(panel).to_have_attribute('aria-busy', 'false')
        assert refresh(page, panel)['data']['reason'] == 'no_published_knowledge'
        points = [teacher.call('POST', f'/chapters/{chapter}/knowledge-points', {
            'title': title, 'content': '<p>PC 指向下一条指令。</p><script>window.c11_bad=1</script>',
            'example': '<p>程序计数器加一。</p>', 'published': True}, 201)['id']
            for title in ('程序计数器', '指令寄存器', '零样本知识')]
        assert refresh(page, panel)['data']['reason'] == 'no_foundational_candidates'
        for kid in points[:2]:
            teacher.call('PATCH', f'/knowledge-points/{kid}', {'is_foundational': True})
        cold = refresh(page, panel)['data']
        assert [r['knowledge_id'] for r in cold['items']] == points[:2]
        student.call('PUT', f'/knowledge-points/{points[0]}/progress', {'completed': True})
        assert [r['knowledge_id'] for r in refresh(page, panel)['data']['items']] == [points[1]]
        student.call('PUT', f'/knowledge-points/{points[0]}/progress', {'completed': False})
        checks.append('real 005 empty course / no foundation / sorted cold start / completed foundation excluded')

        q1, q2 = [teacher.call('POST', f'/courses/{cid}/questions',
            question(practice_available=True, knowledge_ids=points[:2]), 201) for _ in range(2)]
        teacher.call('PATCH', f"/questions/{q1['id']}", {'stem': '较新固定版本'})
        current = refresh(page, panel)['data']
        assert all(r['question_version_id'] == q2['version_id'] for r in current['items'])
        with page.expect_response(lambda r: r.url.endswith(f'/knowledge-points/{points[0]}')):
            panel.get_by_role('button', name=f'阅读知识 #{points[0]}', exact=True).click()
        expect(panel.locator('.recommendation-source h3')).to_have_text('程序计数器')
        expect(panel.locator('.recommendation-source script')).to_have_count(0)
        assert page.evaluate('window.c11_bad === undefined')
        expect(panel.locator('.recommendation-source')).to_contain_text(f'章节 #{chapter}')
        panel.screenshot(path=str(output/f'{channel}-source-desktop.png'))
        panel.get_by_role('button', name=f'去练习 · 版本 #{q2["version_id"]}', exact=True).first.click()
        bank = page.locator('.practice-bank')
        expect(bank.locator('.practice-form')).to_be_visible()
        with page.expect_response(lambda r: '/practice-attempts' in r.url and r.request.method == 'POST') as submitted:
            bank.get_by_role('button', name='提交本次练习', exact=True).click()  # Actual blank: excluded.
        assert submitted.value.status == 201
        expect(bank.locator('.practice-result')).to_be_visible()
        assert refresh(page, panel)['data']['reason'] == 'cold_start'
        key = str(uuid4())
        first = practice(page, q2, key=key)
        assert practice(page, q2, key=key) == first
        value = refresh(page, panel)['data']
        assert [(r['knowledge_id'], r['sample_size'], r['mastery'], r['score']) for r in value['items']] == [
            (points[0], 1, 0, 1), (points[1], 1, 0, 1), (points[2], 0, None, .6)]
        checks.append('latest eligible version minimum ID; safe real knowledge source; existing practice UI 201; blank/replay excluded')

        for _ in range(4):
            practice(page, q2, 'A')
        student.call('PUT', f'/knowledge-points/{points[0]}/progress', {'completed': True})
        value = refresh(page, panel)['data']
        assert [r['knowledge_id'] for r in value['items']] == [points[2], points[1]]
        assert value['items'][1]['mastery'] == .8 and value['items'][1]['reason'] == 'incomplete'
        student.call('PUT', f'/knowledge-points/{points[1]}/progress', {'completed': True})
        teacher.call('PATCH', f'/knowledge-points/{points[2]}', {'published': False})
        empty = refresh(page, panel)['data']
        assert empty['items'] == [] and empty['reason'] == 'all_mastered'
        expect(panel).to_contain_text('均已完成')
        checks.append('five real samples, .8 boundary + completed filter; uncompleted mastery retained; all-mastered metadata')

        student.call('PUT', f'/knowledge-points/{points[0]}/progress', {'completed': False})
        teacher.call('PATCH', f"/questions/{q2['id']}", {'practice_available': False})
        teacher.call('PATCH', f"/questions/{q1['id']}", {'practice_available': False})
        assert refresh(page, panel)['data']['items'][0]['question_version_id'] is None
        expect(panel).to_contain_text('暂无合格的开放客观练习')
        q3 = teacher.call('POST', f'/courses/{cid}/questions', question(practice_available=True, knowledge_ids=[points[0]]), 201)
        refresh(page, panel)
        teacher.call('PATCH', f'/knowledge-points/{points[0]}', {'published': False})
        panel.get_by_role('button', name=f'阅读知识 #{points[0]}', exact=True).click()
        expect(panel.get_by_role('alert')).to_contain_text('已不在当前推荐')
        expect(panel.locator('.recommendation-result')).to_have_count(0)
        teacher.call('PATCH', f'/knowledge-points/{points[0]}', {'published': True})
        refresh(page, panel)
        checks.append('latest closed practice has null entry; unpublish before source click removes stale recommendation')

        panel.get_by_role('button', name=f'去练习 · 版本 #{q3["version_id"]}', exact=True).click()
        expect(bank).to_have_attribute('aria-busy', 'false')
        expect(bank.get_by_label('练习作答 当前数据', exact=True)).to_be_enabled()
        with patch.object(recommendation, 'calculate', side_effect=RuntimeError('C11 explicit fault fixture')):
            failure = refresh(page, panel, 503)
            assert failure['error']['code'] == 'RECOMMENDATION_UNAVAILABLE'
            expect(panel.locator('.recommendation-result')).to_have_count(0)
            bank.get_by_label('练习作答 当前数据', exact=True).check()
            with page.expect_response(lambda r: '/practice-attempts' in r.url and r.request.method == 'POST') as saved:
                bank.get_by_role('button', name='提交本次练习', exact=True).click()
            assert saved.value.status == 201
            expect(bank.locator('.practice-result')).to_be_visible()
            page.set_viewport_size({'width': 390, 'height': 844})
            panel.screenshot(path=str(output/f'{channel}-failure-390.png'))
        value = refresh(page, panel)['data']
        assert value['items'][0]['sample_size'] == 6
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        panel.screenshot(path=str(output/f'{channel}-recovered-390.png'))
        checks.append('server fault fixture returns real HTTP503 while independent practice UI submits201; explicit retry + 390px')

        original = recommendation.calculate
        entered, release = threading.Event(), threading.Event()

        def delayed(*args):
            entered.set()
            if not release.wait(20):
                raise RuntimeError('C11 delay timed out')
            return original(*args)

        with patch.object(recommendation, 'calculate', delayed):
            panel.get_by_role('button', name='刷新推荐', exact=True).click()
            assert entered.wait(5)
            panel.get_by_label('推荐数量', exact=True).fill('2')
            with page.expect_response(lambda r: '/recommendations?' in r.url):
                release.set()
            expect(panel.locator('.recommendation-result')).to_have_count(0)
        refresh(page, panel)
        checks.append('server-delayed genuine response discarded after limit changed; explicit refresh recovers')

        teacher.call('DELETE', f'/courses/{cid}/members/{sid}', status=204)
        assert page.request.get(ORIGIN+f'/api/v1/courses/{cid}/recommendations').status == 404
        panel.get_by_role('button', name='刷新推荐', exact=True).click()
        expect(panel).to_have_attribute('aria-busy', 'false')
        expect(panel.locator('.recommendation-result')).to_have_count(0)
        expect(panel.get_by_label('推荐课程', exact=True).locator('option')).to_have_count(0)
        teacher.call('POST', f'/courses/{cid}/members', {'user_id': sid, 'member_role': 'student'}, 201)
        refresh(page, panel)
        admin.call('PATCH', f'/users/{sid}', {'active': False})
        # Session verification rejects before recommendations can be requested.
        panel.get_by_role('button', name='刷新推荐', exact=True).click()
        expect(panel.get_by_role('alert')).to_be_visible()
        expect(panel.locator('.recommendation-result')).to_have_count(0)
        checks.append('real membership revocation404 + restoration; account deactivation removes result before another query')
        assert errors == []
        return {'channel': channel, 'version': browser.version, 'status': 'passed', 'checks': checks,
                'page_errors': errors, 'course_id': cid}
    except Exception:  # Save synthetic UI diagnostics, then preserve the original failure.
        page.locator('.practice-bank').screenshot(path=str(output/f'{channel}-diagnostic.png'))
        (output/f'{channel}-diagnostic.txt').write_text(page.locator('.practice-bank').inner_text(), encoding='utf-8')
        raise
    finally:
        context.close()
        browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'logs/spec-012-browsers')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'started_at': datetime.now(UTC).isoformat(), 'os': platform.platform(),
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'dirty_paths': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines(),
              'scope': 'local real socket HTTP/UI; synthetic data; explicit calculation fault/delay fixtures; not performance/classroom',
              'server_fixture': 'TESTING=True disables unrelated grading scanner; single-thread WSGI; no worker/concurrency acceptance',
              'browsers': []}
    try:
        with servers() as password, sync_playwright() as playwright:
            for channel in ('chrome', 'msedge'):
                report['browsers'].append(verify(playwright, channel, password, args.output))
                print(f"{channel}: {len(report['browsers'][-1]['checks'])} groups passed", flush=True)
        report['status'] = 'passed'
        return 0
    except Exception as error:  # noqa: BLE001 - preserve locations without credentials/request bodies
        report['status'] = 'failed'
        report['failure_type'] = type(error).__name__
        report['failure_locations'] = [f'{Path(f.filename).name}:{f.name}:{f.lineno}' for f in traceback.extract_tb(error.__traceback__)]
        report['failure_chain'] = []
        cause = error.__cause__ or error.__context__
        while cause is not None:
            report['failure_chain'].append({'type': type(cause).__name__, 'locations': [
                f'{Path(f.filename).name}:{f.name}:{f.lineno}'
                for f in traceback.extract_tb(cause.__traceback__)]})
            cause = cause.__cause__ or cause.__context__
        print(f"FAILED {report['failure_type']}: {report['failure_locations']}", file=sys.stderr)
        return 1
    finally:
        report['finished_at'] = datetime.now(UTC).isoformat()
        (args.output/'browser-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    sys.exit(main())
