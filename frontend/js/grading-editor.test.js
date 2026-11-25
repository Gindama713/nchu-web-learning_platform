import test from 'node:test'
import assert from 'node:assert/strict'
import { profileFields, caseFields } from './grading-editor.js'

const nodes = node => !node || typeof node !== 'object' ? [] : [node, ...(Array.isArray(node.children) ? node.children.flatMap(nodes) : [])]

test('基本表单与高级JSON共用数据，保留时钟和步骤次序', () => {
  const form = { portSchemaText: JSON.stringify({ inputs: { D: 8 }, outputs: { Q: 8 }, clock: 'CLK' }), limitsText: '{}' }
  let message = ''
  let view = profileFields(form, false, value => { message = value })
  const width = nodes(view).filter(n => n.type === 'input' && n.props.type === 'number')[0]
  width.props.onChange({ target: { value: '4' } })
  assert.equal(JSON.parse(form.portSchemaText).inputs.D, 4)
  view = profileFields(form, false, value => { message = value })
  const clock = nodes(view).find(n => n.type === 'input' && n.props.value === 'CLK')
  clock.props.onChange({ target: { value: 'D' } })
  assert.match(message, /独立/)
  assert.equal(JSON.parse(form.portSchemaText).clock, 'CLK')
  let text = JSON.stringify([{ label: 'load', group_code: 'load', visibility: 'public', steps: [
    { step_no: 1, inputs: { D: 5 }, expected: { Q: 5 }, clock_event: 'rising' },
  ] }])
  view = caseFields(text, value => { text = value }, form, ['load'], false, value => { message = value })
  const event = nodes(view).find(n => n.type === 'select' && n.props.value === 'rising')
  event.props.onChange({ target: { value: 'falling' } })
  assert.equal(JSON.parse(text)[0].steps[0].clock_event, 'falling')
  const add = nodes(view).find(n => n.type === 'button' && n.children === '新增步骤')
  add.props.onClick()
  assert.deepEqual(JSON.parse(text)[0].steps.map(step => step.step_no), [1, 2])
  const input = nodes(view).find(n => n.type === 'input' && n.props.value === 5)
  input.props.onChange({ target: { value: 'X' } })
  assert.match(message, /非负整数/)
  assert.equal(JSON.parse(text)[0].steps[0].inputs.D, 5)
})

test('高级JSON结构错误时显示提示，基础表单仍可恢复', () => {
  const form = { portSchemaText: '{"inputs":{"D":8},"outputs":{"Q":8}}', limitsText: '{}' }
  for (const text of ['[null]', '[{"steps":[null]}]', '[{"steps":[{"inputs":{},"expected":null}]}]']) {
    assert.equal(caseFields(text, () => {}, form, [], false, () => {}).props.role, 'alert')
  }
  form.portSchemaText = '{"inputs":null,"outputs":{}}'
  assert.equal(profileFields(form, false, () => {}).props.role, 'alert')
})
