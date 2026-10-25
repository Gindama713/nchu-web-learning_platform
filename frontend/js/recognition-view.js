// SPEC-016 实验图辅助识别：原图预览 + 检测框叠加 + 逐项人工确认。
// 识别只是模板匹配的辅助，确认前不产生任何结构或成绩事实。
import { h, onBeforeUnmount, onMounted, ref } from 'vue'
import { RecognitionClient, gateSymbols, pinLabels } from './recognition-client.js'

const BAND = {
  high: { text: '高置信', color: '#2e7d4f', dash: null },
  low: { text: '低置信', color: '#d18700', dash: '6 4' },
  none: { text: '待定', color: '#8c2b20', dash: '4 4' },
}

const bandOf = item => {
  if (!item) return BAND.none
  if (item.confidence_band === 'high') return BAND.high
  if (item.confidence_band === 'low') return BAND.low
  return BAND.none
}

function readSize(url) {
  return new Promise(resolve => {
    const image = new globalThis.Image()
    image.onload = () => resolve({ width: image.naturalWidth, height: image.naturalHeight })
    image.onerror = () => resolve({ width: 0, height: 0 })
    image.src = url
  })
}

export const RecognitionView = {
  props: { user: { type: Object, required: true } },
  setup(props) {
    const api = new RecognitionClient(props.user.id)
    const courses = ref([])
    const courseId = ref('')
    const preview = ref('')
    const size = ref({ width: 0, height: 0 })
    const result = ref(null)
    const draft = ref([])
    const busy = ref(false)
    const error = ref('')
    const notice = ref('')
    const dragging = ref(false)
    const picker = ref(null)

    function releasePreview() {
      if (preview.value) globalThis.URL.revokeObjectURL(preview.value)
      preview.value = ''
      size.value = { width: 0, height: 0 }
    }

    async function run(action, success = '') {
      if (busy.value) return
      busy.value = true; error.value = ''; notice.value = ''
      try { await action(); notice.value = success } catch (failure) {
        error.value = failure.message
        if (failure.status === 401) courses.value = []
      } finally { busy.value = false }
    }

    async function handleFile(file) {
      if (!file) return
      if (!/^image\/(png|jpeg)$/.test(file.type)) throw new Error('只接受 PNG 或 JPEG 图片。')
      if (file.size > 5 * 1024 * 1024) throw new Error('图片不能超过 5 MB。')
      releasePreview()
      preview.value = globalThis.URL.createObjectURL(file)
      size.value = await readSize(preview.value)
      const created = await api.create(courseId.value, file)
      result.value = created
      draft.value = (created.items ?? []).map(item => ({ ...item }))
      if (created.status === 'unrecognized') notice.value = '没有匹配到支持的门符号，可以换一张或改用实验中的手工建模入口。'
    }

    function pick(event) {
      const file = event.target.files?.[0]
      event.target.value = ''
      run(() => handleFile(file))
    }

    function drop(event) {
      dragging.value = false
      const file = event.dataTransfer?.files?.[0]
      run(() => handleFile(file))
    }

    function remove(index) {
      draft.value.splice(index, 1)
    }

    function setLabel(index, value) {
      draft.value[index] = { ...draft.value[index], label: value || null }
    }

    function setSymbol(index, value) {
      draft.value[index] = { ...draft.value[index], symbol: value }
    }

    const unresolved = () => draft.value.filter(item => !item.label).length

    async function confirm() {
      if (!result.value) return
      const missing = unresolved()
      if (missing) throw new Error(`还有 ${missing} 项没有补齐标签，补全或删除后才能确认。`)
      const done = await api.confirm(result.value.id, draft.value)
      result.value = { ...result.value, ...done }
      draft.value = (done.confirmed_items ?? []).map(item => ({ ...item }))
    }

    async function reset() {
      releasePreview()
      result.value = null
      draft.value = []
      notice.value = ''
      error.value = ''
    }

    async function boot() {
      courses.value = []
      await api.verifySession()
      courses.value = await api.courses()
      if (!courses.value.some(item => String(item.id) === courseId.value)) {
        courseId.value = courses.value.length ? String(courses.value[0].id) : ''
      }
    }

    onMounted(() => { boot().catch(failure => { error.value = failure.message }) })
    onBeforeUnmount(releasePreview)

    function overlay() {
      if (!preview.value || !size.value.width) return null
      const boxes = draft.value.map((item, index) => {
        const [x, y, width, height] = item.bbox
        const band = bandOf(item)
        return h('g', {}, [
          h('rect', {
            x, y, width, height, fill: `${band.color}14`, stroke: band.color,
            'stroke-width': 2, 'stroke-dasharray': band.dash ?? undefined,
            'vector-effect': 'non-scaling-stroke',
          }),
          h('text', {
            x: x + 2, y: Math.max(12, y - 6), 'font-size': 13, fill: band.color,
            'font-weight': 700, 'paint-order': 'stroke', stroke: '#ffffff', 'stroke-width': 3,
          }, `${index + 1} ${item.symbol}`),
        ])
      })
      return h('div', { class: 'recog-stage' }, [
        h('img', { src: preview.value, alt: '待识别的电路图', class: 'recog-image' }),
        h('svg', {
          class: 'recog-overlay',
          viewBox: `0 0 ${size.value.width} ${size.value.height}`,
          preserveAspectRatio: 'xMidYMid meet',
        }, boxes),
      ])
    }

    function itemRow(item, index) {
      const band = bandOf(item)
      const confirmed = result.value?.status === 'confirmed'
      return h('li', { key: `${index}-${item.bbox.join('-')}`, class: 'recog-item' }, [
        h('span', { class: 'recog-index', style: `background:${band.color}` }, String(index + 1)),
        h('div', { class: 'recog-symbol' }, [
          confirmed
            ? h('strong', {}, item.symbol)
            : h('select', {
              value: item.symbol, 'aria-label': `第 ${index + 1} 项符号`,
              onChange: event => setSymbol(index, event.target.value),
            }, gateSymbols.map(code => h('option', { value: code }, code))),
          h('small', {}, `坐标 ${item.bbox.join(', ')}`),
        ]),
        h('div', { class: 'recog-confidence' }, [
          h('div', { class: 'recog-bar' }, [
            h('i', { style: `width:${Math.round((item.confidence ?? 0) * 100)}%;background:${band.color}` }),
          ]),
          h('small', {}, `${band.text} · 相似度 ${((item.confidence ?? 0) * 100).toFixed(1)}%`),
        ]),
        h('label', { class: 'recog-label' }, ['引脚标签',
          confirmed
            ? h('strong', {}, item.label ?? '无')
            : h('select', {
              value: item.label ?? '', 'aria-label': `第 ${index + 1} 项标签`,
              onChange: event => setLabel(index, event.target.value),
            }, [h('option', { value: '' }, '未定'), ...pinLabels.map(label => h('option', { value: label }, label))]),
        ]),
        !confirmed && h('button', {
          type: 'button', class: 'secondary recog-remove', 'aria-label': `删除第 ${index + 1} 项`,
          onClick: () => remove(index),
        }, '删除'),
      ])
    }

    return () => {
      const confirmed = result.value?.status === 'confirmed'
      return h('section', { class: 'card recog-card' }, [
        h('h2', {}, '实验图辅助识别'),
        h('p', {}, '只识别白底黑色的正向标准门符号（NOT / AND / OR / XOR）与固定字典标签；'
          + '不识别连线拓扑、旋转手绘、卡诺图、任意字体或完整 CPU。相似度是模板 IoU，不是正确概率。'
          + '确认只保存结构草稿，不自动判分、不写成绩。'),

        h('div', { class: 'inline-form' }, [
          h('label', {}, ['课程', h('select', {
            value: courseId.value,
            onChange: event => { courseId.value = event.target.value; run(reset) },
          }, courses.value.map(course => h('option', { value: String(course.id) }, course.title ?? `课程 ${course.id}`)))]),
        ]),

        h('div', {
          class: ['recog-dropzone', dragging.value && 'dragging', !courseId.value && 'disabled'],
          onDragOver: event => { event.preventDefault(); dragging.value = true },
          onDragLeave: () => { dragging.value = false },
          onDrop: event => { event.preventDefault(); if (courseId.value) drop(event) },
          onClick: () => courseId.value && picker.value?.click(),
        }, [
          h('input', {
            ref: picker, type: 'file', accept: 'image/png,image/jpeg',
            style: 'display:none', onChange: pick,
          }),
          h('strong', {}, busy.value ? '正在识别…' : '把电路图拖进来，或点击选择文件'),
          h('small', {}, 'PNG / JPEG，最大 5 MB；正向上传的黑白门符号图效果最好'),
        ]),

        error.value && h('p', { class: 'recog-alert', role: 'alert' }, error.value),
        notice.value && h('p', { class: 'recog-notice', role: 'status' }, notice.value),

        overlay(),

        result.value && h('div', { class: 'recog-result' }, [
          h('div', { class: 'recog-summary' }, [
            h('span', { class: `recog-badge ${confirmed ? 'ok' : result.value.status}` },
              confirmed ? '已确认' : result.value.status === 'recognized' ? '待确认' : '未识别'),
            h('span', {}, `共 ${draft.value.length} 项`),
            h('span', {}, unresolved() ? `待补标签 ${unresolved()} 项` : '标签齐全'),
            h('span', { class: 'recog-sha' }, `模板集 ${String(result.value.template_set_sha256 ?? '').slice(0, 12)}…`),
          ]),
          draft.value.length
            ? h('ul', { class: 'recog-list' }, draft.value.map(itemRow))
            : h('p', { class: 'recog-empty' }, result.value.status === 'unrecognized'
              ? '这张图没有匹配到支持的门符号。建议用黑底白线或白底黑线的正向门符号图。'
              : '识别结果已被全部删除。'),
          h('div', { class: 'recog-actions' }, [
            !confirmed && h('button', {
              type: 'button', disabled: busy.value, onClick: () => run(confirm),
            }, busy.value ? '提交中…' : draft.value.length ? '人工确认草稿' : '确认删除全部（空草稿）'),
            !confirmed && h('button', {
              type: 'button', class: 'secondary', disabled: busy.value, onClick: () => run(reset),
            }, '重来'),
            confirmed && h('button', { type: 'button', class: 'secondary', onClick: () => run(reset) }, '识别下一张'),
          ]),
        ]),
      ])
    }
  },
}
