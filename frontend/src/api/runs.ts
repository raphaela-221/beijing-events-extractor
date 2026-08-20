import { deleteJson, getJson, postJson } from '../lib/api'

export type RunStatus = 'queued' | 'running' | 'success' | 'failed' | 'cancelled'

export interface LogLine {
  seq: number
  ts: string
  level: 'info' | 'warn' | 'error' | 'success'
  text: string
}

export interface Run {
  run_id: string
  op_id: string
  op_label: string
  op_group: string
  preset: string | null
  params_json: string
  status: RunStatus
  current_stage: string | null
  stage_index: number | null
  started_at: string
  ended_at: string | null
  duration_ms: number | null
  exit_code: number | null
  operator: string
  log_path: string
  log_lines: number
  log_bytes: number
  summary_json: string | null
  llm_json: string | null
  error_summary: string | null
  error_kind: string | null
  canonical_backup_path: string | null
  artifacts_json: string | null
  pinned: number
  deleted_at: string | null
}

export interface TrashRun extends Run {
  days_left: number
}

export interface LogPage {
  lines: LogLine[]
  total: number
  last_seq: number
  has_more: boolean
}

export interface RunPage {
  items: Run[]
  total: number
  page: number
  page_size: number
}

export interface ListRunsParams {
  op_id?: string[]
  status?: string[]
  operator?: string
  started_from?: string
  started_to?: string
  pinned?: boolean
  sort?: string
  page?: number
  page_size?: number
}

export interface PurgeFilters {
  op_id?: string[]
  status?: string[]
  operator?: string
  started_from?: string
  started_to?: string
  keep_pinned?: boolean
}

export interface PurgeProtectedReason {
  run_id: string
  op_label: string
  reason: string
}

export interface PurgeSample {
  run_id: string
  op_label: string
  started_at: string
  status: RunStatus
}

export interface PurgePreview {
  count: number
  freed_bytes: number
  protected_count: number
  pinned_count: number
  last_success_count: number
  protected_reasons: PurgeProtectedReason[]
  sample: PurgeSample[]
}

export interface BulkDeleteResult {
  deleted_count: number
  freed_bytes: number
  protected_count: number
  deleted: { run_id: string; op_label: string }[]
}

export interface CompareResult {
  has_previous: boolean
  previous_run_id?: string
  previous_started_at?: string
  duration_ms_delta?: number
  events_delta?: number
  tokens_delta?: number
  current?: { events: number; tokens: number }
  previous?: { events: number; tokens: number }
}

export interface Deletion {
  id: number
  run_id: string
  op_label: string
  run_started_at: string | null
  deleted_at: string
  deleted_by: string
  mode: string
  reason: string | null
  artifacts_deleted: number
  freed_bytes: number | null
}

export const runsApi = {
  get: (id: string) => getJson<Run>(`/api/runs/${id}`),
  log: (id: string, from_seq = 0, limit = 2000) =>
    getJson<LogPage>(`/api/runs/${id}/log?from_seq=${from_seq}&limit=${limit}`),
  cancel: (id: string) => postJson<{ ok: boolean }>(`/api/runs/${id}/cancel`),
  logDownloadUrl: (id: string) => `/api/runs/${id}/log/download`,
  streamUrl: (id: string, from_seq = 0) =>
    `/api/runs/${id}/stream?from_seq=${from_seq}`,
  listRuns: (params: ListRunsParams = {}) => {
    const q = new URLSearchParams()
    ;(params.op_id || []).forEach((v) => q.append('op_id', v))
    ;(params.status || []).forEach((v) => q.append('status', v))
    if (params.operator) q.set('operator', params.operator)
    if (params.started_from) q.set('started_from', params.started_from)
    if (params.started_to) q.set('started_to', params.started_to)
    if (params.pinned !== undefined) q.set('pinned', String(params.pinned))
    if (params.sort) q.set('sort', params.sort)
    if (params.page) q.set('page', String(params.page))
    if (params.page_size) q.set('page_size', String(params.page_size))
    return getJson<RunPage>(`/api/runs?${q.toString()}`)
  },
  // P2-A 管理
  pin: (id: string, pinned: boolean) =>
    postJson<{ run_id: string; pinned: boolean }>(`/api/runs/${id}/pin`, { pinned }),
  remove: (id: string, mode: 'trash' | 'purge', delete_artifacts = false) =>
    deleteJson<{ run_id: string; mode: string; freed_bytes?: number }>(
      `/api/runs/${id}?mode=${mode}&delete_artifacts=${delete_artifacts}`,
    ),
  restore: (id: string) =>
    postJson<{ run_id: string; restored: boolean }>(`/api/runs/${id}/restore`),
  trash: () => getJson<{ items: TrashRun[] }>(`/api/runs/trash`),
  purgePreview: (filters: PurgeFilters) =>
    postJson<PurgePreview>(`/api/runs/purge-preview`, filters),
  bulkDelete: (filters: PurgeFilters, mode: 'trash' | 'purge', delete_artifacts = false) =>
    postJson<BulkDeleteResult>(`/api/runs/bulk-delete`, { filters, mode, delete_artifacts }),
  compare: (id: string) => getJson<CompareResult>(`/api/runs/${id}/compare`),
  exportUrl: (params: ListRunsParams = {}) => {
    const q = new URLSearchParams()
    ;(params.op_id || []).forEach((v) => q.append('op_id', v))
    ;(params.status || []).forEach((v) => q.append('status', v))
    if (params.operator) q.set('operator', params.operator)
    if (params.started_from) q.set('started_from', params.started_from)
    if (params.started_to) q.set('started_to', params.started_to)
    if (params.pinned !== undefined) q.set('pinned', String(params.pinned))
    if (params.sort) q.set('sort', params.sort)
    return `/api/runs/export.xlsx?${q.toString()}`
  },
  deletions: () => getJson<{ items: Deletion[] }>(`/api/runs/deletions`),
}
