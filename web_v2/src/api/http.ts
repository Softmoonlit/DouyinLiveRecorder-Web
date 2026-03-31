export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

interface RequestOptions extends RequestInit {
  signal?: AbortSignal
}

export async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  })

  if (!response.ok) {
    let message = response.statusText || '请求失败'
    try {
      const payload = await response.json()
      message = payload.detail || payload.message || payload.error || message
    } catch {
      message = response.statusText || message
    }
    throw new ApiError(message, response.status)
  }

  return (await response.json()) as T
}
