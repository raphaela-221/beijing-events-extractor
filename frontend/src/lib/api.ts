// fetch 封装：带 cookie、401 抛 UnauthorizedError（由调用方/守卫处理）、统一错误提取。
export class UnauthorizedError extends Error {}

async function request(path: string, opts: RequestInit = {}): Promise<Response> {
  const res = await fetch(path, {
    credentials: 'include',
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(opts.headers || {}),
    },
  })
  if (res.status === 401) throw new UnauthorizedError('未登录')
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const j = await res.json()
      msg = j.detail || msg
    } catch {
      /* keep default */
    }
    throw new Error(msg)
  }
  return res
}

export async function getJson<T>(path: string): Promise<T> {
  return (await request(path)).json()
}

export async function postJson<T>(path: string, body?: unknown): Promise<T> {
  return (
    await request(path, {
      method: 'POST',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  ).json()
}

export async function postEmpty(path: string): Promise<void> {
  await request(path, { method: 'POST' })
}

export async function deleteJson<T>(path: string): Promise<T> {
  return (await request(path, { method: 'DELETE' })).json()
}

export async function patchJson<T>(path: string, body?: unknown): Promise<T> {
  return (
    await request(path, {
      method: 'PATCH',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  ).json()
}

// 文件上传：FormData 不设 Content-Type，让浏览器设 multipart boundary。
export async function postForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(path, {
    credentials: 'include',
    method: 'POST',
    body: form,
  })
  if (res.status === 401) throw new UnauthorizedError('未登录')
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const j = await res.json()
      msg = j.detail || msg
    } catch {
      /* keep default */
    }
    throw new Error(msg)
  }
  return res.json()
}
