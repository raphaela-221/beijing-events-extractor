// 全站用时 / 容量 / 日期格式化唯一出口（指南附录 A）。禁止在页面里另写一套。
export function fmtDuration(ms: number | null | undefined): string {
  if (!ms || ms <= 0) return '-'
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}秒`
  const m = Math.floor(s / 60)
  const rs = s % 60
  if (m < 60) return `${m}分${rs.toString().padStart(2, '0')}秒`
  const h = Math.floor(m / 60)
  return `${h}时${m % 60}分`
}

export function fmtBytes(n: number | null | undefined): string {
  if (!n || n <= 0) return '0 B'
  const u = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let v = n
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024
    i++
  }
  return `${v >= 10 || i === 0 ? Math.round(v) : v.toFixed(1)} ${u[i]}`
}

// ISO -> '8月7日 20:11' / '2026-08-07 20:11'。全站统一这两种之一。
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const mm = (d.getMonth() + 1).toString()
  const dd = d.getDate().toString()
  const hh = d.getHours().toString().padStart(2, '0')
  const mi = d.getMinutes().toString().padStart(2, '0')
  return `${mm}月${dd}日 ${hh}:${mi}`
}

export function fmtClock(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return `${d.getHours().toString().padStart(2, '0')}:${d
    .getMinutes()
    .toString()
    .padStart(2, '0')}`
}
