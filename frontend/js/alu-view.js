// SPEC-019 专业组在线实验：74181 + 7400 四位加/减运算器。
// 运算由后端按 74181 功能表计算（/api/v1/alu74181/table），前端只做索引与展示，
// 不在浏览器里重算一遍公式，避免两处实现出现口径差。
import { computed, onMounted, ref } from 'vue'
import { readApi } from './api.js'

const BITS = [3, 2, 1, 0]
const CELLS = Array.from({ length: 16 }, (_, index) => 15 - index)
const RIGHTS = Array.from({ length: 16 }, (_, index) => index)

const PRESETS = [
  { label: '3 + 5', a: 3, b: 5, op: 'add' },
  { label: '15 + 1 进位', a: 15, b: 1, op: 'add' },
  { label: '9 − 4', a: 9, b: 4, op: 'sub' },
  { label: '1 − 15 借位', a: 1, b: 15, op: 'sub' },
]

function lines() {
  return CELLS.map(left => ({ left, rights: RIGHTS }))
}

const ADD_LINES = lines()
const SUB_LINES = lines()

export const AluView = {
  props: { user: { type: Object, required: true } },
  setup() {
    const spec = ref(null)
    const rows = ref([])
    const a = ref(6)
    const b = ref(3)
    const op = ref('add')
    const busy = ref(false)
    const loaded = ref(false)
    const error = ref('')

    const index = computed(() => {
      const map = new Map()
      rows.value.forEach(item => map.set(item.op + ':' + item.a + ':' + item.b, item))
      return map
    })
    const operations = computed(() => spec.value?.operations ?? {})
    const row = computed(() => operations.value[op.value] ?? null)
    const result = computed(() => index.value.get(op.value + ':' + a.value + ':' + b.value) ?? null)

    async function load() {
      if (busy.value) return
      busy.value = true
      error.value = ''
      try {
        const [head, body] = await Promise.all([
          readApi('/api/v1/alu74181/spec'),
          readApi('/api/v1/alu74181/table'),
        ])
        spec.value = head
        rows.value = body.rows
        loaded.value = true
      } catch (failure) {
        error.value = failure.message
      } finally {
        busy.value = false
      }
    }

    const bitOf = (value, bit) => (value >> bit) & 1

    function toggle(which, bit) {
      const target = which === 'a' ? a : b
      target.value ^= 1 << bit
    }

    function apply(preset) {
      a.value = preset.a
      b.value = preset.b
      op.value = preset.op
    }

    function pick(target, left, right) {
      op.value = target
      a.value = left
      b.value = right
    }

    const signed = (target, left, right) => {
      const hit = index.value.get(target + ':' + left + ':' + right)
      const value = hit ? hit.f : 0
      return target === 'sub' && left < right ? value - 16 : value
    }

    function cellStyle(target, left, right) {
      const value = signed(target, left, right)
      const weight = target === 'sub' ? Math.abs(value) : value
      const light = 96 - Math.round((weight / 15) * 28)
      const hue = target === 'sub' && value < 0 ? 4 : target === 'sub' ? 174 : 214
      const saturation = target === 'sub' && value < 0 ? 72 : 78
      return { background: 'hsl(' + hue + ' ' + saturation + '% ' + light + '%)' }
    }

    const isPicked = (left, right) => a.value === left && b.value === right
    const gridLines = target => (target === 'sub' ? SUB_LINES : ADD_LINES)
    const hex = value => value.toString(16).toUpperCase()

    const verify = computed(() => {
      if (!rows.value.length) return null
      let checked = 0
      let mismatch = 0
      rows.value.forEach(item => {
        checked += 1
        if (item.f !== (item.decimal_result & 15)) mismatch += 1
      })
      return { checked, mismatch }
    })

    onMounted(load)

    return {
      spec, rows, a, b, op, busy, loaded, error, operations, row, result,
      bits: BITS, presets: PRESETS, addLines: ADD_LINES, subLines: SUB_LINES,
      load, bitOf, toggle, apply, pick, signed, cellStyle, isPicked, gridLines, hex, verify,
    }
  },
  template: `
  <section class="card alu-lab">
    <div class="alu-head">
      <div>
        <h2>74181 + 7400 四位加减运算器</h2>
        <p class="alu-lede">
          计算机组成原理组在线实验：求两个 4 位数的和与差。控制位与结果均由服务端按
          74181 功能表计算，浏览器只负责展示，不重算公式。
        </p>
      </div>
      <button type="button" class="secondary" :disabled="busy" @click="load">
        {{ busy ? '读取中…' : '重新加载' }}
      </button>
    </div>

    <p v-if="error" class="alu-error" role="alert">读取芯片数据失败：{{ error }}</p>
    <p v-if="!loaded && !error" class="alu-hint" role="status">正在读取 74181 功能表…</p>

    <template v-if="loaded && result">
      <div class="alu-top">
        <section class="alu-block">
          <h3>操作数</h3>
          <div class="alu-operand">
            <span class="alu-name">A</span>
            <div class="alu-switches">
              <button v-for="bit in bits" :key="'a' + bit" type="button"
                :class="['alu-switch', { on: bitOf(a, bit) }]"
                :aria-pressed="bitOf(a, bit) === 1 ? 'true' : 'false'"
                :aria-label="'A 的第 ' + bit + ' 位'"
                @click="toggle('a', bit)">
                <span class="alu-weight">{{ 1 << bit }}</span>
                <span class="alu-lamp"></span>
              </button>
            </div>
            <span class="alu-value">{{ a }}</span>
          </div>

          <div class="alu-operand">
            <span class="alu-name">B</span>
            <div class="alu-switches">
              <button v-for="bit in bits" :key="'b' + bit" type="button"
                :class="['alu-switch', { on: bitOf(b, bit) }]"
                :aria-pressed="bitOf(b, bit) === 1 ? 'true' : 'false'"
                :aria-label="'B 的第 ' + bit + ' 位'"
                @click="toggle('b', bit)">
                <span class="alu-weight">{{ 1 << bit }}</span>
                <span class="alu-lamp"></span>
              </button>
            </div>
            <span class="alu-value">{{ b }}</span>
          </div>

          <div class="alu-ops" role="group" aria-label="运算选择">
            <button v-for="(item, key) in operations" :key="key" type="button"
              :class="['alu-op', { active: op === key }]"
              :aria-pressed="op === key ? 'true' : 'false'"
              @click="op = key">{{ item.label }}</button>
          </div>

          <div class="alu-presets">
            <button v-for="preset in presets" :key="preset.label" type="button"
              class="alu-preset" @click="apply(preset)">{{ preset.label }}</button>
          </div>
        </section>

        <section class="alu-block alu-chip">
          <h3>芯片控制位</h3>
          <dl class="alu-kv">
            <dt>M（模式）</dt>
            <dd><b>{{ row.m }}</b> 算术模式</dd>
            <dt>S3 S2 S1 S0</dt>
            <dd class="alu-mono">{{ row.s3s2s1s0 }}</dd>
            <dt>Cn̄（进位输入）</dt>
            <dd><b>{{ row.cn_bar ? 'H' : 'L' }}</b>
              {{ row.cn_bar ? '不注入进位' : '注入进位 +1' }}</dd>
            <dt>功能</dt>
            <dd class="alu-mono">{{ row.formula }}</dd>
            <dt>内部加法</dt>
            <dd class="alu-mono">
              {{ result.a }} + {{ result.operand_b }} + {{ result.carry_in }} = {{ result.internal_sum }}
            </dd>
          </dl>
          <p class="alu-note">{{ row.note }}</p>
        </section>
      </div>

      <section class="alu-block alu-output">
        <h3>结果 F</h3>
        <div class="alu-readout">
          <div class="alu-leds">
            <div v-for="bit in bits" :key="'f' + bit" :class="['alu-led', { on: bitOf(result.f, bit) }]">
              <span class="alu-led-bit">F{{ bit }}</span>
              <span class="alu-led-digit">{{ bitOf(result.f, bit) }}</span>
            </div>
          </div>
          <div class="alu-number">
            <strong>{{ result.f }}</strong>
            <span>十进制 · 0x{{ hex(result.f) }} · 二进制 {{ result.f_bits }}</span>
            <span class="alu-expression">{{ result.expression }} = {{ result.decimal_result }}</span>
          </div>
        </div>

        <div class="alu-flags">
          <span :class="['alu-flag', { on: result.cn4 === 0 }]">Cn+4 = {{ result.cn4 }}</span>
          <span v-if="op === 'add'" :class="['alu-flag', { on: result.carry === 1 }]">
            {{ result.carry ? '最高位进位' : '无进位' }}
          </span>
          <span v-else :class="['alu-flag', { on: result.borrow === 1 }]">
            {{ result.borrow ? '需要借位' : '无需借位' }}
          </span>
          <span :class="['alu-flag', { on: result.equal === 1 }]">A=B {{ result.equal }}</span>
          <span :class="['alu-flag', { on: result.zero === 1 }]">{{ result.zero ? '结果为零' : '结果非零' }}</span>
        </div>

        <div class="alu-columns">
          <div class="alu-col">
            <span class="alu-col-label">A</span>
            <span v-for="bit in bits" :key="'ca' + bit" class="alu-col-cell">{{ bitOf(result.a, bit) }}</span>
          </div>
          <div class="alu-col">
            <span class="alu-col-label">{{ op === 'sub' ? 'B̄' : 'B' }}</span>
            <span v-for="bit in bits" :key="'cb' + bit" class="alu-col-cell">{{ bitOf(result.operand_b, bit) }}</span>
          </div>
          <div class="alu-col alu-col-sum">
            <span class="alu-col-label">F</span>
            <span v-for="bit in bits" :key="'cf' + bit" class="alu-col-cell">{{ bitOf(result.f, bit) }}</span>
          </div>
          <p class="alu-col-note">
            {{ op === 'sub'
              ? '减法时 B 先取反再送入 74181，Cn̄ 拉低相当于 +1，合起来就是 A + B̄ + 1。'
              : '加法时 B 原样送入，Cn̄ 保持高电平，不额外加 1。' }}
          </p>
        </div>
      </section>

      <section class="alu-block alu-grids">
        <div class="alu-grid-head">
          <h3>16 × 16 全组合</h3>
          <p class="alu-hint" v-if="verify">
            共 {{ verify.checked }} 组，与整数运算逐一比对，
            不一致 {{ verify.mismatch }} 组。点任意格子可直接取该组操作数。
          </p>
        </div>

        <div class="alu-grid-wrap">
          <div v-for="target in ['add', 'sub']" :key="target" class="alu-grid-block">
            <h4>{{ operations[target] ? operations[target].label : target }}</h4>
            <div class="alu-grid">
              <div class="alu-grid-line alu-grid-head-line">
                <span class="alu-axis alu-corner">A＼B</span>
                <span v-for="right in addLines[0].rights" :key="'h' + target + right" class="alu-axis">{{ right }}</span>
              </div>
              <div v-for="line in gridLines(target)" :key="target + '-' + line.left" class="alu-grid-line">
                <span class="alu-axis">{{ line.left }}</span>
                <button v-for="right in line.rights" :key="target + '-' + line.left + '-' + right"
                  type="button" tabindex="-1" class="alu-cell"
                  :class="{ picked: isPicked(line.left, right) }"
                  :style="cellStyle(target, line.left, right)"
                  :title="line.left + (target === 'add' ? ' + ' : ' − ') + right + ' = ' + signed(target, line.left, right)"
                  @click="pick(target, line.left, right)">{{ signed(target, line.left, right) }}</button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="alu-block alu-about">
        <h3>芯片说明</h3>
        <div class="alu-about-grid">
          <article v-for="chip in spec.chips" :key="chip.model">
            <h4>{{ chip.model }} · {{ chip.title }}</h4>
            <ul>
              <li v-for="note in chip.notes" :key="note">{{ note }}</li>
            </ul>
          </article>
        </div>
      </section>
    </template>
  </section>
  `,
}
