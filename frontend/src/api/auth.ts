import { getJson, postJson, postEmpty, patchJson } from '../lib/api'
import type { User } from '../stores/useAuthStore'

export interface Account {
  username: string
  role: 'admin' | 'operator'
  display_name: string
}

export const authApi = {
  me: () => getJson<User>('/api/auth/me'),
  login: (username: string, password: string) =>
    postJson<User>('/api/auth/login', { username, password }),
  logout: () => postEmpty('/api/auth/logout'),
  changePassword: (old_password: string, new_password: string) =>
    postJson<{ ok: boolean }>('/api/auth/change-password', { old_password, new_password }),
  listUsers: () => getJson<{ items: Account[] }>('/api/auth/users'),
  createUser: (body: {
    username: string
    password: string
    display_name?: string
    role?: string
  }) => postJson<{ ok: boolean }>('/api/auth/users', body),
  updateUser: (
    username: string,
    body: { role?: string; password?: string; display_name?: string }
  ) => patchJson<{ ok: boolean }>(`/api/auth/users/${encodeURIComponent(username)}`, body),
}
