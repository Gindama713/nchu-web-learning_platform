// SPEC-016 识别页面：上传、置信度标注、未识别提示、未补标签不能确认。
import assert from 'node:assert/strict'
import test from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createRenderer, h, nextTick } from 'vue'

import { RecognitionView } from './recognition-view.js'

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
const flush = async () => { for (let i = 0; i < 8; i += 1) { await setImmediate(); await nextTick() } }

const recognized = {
  id: 11, status: 'recognized', template_set_sha256: 'e5fad902074d5401cb207932a72b539cdf2647f3fffcd29b65b42fe0bd016a49',
  items: [
    { symbol: 'AND', bbox: [80, 60, 160, 120], confidence: 0.6, confidence_band: 'low', label: 'A' },
    { symbol: 'NOT', bbox: [350, 60, 180, 120], confidence: 0.92, confidence_band: 'high', label: 'Y' },
  ],
}

function mount({ payload = recognized, onConfirm = null } = {}) {
  const calls = []
  const root = element('root')
  const saved = {
    fetch: globalThis.fetch, create: globalThis.URL.createObjectURL,
    revoke: globalThis.URL.revokeObjectURL, Image: globalThis.Image,
  }
  globalThis.URL.createObjectURL = () => 'blob:preview'
  globalThis.URL.revokeObjectURL = () => {}
  globalThis.Image = class {
    set src(_value) { this.naturalWidth = 640; this.naturalHeight = 240; this.onload?.() }
  }
  globalThis.fetch = async (path, options = {}) => {
    calls.push({ path, options })
    const ok = (data, extra = {}) => ({ ok: true, status: 200, json: async () => ({ data, ...extra }) })
    if (path.endsWith('/auth/session')) return ok({ user: { id: 7 }, csrf_token: 'tk' })
    if (path.startsWith('/api/v1/courses?')) return ok([{ id: 3, title: 'CPU' }], { total: 1 })
    if (path.endsWith('/courses/3/recognitions') && options.method === 'POST') return ok(payload)
    if (path.endsWith('/confirm') && options.method === 'POST') {
      onConfirm?.(JSON.parse(options.body))
      return ok({ ...payload, status: 'confirmed', confirmed_items: payload.items })
    }
    throw new Error('unexpected ' + path)
  }
  const app = renderer.createApp({ render: () => h(RecognitionView, { user: { id: 7 } }) })
  app.mount(root)
  return {
    root, calls,
    restore: () => {
      globalThis.fetch = saved.fetch
      globalThis.URL.createObjectURL = saved.create
      globalThis.URL.revokeObjectURL = saved.revoke
      globalThis.Image = saved.Image
    },
  }
}

function upload(root, file = new globalThis.Blob(['fake'], { type: 'image/png' })) {
  const input = all(root).find(node => node.type === 'input' && node.props.type === 'file')
  input.props.onChange({ target: { files: [file], value: '' } })
}

test('初始渲染给出上传入口与人工确认说明', async () => {
  const view = mount()
  try {
    await flush()
    const text = content(view.root)
    assert.match(text, /把电路图拖进来/)
    assert.match(text, /所有结果必须人工确认/)
    assert.match(text, /不自动判分/)
  } finally { view.restore() }
})

test('上传后显示识别项、低置信度与坐标', async () => {
  const view = mount()
  try {
    await flush()
    upload(view.root)
    await flush()
    const text = content(view.root)
    assert.match(text, /待确认/)
    assert.match(text, /共 2 项/)
    assert.match(text, /低置信/)
    assert.match(text, /80, 60, 160, 120/)
  } finally { view.restore() }
})

test('未识别时明确提示换图，而不是给一个空结果', async () => {
  const view = mount({ payload: { id: 12, status: 'unrecognized', items: [] } })
  try {
    await flush()
    upload(view.root)
    await flush()
    const text = content(view.root)
    assert.match(text, /没有匹配到支持的门符号/)
    assert.match(text, /未识别/)
  } finally { view.restore() }
})

test('标签没补齐时拒绝确认并说明还差几项', async () => {
  const view = mount({
    payload: { ...recognized, items: [{ ...recognized.items[0], label: null }, recognized.items[1]] },
  })
  try {
    await flush()
    upload(view.root)
    await flush()
    assert.match(content(view.root), /待补标签 1 项/)
    button(view.root, '人工确认草稿').props.onClick()
    await flush()
    assert.match(content(view.root), /还有 1 项没有补齐标签/)
  } finally { view.restore() }
})
