import { create } from 'zustand'
import { getJson, postJson } from '../lib/api'

export interface LockState {
  held: boolean
  holder?: string
  since?: string
  is_me?: boolean
  refresh: () => Promise<void>
  acquire: () => Promise<LockState>
  release: () => Promise<void>
}

export const useLockStore = create<LockState>((set) => ({
  held: false,
  refresh: async () => {
    try {
      const s = await getJson<LockState>('/api/lock')
      set(s)
    } catch {
      /* ignore */
    }
  },
  acquire: async () => {
    const s = await postJson<LockState>('/api/lock/acquire')
    set(s)
    return s
  },
  release: async () => {
    await postJson('/api/lock/release')
    try {
      const s = await getJson<LockState>('/api/lock')
      set(s)
    } catch {
      /* ignore */
    }
  },
}))
