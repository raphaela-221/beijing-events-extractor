import { getJson, postJson } from '../lib/api'

export interface CanonicalEvent {
  no: string
  topic: string
  headline: string
  start_date: string
  end_date: string
  priority: string
  keywords: string
  dates: string
}

export interface PreviewResult {
  items: CanonicalEvent[]
  total: number
  page: number
  page_size: number
}

export interface DiffItem {
  type: 'add' | 'del' | 'mod'
  no: string
  headline: string
  field: string
  change: string
}

export interface DiffSummary {
  added: number
  deleted: number
  modified: number
  items: DiffItem[]
}

export interface InterveningRun {
  run_id: string
  op_id: string
  op_label: string
  started_at: string
  ended_at: string | null
  status: string
  operator: string
}

export interface UploadResult {
  upload_ok: boolean
  verified: boolean
  hash_match: boolean
  current_hash: string
  downloaded_hash: string | null
  downloaded_at: string | null
  intervening_runs: InterveningRun[]
  diff: DiffSummary
}

export interface DownloadResult {
  blob: Blob
  hash: string
  download_id: string
}

export interface CanonicalRow {
  row: number
  exists: boolean
  no: string
  topic: string
  headline: string
  start_date: string
  end_date: string
  dates: string
  desc: string
}

export interface VerifyResult {
  code: number // 0=完好 1=损坏 2=不存在
  detail: string
}

export const canonicalApi = {
  preview(params: { page: number; page_size: number; search?: string; priority?: string }) {
    const sp = new URLSearchParams({ page: String(params.page), page_size: String(params.page_size) })
    if (params.search) sp.set('search', params.search)
    if (params.priority) sp.set('priority', params.priority)
    return getJson<PreviewResult>(`/api/canonical/preview?${sp}`)
  },

  // 下载文件 + 读响应头（X-Canonical-Hash / X-Download-Id）。fetch 同源可读自定义头。
  async download(): Promise<DownloadResult> {
    const r = await fetch('/api/canonical/download', { credentials: 'include' })
    if (r.status === 401) throw new Error('未登录')
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const blob = await r.blob()
    return {
      blob,
      hash: r.headers.get('X-Canonical-Hash') || '',
      download_id: r.headers.get('X-Download-Id') || '',
    }
  },

  upload(upload_id: string, download_id: string | null) {
    return postJson<UploadResult>('/api/canonical/upload', { upload_id, download_id })
  },

  commit(upload_id: string) {
    return postJson<{ committed: boolean; backup_path: string; verified: boolean }>(
      '/api/canonical/commit',
      { upload_id },
    )
  },

  // 按行号读单行（dates_add_row 的 row_ref 回显用）
  getRow(row: number) {
    return getJson<CanonicalRow>(`/api/canonical/row?row=${row}`)
  },

  // 跑 verify_canonical.py（write 后结构确认 / 设置页 canonical 状态用）
  verify() {
    return getJson<VerifyResult>('/api/canonical/verify')
  },
}
