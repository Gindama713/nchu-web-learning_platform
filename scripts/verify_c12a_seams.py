"""C12a gap checks on merged code; real sockets/UI, synthetic accounts only.

Does not rerun the dedicated 008/010B or 013 suites. Account bootstrap and
TEST_NOW come from the existing isolated runner; all learning writes use APIs.
"""

import argparse
import json
import sqlite3
import subprocess
import traceback
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import expect, sync_playwright

from backend.shared.db import connect, migrate
from scripts.verify_spec006_papers import running
from scripts.verify_spec006_questions import ORIGIN, ROOT


def login(page, number, password):
    page.goto(ORIGIN)
    expect(page.get_by_label('学号', exact=True)).to_be_visible()
    with page.expect_response(lambda r: r.url.endswith('/auth/session')):
        page.reload()
    page.get_by_label('学号', exact=True).fill(number)
    page.get_by_label('密码', exact=True).fill(password)
    with page.expect_response(lambda r: r.url.endswith('/auth/login') and r.request.method == 'POST') as info:
        page.get_by_role('button', name='登录', exact=True).click()
    assert info.value.status == 200
    expect(page.locator('.question-bank').get_by_label('题库课程')).to_be_enabled()
    expect(page.locator('.question-bank').get_by_text('正在加载或保存…')).to_have_count(0)


def get(context, path, status=200):
    response = context.request.get(ORIGIN + '/api/v1' + path)
    assert response.status == status, f'GET {path}: {response.status}, expected {status}'
    return response


def write(context, method, path, body, expected=200):
    session = get(context, '/auth/session').json()['data']
    response = context.request.fetch(ORIGIN + '/api/v1' + path, method=method, data=body,
                                     headers={'Origin': ORIGIN, 'X-CSRF-Token': session['csrf_token']})
    assert response.status == expected, f'{method} {path}: {response.status}, expected {expected}'
    return response.json() if expected != 204 else None


