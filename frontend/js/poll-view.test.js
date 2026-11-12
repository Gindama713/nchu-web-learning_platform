// 投票界面的组件测试：用 renderer 替身跑真实 setup，fetch 打桩。
// 真实浏览器里的效果另有 CDP 脚本（test-tmp/cdp/verify-poll.js）验证。
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer, nextTick, reactive } from 'vue'
import { PollModal, PollPanel, percent, studentState, togglePick } from './poll-view.js'

// v-model 走的是 vModelText / vModelSelect 指令，它们会在元素上挂原生监听并读 el.value。
// 替身必须提供 addEventListener 与 value/checked，否则连模板都挂不上。
const node = (type, text = '') => ({
  type, text, children: [], props: {}, parent: null,
  value: '', checked: false, listeners: {},
  addEventListener(name, handler) { this.listeners[name] = handler },
  removeEventListener(name) { delete this.listeners[name] },
})
function remove(n) { if (n.parent) n.parent.children.splice(n.parent.children.indexOf(n), 1); n.parent = null }
const renderer = createRenderer({
  createElement: node, createText: text => node('text', text), createComment: () => node('comment'),
  setText: (n, text) => { n.text = text }, setElementText: (n, text) => { n.text = text; n.children = [] },
  patchProp: (n, key, old, value) => { n.props[key] = value },
  insert: (n, parent, anchor) => { remove(n); parent.children.splice(anchor ? parent.children.indexOf(anchor) : parent.children.length, 0, n); n.parent = parent },
  remove, parentNode: n => n.parent, nextSibling: n => n.parent?.children[n.parent.children.indexOf(n) + 1] ?? null,
})
const all = n => [n, ...n.children.flatMap(all)]
const content = n => n.text + n.children.map(content).join('')
const flush = async () => { await setImmediate(); await nextTick() }
const button = (root, label) => all(root).find(n => n.type === 'button' && content(n).includes(label))
const control = (root, label) => all(root).find(n => n.props['aria-label'] === label)
// 组件里不用 v-model（指令会直接摸 DOM，替身撑不起来），统一是 :value + @input/@change，
// 所以测试只要按 props 把事件派发出去即可。
const change = (root, label, value) => {
  const n = control(root, label)
  const handler = n.props.onInput ?? n.props.onChange
  handler({ target: { value, checked: value === true } })
}
const submitForm = async root => {
  all(root).find(n => n.type === 'form').props.onSubmit({ preventDefault() {} })
  await flush()
}

const options = [
  { id: 21, ordinal: 1, label: '1 处' },
  { id: 22, ordinal: 2, label: '2 处' },
  { id: 23, ordinal: 3, label: '3 处' },
]
const poll = (overrides = {}) => ({
  id: 9, course_id: 2, task_id: 4, title: '这段流水线有几处数据冒险？', type: 'single',
  max_choices: null, anonymous: false, has_correct: true, status: 'open', open: true,
  voted: 2, eligible: 3, options, ...overrides,
})
const report = (overrides = {}) => ({
  counts: [
    { option_id: 21, ordinal: 1, label: '1 处', is_correct: false, count: 1, ratio: 0.5 },
    { option_id: 22, ordinal: 2, label: '2 处', is_correct: true, count: 1, ratio: 0.5 },
    { option_id: 23, ordinal: 3, label: '3 处', is_correct: false, count: 0, ratio: 0 },
  ],
  voted: 2, eligible: 3,
  correct: { answered: 2, right: 1, wrong: 1, accuracy: 0.5, option_ids: [22] },
  unvoted: [{ student_id: 5, name: '学生02', student_no: '24210002' }],
  details: [
    { student_id: 3, name: '学生00', student_no: '24210000', submitted_at: '2026-11-12T08:00:00.000Z',
      labels: ['2 处'], correct: true },
    { student_id: 4, name: '学生01', student_no: '24210001', submitted_at: '2026-11-12T08:01:00.000Z',
      labels: ['1 处'], correct: false },
  ],
  ...overrides,
})

