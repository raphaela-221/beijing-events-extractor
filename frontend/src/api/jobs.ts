import { getJson, postJson } from '../lib/api'

export interface Param {
  name: string
  type: 'bool' | 'string' | 'text' | 'int' | 'date' | 'month' | 'enum' | 'files' | 'row_ref'
  label: string
  help: string
  default: unknown
  choices: string[] | null
  required: boolean
  advanced: boolean
}

export interface JobSchema {
  id: string
  group: string
  label: string
  desc: string
  danger: 'none' | 'write_canonical' | 'destructive'
  needs_lock: boolean
  stages: string[]
  params: Param[]
  artifacts: string[]
  preflight: string[]
  dry_run_pair: string | null
  admin_only: boolean
}

export interface LastRun {
  run_id: string
  started_at: string
  status: string
}

export const jobsApi = {
  list: () => getJson<JobSchema[]>('/api/jobs'),
  get: (id: string) => getJson<JobSchema>(`/api/jobs/${id}`),
  run: (id: string, params: Record<string, unknown>, preset?: string) =>
    postJson<{ run_id: string }>(`/api/jobs/${id}/run`, { params, preset }),
  lastRuns: () => getJson<Record<string, LastRun>>('/api/jobs/last-runs'),
}
