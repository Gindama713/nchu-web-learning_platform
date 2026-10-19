"""Chrome/Edge consumption of the same actual 012/006/013/008/010B facts."""

import argparse
import hashlib
import json
import shutil
import socket
import subprocess
import threading
import time
import traceback
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

from scripts.verify_spec006_questions import QuietHandler
from scripts.verify_spec013_browsers import login
from tests.test_consumption_seams import ConsumptionSeamsTest, redacted
from tests.test_questions import ORIGIN

ROOT = Path(__file__).resolve().parents[1]


def save(path, data):
    path.write_text(json.dumps(redacted(data), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


@contextmanager
def serving(case):
    for port in (5000, 5173):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
    server = make_server('127.0.0.1', 5000, case.app, request_handler=QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    process = None
    try:
        with (Path(case.temporary.name) / 'vite.log').open('wb') as log:
            process = subprocess.Popen([shutil.which('node') or 'node',
                                        str(ROOT / 'frontend/node_modules/vite/bin/vite.js'),
                                        '--host', '127.0.0.1', '--port', '5173', '--strictPort'],
                                       cwd=ROOT / 'frontend', stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError('Vite exited before readiness')
                try:
                    with urlopen(ORIGIN, timeout=1) as response:
                        if response.status == 200:
                            break
                except (URLError, TimeoutError):
                    time.sleep(.1)
            else:
                raise RuntimeError('Vite readiness timed out')
            yield
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()


def record(records, method, path, body, status, raw, content_type, key=None):
    records.append({'transport': 'real socket', 'method': method, 'path': path, 'request': redacted(body),
                    'status': status, 'idempotency_key': key, 'body_sha256': hashlib.sha256(raw).hexdigest(),
                    'response': redacted(json.loads(raw)) if 'application/json' in content_type else None,
                    'csv': raw.decode('utf-8-sig') if 'text/csv' in content_type else None})


def watch(page, records, errors):
    def capture(response):
        if '/api/v1/' not in response.url:
            return
        request = response.request
        body = json.loads(request.post_data) if request.post_data else None
        record(records, request.method, response.url.split('/api/v1')[1], body, response.status,
               response.body(), response.headers.get('content-type', ''), request.headers.get('idempotency-key'))
    page.on('response', capture)
    page.on('pageerror', lambda error: errors.append(type(error).__name__))


def api(context, records, method, path, body=None, status=200, key=None):
    headers = {'Origin': ORIGIN}
    if method != 'GET':
        session = context.request.get(ORIGIN + '/api/v1/auth/session').json()['data']
        headers['X-CSRF-Token'] = session['csrf_token']
    if key:
        headers['Idempotency-Key'] = key
    response = context.request.fetch(ORIGIN + '/api/v1' + path, method=method, data=body, headers=headers)
    record(records, method, path, body, response.status, response.body(), response.headers.get('content-type', ''), key)
    assert response.status == status, f'{method} {path}: {response.status}'
    return response


def action(page, panel, button, fragment, status=200):
    with page.expect_response(lambda r: fragment in r.url) as pending:
        panel.get_by_role('button', name=button, exact=True).click()
    assert pending.value.status == status
    pending.value.body()
    expect(panel).to_have_attribute('aria-busy', 'false')
    return pending.value.json()['data'] if status < 400 else pending.value.json()


def shot(page, panel, output, name):
    page.set_viewport_size({'width': 390, 'height': 1200})
    panel.scroll_into_view_if_needed()
    expect(panel).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    panel.screenshot(path=str(output / name), animations='disabled')
    page.set_viewport_size({'width': 1440, 'height': 1000})


def download(page, panel):
    with page.expect_download() as pending:
        panel.get_by_role('button', name='导出当前快照 CSV', exact=True).click()
    return Path(pending.value.path()).read_bytes()


def restore(page, panel, value):
    panel.get_by_label('原快照编号', exact=True).fill(str(value['analysis_run_id']))
    data = action(page, panel, '恢复原快照', 'analysis_run_id=')
    assert data == value


def verify_a(case, teacher, student, records, output, channel, checks):
    tp, sp = teacher.new_page(), student.new_page()
    watch(tp, records, checks['page_errors'])
    watch(sp, records, checks['page_errors'])
    login(tp, 'T006TEACH', case.password)
    login(sp, 'T006STUD1', case.password)
    q = case.create_question(knowledge_ids=[1, 2], practice_available=True, explanation='原版A解析')
    for kid in (1, 2):
        case.call(case.teacher, 'PATCH', f'/knowledge-points/{kid}', {'is_foundational': True})
    rec, practice = sp.locator('.recommendation-bank'), sp.locator('.practice-bank')
    cold = action(sp, rec, '刷新推荐', '/recommendations?')
    assert cold['reason'] == 'cold_start'
    rec.get_by_role('button', name=f"去练习 · 版本 #{q['version_id']}", exact=True).first.click()
    expect(practice.locator('.practice-form')).to_be_visible()
    practice.get_by_label('练习作答 当前数据', exact=True).check()
    wrong = action(sp, practice, '提交本次练习', '/practice-attempts', 201)
    case.advance()
    old = case.query('knowledge')
    teacher_bank = tp.locator('.analytics-bank')
    restore(tp, teacher_bank, old)
    old_csv = download(tp, teacher_bank)
    assert old_csv == case.export(old)
    own_bank = sp.locator('.analytics-bank')
    own = action(sp, own_bank, '查询统计', 'dimension=knowledge')
    case.phase('browser_a_wrong', original=old, own=own)
    practice.get_by_role('button', name='我的错题', exact=True).click()
    expect(practice.get_by_text('累计错答 1 次 · 待重练 · 来源 练习', exact=True)).to_be_visible()
    newer = case.call(case.teacher, 'PATCH', f"/questions/{q['id']}",
                      {'answer': 'B', 'knowledge_ids': [2], 'explanation': '新版B解析'}).json['data']
    practice.get_by_role('button', name=f"#{q['id']} · v1 · {q['stem']}", exact=True).click()
    practice.get_by_label('练习作答 下一条指令地址', exact=True).check()
    action(sp, practice, '提交本次练习', '/practice-attempts', 201)
    current_rec = action(sp, rec, '刷新推荐', '/recommendations?')
    assert next(v for v in current_rec['items'] if v['knowledge_id'] == 1)['question_version_id'] is None
    rec.get_by_role('button', name=f"去练习 · 版本 #{newer['version_id']}", exact=True).click()
    practice.get_by_label('练习作答 当前数据', exact=True).check()
    action(sp, practice, '提交本次练习', '/practice-attempts', 201)
    case.call(case.student, 'PUT', '/knowledge-points/1/progress', {'completed': True})
    case.advance()
    updated = action(sp, own_bank, '查询统计', 'dimension=knowledge')
    assert (updated['sample_size'], updated['metrics']['correct_count']) == (3, 2)
    assert [(v['answered_count'], v['correct_count']) for v in updated['metrics']['items']] == [(2, 1), (3, 2)]
    final_rec = action(sp, rec, '刷新推荐', '/recommendations?')
    assert [(v['knowledge_id'], v['sample_size'], v['score']) for v in final_rec['items']] == [(2, 3, .466667), (1, 2, .4)]
    practice.get_by_role('button', name='我的错题', exact=True).click()
    expect(practice.get_by_text('累计错答 1 次 · 已掌握 · 来源 练习', exact=True)).to_be_visible()
    shot(sp, practice, output, f'{channel}-a-fixed-wrong.png')
    shot(sp, own_bank, output, f'{channel}-a-new-knowledge.png')
    shot(sp, rec, output, f'{channel}-a-new-recommendation.png')
    restore(sp, own_bank, own)
    tp.reload()
    expect(teacher_bank.get_by_label('原快照编号', exact=True)).to_have_value(str(old['analysis_run_id']))
    expect(teacher_bank.locator('.analytics-report')).to_be_visible()
    assert download(tp, teacher_bank) == old_csv
    shot(tp, teacher_bank, output, f'{channel}-a-old-snapshot.png')
    case.phase('browser_a', original=old, updated=updated, recommendation=final_rec, wrong_attempt=wrong)
    checks['checks'].append('A: recommendation entry -> wrong v1 -> wrong-book correct v1 -> latest v2; same facts n3/c2, per-tag2/1 and3/2; old ID/CSV unchanged')
    sp.close()
    return tp


def quiz_bank(page):
    return page.locator('.paper-bank').filter(has=page.get_by_role('heading', name='随堂测', exact=True))


def verify_b(case, tp, teacher, student, records, output, channel, checks):
    qs = case.seed_generation()
    tp.reload()
    bank = quiz_bank(tp)
    expect(bank).to_have_attribute('aria-busy', 'false')
    bank.get_by_role('button', name='智能组卷', exact=True).click()
    panel = bank.locator('.generation-panel')
    expect(panel).to_have_attribute('aria-busy', 'false')
    for label, value in [('新试卷标题', '生成卷消费接缝'), ('选题数量', '3'), ('试卷总分', '10.01'),
                         ('简单题配额', '1'), ('中等题配额', '1'), ('困难题配额', '1'), ('随机种子（可留空）', '42')]:
        panel.get_by_label(label, exact=True).fill(value)
    panel.get_by_label('要求保密', exact=True).check()
    first = action(tp, panel, '生成并保存草稿', '/generated-papers', 201)
    assert first['points_hundredths'] == [334, 334, 333]
    assert set(first['selected_version_ids']) == {q['version_id'] for q in qs}
    original_generation = case.facts()['generation_snapshot'][0]
    shot(tp, panel, output, f'{channel}-b-generated-draft.png')
    panel.get_by_role('button', name='查看草稿与发布设置', exact=True).click()
    # Both browser contexts use UTC input. Server/API stamps remain UTC.
    for label, value in [('试卷开始', '2026-10-13T12:00'), ('试卷截止', '2026-10-13T12:10')]:
        bank.get_by_label(label, exact=True).fill(value)
    bank.get_by_label('保密确认说明', exact=True).fill('未公开且非简单复制确认')
    action(tp, bank, '发布随堂测并冻结名单', f'/courses/{case.course_id}/quizzes', 201)
    pid = first['paper_id']
    sp = student.new_page()
    watch(sp, records, checks['page_errors'])
    sp.goto(ORIGIN)  # Same context from A: restore its real authenticated session.
    sbank = quiz_bank(sp)
    expect(sbank).to_have_attribute('aria-busy', 'false')
    sbank.get_by_role('button', name=f'#{pid} · 生成卷消费接缝 · 进行中', exact=True).click()
    expect(sbank.locator('.attempt-answer-form')).to_be_visible()
    order = first['selected_version_ids']
    for q in qs:
        i = order.index(q['version_id']) + 1
        if q['type'] == 'single':
            sbank.get_by_label(f'第 {i} 题作答 下一条指令地址', exact=True).check()
        elif q['type'] == 'boolean':
            sbank.get_by_label(f'第 {i} 题作答 错误', exact=True).check()
        else:
            sbank.get_by_label(f'第 {i} 题作答', exact=True).fill('真实页面人工回答')
    sbank.get_by_label('确认交卷，接受漏答0分且提交后不可修改', exact=True).check()
    with sp.expect_response(lambda r: f'/quizzes/{pid}/attempts' in r.url) as pending:
        sbank.get_by_role('button', name='提交整份答卷', exact=True).click()
    assert pending.value.status == 201
    submitted = pending.value.json()['data']
    assert submitted['status'] == 'partial'
    case.call(case.outsider, 'POST', f'/quizzes/{pid}/attempts', {'answers': []}, 201, key=str(uuid4()))
    case.advance(601)
    analytic = tp.locator('.analytics-bank')
    analytic.get_by_label('统计维度', exact=True).select_option('scores')
    analytic.get_by_label('成绩类别', exact=True).select_option('quiz')
    old = action(tp, analytic, '查询统计', 'dimension=scores')
    assert [old['metrics'][k] for k in ('expected_count', 'submitted_count', 'missing_count', 'graded_count', 'partial_count')] == [3, 2, 1, 1, 1]
    csv_before = download(tp, analytic)
    case.phase('browser_b_pending', generation=first, scores=old)
    shot(tp, analytic, output, f'{channel}-b-pending-scores.png')
    manual_points = first['points_hundredths'][order.index(qs[2]['version_id'])]
    api(teacher, records, 'PATCH', f"/attempts/{submitted['id']}/manual-scores", {'revision': 0, 'items': [
        {'question_version_id': qs[2]['version_id'], 'score': manual_points / 100, 'comment': '按原生成配分批阅'}]})
    bank.get_by_role('button', name='重新加载试卷', exact=True).click()
    bank.get_by_role('button', name=f'#{pid} · 生成卷消费接缝 · 已截止', exact=True).click()
    action(tp, bank, '发布讲评并开放答案', f'/quizzes/{pid}/review')
    case.call(case.teacher, 'PATCH', f"/questions/{qs[0]['id']}", {'answer': 'B', 'knowledge_ids': [2]})
    case.advance()
    newer = action(tp, analytic, '查询统计', 'dimension=scores')
    p = dict(zip(order, first['points_hundredths'], strict=True))
    assert newer['metrics']['mean_percentage'] == round((p[qs[0]['version_id']] + manual_points) / 1001 * 50, 2)
    assert (newer['metrics']['graded_count'], newer['metrics']['partial_count']) == (2, 0)
    shot(tp, analytic, output, f'{channel}-b-new-scores.png')
    restore(tp, analytic, old)
    assert download(tp, analytic) == csv_before
    tp.reload()
    expect(analytic.locator('.analytics-report')).to_contain_text(f"原快照 #{old['analysis_run_id']}")
    assert download(tp, analytic) == csv_before
    shot(tp, analytic, output, f'{channel}-b-old-scores.png')
    for kind in ('exam', 'homework'):
        analytic.get_by_label('成绩类别', exact=True).select_option(kind)
        empty = action(tp, analytic, '查询统计', 'dimension=scores')
        assert empty['metrics']['expected_count'] == 0
    assert case.facts()['generation_snapshot'][0] == original_generation
    detail = api(student, records, 'GET', f'/papers/{pid}').json()['data']
    assert next(v for v in detail['items'] if v['question_version_id'] == qs[0]['version_id'])['answer'] == 'A'
    bank.get_by_role('button', name='重新加载试卷', exact=True).click()
    bank.get_by_role('button', name=f'#{pid} · 生成卷消费接缝 · 已截止', exact=True).click()
    bank.get_by_role('button', name='从此快照重放', exact=True).click()
    panel.get_by_label('新试卷标题', exact=True).fill('已开放保密原卷重放')
    rejection = action(tp, panel, '重放并保存新草稿', '/generated-papers', 409)
    assert rejection['error']['code'] == 'QUESTION_PUBLIC'
    expect(panel.locator('.generation-result')).to_have_count(0)
    shot(tp, panel, output, f'{channel}-b-replay-current-eligibility.png')
    assert len(case.facts()['generation_snapshot']) == 1
    case.phase('browser_b', generation=first, original_scores=old, new_scores=newer, replay=rejection)
    checks['checks'].append('B: generated quiz UI -> dedicated publish roster3 -> real UI partial + blank + missing -> scores quiz only; grade new percentage; old CSV/ID and generation row unchanged; confidential replay409')
    sp.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'logs/consumption/browsers')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'started_at': datetime.now(UTC).isoformat(),
              'tested_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'dirty_paths': subprocess.check_output(['git', 'status', '--porcelain'], text=True).splitlines(),
              'fixtures': 'Only admin/teacher SQL bootstrap, random secrets and TEST_NOW; all business via actual API. '
                          'Handler setup/changes and browser socket requests saved separately; no response replacement.',
              'browsers': []}
    try:
        with sync_playwright() as playwright:
            for channel in ('chrome', 'msedge'):
                case = ConsumptionSeamsTest()
                records = []
                case.setUp()
                entry = {'channel': channel, 'checks': [], 'page_errors': [], 'browser_timezone': 'UTC'}
                report['browsers'].append(entry)
                try:
                    with serving(case):
                        browser = playwright.chromium.launch(channel=channel, headless=True)
                        entry['version'] = browser.version
                        try:
                            teacher = browser.new_context(timezone_id='UTC', viewport={'width': 1440, 'height': 1000})
                            student = browser.new_context(timezone_id='UTC', viewport={'width': 1440, 'height': 1000})
                            tp = verify_a(case, teacher, student, records, args.output, channel, entry)
                            verify_b(case, tp, teacher, student, records, args.output, channel, entry)
                            assert not entry['page_errors']
                            entry['status'] = 'passed'
                        finally:
                            browser.close()
                finally:
                    save(args.output / f'{channel}-socket-requests.json', records)
                    save(args.output / f'{channel}-handler-requests.json', case.records)
                    save(args.output / f'{channel}-facts.json', {'phases': case.phases, 'final_facts': case.facts()})
                    case.doCleanups()
                print(f'{channel}: two consumption seams passed', flush=True)
        report['status'] = 'passed'
    except Exception as error:  # noqa: BLE001 - retain redacted diagnostics, never credentials or request bodies
        report['status'] = 'failed'
        report['failure_type'] = type(error).__name__
        report['failure_locations'] = [f'{Path(f.filename).name}:{f.name}:{f.lineno}'
                                       for f in traceback.extract_tb(error.__traceback__)]
        raise RuntimeError('Consumption browser preflight failed; see redacted report') from None
    finally:
        save(args.output / 'report.json', report)


if __name__ == '__main__':
    main()
