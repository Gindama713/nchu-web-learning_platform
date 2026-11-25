// Basic controls edit the SAME JSON strings used by the advanced editor.
import { h } from 'vue'

const parse = text => { try { return JSON.parse(text) } catch { return null } }
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value)
const portSchema = value => object(value) && object(value.inputs) && object(value.outputs)
const field = (label, value, change, options = {}) => h('label', { class: 'knowledge-field' }, [
  h('span', label), h('input', { value, onChange: event => change(event.target.value), ...options }),
])
const select = (label, value, choices, change, disabled) => h('label', { class: 'knowledge-field' }, [
  h('span', label), h('select', { value, disabled, onChange: event => change(event.target.value) },
    choices.map(([key, title]) => h('option', { value: key }, title))),
])
const button = (label, action, disabled) => h('button', { type: 'button', onClick: action, disabled }, label)

export function profileFields(form, busy, error) {
  const schema = parse(form.portSchemaText)
  const limits = parse(form.limitsText || '{}')
  if (!portSchema(schema) || !object(limits)) return h('p', { role: 'alert' }, '请先修正高级编辑器中的JSON，或载入公开模板。')
  function edit(change) {
    try {
      change(schema)
      form.portSchemaText = JSON.stringify(schema)
      error('')
    } catch (failure) { error(failure.message) }
  }
  const ports = ['inputs', 'outputs'].flatMap(side => Object.entries(schema[side]).map(([label, width]) =>
    h('div', { class: 'grading-port-row', key: `${side}:${label}` }, [
      field(`${side === 'inputs' ? '输入' : '输出'}端口名`, label, name => edit(value => {
        if (!/^[A-Za-z0-9_]{1,32}$/.test(name) || name.toUpperCase() === 'CLK' ||
            (name !== label && (name in value.inputs || name in value.outputs || name === value.clock))) {
          throw new Error('端口名须唯一，CLK请在独立时钟栏配置。')
        }
        delete value[side][label]; value[side][name] = width
      }), { disabled: busy }),
      field('位宽（1—8）', width, number => edit(value => { value[side][label] = Number(number) }),
        { type: 'number', min: 1, max: 8, disabled: busy }),
      button('删除端口', () => edit(value => { delete value[side][label] }), busy),
    ])))
  return h('div', { class: 'grading-basic-editor' }, [
    h('h4', '数据端口'), ...ports,
    ...['inputs', 'outputs'].map(side => button(side === 'inputs' ? '新增输入端口' : '新增输出端口', () => edit(value => {
      let index = 1
      while (`PORT${index}` in value.inputs || `PORT${index}` in value.outputs) index++
      value[side][`PORT${index}`] = 1
    }), busy)),
    field('时钟端口（组合电路留空，例如CLK）', schema.clock || '', value => edit(current => {
      if (value && (!/^[A-Za-z0-9_]{1,32}$/.test(value) || value in current.inputs || value in current.outputs)) {
        throw new Error('时钟必须是独立的1位输入端口。')
      }
      if (value) current.clock = value
      else delete current.clock
    }), { disabled: busy }),
    h('h4', '执行限额'),
    ...[['cpu_seconds', '每例超时（秒）', 10], ['memory_mib', 'JVM最大堆（MiB）', 512],
      ['output_bytes', '最大输出（字节）', 1048576]].map(([key, title, maximum]) =>
      field(title, limits[key] ?? maximum, value => {
        limits[key] = Number(value); form.limitsText = JSON.stringify(limits)
      }, { type: 'number', min: 1, max: maximum, disabled: busy })),
  ])
}

export function caseFields(text, update, form, groups, busy, error) {
  const cases = parse(text)
  const schema = parse(form.portSchemaText)
  if (!portSchema(schema) || !Array.isArray(cases) || !cases.every(item => object(item) && Array.isArray(item.steps) &&
      item.steps.every(step => object(step) && object(step.inputs) && object(step.expected)))) {
    return h('p', { role: 'alert' }, '载入模板或修正高级JSON后可使用步骤表单。')
  }
  function edit(change) {
    try { change(cases); update(JSON.stringify(cases)); error('') }
    catch (failure) { error(failure.message) }
  }
  function valueChanged(step, side, label, value) {
    if (value === '') delete step[side][label]
    else if (side === 'expected' && /^[XZ]$/i.test(value)) step[side][label] = value.toUpperCase()
    else if (/^\d+$/.test(value) && Number.isSafeInteger(Number(value))) step[side][label] = Number(value)
    else throw new Error(`端口${label}请输入非负整数${side === 'expected' ? '、X或Z' : ''}；留空表示保持输入/不检查输出。`)
  }
  const blankStep = () => ({ step_no: 1, inputs: Object.fromEntries(Object.keys(schema.inputs).map(k => [k, 0])),
    expected: Object.fromEntries(Object.keys(schema.outputs).map(k => [k, 0])), clock_event: 'none' })
  return h('div', { class: 'grading-basic-editor' }, [
    h('p', '每步先稳定输入，再施加时钟边沿，最后比较预期输出。输入留空保持上一步；输出留空不检查，至少检查一项。'),
    ...cases.map((item, index) => h('details', { class: 'grading-case', key: index, open: index === 0 }, [
      h('summary', `用例 ${index + 1} · ${item.label} · ${item.group_code}`),
      field('用例名称', item.label, value => edit(() => { item.label = value }), { disabled: busy }),
      groups.length ? select('评分组', item.group_code, groups.map(g => [g, g]), value => edit(() => { item.group_code = value }), busy)
        : field('评分组', item.group_code, value => edit(() => { item.group_code = value }), { disabled: busy }),
      select('可见性', item.visibility, [['public', '公开'], ['hidden', '隐藏']], value => edit(() => { item.visibility = value }), busy),
      ...(item.steps || []).map((step, number) => h('details', { class: 'grading-step', key: number, open: number === 0 }, [
        h('summary', `步骤 ${number + 1} · ${step.clock_event}`),
        select('时钟事件', step.clock_event, [['none', '不施加边沿'], ['rising', '上升沿'], ['falling', '下降沿']],
          value => edit(() => { step.clock_event = value }), busy),
        ...['inputs', 'outputs'].flatMap(side => Object.entries(schema[side]).map(([label, width]) => {
          const target = side === 'inputs' ? 'inputs' : 'expected'
          return field(`${target === 'inputs' ? '输入' : '预期'} ${label}（${width}位）`, step[target]?.[label] ?? '',
            value => edit(() => valueChanged(step, target, label, value)), { disabled: busy, inputmode: 'text' })
        })),
        button('删除步骤', () => edit(() => {
          item.steps.splice(number, 1); item.steps.forEach((s, i) => { s.step_no = i + 1 })
        }), busy),
      ])),
      button('新增步骤', () => edit(() => {
        if (item.steps.length >= 1024) throw new Error('每个用例最多1024步。')
        item.steps.push({ ...blankStep(), step_no: item.steps.length + 1 })
      }), busy),
      button('删除用例', () => edit(() => { cases.splice(index, 1) }), busy),
    ])),
    button('新增用例', () => edit(() => {
      if (cases.length >= 128) throw new Error('每个测试集最多128个用例。')
      cases.push({ label: `用例${cases.length + 1}`, group_code: groups[0] || 'add', visibility: 'public', steps: [blankStep()] })
    }), busy),
  ])
}