function stubFetch(fixture) {
  const paths = []
  const old = globalThis.fetch
  globalThis.fetch = async (path, init = {}) => {
    paths.push({ path, init })
    const ok = data => ({ ok: true, status: 200, json: async () => ({ data, total: Array.isArray(data) ? data.length : undefined }) })
    const fail = (status, code) => ({ ok: false, status, json: async () => ({ error: { code, message: '受控失败' } }) })
    if (path.endsWith('/auth/session')) return ok({ user: { id: 1, role: 'teacher' }, csrf_token: 'current' })
    if (path.includes('/polls?status=open')) return ok(fixture.open ?? [])
    if (path.includes('/polls?status=all')) return ok(fixture.polls ?? [])
    if (path.endsWith('/results')) return fixture.reportFail ? fail(403, 'FORBIDDEN') : ok(fixture.report ?? report())
    if (path.endsWith('/ballots') && init.method === 'POST') {
      if (fixture.voteFail) return fail(fixture.voteFail.status, fixture.voteFail.code)
      // 真实的投票响应就是 render()：投完之后才带上 counts 与 correct_option_ids
      return ok(poll({ ...fixture.votedIn, counts: report().counts, my_option_ids: [22],
        correct_option_ids: [22] }))
    }
    if (path.includes('/polls') && init.method === 'POST') return ok(poll({ id: 10, title: '新题目' }))
    if (path.endsWith('/close')) return ok(poll({ status: 'closed', open: false }))
    return ok({})
  }
  return { paths, restore: () => { globalThis.fetch = old } }
}

async function mountPanel(t, fixture, props = {}) {
  const stub = stubFetch(fixture)
  const root = node('root')
  const user = reactive({ id: 1, role: 'teacher' })
  const app = renderer.createApp(PollPanel, { user, courseId: 2, tasks: [], ...props })
  app.mount(root)
  t.after(() => { app.unmount(); stub.restore() })
  await flush()
  return { root, stub, user }
}

test('纯函数：参与率、学生状态、选择上限', () => {
  assert.equal(percent(2, 3), 67)
  assert.equal(percent(0, 0), 0)
  assert.equal(studentState({ my_option_ids: [1], open: true, can_vote: false }), '已投票')
  assert.equal(studentState({ my_option_ids: [], open: true, can_vote: true }), '待投票')
  assert.equal(studentState({ my_option_ids: [], open: true, can_vote: false, reason: 'NOT_CHECKED_IN' }),
    '签到之后才能投票')
  // 单选：点第二项会替换第一项，不会累加
  assert.deepEqual(togglePick({ type: 'single', options }, [21], 22).picks, [22])
  // 多选：上限 2，选满了给提示但不改变已选
  const multiple = { type: 'multiple', max_choices: 2, options }
  assert.deepEqual(togglePick(multiple, [21, 22], 23), { picks: [21, 22], error: '这道题最多选 2 项' })
  assert.deepEqual(togglePick(multiple, [21], 21).picks, [], '再点一次就是取消')
})

test('老师看结果：分布、正确率、未投名单、逐人明细表都在', async t => {
  const { root } = await mountPanel(t, { polls: [poll()] })
  assert.match(content(root), /这段流水线有几处数据冒险/)
  assert.match(content(root), /已投 2 \/ 3/)
  await (button(root, '看结果').props.onClick(), flush())
  assert.match(content(root), /参与率 67%/)
  assert.match(content(root), /对 1 · 错 1/)
  assert.match(content(root), /正确率 50%/)
  assert.match(content(root), /未投票 1 人/)
  assert.match(content(root), /学生02/, '未投名单里要有没投的人')
  // 逐人明细：姓名、学号、所选、判定
  assert.match(content(root), /24210000/)
  assert.match(content(root), /答对/)
  assert.match(content(root), /答错/)
  assert.match(content(root), /2 处/)
})

test('匿名投票：只给分布与未投名单，不给逐人明细', async t => {
  const { root } = await mountPanel(t, {
    polls: [poll({ anonymous: true })],
    report: report({ details: [] }),
  })
  await (button(root, '看结果').props.onClick(), flush())
  assert.match(content(root), /匿名投票/)
  assert.doesNotMatch(content(root), /24210000/, '匿名时不能出现学号')
  assert.match(content(root), /学生02/, '未投名单照旧给，参与率要能追')
})

