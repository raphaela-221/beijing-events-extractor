import { getJson } from '../lib/api'

export type CheckStatus = 'ok' | 'warn' | 'block'

export interface HealthCheck {
  id: string
  status: CheckStatus
  detail: string
  block: boolean
}

export interface NextAction {
  id: string
  title: string
  desc: string
  link: string
  severity: string
}

export interface PipelineStats {
  total_events?: number
  high_priority?: number
  covered_months?: number
  last_modified?: string
}

export interface PipelineState {
  checks: HealthCheck[]
  next_action: NextAction | null
  stats: PipelineStats
}

export const pipelineApi = {
  state: () => getJson<PipelineState>('/api/pipeline/state'),
}
