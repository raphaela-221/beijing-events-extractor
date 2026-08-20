import { getJson, postJson } from '../lib/api'

export interface LatestZip {
  name: string
  size_bytes: number
  created_at: string
}

export interface PublishState {
  preview_path: string
  external_url: string
  external_url_source: 'env' | 'self'
  share_path: string
  platform_upload_url: string
  canonical_ok: boolean
  latest_zip: LatestZip | null
}

export interface PublishRecord {
  publish_id: string
  created_at: string
  operator: string
  zip_path: string | null
  note: string | null
}

export interface ZipResult {
  zip_name: string
  size_bytes: number
  created_at: string
}

export const publishApi = {
  state: () => getJson<PublishState>('/api/publish/state'),
  setSharePath: (path: string) =>
    postJson<{ share_path: string }>('/api/publish/share-path', { path }),
  zip: () => postJson<ZipResult>('/api/publish/zip'),
  markDone: (body: { zip_name?: string; note?: string }) =>
    postJson<PublishRecord>('/api/publish/mark-done', body),
  history: () => getJson<PublishRecord[]>('/api/publish/history'),
  downloadUrl: (name: string) => `/api/publish/download/${encodeURIComponent(name)}`,
}
