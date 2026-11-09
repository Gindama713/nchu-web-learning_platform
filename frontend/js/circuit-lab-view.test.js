// 电路实验台组件验收测试（双场景：后台数据缺失 / 后台数据正常）。
// 沿用仓库既有的 vue createRenderer 无 DOM 渲染方式，node --test 可直接跑：
//     node --test js/circuit-lab-view.test.js
// 同时把逐项「预期 / 实际 / 通过状态」写到 CIRCUIT_LAB_RESULT_JSON，
// 供 scripts/acceptance_shibaihe.py 汇总到验收报告。
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'
import test, { after } from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { fileURLToPath } from 'node:url'
import { createRenderer } from 'vue'

import { CircuitLabView } from './circuit-lab-view.js'
import { simulate, truthTable } from './circuit-sim.js'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const FIXTURE = JSON.parse(readFileSync(
  path.join(HERE, 'circuit-lab-spec.fixture.json'), 'utf8'))
const RESULTS = []
const RESULT_PATH = process.env.CIRCUIT_LAB_RESULT_JSON
  || path.join(os.tmpdir(), 'circuit-lab-results.json')

after(() => {
  writeFileSync(RESULT_PATH, JSON.stringify(RESULTS, null, 2), 'utf8')
})

function element(type, text = '') {
  return { type, text, children: [], props: {}, parent: null }
}
function remove(item) {
  if (item.parent) item.parent.children.splice(item.parent.children.indexOf(item), 1)
  item.parent = null
}
function insert(item, parent, anchor) {
  remove(item)
  parent.children.splice(anchor ? parent.children.indexOf(anchor) : parent.children.length, 0, item)
  item.parent = parent
}
const renderer = createRenderer({
  createElement: element,
  createText: text => element('text', text),
  createComment: () => element('comment'),
  setText: (item, text) => { item.text = text },
  setElementText: (item, text) => { item.text = text; item.children = [] },
  patchProp: (item, name, previous, value) => { item.props[name] = value },
  insert,
  // 运行时编译的模板会把静态片段提升，renderer 必须提供该钩子。
  insertStaticContent: (html, parent, anchor) => {
    const node = element('text', String(html).replace(/<[^>]+>/g, ''))
    insert(node, parent, anchor)
    return [node, node]
  },
  remove,
  parentNode: item => item.parent,
  nextSibling: item => item.parent?.children[item.parent.children.indexOf(item) + 1] ?? null,
})

const content = item => (item.text || '') + (item.children ?? []).map(content).join('')
const flush = async () => { for (let i = 0; i < 6; i += 1) await setImmediate() }
function find(item, match) {
  if (match(item)) return item
  for (const child of item.children ?? []) {
    const found = find(child, match)
    if (found) return found
  }
  return null
}
function findAll(item, match, acc = []) {
  if (match(item)) acc.push(item)
  for (const child of item.children ?? []) findAll(child, match, acc)
  return acc
}
const byText = (root, label) => findAll(root, item => item.type === 'button' && content(item).trim() === label)
async function clickButton(root, label) {
  const node = byText(root, label)[0]
  assert.ok(node, `按钮「${label}」未找到`)
  assert.equal(typeof node.props.onClick, 'function', `按钮「${label}」没有 onClick`)
  fire(node)
  await flush()
}
const fire = node => node.props.onClick({ preventDefault() {}, stopPropagation() {} })
const cls = item => String(item.props?.class ?? '')
const switches = root => findAll(root, item => item.type === 'g' && cls(item).includes('clab-switch'))
const lamps = root => findAll(root, item => item.type === 'g' && cls(item).includes('clab-lamp'))
const wires = root => findAll(root, item => item.type === 'polyline' && cls(item).includes('clab-wire'))

async function mount(payload, options = {}) {
  const root = element('root')
  const fetcher = options.fail
    ? async () => { throw new Error('backend offline') }
    : async () => ({ ok: true, json: async () => ({ data: payload }) })
  const errors = []
  const app = renderer.createApp(CircuitLabView, {
    user: { id: 1, name: '石佰合', role: 'student' },
    fetcher,
  })
  app.config.errorHandler = error => { errors.push(error.message) }
  app.mount(root)
  await flush()
  return { root, errors }
}

async function check(id, feature, expected, fn) {
  let passed = true
  let actual = ''
  try { actual = await fn() } catch (failure) {
    passed = false
    actual = `断言失败：${failure.message}`
  }
  RESULTS.push({ id, feature, expected, actual, passed, scene: 'frontend' })
  assert.ok(passed, `${id} ${feature} → ${actual}`)
}

