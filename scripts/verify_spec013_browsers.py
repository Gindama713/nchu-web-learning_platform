"""C09 installed Chrome/Edge real HTTP/UI; synthetic accounts, no production data."""

import argparse
import json
import platform
import subprocess
import sys
import traceback
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import expect, sync_playwright

from scripts.verify_spec005_browsers import ORIGIN, Api, servers
from tests.test_question_validation import question


def login(page, number, password):
    # Finish initial session restoration before submitting a new login. Assert
    # only the paper module under test, with room for concurrent module requests.
    with page.expect_response(lambda r: r.url.endswith('/auth/session')) as initial:
        page.goto(ORIGIN)
    initial.value.body()
    page.get_by_label('学号', exact=True).fill(number)
    page.get_by_label('密码', exact=True).fill(password)
    with page.expect_response(lambda r: r.url.endswith('/auth/login')) as pending:
        page.get_by_role('button', name='登录', exact=True).click()
    assert pending.value.status == 200
    expect(page.locator('.paper-bank')).to_have_count(2, timeout=15000)
    expect(page.locator('.paper-bank').first).to_have_attribute('aria-busy', 'false', timeout=15000)


def generate(page, panel, title, *, replay=False, status=201):
    panel.get_by_label('新试卷标题', exact=True).fill(title)
    with page.expect_response(lambda r: r.url.endswith('/generated-papers') and r.request.method == 'POST') as pending:
        panel.get_by_role('button', name='重放并保存新草稿' if replay else '生成并保存草稿', exact=True).click()
    response = pending.value
    assert response.status == status
    return response.json()