def verify(playwright, channel, output):
    entry = {'channel': channel, 'checks': [], 'page_errors': [], 'http_checks': []}
    with running(False) as (app, password, course, at):
        browser = playwright.chromium.launch(channel=channel, headless=True)
        try:
            entry['version'] = browser.version
            teacher = browser.new_context(viewport={'width': 1440, 'height': 1000}, timezone_id='Asia/Shanghai')
            student = browser.new_context(viewport={'width': 1440, 'height': 1000}, timezone_id='Asia/Shanghai')
            tp, sp = teacher.new_page(), student.new_page()
            for page in (tp, sp):
                page.on('pageerror', lambda error: entry['page_errors'].append(type(error).__name__))
            login(tp, 'B006TEACH', password)
            chapter = write(teacher, 'POST', f'/courses/{course}/chapters', {'title': 'C12a CPU'}, 201)['data']['id']
            points = [write(teacher, 'POST', f'/chapters/{chapter}/knowledge-points', {
                'title': title, 'content': '<p>PC 程序计数器</p>', 'published': True,
                'is_foundational': True}, 201)['data']['id'] for title in ('C12a程序计数器', 'C12a零样本')]
            bank = tp.locator('.question-bank')
            bank.get_by_role('button', name='重新加载题库', exact=True).click()
            expect(bank.get_by_role('button', name='新增题目', exact=True)).to_be_enabled()
            created = []
            for kind in ('single', 'multiple', 'boolean', 'numeric', 'short'):
                bank.get_by_role('button', name='新增题目', exact=True).click()
                form = bank.locator('.question-editor')
                form.get_by_text('题型', exact=True).locator('..').locator('select').select_option(kind)
                form.get_by_label('题干', exact=True).fill('C12a真实标签' + kind)
                form.get_by_label('C12a程序计数器', exact=True).check()
                if kind in ('single', 'multiple'):
                    for index in (1, 2):
                        form.get_by_label(f'选项 {index} 内容', exact=True).fill(f'内容{index}')
                    if kind == 'single':
                        form.get_by_text('正确答案', exact=True).locator('..').locator('select').select_option('A')
                    else:
                        form.get_by_label('A', exact=True).check()
                        form.get_by_label('B', exact=True).check()
                elif kind == 'numeric':
                    form.get_by_label('正确数值', exact=True).fill('2.5')
                    form.get_by_label('允许误差', exact=True).fill('0.1')
                elif kind == 'short':
                    form.get_by_label('参考答案', exact=True).fill('人工评分参考')
                if kind == 'boolean':
                    form.get_by_label('开放为公开练习（曾公开后不再具备保密资格）', exact=True).check()
                with tp.expect_response(lambda r: r.url.endswith(f'/courses/{course}/questions')
                                        and r.request.method == 'POST') as saved:
                    form.get_by_role('button', name='保存新版本', exact=True).click()
                assert saved.value.status == 201
                created.append(saved.value.json()['data'])
                expect(bank.locator('.question-detail')).to_be_visible()
            entry['checks'].append('Q1_real_005_tags_create_all_five_types_through_006_editor')
            public = created[2]
            bank.get_by_role('button', name=f"#{public['id']} · v1 · {public['stem']}", exact=True).click()
            bank.get_by_role('button', name='编辑为新版本', exact=True).click()
            form = bank.locator('.question-editor')
            form.get_by_label('题干', exact=True).fill('C12a新版私有判断')
            form.get_by_text('正确答案', exact=True).locator('..').locator('select').select_option('false')
            form.get_by_label('开放为公开练习（曾公开后不再具备保密资格）', exact=True).uncheck()
            with tp.expect_response(lambda r: r.url.endswith(f"/questions/{public['id']}")
                                    and r.request.method == 'PATCH') as saved:
                form.get_by_role('button', name='保存新版本', exact=True).click()
            latest = saved.value.json()['data']
            assert saved.value.status == 200 and latest['version'] == 2
            entry['checks'].append('Q2_real_editor_appends_private_v2_and_keeps_original_public_version')
            login(sp, 'B006STUD1', password)
            student_id = get(student, '/auth/session').json()['data']['user']['id']
            session = get(student, '/auth/session').json()['data']
            endpoint = f"/questions/{public['id']}/practice-attempts"
            headers = {'Origin': ORIGIN, 'X-CSRF-Token': session['csrf_token'], 'Idempotency-Key': str(uuid4())}
            body = {'question_version_id': public['version_id'], 'answer': False}
            first = student.request.post(ORIGIN + '/api/v1' + endpoint, data=body, headers=headers)
            replay = student.request.post(ORIGIN + '/api/v1' + endpoint, data=body, headers=headers)
            assert first.status == replay.status == 201 and first.body() == replay.body()
            assert not first.json()['data']['correct']
            practice = sp.locator('.practice-bank')
            practice.get_by_role('button', name='我的错题', exact=True).click()
            expect(practice.get_by_text('累计错答 1 次 · 待重练 · 来源 练习', exact=True)).to_be_visible()
            practice.get_by_role('button', name=f"#{public['id']} · v1 · {public['stem']}", exact=True).click()
            practice.get_by_label('练习作答 正确', exact=True).check()
            practice.get_by_role('button', name='提交本次练习', exact=True).click()
            expect(practice.get_by_text('正确 · 100 分', exact=True)).to_be_visible()
            expect(practice.get_by_text('累计错答 1 次 · 已掌握 · 来源 练习', exact=True)).to_be_visible()
            practice.get_by_role('button', name='再次练习此版本', exact=True).click()
            practice.get_by_label('练习作答 错误', exact=True).check()
            practice.get_by_role('button', name='提交本次练习', exact=True).click()
            expect(practice.get_by_text('累计错答 2 次 · 待重练 · 来源 练习', exact=True)).to_be_visible()
            entry['checks'].append('Q3_old_public_v1_replay_once_wrong_correct_resolved_new_wrong_ui_uses_original_answer')
            write(student, 'PUT', f'/knowledge-points/{points[0]}/bookmark', {'bookmarked': True})
            write(student, 'PUT', f'/knowledge-points/{points[0]}/progress', {'completed': True})
            app.config['TEST_NOW'] = at + timedelta(minutes=1)
            query = f'/courses/{course}/analytics?dimension=knowledge'
            old = get(student, query).json()['data']
            assert old['sample_size'] == 3 and old['metrics']['mastery'] == 1 / 3
            assert old['metrics']['progress'] == 0.5
            assert old['metrics']['items'][1]['mastery'] is None
            snapshot = f"/courses/{course}/analytics?analysis_run_id={old['analysis_run_id']}"
            analytics = sp.locator('.analytics-bank')
            analytics.get_by_role('button', name='查询统计', exact=True).click()
            expect(analytics.locator('dd').filter(has_text='33.33%')).to_have_count(1)
            expect(analytics.locator('.analytics-report')).to_contain_text('（Asia/Shanghai）')
            expect(analytics.locator('.analytics-report')).not_to_contain_text('T00:00:00.000Z')
            entry['checks'].append('Q4_practice_facts_to_knowledge_three_samples_one_correct_half_progress_zero_sample_ui')
            write(teacher, 'PATCH', f'/knowledge-points/{points[0]}', {'published': False})
            now = get(student, query).json()['data']
            assert now['sample_size'] == 3 and now['metrics']['progress'] == 0
            assert now['metrics']['mastery'] == 1 / 3
            assert [p['knowledge_id'] for p in now['metrics']['items']] == [points[1]]
            assert now['metrics']['items'][0]['mastery'] is None
            assert get(student, snapshot).json()['data'] == old
            write(teacher, 'PATCH', f'/knowledge-points/{points[0]}', {'published': True})
            assert get(student, query).json()['data']['metrics'] == old['metrics']
            entry['checks'].append('Q5_current_published_set_changes_new_statistics_only_republish_restores_real_history')
            write(teacher, 'DELETE', f'/courses/{course}/members/{student_id}', {}, 204)
            get(student, snapshot, 404)
            get(student, f'/knowledge-points/{points[0]}', 404)
            practice.get_by_role('button', name='重新加载练习与错题', exact=True).click()
            expect(practice.get_by_role('button', name=f"#{public['id']} · v1 · {public['stem']}", exact=True)).to_have_count(0)
            write(teacher, 'POST', f'/courses/{course}/members', {'user_id': student_id, 'member_role': 'student'}, 201)
            sp.get_by_role('button', name='退出', exact=True).click()
            login(sp, 'B006STUD1', password)
            practice.get_by_role('button', name='我的错题', exact=True).click()
            expect(practice.get_by_text('累计错答 2 次 · 待重练 · 来源 练习', exact=True)).to_be_visible()
            detail = get(student, f'/knowledge-points/{points[0]}').json()['data']
            assert detail['is_bookmarked'] and detail['progress']['completed']
            get(student, f'/courses/{course}/analytics/export?analysis_run_id={old["analysis_run_id"]}&format=csv', 403)
            get(teacher, snapshot, 404)
            entry['checks'].append('Q6_revoke_hides_old_data_rejoin_relogin_keeps_personal_history_creator_isolation_export403')
            analytics = sp.locator('.analytics-bank')
            with closing(connect(app.config['DATABASE_PATH'])) as db:
                db.execute("CREATE TRIGGER c12a_fail BEFORE INSERT ON analysis_run BEGIN SELECT RAISE(ABORT,'c12a'); END")
            try:
                get(student, query, 503)
                analytics.get_by_role('button', name='查询统计', exact=True).click()
                expect(analytics.locator('[role=alert]')).to_be_visible()
                expect(analytics.locator('.analytics-report')).to_have_count(0)
            finally:
                with closing(connect(app.config['DATABASE_PATH'])) as db:
                    db.execute('DROP TRIGGER c12a_fail')
            analytics.get_by_role('button', name='查询统计', exact=True).click()
            expect(analytics.locator('dd').filter(has_text='33.33%')).to_have_count(1)
            entry['checks'].append('Q7_explicit_database_failure_fixture_real503_ui_clears_old_report_and_explicit_retry_recovers')
            backup = Path(app.config['DATABASE_PATH']).with_name('restored.db')
            with closing(connect(app.config['DATABASE_PATH'])) as source, closing(connect(backup)) as target:
                source.backup(target)
                assert target.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
                assert target.execute('PRAGMA foreign_key_check').fetchall() == []
            migrate(backup)
            app.config['DATABASE_PATH'] = str(backup)
            assert get(student, snapshot).json()['data'] == old
            assert get(student, '/users/me/wrong-questions').json()['data'][0]['wrong_count'] == 2
            entry['checks'].append('Q8_controlled_consistent_sqlite_backup_runner_replay_same_session_snapshot_wrong_history_http')
            for suffix in ('resources', 'preparations', 'experiments', 'recommendations'):
                response = get(teacher, f'/courses/{course}/{suffix}', 404)
                entry['http_checks'].append({'path': f'/courses/:id/{suffix}', 'status': response.status,
                                              'code': response.json()['error']['code']})
            response = get(teacher, '/health', 503)
            assert response.json()['data']['grader_ready'] is False
            entry['http_checks'].append({'path': '/health', 'status': 503, 'grader_ready': False})
            entry['absent_routes'] = [part for part in ('/qa', '/resources', '/preparations', '/experiments')
                                      if not any(part in rule.rule for rule in app.url_map.iter_rules())]
            for page, area, name in ((tp, bank, 'five-types'), (sp, analytics, 'statistics')):
                page.set_viewport_size({'width': 390, 'height': 844})
                area.scroll_into_view_if_needed()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                area.screenshot(path=str(output / f'{channel}-{name}-390.png'))
            entry['checks'].append('Q9_dependency_probes_missing_routes_health_grader_false_and_two_390px_screens')
            assert not entry['page_errors']
            entry['status'] = 'passed'
            return entry
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'logs/c12a-seams')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'started_at': datetime.now(UTC).isoformat(), 'executor': 'Codex under Huang Juncheng authorization',
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'dirty_paths': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines(),
              'scope': 'merged 001/005/006 -> 010B gaps; real HTTP/UI; synthetic data; fault fixture explicitly labeled',
              'browsers': []}
    try:
        with sync_playwright() as playwright:
            for channel in ('chrome', 'msedge'):
                report['browsers'].append(verify(playwright, channel, args.output))
        report['status'] = 'passed'
    except (AssertionError, OSError, RuntimeError, ValueError, sqlite3.Error, PlaywrightError) as error:
        report['status'] = 'failed'
        report['failure_type'] = type(error).__name__
        report['failure_location'] = [f'{frame.name}:{frame.lineno}' for frame in traceback.extract_tb(error.__traceback__)
                                      if frame.filename == __file__]
        raise RuntimeError('C12a verification failed; see redacted failure type/location in report.json') from None
    finally:
        report['finished_at'] = datetime.now(UTC).isoformat()
        (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'status': report['status'], 'browsers': len(report['browsers'])}))


if __name__ == '__main__':
    main()