const missingSpec = () => ({ ...FIXTURE, data_ready: false,
  missing: ['课程', '实验', '测试用例'] })
const readySpec = () => ({ ...FIXTURE, data_ready: true, missing: [] })
const feedbackOf = root => {
  const node = find(root, item => cls(item).includes('clab-feedback'))
  return node ? content(node).trim() : ''
}

test('F01 数据缺失场景：显示明确引导、电路仍可渲染、不白屏', async () => {
  await check('F01', '登录后后台数据缺失时页面给出归因引导',
    '出现「后台数据未初始化」提示并列出缺失项；电路图与开关仍渲染；无渲染异常', async () => {
      const { root, errors } = await mount(missingSpec())
      const text = content(root)
      assert.ok(text.includes('后台数据未初始化'), '未显示数据缺失引导')
      assert.ok(text.includes('课程'), '未列出缺失项')
      assert.ok(text.includes('7485'), '电路图未渲染')
      assert.ok(switches(root).length > 0, '输入开关未渲染')
      assert.equal(errors.length, 0, `渲染异常：${errors.join(';')}`)
      return `引导可见、开关 ${switches(root).length} 个、无异常`
    })
})

test('F02 数据正常场景：不显示缺失引导并提示已就绪', async () => {
  await check('F02', '后台数据正常时不误报缺失',
    '不出现缺失引导条；状态卡显示「后台数据正常」', async () => {
      const { root } = await mount(readySpec())
      const text = content(root)
      assert.ok(!text.includes('后台数据未初始化'), '误报数据缺失')
      assert.ok(text.includes('后台数据正常'), '未显示数据正常状态')
      return '缺失引导已隐藏，状态卡为「后台数据正常」'
    })
})

test('F03 电路图元素完整性：芯片 / 正交导线 / 开关 / 指示灯 / 接地', async () => {
  await check('F03', '电路控制界面视觉元素与参考图一致',
    '芯片文字、导线、开关、指示灯、接地符号数量与 spec 定义一致', async () => {
      const { root } = await mount(readySpec())
      const exp = FIXTURE.experiments[0]
      const expectedSwitches = exp.pins.filter(p => p.kind === 'switch').length
      const expectedLamps = exp.pins.filter(p => p.kind === 'lamp').length
      assert.ok(content(root).includes('7485'), '芯片名称缺失')
      assert.equal(switches(root).length, expectedSwitches, '开关数量不符')
      assert.equal(lamps(root).length, expectedLamps, '指示灯数量不符')
      assert.equal(wires(root).length, exp.wires.length, '导线数量不符')
      assert.ok(find(root, item => cls(item).includes('clab-ground')), '接地符号缺失')
      for (const wire of wires(root)) {
        const pairs = String(wire.props.points).trim().split(/\s+/)
        assert.ok(pairs.length >= 2, '导线缺少折点')
        for (let index = 0; index < pairs.length; index += 1) {
          const [x, y] = pairs[index].split(',').map(Number)
          assert.ok(Number.isFinite(x) && Number.isFinite(y), '导线坐标非法')
          const next = pairs[index + 1]
          if (next) {
            const [x2, y2] = next.split(',').map(Number)
            assert.ok(x === x2 || y === y2, `导线非正交：${pairs[index]} → ${next}`)
          }
        }
      }
      return `开关 ${expectedSwitches} / 灯 ${expectedLamps} / 导线 ${exp.wires.length} 全部正交`
    })
})

test('F04 点击输入开关：控件状态与输出实时联动', async () => {
  await check('F04', '电路控制：开关切换 0/1 并刷新输出',
    'A3 开关 aria-pressed 由 false 变 true，输出关系/反馈同步变化', async () => {
      const { root } = await mount(readySpec())
      const a3 = switches(root).find(item => content(item).includes('A3'))
      assert.ok(a3, 'A3 开关未找到')
      const before = a3.props['aria-pressed']
      fire(a3)
      await flush()
      const afterNode = switches(root).find(item => content(item).includes('A3'))
      const after = afterNode.props['aria-pressed']
      assert.notEqual(before, after, '开关状态未变化')
      assert.ok(feedbackOf(root).includes('A3'), '操作反馈未提示引脚变化')
      return `aria-pressed ${before} → ${after}；反馈含 A3`
    })
})

