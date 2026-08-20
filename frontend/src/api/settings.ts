import { getJson, postJson } from '../lib/api'

export type CheckStatus = 'ok' | 'warn' | 'block'

export interface HealthCheck {
  id: string
  status: CheckStatus
  detail: string
  block: boolean
}

export interface DataStats {
  runs_count: number
  trash_count: number
  bak_count: number
  data_size: number
  db_size: number
  free_space: number
}

export interface LastSelfcheck {
  at: string
  ok: boolean
  block_count: number
  warn_count: number
}

export interface LastCleanup {
  at: string
  purged_runs: number
  deleted_baks: number
  orphans: number
  freed_bytes: number
  retention_days: number
  bak_keep: number
}

export interface SelfcheckResult extends LastSelfcheck {
  checks: HealthCheck[]
  data_stats: DataStats
}

export interface Settings {
  retention_days: number
  canonical_bak_keep: number
  last_selfcheck: LastSelfcheck | null
  last_cleanup: LastCleanup | null
  keys: { deepseek: boolean; ark: boolean }
  data_stats: DataStats
}

export interface KeyProvider {
  configured: boolean
  masked: string
  base_url: string
  model: string
}

export interface QwenStatus {
  enabled: boolean
  script_ok: boolean
  endpoint_ok: boolean
  reason: string
}

export interface KeysConfig {
  deepseek: KeyProvider
  ark: KeyProvider
  qwen: QwenStatus
}

export const settingsApi = {
  get: () => getJson<Settings>('/api/settings'),
  update: (body: { retention_days?: number; canonical_bak_keep?: number }) =>
    postJson<{ retention_days: number; canonical_bak_keep: number }>('/api/settings', body),
  selfcheck: () => postJson<SelfcheckResult>('/api/settings/selfcheck'),
  cleanup: () => postJson<LastCleanup>('/api/settings/cleanup'),
  getKeys: () => getJson<KeysConfig>('/api/settings/keys'),
  updateKeys: (body: {
    deepseek?: { key?: string; base_url?: string; model?: string }
    ark?: { key?: string; base_url?: string; model?: string }
  }) => postJson<{ ok: boolean }>('/api/settings/keys', body),
}