test('老师出题：选项与正确答案按接口约定提交，成功后提示并选中新投票', async t => {
  const { root, stub } = await mountPanel(t, { polls: [] }, { tasks: [{ id: 4, title: '课堂点到', status: 'open' }] })
  button(root, '发起一场投票').props.onClick(); await flush()
  change(root, '题目', '这条指令属于哪种寻址方式？'); await flush()
  change(root, '选项 1', '立即寻址'); await flush()
  change(root, '选项 2', '寄存器间接寻址'); await flush()
  // 正确答案是「在选项左边打勾」，不再有下拉
  assert.equal(control(root, '正确答案'), undefined, '正确答案不该还是下拉')
  // 勾选按钮的可见文字只有一个 ✓，只能按 aria-label 找
  control(root, '标记第 2 项为正确答案').props.onClick(); await flush()
  assert.match(content(root), /✓/)
  await submitForm(root)
  const posted = stub.paths.find(entry => entry.init.method === 'POST')
  assert.equal(posted.path, '/api/v1/courses/2/polls')
  assert.deepEqual(JSON.parse(posted.init.body), {
    task_id: 4, title: '这条指令属于哪种寻址方式？', type: 'single',
    options: ['立即寻址', '寄存器间接寻址'], max_choices: null, anonymous: true, correct_ordinals: [2],
  })
  assert.equal(posted.init.headers['X-CSRF-Token'], 'current')
  assert.match(content(root), /已经发出去/)
})

test('未投名单默认只铺 12 个，点一下才全展开（160 人的课不能一次铺满）', async t => {
  const many = Array.from({ length: 20 }, (_, index) => ({
    student_id: 100 + index, name: `学生${index}`, student_no: `242109${String(index).padStart(2, '0')}`,
  }))
  const { root } = await mountPanel(t, { polls: [poll()], report: report({ unvoted: many, details: [] }) })
  await (button(root, '看结果').props.onClick(), flush())
  // 自定义 renderer 里 class 是普通 prop，按名字文案数更稳
  const chips = () => all(root).filter(n => n.type === 'span' && /^学生\d+$/.test(content(n))).length
  assert.equal(chips(), 12)
  await (button(root, '还有 8 人，展开').props.onClick(), flush())
  assert.equal(chips(), 20)
  await (button(root, '收起名单').props.onClick(), flush())
  assert.equal(chips(), 12)
})

test('学生没投票时点看结果给的是提示，不是空表', async t => {
  const { root } = await mountPanel(t, { polls: [poll({ my_option_ids: [], can_vote: true })] },
    { user: { id: 7, role: 'student' } })
  button(root, '看结果').props.onClick(); await flush()
  assert.match(content(root), /投完票才能看分布/)
})

async function mountModal(t, fixture, props = { courseId: 2 }) {
  const stub = stubFetch(fixture)
  const root = node('root')
  const app = renderer.createApp(PollModal, props)
  app.mount(root)
  t.after(() => { app.unmount(); stub.restore() })
  await flush()
  return { root, stub }
}

test('学生桌面：进行中的投票自动弹出来，选一项提交后立刻看到分布', async t => {
  const { root, stub } = await mountModal(t, { open: [poll({ can_vote: true, my_option_ids: [] })] })
  assert.match(content(root), /课堂投票 · 单选 · 实名/)
  assert.doesNotMatch(content(root), /最多选/, '单选题不该出现多选上限')
  button(root, '2 处').props.onClick(); await flush()
  assert.match(content(root), /已选 1 项/)
  await (button(root, '提交').props.onClick(), flush())
  const posted = stub.paths.find(entry => entry.init.method === 'POST')
  assert.deepEqual(JSON.parse(posted.init.body), { option_ids: [22] })
  assert.match(content(root), /共 2 人投票/)
  assert.match(content(root), /正确/)
})

test('学生点「稍后」后不再自动弹，投票失败要把原因写在浮层里', async t => {
  const { root } = await mountModal(t, { open: [poll({ can_vote: true, my_option_ids: [] })] })
  button(root, '稍后').props.onClick(); await flush()
  assert.doesNotMatch(content(root), /课堂投票 · 单选/)
  // 换一场再投，这次被后端拒绝：浮层不关，原因要写出来
  const second = await mountModal(t, {
    open: [poll({ id: 12, can_vote: true, my_option_ids: [] })],
    voteFail: { status: 409, code: 'ALREADY_VOTED' },
  })
  button(second.root, '2 处').props.onClick(); await flush()
  await (button(second.root, '提交').props.onClick(), flush())
  assert.match(content(second.root), /你已经投过票了/, '原因要留在浮层里，不能一闪就没')
  // 这时候只剩「知道了」，点了才收
  assert.equal(button(second.root, '提交'), undefined)
  button(second.root, '知道了').props.onClick(); await flush()
  assert.doesNotMatch(content(second.root), /课堂投票 · 单选/)
})

test('投票前不显示分布：浮层里只有题目和选项', async t => {
  const { root } = await mountModal(t, { open: [poll({ can_vote: true, my_option_ids: [] })] })
  assert.doesNotMatch(content(root), /人 ·/)
  assert.doesNotMatch(content(root), /正确/)
})
