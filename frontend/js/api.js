export async function readApi(path, fetcher = fetch) {
  const response = await fetcher(path)
  const body = await response.json()
  if (!response.ok) throw new Error(body.error?.message ?? `HTTP ${response.status}`)
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
  if (!response.ok) throw new Error(content.error?.message ?? `HTTP ${response.status}`)
  return content.data
}