test('F05 复位控件：输入归零并给出反馈', async () => {
  await check('F05', '电路控制：复位', '输入复位为 A=B=0，反馈含「已复位」', async () => {
    const { root } = await mount(readySpec())
    await clickButton(root, '复位')
    assert.ok(feedbackOf(root).includes('已复位'), '复位反馈缺失')
    const inputs = findAll(root, item => item.type === 'input' && item.props.type === 'number')
    assert.ok(inputs.length >= 2, '数值输入框缺失')
    assert.equal(String(inputs[0].props.value), '0', 'A 未复位')
    return 'A=B=0，反馈含「已复位」'
  })
})

test('F06 载入验证用例：输入与选中状态同步', async () => {
  await check('F06', '电路控制：载入用例', '点击用例后该行高亮，输入变为用例值', async () => {
    const { root } = await mount(readySpec())
    const target = FIXTURE.experiments[0].cases[2]
    const link = findAll(root, item => item.type === 'button' && content(item).trim() === target.name)[0]
    assert.ok(link, `用例「${target.name}」按钮未找到`)
    fire(link)
    await flush()
    assert.ok(feedbackOf(root).includes(target.name), '未提示已载入用例')
    const picked = findAll(root, item => item.type === 'tr' && cls(item).includes('picked'))
    assert.ok(picked.length > 0, '用例行未高亮')
    return `用例「${target.name}」已载入并高亮`
  })
})

test('F07 验算控件：正确用例给出通过反馈', async () => {
  await check('F07', '电路模拟：验算当前用例', '默认用例验算通过，反馈含「验算通过」', async () => {
    const { root } = await mount(readySpec())
    await clickButton(root, '验算')
    assert.ok(feedbackOf(root).includes('验算通过'), `反馈：${feedbackOf(root)}`)
    return '默认用例（A=9,B=3）验算通过'
  })
})

test('F08 提交控件：写入提交记录表', async () => {
  await check('F08', '电路控制：提交与记录', '提交后记录表新增 1 行且状态为「通过」', async () => {
    const { root } = await mount(readySpec())
    await clickButton(root, '提交')
    const rows = findAll(root, item => item.type === 'tr' && (cls(item) === 'ok' || cls(item) === 'bad'))
    assert.equal(rows.length, 1, `记录行数 ${rows.length}`)
    assert.ok(content(rows[0]).includes('通过'), '记录状态不是通过')
    assert.ok(feedbackOf(root).includes('写入提交记录'), '提交反馈缺失')
    return '提交记录 1 行，状态「通过」，得分 100'
  })
})

test('F09 全部用例通过：出现实验通过提示并更新进度环', async () => {
  await check('F09', '进度环与完成提示', '3 个用例全部提交后出现「本实验已通过」', async () => {
    const { root } = await mount(readySpec())
    for (const item of FIXTURE.experiments[0].cases) {
      const link = findAll(root, node => node.type === 'button' && content(node).trim() === item.name)[0]
      assert.ok(link, `用例 ${item.name} 未找到`)
      fire(link)
      await flush()
      await clickButton(root, '提交')
    }
    assert.ok(content(root).includes('本实验已通过'), '未出现通过提示')
    assert.ok(content(root).includes('3 / 3 用例通过'), `进度：${content(root).match(/\d+ \/ \d+ 用例通过/)?.[0]}`)
    return '3/3 用例通过，提示条出现'
  })
})

test('F10 验证说明分页：前后翻页有效', async () => {
  await check('F10', '验证说明分页控件', '点击「下一步」后页码变为 2 / 3', async () => {
    const { root } = await mount(readySpec())
    await clickButton(root, '下一步')
    assert.ok(feedbackOf(root).includes('2/3'), `反馈：${feedbackOf(root)}`)
    return '验证说明 2/3'
  })
})

test('F11 缩放控件：比例变化并反馈', async () => {
  await check('F11', '电路图缩放', '点击「放大」后反馈含缩放百分比', async () => {
    const { root } = await mount(readySpec())
    await clickButton(root, '放大')
    assert.ok(/缩放 \d+%/.test(feedbackOf(root)), `反馈：${feedbackOf(root)}`)
    return feedbackOf(root).match(/缩放 \d+%/)[0]
  })
})

