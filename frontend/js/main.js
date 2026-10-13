import { createApp, h, onMounted, ref } from 'vue'
import { readApi } from './api.js'
import { KnowledgeView } from './knowledge-view.js'
import '../styles/main.css'
import '../styles/knowledge.css'

createApp({
  setup() {
    const modules = ref([])
    const message = ref('正在连接 API…')
    const active = ref('knowledge')

    onMounted(async () => {
      try {
        modules.value = await readApi('/api/v1/modules')
        message.value = '项目骨架已启动。业务模块按 SPEC 逐项实现。'
      } catch (error) {
        message.value = `API 连接失败：${error.message}`
      }
    })

    return () => h('main', { class: 'page' }, [
      h('header', { class: 'hero' }, [
        h('p', { class: 'eyebrow' }, 'g24201710 · 计算机组成原理'),
        h('h1', '中央处理器课程学习系统'),
        h('p', { role: 'status' }, message.value),
      ]),
      h('nav', { class: 'module-nav', 'aria-label': '模块导航' }, [
        h('button', { type: 'button', 'aria-pressed': active.value === 'knowledge', onClick: () => { active.value = 'knowledge' } }, '课程知识'),
        h('button', { type: 'button', 'aria-pressed': active.value === 'catalog', onClick: () => { active.value = 'catalog' } }, '模块目录'),
      ]),
      active.value === 'knowledge' ? h(KnowledgeView) : h('section', { 'aria-labelledby': 'modules-title' }, [
        h('h2', { id: 'modules-title' }, '模块规划'),
        h('div', { class: 'grid' }, modules.value.map((module) => h('article', { class: 'card', key: module.spec }, [
          h('span', { class: 'tag' }, module.group),
          h('h3', module.name),
          h('p', module.spec),
          h('small', module.spec === 'SPEC-005' ? '模块实现待公共能力接入' : '待实现'),
        ]))),
      ]),
    ])
  },
}).mount('#app')
