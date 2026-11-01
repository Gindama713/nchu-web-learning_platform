// Display only: publication payloads, server windows and saved UTC facts stay unchanged.
const shanghai = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
})

export function paperTime(value, empty = '—') {
  if (value === null || value === undefined || value === '') return empty
  // Do not interpret missing zones in the browser's local timezone.
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|[+-]\d{2}:\d{2})$/.test(value)) return '时间异常'
  const date = new Date(value)
  const [year, month, day] = value.slice(0, 10).split('-').map(Number)
  if (!Number.isFinite(date.getTime()) || day < 1 || day > new Date(Date.UTC(year, month, 0)).getUTCDate()) return '时间异常'
  const parts = Object.fromEntries(shanghai.formatToParts(date).map(part => [part.type, part.value]))
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second} (Asia/Shanghai)`
}
