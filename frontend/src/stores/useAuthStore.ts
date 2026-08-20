import { create } from 'zustand'
import { getJson, postJson } from '../lib/api'

export interface User {
  username: string
  role: 'admin' | 'operator'
  display_name: string
}

interface AuthState {
  user: User | null
  loading: boolean // 首次 /me 加载中
  fetchMe: () => Promise<void>
  login: (u: string, p: string) => Promise<void>
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: true,
  fetchMe: async () => {
    try {
      const u = await getJson<User>('/api/auth/me')
      set({ user: u, loading: false })
    } catch {
      set({ user: null, loading: false })
    }
  },
  login: async (u, p) => {
    const me = await postJson<User>('/api/auth/login', {
      username: u,
      password: p,
    })
    set({ user: me })
  },
  logout: async () => {
    try {
      await postJson('/api/auth/logout')
    } finally {
      set({ user: null })
    }
  },
}))
