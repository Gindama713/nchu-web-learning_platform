// SPEC-014 预警页面：列表、原因、未处理计数、处理记录闭环、空批次提示。
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer, h, nextTick } from 'vue'

import { WarningView } from './warning-view.js'

const element = (type, text = '') => ({ type, text, children: [], props: {}, parent: null })
function remove(node) { if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1); node.parent = null }
const renderer = createRenderer({
  createElement: element, createText: text => element('text', text), createComment: () => element('comment'),
  setText: (node, text) => { node.text = text }, setElementText: (node, text) => { node.text = text; node.children = [] },
  patchProp: (node, name, old, value) => { node.props[name] = value },
  insert: (node, parent, anchor) => {
    remove(node)
    parent.children.splice(anchor ? parent.children.indexOf(anchor) : parent.children.length, 0, node)
    node.parent = parent
  },
  remove, parentNode: node => node.parent,
  nextSibling: node => node.parent?.children[node.parent.children.indexOf(node) + 1] ?? null,
})
const all = node => [node, ...node.children.flatMap(all)]
const content = node => node.text + node.children.map(content).join('')
const button = (root, label) => all(root).find(node => node.type === 'button' && content(node).trim() === label)
const flush = async () => { for (let i = 0; i < 6; i += 1) { await setImmediate(); await nextTick() } }

const warning = (overrides = {}) => ({
  id: 9, student_id: 12, status: 'open', sample_size: 10,
  reasons: [{ code: 'LOW_OBJECTIVE_RATE', value: 0.5, sample_size: 10 }],
  ...overrides,
})

function mount({ content: payload = null, runs = [], onPatch = null } = {}) {
  const calls = []
  const root = element('root')
  const oldFetch = globalThis.fetch
  const body = payload ?? {
    data: [warning()], total: 1, analysis_run_id: 44, model_status: 'clustered',
  }
  globalThis.fetch = async (path, options = {}) => {
    calls.push({ path, options })
    const ok = (data, extra = {}) => ({ ok: true, status: 200, json: async () => ({ data, ...extra }) })
    if (path.endsWith('/auth/session')) return ok({ user: { id: 7 }, csrf_token: 'tk' })
    if (path.startsWith('/api/v1/courses?')) return ok([{ id: 3, title: 'CPU' }], { total: 1 })
    if (path.includes('/members?')) return ok([{ user_id: 12, name: '莫涛', student_no: '24201501' }], { total: 1 })
    if (path.includes('/warnings?')) return ok(body.data, body)
    if (path.includes('/warning-runs?')) return ok(runs, { total: runs.length })
    if (path.endsWith('/warning-runs') && options.method === 'POST') return ok({ analysis_run_id: 45 })
    if (path.includes('/warnings/9') && options.method === 'PATCH') {
      onPatch?.(JSON.parse(options.body))
      return ok({ id: 9, status: 'handled' })
    }
    throw new Error('unexpected ' + path)
  }
  const app = renderer.createApp({ render: () => h(WarningView, { user: { id: 7 } }) })
  app.mount(root)
  return { root, calls, restore: () => { globalThis.fetch = oldFetch } }
}

test('渲染学生、原因与未处理计数', async () => {
  const view = mount()
  try {
    await flush()
    const text = content(view.root)
    assert.match(text, /学习预警/)
    assert.match(text, /莫涛/)
    assert.match(text, /客观题正确率偏低/)
    assert.match(text, /未处理 1/)
    assert.match(text, /批次 #44/)
    assert.match(text, /已聚类/)
  } finally { view.restore() }
})

test('标记处理：填备注后 PATCH 并把状态写成已处理', async () => {
  let patched = null
  const view = mount({ onPatch: payload => { patched = payload } })
  try {
    await flush()
    button(view.root, '标记处理').props.onClick()
    await flush()
    const input = all(view.root).find(node => node.type === 'input' && node.props['aria-label'] === '处理记录')
    assert.ok(input, '应出现处理记录输入框')
    input.props.onInput({ target: { value: '已单独联系' } })
    await flush()
    button(view.root, '确认').props.onClick()
    await flush()
    assert.deepEqual(patched, { status: 'handled', note: '已单独联系' })
    assert.match(content(view.root), /已记录处理/)
  } finally { view.restore() }
})

test('没有批次时给出生成引导，而不是空白列表', async () => {
  const view = mount({ content: { data: [], total: 0, analysis_run_id: null, model_status: 'no_run' } })
  try {
    await flush()
    const text = content(view.root)
    assert.match(text, /还没有预警批次/)
    assert.match(text, /尚未生成批次/)
  } finally { view.restore() }
})

test('切换「只看未处理」会带 status=open 重新查询', async () => {
  const view = mount()
  try {
    await flush()
    const select = all(view.root).find(node => node.type === 'select' &&
      node.children.some(child => content(child).includes('未处理')))
    select.props.onChange({ target: { value: 'open' } })
    await flush()
    assert.ok(view.calls.some(entry => entry.path.includes('status=open')), '应发出带筛选的请求')
  } finally { view.restore() }
})
