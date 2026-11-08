import { defineConfig } from 'vite'

// 后端地址：开发时 Flask 跑在本机 5000；被占用时可用 VITE_API 覆盖（如 5001）
const API = globalThis.process?.env?.VITE_API ?? 'http://127.0.0.1:5000'
// changeOrigin 必须保持 false：后端按 Origin 与 Host 是否同源做 CSRF 校验，
// 代理一旦改写 Host，用局域网 IP 访问时 Origin 就对不上，写请求会 403 CSRF_FAILED。
// SPEC-019：/help、/who 挂在 Flask 根路径，开发服务器需一并转发。
const proxy = {
  '/api': { target: API, changeOrigin: false },
  '/help': { target: API, changeOrigin: false },
  '/who': { target: API, changeOrigin: false },
}

export default defineConfig({
  resolve: { alias: { vue: 'vue/dist/vue.esm-bundler.js' } },
  server: { proxy },
  preview: { proxy },
})
