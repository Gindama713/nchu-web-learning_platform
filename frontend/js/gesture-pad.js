// 3×3 手势画布：按住划过若干点，松手后把点的序列抛给父组件。
// 用 SVG + Pointer Events 实现，鼠标和触屏同一套代码；touch-action 交给 CSS，
// 否则手指滑动会被浏览器当成滚动，画到一半就断了。
import { computed, ref } from 'vue'

const DOTS = Array.from({ length: 9 }, (_, index) => ({
  index,
  x: 60 + (index % 3) * 90,
  y: 60 + Math.floor(index / 3) * 90,
}))
const HIT_RADIUS = 34

export const GesturePad = {
  name: 'GesturePad',
  props: {
    disabled: { type: Boolean, default: false },
    label: { type: String, default: '手势图案' },
  },
  emits: ['done'],
  setup(props, { emit }) {
    const picked = ref([])
    const drawing = ref(false)

    const points = computed(() => picked.value.map(index => `${DOTS[index].x},${DOTS[index].y}`).join(' '))
    const isPicked = index => picked.value.includes(index)

    function locate(event) {
      const rect = event.currentTarget.getBoundingClientRect()
      return {
        x: ((event.clientX - rect.left) * 300) / (rect.width || 1),
        y: ((event.clientY - rect.top) * 300) / (rect.height || 1),
      }
    }
    function hitTest(point) {
      let best = -1
      let bestDistance = HIT_RADIUS
      DOTS.forEach(dot => {
        const distance = Math.hypot(dot.x - point.x, dot.y - point.y)
        if (distance <= bestDistance) {
          best = dot.index
          bestDistance = distance
        }
      })
      return best
    }
    function reset() {
      picked.value = []
      drawing.value = false
    }
    function start(event) {
      if (props.disabled) return
      drawing.value = true
      const index = hitTest(locate(event))
      picked.value = index >= 0 ? [index] : []
      event.currentTarget.setPointerCapture?.(event.pointerId)
    }
    function move(event) {
      if (!drawing.value || props.disabled) return
      const index = hitTest(locate(event))
      if (index >= 0 && !picked.value.includes(index)) picked.value = [...picked.value, index]
    }
    function finish() {
      if (!drawing.value) return
      drawing.value = false
      const pattern = picked.value.slice()
      if (pattern.length) emit('done', pattern)
    }

    return { dots: DOTS, picked, points, isPicked, start, move, finish, reset }
  },
  template: `
    <div class="gesture-pad" :class="{ active: picked.length, disabled }">
      <svg viewBox="0 0 300 300" role="application" :aria-label="label"
        @pointerdown.prevent="start" @pointermove.prevent="move"
        @pointerup.prevent="finish" @pointercancel="finish" @pointerleave="finish">
        <polyline v-if="points" :points="points" fill="none" stroke="#2f6fd0" stroke-width="7"
          stroke-linecap="round" stroke-linejoin="round" opacity=".8" />
        <circle v-for="dot in dots" :key="dot.index" :cx="dot.x" :cy="dot.y"
          :r="isPicked(dot.index) ? 17 : 12"
          :fill="isPicked(dot.index) ? '#2f6fd0' : '#fff'"
          stroke="#2f6fd0" stroke-width="3" />
      </svg>
    </div>`,
}
