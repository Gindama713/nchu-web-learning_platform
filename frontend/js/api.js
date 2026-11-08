// 接口失败时把状态码和后端错误码一起带出来：调用方要靠 code 分辨
// 「CSRF 过期」这种可以自动重试的情况，光有 message 只能靠匹配文案，太脆。
function failure(content, status) {
  const error = new Error(content.error?.message ?? `HTTP ${status}`)
  error.status = status
  error.code = content.error?.code
  return error
}

export async function readApi(path, fetcher = fetch) {
  const response = await fetcher(path)
  const body = await response.json()
  if (!response.ok) throw failure(body, response.status)
  return body.data
}

export async function apiRequest(path, method, payload, csrfToken, extraHeaders = {}) {
  const form = payload instanceof FormData
  const response = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: {
      ...(!form && payload !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
      ...extraHeaders,
    },
    body: payload === undefined ? undefined : form ? payload : JSON.stringify(payload),
  })
  if (response.status === 204) return null
  const content = await response.json()
  if (!response.ok) throw failure(content, response.status)
  return content.data
}