def verify(playwright, channel, password, output):
    admin, teacher, student = Api(), Api(), Api()
    admin.login('T005ADMIN', password)
    teacher_id = teacher.login('T005TEACH', password)
    number = 'T013CHROME' if channel == 'chrome' else 'T013EDGE01'
    student.call('POST', '/auth/register', {'student_no': number, 'name': number, 'password': password}, 201)
    student_id = student.login(number, password)
    course_id = admin.call('POST', '/courses', {'title': f'C09 CPU {channel}', 'teacher_id': teacher_id}, 201)['id']
    teacher.call('POST', f'/courses/{course_id}/members', {'user_id': student_id, 'member_role': 'student'}, 201)
    chapter_id = teacher.call('POST', f'/courses/{course_id}/chapters', {'title': 'CPU'}, 201)['id']
    knowledge_id = teacher.call('POST', f'/chapters/{chapter_id}/knowledge-points',
                                {'title': '程序计数器', 'content': '下一条指令地址', 'published': True}, 201)['id']
    questions = [teacher.call('POST', f'/courses/{course_id}/questions',
                              question(knowledge_ids=[knowledge_id], practice_available=True), 201) for _ in range(3)]
    browser = playwright.chromium.launch(channel=channel, headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, timezone_id='UTC')
    errors, checks = [], []
    try:
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(type(error).__name__))
        login(page, 'T005TEACH', password)
        bank = page.locator('.paper-bank').filter(has=page.get_by_role('heading', name='课程试卷', exact=True))
        # Exercise explicit recovery after simultaneous application module boot;
        # never substitute fake list responses or change the shared auth module.
        bank.get_by_role('button', name='重新加载试卷', exact=True).click()
        expect(bank).to_have_attribute('aria-busy', 'false', timeout=15000)
        bank.get_by_label('试卷课程', exact=True).select_option(str(course_id))
        expect(bank).to_have_attribute('aria-busy', 'false')
        bank.get_by_role('button', name='智能组卷', exact=True).click()
        panel = bank.locator('.generation-panel')
        expect(panel).to_have_attribute('aria-busy', 'false')
        panel.get_by_label('随机种子（可留空）', exact=True).fill('9223372036854775807')
        panel.get_by_label('程序计数器', exact=True).check()
        first = generate(page, panel, 'CPU约束草稿')['data']
        expect(panel.get_by_role('heading', name='草稿已保存', exact=True)).to_be_visible()
        assert first['points_hundredths'] == [334, 334, 333]
        assert first['seed_text'] == '9223372036854775807'
        detail = teacher.call('GET', f"/papers/{first['paper_id']}")
        assert detail['status'] == 'draft' and detail['participant_count'] == 0
        panel.screenshot(path=str(output/f'{channel}-result-desktop.png'))
        checks.append('real UI first generation: draft, exact 334/334/333, signed64 seed, fixed versions/coverage')
        teacher.call('POST', f'/courses/{course_id}/questions', question(knowledge_ids=[knowledge_id]), 201)
        teacher.call('PATCH', f"/questions/{questions[0]['id']}", {'stem': '新增版本'})
        student_page = context.browser.new_page(viewport={'width': 390, 'height': 844})
        login(student_page, number, password)
        session = student_page.request.get(ORIGIN+'/api/v1/auth/session').json()['data']
        response = student_page.request.post(ORIGIN+f"/api/v1/questions/{questions[0]['id']}/practice-attempts",
            data={'question_version_id': questions[0]['version_id'], 'answer': 'A'},
            headers={'Origin': ORIGIN, 'X-CSRF-Token': session['csrf_token'], 'Idempotency-Key': str(uuid4())})
        assert response.status == 201
        expect(student_page.get_by_role('button', name='智能组卷', exact=True)).to_have_count(0)
        student_page.close()
        panel.get_by_role('button', name='查看草稿与发布设置', exact=True).click()
        expect(bank.locator('.paper-detail h3')).to_have_text('CPU约束草稿')
        bank.get_by_role('button', name='从此快照重放', exact=True).click()
        expect(panel.get_by_label('原快照编号', exact=True)).to_have_value(str(first['generation_snapshot_id']))
        expect(panel.get_by_label('随机种子（可留空）', exact=True)).to_have_count(0)
        replay = generate(page, panel, 'CPU快照重放', replay=True)['data']
        assert (replay['selected_version_ids'], replay['points_hundredths']) == (
            first['selected_version_ids'], first['points_hundredths'])
        checks.append('new question/version/real practice answer: UI replay exact; student has no generation entry')
        page.set_viewport_size({'width': 390, 'height': 844})
        panel.screenshot(path=str(output/f'{channel}-replay-390.png'))
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        checks.append('390px result and replay form without horizontal overflow')
        panel.get_by_role('button', name='首次生成', exact=True).click()
        expect(panel).to_have_attribute('aria-busy', 'false')
        panel.get_by_label('选题数量', exact=True).fill('100')
        panel.get_by_label('简单题配额', exact=True).fill('100')
        failure = generate(page, panel, '无解草稿', status=422)
        assert failure['error']['code'] == 'INFEASIBLE_CONSTRAINTS'
        expect(panel.get_by_role('heading', name='本次未生成草稿', exact=True)).to_be_visible()
        expect(panel.get_by_label('新试卷标题', exact=True)).to_have_value('无解草稿')
        expect(panel.locator('.generation-result')).to_have_count(0)
        panel.screenshot(path=str(output/f'{channel}-failure-390.png'))
        checks.append('real 422 failure keeps parameters, gives corrective guidance, removes previous result')
        quiz = page.locator('.paper-bank').filter(has=page.get_by_role('heading', name='随堂测', exact=True))
        quiz.get_by_label('试卷课程', exact=True).select_option(str(course_id))
        expect(quiz).to_have_attribute('aria-busy', 'false')
        quiz.get_by_role('button', name='智能组卷', exact=True).click()
        qpanel = quiz.locator('.generation-panel')
        expect(qpanel).to_have_attribute('aria-busy', 'false')
        quiz_result = generate(page, qpanel, '组卷随堂测')['data']
        assert teacher.call('GET', f"/papers/{quiz_result['paper_id']}")['kind'] == 'quiz'
        qpanel.get_by_role('button', name='查看草稿与发布设置', exact=True).click()
        expect(quiz.get_by_role('button', name='发布随堂测并冻结名单', exact=True)).to_be_visible()
        now = datetime.now(UTC)
        for label, value in [('试卷开始', now - timedelta(minutes=1)), ('试卷截止', now + timedelta(hours=1))]:
            quiz.get_by_label(label, exact=True).fill(value.strftime('%Y-%m-%dT%H:%M'))
        with page.expect_response(lambda r: r.url.endswith(f'/courses/{course_id}/quizzes') and r.request.method == 'POST') as pending:
            quiz.get_by_role('button', name='发布随堂测并冻结名单', exact=True).click()
        assert pending.value.status == 201
        published = teacher.call('GET', f"/papers/{quiz_result['paper_id']}")
        assert published['status'] == 'published' and published['review_at'] is None
        assert published['participant_count'] == 1
        checks.append('generated quiz uses existing explicit publish flow; frozen roster, no automatic review')
        assert not errors
        return {'channel': channel, 'version': browser.version, 'status': 'passed', 'checks': checks,
                'page_errors': errors, 'course_id': course_id}
    finally:
        context.close()
        browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'logs/spec-013-browsers')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'started_at': datetime.now(UTC).isoformat(), 'os': platform.platform(),
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'dirty_paths': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines(),
              'scope': 'local real HTTP/UI with synthetic data; initial admin/teacher SQL bootstrap only; not classroom/performance',
              'browsers': []}
    try:
        with servers() as password, sync_playwright() as playwright:
            for channel in ('chrome', 'msedge'):
                try:
                    result = verify(playwright, channel, password, args.output)
                except Exception as error:  # preserve original error if Windows cleanup also fails
                    report['browser_failure'] = {'channel': channel, 'type': type(error).__name__,
                        'locations': [f'{Path(frame.filename).name}:{frame.name}:{frame.lineno}'
                                      for frame in traceback.extract_tb(error.__traceback__)]}
                    raise
                report['browsers'].append(result)
                print(f"{channel} {result['version']}: {len(result['checks'])} groups passed", flush=True)
        report['status'] = 'passed'
    except Exception as error:  # noqa: BLE001 - never print credentials/HTTP request bodies
        report['status'] = 'failed'
        report['failure_type'] = type(error).__name__
        report['failure_locations'] = [f'{frame.name}:{frame.lineno}' for frame in traceback.extract_tb(error.__traceback__)
                                       if Path(frame.filename) == Path(__file__)]
        print(f"FAILED {report['failure_type']}: {report['failure_locations']}", file=sys.stderr)
        return 1
    finally:
        report['finished_at'] = datetime.now(UTC).isoformat()
        (args.output/'browser-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
