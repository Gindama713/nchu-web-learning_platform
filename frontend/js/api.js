export async function readApi(path, fetcher = fetch) {
  const response = await fetcher(path)
  const body = await response.json()
  if (!response.ok) throw new Error(body.error?.message ?? `HTTP ${response.status}`)
  return body.data
}