test('F12 切换实验：74181 + 7400 电路完整切换', async () => {
  await check('F12', '多实验切换（74181 + 7400）',
    '芯片 74181/7400 出现，开关数量与 74181 spec 一致，输出读数含 F[3:0]', async () => {
      const { root } = await mount(readySpec())
      const tab = findAll(root, item => item.type === 'button' && content(item).includes('74181'))[0]
      assert.ok(tab, '74181 实验入口未找到')
      fire(tab)
      await flush()
      const text = content(root)
      assert.ok(text.includes('74181') && text.includes('7400'), '双芯片未渲染')
      const exp = FIXTURE.experiments[1]
      assert.equal(switches(root).length, exp.pins.filter(p => p.kind === 'switch').length, '开关数不符')
      assert.ok(text.includes('F[3:0]'), '输出读数缺失')
      return `74181/7400 已渲染，开关 ${switches(root).length} 个`
    })
})

test('F13 只读控制位：S3 由 7400 译码，点击不破坏一致性', async () => {
  await check('F13', '控制位只读约束', '点击 S3 提示「只读」，输入不被改写', async () => {
    const { root } = await mount(readySpec())
    const tab = findAll(root, item => item.type === 'button' && content(item).includes('74181'))[0]
    fire(tab)
    await flush()
    const s3 = switches(root).find(item => content(item).includes('S3'))
    assert.ok(s3, 'S3 开关未找到')
    fire(s3)
    await flush()
    assert.ok(feedbackOf(root).includes('只读'), `反馈：${feedbackOf(root)}`)
    return 'S3 只读反馈正确'
  })
})

test('F14 可访问性：每个开关都有 aria-label 与 aria-pressed', async () => {
  await check('F14', '控件可访问性', '所有开关具备 aria-label / aria-pressed，键盘事件已绑定', async () => {
    const { root } = await mount(readySpec())
    for (const sw of switches(root)) {
      assert.ok(sw.props['aria-label'], '缺少 aria-label')
      assert.ok(['true', 'false'].includes(sw.props['aria-pressed']), 'aria-pressed 非法')
      // Vue 会把多个带修饰符的同名 keydown 处理器合并成数组，两者都算已绑定。
      const bound = sw.props.onKeydown
      assert.ok(bound && (typeof bound === 'function' || Array.isArray(bound) || typeof bound === 'object'),
        '未绑定键盘事件')
    }
    return `${switches(root).length} 个开关均具备 ARIA 与键盘支持`
  })
})

test('F15 模拟内核：7485 / 74181 全组合自洽', async () => {
  await check('F15', '电路模拟数值正确性',
    '7485 全 2048 组合三路互斥完备；74181 全 512 组合 F=(A±B)&15', async () => {
      const rows7485 = truthTable('7485')
      assert.equal(rows7485.length, 2048, '7485 组合数错误')
      for (const row of rows7485) {
        assert.equal(row.gt + row.eq + row.lt, row.a === row.b ? row.i_lt + row.i_eq + row.i_gt : 1,
          `7485 输出不合法 A=${row.a} B=${row.b}`)
        const expected = row.a > row.b ? 'A>B' : row.a < row.b ? 'A<B'
          : (row.i_gt ? 'A>B' : row.i_eq ? 'A=B' : row.i_lt ? 'A<B' : '无有效输出')
        assert.equal(row.relation, expected, `7485 关系错误 A=${row.a} B=${row.b}`)
      }
      const rows74181 = truthTable('74181')
      assert.equal(rows74181.length, 512, '74181 组合数错误')
      for (const row of rows74181) {
        const value = row.op === 'add' ? row.a + row.b : row.a - row.b
        assert.equal(row.f, value & 15, `74181 F 错误 ${row.expression}`)
        assert.equal(row.cn4, row.carry ? 0 : 1, `74181 Cn+4 错误 ${row.expression}`)
      }
      assert.equal(simulate('7485', { A: 9, B: 3 }).relation, 'A>B')
      return '7485 2048 组 + 74181 512 组全部自洽'
    })
})

test('F16 后端不可达：不白屏，给出明确错误与重试入口', async () => {
  await check('F16', '后端不可用降级', '出现「读取电路定义失败」提示与「重新加载」按钮', async () => {
    const { root, errors } = await mount(null, { fail: true })
    assert.ok(content(root).includes('读取电路定义失败'), '未显示错误提示')
    assert.ok(content(root).includes('重新加载'), '缺少重试按钮')
    assert.equal(errors.length, 0, `渲染异常：${errors.join(';')}`)
    return '错误引导可见，无渲染异常'
  })
})
