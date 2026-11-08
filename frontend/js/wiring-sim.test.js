// Pure simulation tests for the EXP-01/EXP-02 style panels (AC-03/AC-08).
import assert from 'node:assert/strict'
import test from 'node:test'
import { initialState, propagate, resetSim, stepSim } from './wiring-sim.js'

const EXP01 = {
  components: [
    { id: 'sw_a', type: 'SWITCH', params: { width: 8, initial: 0 }, ports: { OUT: 'sw_a_out' } },
    { id: 'sw_b', type: 'SWITCH', params: { width: 8, initial: 0 }, ports: { OUT: 'sw_b_out' } },
    { id: 'sw_op', type: 'SWITCH', params: { width: 3, initial: 0 }, ports: { OUT: 'sw_op_out' } },
    { id: 'alu', type: 'ALU8', params: {}, ports: { A: 'alu_a', B: 'alu_b', OP: 'alu_op', Y: 'alu_y', Z: 'alu_z', C: 'alu_c' } },
    { id: 'led_y', type: 'LED', params: { width: 8 }, ports: { IN: 'led_y_in' } },
    { id: 'led_z', type: 'LED', params: { width: 1 }, ports: { IN: 'led_z_in' } },
    { id: 'led_c', type: 'LED', params: { width: 1 }, ports: { IN: 'led_c_in' } },
  ],
  terminals: [
    { id: 'sw_a_out', component_id: 'sw_a', name: 'OUT', direction: 'out', width: 8, required: false },
    { id: 'sw_b_out', component_id: 'sw_b', name: 'OUT', direction: 'out', width: 8, required: false },
    { id: 'sw_op_out', component_id: 'sw_op', name: 'OUT', direction: 'out', width: 3, required: false },
    { id: 'alu_a', component_id: 'alu', name: 'A', direction: 'in', width: 8, required: true },
    { id: 'alu_b', component_id: 'alu', name: 'B', direction: 'in', width: 8, required: true },
    { id: 'alu_op', component_id: 'alu', name: 'OP', direction: 'in', width: 3, required: true },
    { id: 'alu_y', component_id: 'alu', name: 'Y', direction: 'out', width: 8, required: false },
    { id: 'alu_z', component_id: 'alu', name: 'Z', direction: 'out', width: 1, required: false },
    { id: 'alu_c', component_id: 'alu', name: 'C', direction: 'out', width: 1, required: false },
    { id: 'led_y_in', component_id: 'led_y', name: 'IN', direction: 'in', width: 8, required: false },
    { id: 'led_z_in', component_id: 'led_z', name: 'IN', direction: 'in', width: 1, required: false },
    { id: 'led_c_in', component_id: 'led_c', name: 'IN', direction: 'in', width: 1, required: false },
  ],
}

const EXP_WIRES = [
  { id: 'w1', from_terminal: 'sw_a_out', to_terminal: 'alu_a' },
  { id: 'w2', from_terminal: 'sw_b_out', to_terminal: 'alu_b' },
  { id: 'w3', from_terminal: 'sw_op_out', to_terminal: 'alu_op' },
  { id: 'w4', from_terminal: 'alu_y', to_terminal: 'led_y_in' },
  { id: 'w5', from_terminal: 'alu_z', to_terminal: 'led_z_in' },
  { id: 'w6', from_terminal: 'alu_c', to_terminal: 'led_c_in' },
]

const REG = {
  components: [
    { id: 'sw_d', type: 'SWITCH', params: { width: 8, initial: 0 }, ports: { OUT: 'sw_d_out' } },
    { id: 'sw_en', type: 'SWITCH', params: { width: 1, initial: 1 }, ports: { OUT: 'sw_en_out' } },
    { id: 'clk', type: 'CLOCK', params: {}, ports: { OUT: 'clk_out' } },
    { id: 'rst', type: 'RESET', params: {}, ports: { OUT: 'rst_out' } },
    { id: 'reg', type: 'REG8', params: {}, ports: { D: 'reg_d', CLK: 'reg_clk', RESET: 'reg_rst', EN: 'reg_en', Q: 'reg_q' } },
    { id: 'led_q', type: 'LED', params: { width: 8 }, ports: { IN: 'led_q_in' } },
  ],
  terminals: [
    { id: 'sw_d_out', component_id: 'sw_d', name: 'OUT', direction: 'out', width: 8, required: false },
    { id: 'sw_en_out', component_id: 'sw_en', name: 'OUT', direction: 'out', width: 1, required: false },
    { id: 'clk_out', component_id: 'clk', name: 'OUT', direction: 'out', width: 1, required: false },
    { id: 'rst_out', component_id: 'rst', name: 'OUT', direction: 'out', width: 1, required: false },
    { id: 'reg_d', component_id: 'reg', name: 'D', direction: 'in', width: 8, required: true },
    { id: 'reg_clk', component_id: 'reg', name: 'CLK', direction: 'in', width: 1, required: true },
    { id: 'reg_rst', component_id: 'reg', name: 'RESET', direction: 'in', width: 1, required: true },
    { id: 'reg_en', component_id: 'reg', name: 'EN', direction: 'in', width: 1, required: true },
    { id: 'reg_q', component_id: 'reg', name: 'Q', direction: 'out', width: 8, required: false },
    { id: 'led_q_in', component_id: 'led_q', name: 'IN', direction: 'in', width: 8, required: false },
  ],
}

const REG_WIRES = [
  { id: 'w1', from_terminal: 'sw_d_out', to_terminal: 'reg_d' },
  { id: 'w2', from_terminal: 'sw_en_out', to_terminal: 'reg_en' },
  { id: 'w3', from_terminal: 'clk_out', to_terminal: 'reg_clk' },
  { id: 'w4', from_terminal: 'rst_out', to_terminal: 'reg_rst' },
  { id: 'w5', from_terminal: 'reg_q', to_terminal: 'led_q_in' },
]

test('EXP-01 0xFF + 0x01 drives Y=0 Z=1 C=1 (AC-03)', () => {
  const state = { ...initialState(EXP01), wires: EXP_WIRES, inputs: { sw_a_out: 255, sw_b_out: 1, sw_op_out: 0 } }
  const values = propagate(EXP01, state)
  assert.equal(values.get('led_y_in'), 0)
  assert.equal(values.get('led_z_in'), 1)
  assert.equal(values.get('led_c_in'), 1)
})

test('unwired LED reads Z and undriven ALU input propagates X (AC-08)', () => {
  const state = { ...initialState(EXP01), wires: [EXP_WIRES[0]] }
  const values = propagate(EXP01, state)
  assert.equal(values.get('alu_b'), 'Z')
  assert.equal(values.get('alu_y'), 'X')
  assert.equal(values.get('led_y_in'), 'Z')
})

test('REG8 latches D on step and holds when disabled (AC-03/AC-04)', () => {
  let state = { ...initialState(REG), wires: REG_WIRES }
  state = resetSim(REG, state)
  assert.equal(state.reg_q, 0)
  state.inputs.sw_d_out = 0xA5
  state = stepSim(REG, state)
  assert.equal(state.reg_q, 0xA5)
  const values = propagate(REG, state)
  assert.equal(values.get('led_q_in'), 0xA5)
  state.inputs.sw_en_out = 0
  state.inputs.sw_d_out = 0x3C
  state = stepSim(REG, state)
  assert.equal(state.reg_q, 0xA5)
})
