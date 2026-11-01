"""Bounded real socket/UI consumption; records absent 007 UI as blocked."""

import argparse
import re
import subprocess
import traceback
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from flask import request, request_finished
from playwright.sync_api import expect, sync_playwright

from scripts.i03_subchain import Subchain
from scripts.i03_support import ROOT, facts, record, save
from scripts.verify_spec006_papers import running
from scripts.verify_spec006_questions import ORIGIN
from scripts.verify_spec010b_analytics import download
from scripts.verify_spec011_qa import search, sign_in


def verify(playwright, channel, output):
    records, checks, errors = [], [], []
    result = {'channel': channel, 'checks': checks, 'page_errors': errors, '007_UI': 'blocked: page not registered'}
    with running(False) as (app, password, course, at):
        def observed(sender, response, **_kwargs):
            if request.path.startswith('/api/v1/'):
                actual = response.get_json(silent=True) if response.is_json else response.get_data(as_text=True)
                record(records, 'socket-client', request.method, request.full_path.rstrip('?'),
                       request.get_json(silent=True), response.status_code, actual, 'socket HTTP')
        request_finished.connect(observed, app, weak=False)
        browser = playwright.chromium.launch(channel=channel, headless=True)
        scenario = None
        try:
            result['version'] = browser.version
            teacher = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
            page = teacher.new_page()
            page.on('pageerror', lambda e: errors.append(type(e).__name__))
            sign_in(page, 'B006TEACH', password)
            student = browser.new_context(viewport={'width': 390, 'height': 844})
            sp = student.new_page()
            sp.on('pageerror', lambda e: errors.append(type(e).__name__))
            sign_in(sp, 'B006STUD1', password)

            def call(client, method, path, data=None, status=200, headers=None):
                response = client.request.fetch(ORIGIN + '/api/v1' + path, method=method,
                    **({'data': data} if data is not None else {}),
                    headers={'Origin': ORIGIN, 'X-CSRF-Token': getattr(client, 'csrf', ''), **(headers or {})})
                assert response.status == status, f'{method} {path}: expected {status}, got {response.status}'
                return SimpleNamespace(json=response.json() if 'json' in response.headers.get('content-type', '') else None,
                                       data=response.body(), status_code=response.status)

            for context in (teacher, student):
                context.csrf = call(context, 'GET', '/auth/session').json['data']['csrf_token']
            demo = call(teacher, 'POST', f'/courses/{course}/demo-sessions', {'preset': 'cpu'}, 201).json['data']
            call(student, 'GET', f'/courses/{course}/demo-sessions')
            call(student, 'GET', f"/demo-sessions/{demo['id']}")
            call(student, 'PUT', f"/demo-sessions/{demo['id']}/state", {'revision': 0, 'action': 'step'}, 403)
            result['student_headings'] = sp.get_by_role('heading').all_text_contents()
            result['teacher_headings'] = page.get_by_role('heading').all_text_contents()
            assert not any('课堂演示' in text for text in result['teacher_headings'] + result['student_headings'])
            checks.append('007_real_socket_list_read_student_write403; no_classroom_UI_pass_claim')
            scenario = Subchain(call, app, teacher, [student] + [browser.new_context() for _ in range(3)], course, at, password)
            scenario.seed()
            scenario.submit()
            scenario.verify_before_review()
            checks.append('four_frozen_students_three_attempts_five_objective_answers_original_tags_60percent_and_old_snapshots')
            sp.reload()
            wrong = sp.locator('.practice-bank')
            expect(wrong).to_have_attribute('aria-busy', 'false')
            wrong.get_by_role('button', name='我的错题', exact=True).click()
            wrong.get_by_role('button', name=f"#{scenario.questions[0]['id']} · v1 · I03原版本第1题", exact=True).click()
            expect(wrong.get_by_text('答案与解析尚受保护，请等待允许讲评。', exact=True)).to_be_visible()
            expect(wrong.locator('.attempt-reference')).to_have_count(0)
            wrong.screenshot(path=str(output / f'{channel}-wrong-protected.png'))
            attempts = sp.locator('.attempt-bank.card')
            attempts.get_by_role('button', name='重新加载答卷', exact=True).click()
            attempts.get_by_role('button', name=re.compile(f'^答卷 #{scenario.attempts[0]} ·')).click()
            expect(attempts.locator('.attempt-result')).to_be_visible()
            expect(attempts.locator('.attempt-reference')).to_have_count(0)
            checks.append('actual_wrong_and_attempt_pages_hide_standard_answers_after_close_before_review')
            scenario.review()
            wrong.get_by_role('button', name='重新加载练习与错题', exact=True).click()
            wrong.get_by_role('button', name=f"#{scenario.questions[0]['id']} · v1 · I03原版本第1题", exact=True).click()
            expect(wrong.get_by_text('参考答案：A', exact=True)).to_be_visible()
            expect(wrong.get_by_text('解析：I03原版本解析1', exact=True)).to_be_visible()
            wrong.screenshot(path=str(output / f'{channel}-wrong-reviewed.png'))
            attempts.get_by_role('button', name='重新加载此答卷', exact=True).click()
            expect(attempts.locator('.attempt-reference').first).to_contain_text('参考答案：A')
            checks.append('real_review_releases_original_answer_A_not_new_version_B_on_wrong_and_attempt_pages')
            # Existing manual knowledge/QA entries only; there is no label -> QA link in this application.
            result['wrong_to_qa_navigation'] = 'manual existing knowledge and QA panels; no automatic jump'
            knowledge = sp.locator('[aria-labelledby="knowledge-title"]')
            knowledge.get_by_role('button', name='重新加载', exact=True).click()
            knowledge.get_by_role('button', name='程序计数器', exact=True).click()
            expect(knowledge.locator('.knowledge-detail')).to_contain_text('I03原始知识出处')
            scenario.qa()
            qa_bank = sp.get_by_role('region', name='课程检索问答')
            found = search(sp, qa_bank, '程序计数器')['data']
            assert scenario.points[0] in [r['knowledge_id'] for r in found['matches']]
            qa_bank.get_by_role('button', name=f'打开知识出处 #{scenario.points[0]}', exact=True).click()
            expect(qa_bank.locator('.qa-source')).to_contain_text('I03原始知识出处')
            qa_bank.screenshot(path=str(output / f'{channel}-qa-source.png'))
            checks.append('manual_published_knowledge_entry_real_QA_matches_citation_and_source_body_same_course')
            analytics = page.locator('.analytics-bank')
            analytics.get_by_label('原快照编号', exact=True).fill(str(scenario.old['knowledge']['analysis_run_id']))
            analytics.get_by_role('button', name='恢复原快照', exact=True).click()
            expect(analytics.locator('dd').filter(has_text='60.00%')).to_have_count(1)
            assert download(page, analytics) == scenario.csv['knowledge']
            page.set_viewport_size({'width': 390, 'height': 844})
            analytics.screenshot(path=str(output / f'{channel}-original-knowledge.png'))
            analytics.get_by_label('原快照编号', exact=True).fill(str(scenario.old['scores']['analysis_run_id']))
            analytics.get_by_role('button', name='恢复原快照', exact=True).click()
            expect(analytics.locator('dd').filter(has_text='25.00%')).to_have_count(1)
            assert download(page, analytics) == scenario.csv['scores']
            checks.append('actual_010B_page_restores_old_60percent_knowledge_and_25percent_scores_CSV_after_grade31_67')
            # Cache a real result, unpublish its citation, then click the existing citation button.
            search(sp, qa_bank, '算术逻辑单元')
            scenario.unpublish()
            qa_bank.get_by_role('button', name=f'打开知识出处 #{scenario.points[1]}', exact=True).click()
            expect(qa_bank.get_by_role('alert')).to_be_visible()
            expect(qa_bank.locator('.qa-matches')).to_have_count(0)
            expect(qa_bank.locator('.qa-source')).to_have_count(0)
            qa_bank.screenshot(path=str(output / f'{channel}-unpublished-cleared.png'))
            search(sp, qa_bank, '程序计数器')
            qa_bank.get_by_role('button', name=f'打开知识出处 #{scenario.points[0]}', exact=True).click()
            expect(qa_bank.locator('.qa-source')).to_be_visible()
            scenario.revoke()
            search(sp, qa_bank, '程序计数器', expected=404)
            expect(qa_bank.locator('.qa-source')).to_have_count(0)
            expect(qa_bank.locator('.qa-matches')).to_have_count(0)
            expect(qa_bank.get_by_role('button', name='查询课程知识', exact=True)).to_be_disabled()
            wrong.get_by_role('button', name='重新加载练习与错题', exact=True).click()
            expect(wrong.locator('.practice-detail')).to_have_count(0)
            expect(wrong.get_by_text('共 0 道错题', exact=True)).to_be_visible()
            qa_bank.screenshot(path=str(output / f'{channel}-revoked-cleared.png'))
            checks.append('real_unpublish_citation404_and_membership_revocation404_clear_old_QA_sources_and_wrong_results')
            for current in (sp, page):
                assert current.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert errors == []
            result['result'] = 'passed'
            return result
        except Exception as error:
            result.update(result='failed', error_type=type(error).__name__)
            raise
        finally:
            save(output / f'{channel}-requests.json', records)
            save(output / f'{channel}-facts.json', {'stages': scenario.stages if scenario else {},
                 'final': facts(app.config['DATABASE_PATH']), 'fixtures': [
                     'bootstrap admin/teacher; initial student/course/member via actual handlers in existing running helper',
                     'all later successful business via real socket HTTP; TEST_NOW only; no injected faults or success mocks']})
            save(output / f'{channel}-report.json', result)
            request_finished.disconnect(observed, app)
            browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'logs/i03/browsers')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'date': datetime.now(UTC).isoformat(),
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'dirty_paths': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines(),
              'scope': 'bounded actual socket and existing UI; missing 007/preparation pages remain blocked', 'browsers': []}
    try:
        with sync_playwright() as playwright:
            for channel in ('chrome', 'msedge'):
                report['browsers'].append(verify(playwright, channel, args.output))
        report['result'] = 'passed'
    except Exception:
        report['result'] = 'failed'
        traceback.print_exc()
        raise
    finally:
        save(args.output / 'report.json', report)
        print({'result': report['result'], 'browsers': len(report['browsers'])})


if __name__ == '__main__':
    main()
