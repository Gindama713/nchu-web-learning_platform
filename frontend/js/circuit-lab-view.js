// SPEC-009 电路实验台：对照课堂作品实现的芯片级「电路控制」界面。
//
// 布局与参考图一致：左侧深色实验栏 / 顶部标题与工具栏 / 左信息卡（进度环 +
// 验证说明 + 分页）/ 中间 SVG 电路图（芯片、开关、指示灯、绿色正交导线、接地）
// / 右侧控制面板（输入设置、验证用例、输出读数、芯片说明）/ 底部提交记录。
//
// 所有开关状态与输出都由 circuit-sim.js 的芯片功能表实时求值；后端
// /api/v1/circuit-lab/spec 提供电路定义与 data_ready，/compute 提供权威复核。
// 后台业务数据缺失时页面给出明确引导而不是空白，且电路模拟仍可离线使用。
import { computed, onMounted, ref } from 'vue'
import { readApi } from './api.js'
import {
  checkCase, defaultInputs, inputSummary, pinState, setNumeric, simulate, togglePin,
} from './circuit-sim.js'

const RING_LENGTH = 2 * Math.PI * 26

export const CircuitLabView = {
  props: {
    user: { type: Object, required: true },
    // 测试注入点：不传时使用浏览器 fetch。
    fetcher: { type: Function, default: null },
  },
  setup(props) {
    const spec = ref(null)
    const loaded = ref(false)
    const busy = ref(false)
    const error = ref('')
    const activeId = ref('7485')
    const activeCase = ref('')
    const inputs = ref({})
    const docPage = ref(0)
    const attempts = ref([])
    const feedback = ref('拨动芯片引脚开关，观察输出指示灯与右侧读数。')
    const feedbackTone = ref('info')
    const scale = ref(1)
    const showHelp = ref(false)
    const simulateOnly = ref(false)

    const get = path => props.fetcher ? readApi(path, props.fetcher) : readApi(path)

    const experiments = computed(() => spec.value?.experiments ?? [])
    const experiment = computed(() => experiments.value.find(item => item.id === activeId.value) ?? null)
    const dataReady = computed(() => spec.value?.data_ready === true)
    const missing = computed(() => spec.value?.missing ?? [])
    const cases = computed(() => experiment.value?.cases ?? [])
    const output = computed(() => simulate(activeId.value, inputs.value))
    const doc = computed(() => experiment.value?.doc ?? [])
    const currentDoc = computed(() => doc.value[docPage.value] ?? null)
    const passedIds = computed(() => new Set(
      attempts.value.filter(item => item.experimentId === activeId.value && item.passed)
        .map(item => item.caseId)))
    const progress = computed(() => ({ passed: passedIds.value.size, total: cases.value.length }))
    const ring = computed(() => {
      const ratio = progress.value.total ? progress.value.passed / progress.value.total : 0
      return { dash: RING_LENGTH.toFixed(2), offset: (RING_LENGTH * (1 - ratio)).toFixed(2),
        percent: Math.round(ratio * 100) }
    })
    const allPassed = computed(() => progress.value.total > 0 && progress.value.passed === progress.value.total)
    const wires = computed(() => experiment.value?.wires ?? [])
    const points = wire => wire.points.map(pair => pair.join(',')).join(' ')

    function note(text, tone = 'info') {
      feedback.value = text
      feedbackTone.value = tone
    }

    function applyExperiment(exp) {
      if (!exp) return
      inputs.value = defaultInputs(exp)
      activeCase.value = exp.cases[0]?.id ?? ''
      docPage.value = 0
    }

    async function load() {
      if (busy.value) return
      busy.value = true
      error.value = ''
      try {
        const data = await get('/api/v1/circuit-lab/spec')
        spec.value = data
        loaded.value = true
        if (data.experiments?.length && !data.experiments.some(item => item.id === activeId.value)) {
          activeId.value = data.experiments[0].id
        }
        applyExperiment(experiment.value)
        note(data.data_ready
          ? '后台数据已就绪：电路模拟、验算与提交均可用。'
          : `后台数据未初始化（缺少 ${(data.missing ?? []).join('、') || '业务数据'}）；`
            + '电路模拟与验算仍可用，提交为本次会话记录。', data.data_ready ? 'success' : 'warn')
      } catch (failure) {
        error.value = failure.message
        simulateOnly.value = true
        note(`读取电路定义失败：${failure.message}。请确认后端已启动后点击「重新加载」。`, 'error')
      } finally {
        busy.value = false
      }
    }

    function selectExperiment(id) {
      if (id === activeId.value) return
      activeId.value = id
      applyExperiment(experiment.value)
      note(`已切换到「${experiment.value?.title ?? id}」，输入已重置为首个用例。`)
    }

    function useCase(item) {
      activeCase.value = item.id
      inputs.value = { ...item.inputs }
      const index = cases.value.findIndex(candidate => candidate.id === item.id)
      if (index >= 0) docPage.value = Math.min(index, Math.max(0, doc.value.length - 1))
      note(`已载入用例「${item.name}」：${inputSummary(item.inputs)}。点击「验算」或「提交」。`)
    }

    function onPin(pin) {
      if (pin.group === 'control' && pin.id !== 'Cn') {
        note(`${pin.label} 由 7400 依据运算译码，是只读控制位；切换加减请点击 Cn̄。`, 'warn')
        return
      }
      const before = pinState(activeId.value, inputs.value, pin)
      inputs.value = togglePin(activeId.value, inputs.value, pin)
      const after = pinState(activeId.value, inputs.value, pin)
      note(`${pin.label}：${before} → ${after}；当前 ${activeId.value === '7485'
        ? `关系 ${output.value.relation}` : `F=0x${output.value.f.toString(16).toUpperCase()}`}。`)
    }

    function onControl(row, value) {
      inputs.value = setNumeric(activeId.value, inputs.value, row.key, value)
      note(`${row.label} 已设为 ${value}，输出已实时刷新。`)
    }

    function reset() {
      inputs.value = activeId.value === '7485'
        ? { A: 0, B: 0, I_LT: 0, I_EQ: 1, I_GT: 0 }
        : { A: 0, B: 0, OP: 'sub' }
      activeCase.value = ''
      note('输入已复位（A=B=0，级联 A=B=1 / 减法模式）。')
    }

    function evaluate() {
      const exp = experiment.value
      if (!exp) return null
      return checkCase({ ...exp, active_case: activeCase.value || exp.cases[0].id }, inputs.value)
    }

    function verify() {
      const result = evaluate()
      if (!result) return
      const detail = result.details.map(item =>
        `${item.key} 期望 ${item.expected} / 实际 ${item.actual}`).join('，')
      note(result.passed
        ? `用例「${result.case.name}」验算通过：${detail}。`
        : `用例「${result.case.name}」未通过：${detail}。`, result.passed ? 'success' : 'error')
    }

    function submit() {
      const result = evaluate()
      if (!result) return
      const now = new Date()
      const at = Number.isFinite(now.getTime())
        ? `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`
        : '--:--:--'
      attempts.value = [{
        no: attempts.value.length + 1,
        at,
        experimentId: activeId.value,
        experiment: experiment.value?.title ?? activeId.value,
        caseId: result.case.id,
        caseName: result.case.name,
        inputs: inputSummary(inputs.value),
        expected: JSON.stringify(result.case.expected),
        actual: result.details.map(item => `${item.key}=${item.actual}`).join(' '),
        passed: result.passed,
        score: result.passed ? 100 : 0,
      }, ...attempts.value]
      const suffix = dataReady.value ? '' : '（后台数据未初始化，记录仅保存在本次会话）'
      note(result.passed
        ? `用例「${result.case.name}」提交通过，已写入提交记录${suffix}。`
        : `用例「${result.case.name}」提交未通过，请检查输入后重试${suffix}。`,
      result.passed ? 'success' : 'error')
    }

    function page(delta) {
      if (!doc.value.length) return
      docPage.value = (docPage.value + delta + doc.value.length) % doc.value.length
      note(`验证说明 ${docPage.value + 1}/${doc.value.length}：${currentDoc.value?.title ?? ''}。`)
    }

    function zoom(delta) {
      scale.value = Math.min(1.4, Math.max(0.7, Math.round((scale.value + delta) * 10) / 10))
      note(`电路图缩放 ${Math.round(scale.value * 100)}%。`)
    }

    const pinValue = pin => pinState(activeId.value, inputs.value, pin)
    const chipRect = chip => chip ? { x: chip.x, y: chip.y, width: chip.w, height: chip.h } : null

    onMounted(load)

    return {
      spec, loaded, busy, error, activeId, activeCase, inputs, docPage, attempts,
      feedback, feedbackTone, scale, showHelp, simulateOnly,
      experiments, experiment, dataReady, missing, cases, output, doc, currentDoc,
      progress, ring, allPassed, wires, points,
      load, selectExperiment, useCase, onPin, onControl, reset, verify, submit, page, zoom,
      pinValue, chipRect,
    }
  },
  template: `
  <section class="clab" aria-label="电路实验台">
    <aside class="clab-side">
      <div class="clab-side-title">实验目录</div>
      <button v-for="item in experiments" :key="item.id" type="button"
        :class="['clab-side-item', { active: item.id === activeId }]"
        :aria-pressed="item.id === activeId ? 'true' : 'false'"
        @click="selectExperiment(item.id)">
        <span class="clab-side-dot"></span>{{ item.title }}
      </button>
      <div class="clab-side-title">图例</div>
      <ul class="clab-legend">
        <li><i class="lg-sw"></i>输入开关（点击切换 0/1）</li>
        <li><i class="lg-lamp"></i>输出指示灯（红色为 1）</li>
        <li><i class="lg-wire"></i>信号导线</li>
        <li><i class="lg-gnd"></i>接地</li>
      </ul>
      <div class="clab-side-status" :class="dataReady ? 'ok' : 'warn'">
        <strong>{{ dataReady ? '后台数据正常' : '后台数据缺失' }}</strong>
        <span>{{ user.name }} · {{ user.role }}</span>
        <span>{{ progress.passed }}/{{ progress.total }} 用例通过</span>
      </div>
    </aside>

    <div class="clab-main">
      <header class="clab-head">
        <div>
          <p class="clab-eyebrow">计算机组成原理 · 在线实验</p>
          <h2>{{ experiment ? experiment.title : '电路实验台' }}</h2>
        </div>
        <div class="clab-tools" role="group" aria-label="电路控制工具栏">
          <button type="button" class="clab-tool" @click="reset">复位</button>
          <button type="button" class="clab-tool" @click="page(-1)">上一步</button>
          <button type="button" class="clab-tool" @click="page(1)">下一步</button>
          <button type="button" class="clab-tool" @click="zoom(-0.1)">缩小</button>
          <button type="button" class="clab-tool" @click="zoom(0.1)">放大</button>
          <button type="button" class="clab-tool" @click="showHelp = !showHelp">说明</button>
          <button type="button" class="clab-tool" :disabled="busy" @click="load">
            {{ busy ? '读取中…' : '重新加载' }}</button>
          <button type="button" class="clab-tool primary" @click="verify">验算</button>
          <button type="button" class="clab-tool primary" @click="submit">提交</button>
        </div>
      </header>

      <div v-if="error" class="clab-alert error" role="alert">
        读取电路定义失败：{{ error }}。后端未就绪时不会白屏，点击「重新加载」可恢复。
      </div>
      <div v-else-if="!dataReady" class="clab-alert warn" role="status">
        <strong>后台数据未初始化，以下数据缺失：</strong>
        <span>{{ missing.length ? missing.join(' / ') : '课程与实验业务数据' }}</span>
        <p>电路模拟、开关控制与验算不依赖后台数据，仍可正常使用；提交记录仅保存在本次会话。
          需要完整判分与统计时，请由教师创建课程/实验/测试集，或运行
          <code>python scripts/seed_teacher_course.py</code> 初始化课程。</p>
      </div>

      <div class="clab-grid" v-if="experiment">
        <section class="clab-doc">
          <div class="clab-progress">
            <svg class="clab-ring" viewBox="0 0 64 64" aria-hidden="true">
              <circle class="clab-ring-bg" cx="32" cy="32" r="26"></circle>
              <circle class="clab-ring-fg" cx="32" cy="32" r="26"
                :stroke-dasharray="ring.dash" :stroke-dashoffset="ring.offset"></circle>
            </svg>
            <div><strong>{{ ring.percent }}%</strong><span>{{ progress.passed }} / {{ progress.total }} 用例通过</span></div>
          </div>
          <h3>{{ currentDoc ? currentDoc.title : experiment.subtitle }}</h3>
          <p class="clab-doc-body">{{ currentDoc ? currentDoc.body : '' }}</p>
          <p class="clab-hint">{{ currentDoc ? currentDoc.hint : '' }}</p>
          <div class="clab-pager">
            <button type="button" @click="page(-1)" aria-label="上一页">‹</button>
            <span>{{ docPage + 1 }} / {{ doc.length || 1 }}</span>
            <button type="button" @click="page(1)" aria-label="下一页">›</button>
          </div>
          <div class="clab-doc-note" v-if="showHelp">
            <strong>操作说明</strong>
            <p>点击方形输入开关切换 0/1；红色圆形指示灯为高电平。S3–S0 与 M 由 7400 译码，
              为只读控制位；点击 Cn̄ 可在加法/减法之间切换。右侧面板可直接输入数值或载入用例。</p>
          </div>
        </section>

        <section class="clab-canvas" aria-label="电路图">
          <svg class="clab-svg" viewBox="0 0 760 600"
            :style="{ transform: 'scale(' + scale + ')' }" role="img"
            :aria-label="experiment.title + ' 电路图'">
            <polyline v-for="(wire, index) in wires" :key="'w' + index"
              :points="points(wire)" :class="['clab-wire', 'tone-' + wire.tone]"></polyline>
            <g v-if="experiment.ground" class="clab-ground"
              :transform="'translate(' + experiment.ground.x + ',' + experiment.ground.y + ')'">
              <line x1="0" y1="0" x2="0" y2="-10"></line>
              <line x1="-14" y1="0" x2="14" y2="0"></line>
              <line x1="-9" y1="5" x2="9" y2="5"></line>
              <line x1="-4" y1="10" x2="4" y2="10"></line>
            </g>
            <g v-if="experiment.chip" class="clab-chip">
              <rect :x="experiment.chip.x" :y="experiment.chip.y"
                :width="experiment.chip.w" :height="experiment.chip.h" rx="8"></rect>
              <text :x="experiment.chip.x + experiment.chip.w / 2"
                :y="experiment.chip.y + experiment.chip.h / 2 - 2" text-anchor="middle"
                class="clab-chip-name">{{ experiment.chip.label }}</text>
              <text :x="experiment.chip.x + experiment.chip.w / 2"
                :y="experiment.chip.y + experiment.chip.h / 2 + 20" text-anchor="middle"
                class="clab-chip-sub">{{ experiment.chip.sub }}</text>
            </g>
            <g v-if="experiment.chip2" class="clab-chip">
              <rect :x="experiment.chip2.x" :y="experiment.chip2.y"
                :width="experiment.chip2.w" :height="experiment.chip2.h" rx="8"></rect>
              <text :x="experiment.chip2.x + experiment.chip2.w / 2"
                :y="experiment.chip2.y + experiment.chip2.h / 2 - 2" text-anchor="middle"
                class="clab-chip-name">{{ experiment.chip2.label }}</text>
              <text :x="experiment.chip2.x + experiment.chip2.w / 2"
                :y="experiment.chip2.y + experiment.chip2.h / 2 + 20" text-anchor="middle"
                class="clab-chip-sub">{{ experiment.chip2.sub }}</text>
            </g>
            <g v-for="pin in experiment.pins" :key="pin.id">
              <g v-if="pin.kind === 'switch'" class="clab-switch" role="button" tabindex="0"
                :class="{ on: pinValue(pin) === 1, readonly: pin.group === 'control' && pin.id !== 'Cn' }"
                :aria-pressed="pinValue(pin) === 1 ? 'true' : 'false'"
                :aria-label="pin.label + ' 输入开关'"
                @click="onPin(pin)" @keydown.enter.prevent="onPin(pin)" @keydown.space.prevent="onPin(pin)">
                <rect :x="pin.x - 13" :y="pin.y - 13" width="26" height="26" rx="3"></rect>
                <circle :cx="pin.x" :cy="pin.y" r="6"></circle>
                <text :x="pin.x" :y="pin.side === 'top' ? pin.y - 22 : pin.y + 32"
                  text-anchor="middle" class="clab-pin-label">{{ pin.label }}</text>
              </g>
              <g v-else class="clab-lamp" :class="{ on: pinValue(pin) === 1 }"
                role="img" :aria-label="pin.label + ' 输出 ' + pinValue(pin)">
                <circle :cx="pin.x" :cy="pin.y" r="13"></circle>
                <circle :cx="pin.x" :cy="pin.y" r="5" class="clab-lamp-core"></circle>
                <text :x="pin.x" :y="pin.y + 32" text-anchor="middle"
                  class="clab-pin-label">{{ pin.label }}</text>
              </g>
            </g>
          </svg>
          <p class="clab-canvas-caption">点击引脚开关改变输入 · 导线绿色为导通 · 输出红色为高电平</p>
        </section>

        <section class="clab-panel">
          <h3>输入设置</h3>
          <table class="clab-table"><tbody>
            <tr v-for="row in experiment.control_rows" :key="row.key">
              <th>{{ row.label }}</th>
              <td>
                <input v-if="row.type === 'numeric'" type="number" min="0" max="15"
                  :aria-label="row.label" :value="inputs[row.key]"
                  @input="onControl(row, $event.target.value)">
                <select v-else-if="row.type === 'choice'" :aria-label="row.label"
                  :value="inputs[row.key]" @change="onControl(row, $event.target.value)">
                  <option v-for="option in row.options" :key="option" :value="option">{{ option }}</option>
                </select>
                <button v-else-if="row.type === 'toggle'" type="button" class="clab-mini-toggle"
                  :class="{ on: inputs[row.key] === 1 }" :aria-label="row.label"
                  @click="onControl(row, inputs[row.key] === 1 ? 0 : 1)">
                  {{ inputs[row.key] === 1 ? '1' : '0' }}</button>
                <span v-else class="clab-mono">{{ output.s3s2s1s0 }}</span>
              </td>
              <td class="clab-hint-cell">{{ row.hint || (inputs[row.key] ?? '—') }}</td>
            </tr>
          </tbody></table>

          <h3>验证用例</h3>
          <table class="clab-table clab-cases"><thead><tr><th>用例</th><th>期望</th><th>状态</th></tr></thead>
            <tbody><tr v-for="item in cases" :key="item.id"
              :class="{ picked: item.id === activeCase }" @click="useCase(item)">
              <td><button type="button" class="clab-link" @click.stop="useCase(item)">{{ item.name }}</button></td>
              <td class="clab-mono">{{ JSON.stringify(item.expected) }}</td>
              <td><span :class="['clab-badge',
                attempts.some(a => a.caseId === item.id && a.passed) ? 'pass' : 'idle']">
                {{ attempts.some(a => a.caseId === item.id && a.passed) ? '已通过' : '未提交' }}</span></td>
            </tr></tbody></table>

          <h3>输出读数</h3>
          <ul class="clab-outputs">
            <li v-for="out in experiment.outputs" :key="out.key">
              <span>{{ out.label }}</span>
              <b :class="{ hot: Number(output[out.key]) === 1 }">{{ output[out.key] }}</b>
            </li>
          </ul>
          <p class="clab-panel-note">{{ output.relation ? '比较结果：' + output.relation
            : '表达式：' + output.expression + ' = ' + output.decimal_result + '（F=' + output.f_hex + '）' }}</p>
        </section>
      </div>

      <p :class="['clab-feedback', 'tone-' + feedbackTone]" role="status" aria-live="polite">
        {{ feedback }}</p>

      <section class="clab-records">
        <h3>提交记录</h3>
        <table class="clab-table"><thead><tr>
          <th>时间</th><th>实验</th><th>用例</th><th>输入</th><th>结果</th><th>得分</th><th>状态</th>
        </tr></thead><tbody>
          <tr v-for="item in attempts" :key="item.no" :class="item.passed ? 'ok' : 'bad'">
            <td>{{ item.at }}</td><td>{{ item.experiment }}</td><td>{{ item.caseName }}</td>
            <td class="clab-mono">{{ item.inputs }}</td><td class="clab-mono">{{ item.actual }}</td>
            <td>{{ item.score }}</td>
            <td><span :class="['clab-badge', item.passed ? 'pass' : 'fail']">
              {{ item.passed ? '通过' : '未通过' }}</span></td>
          </tr>
          <tr v-if="!attempts.length"><td colspan="7" class="clab-empty">暂无提交记录，点击「提交」验证当前用例。</td></tr>
        </tbody></table>
      </section>
      <p v-if="allPassed" class="clab-passed" role="status">
        本实验已通过，可前往目录或自行做下一实验。</p>
    </div>
  </section>
  `,
}
