let refreshRequest: Promise<boolean> | null = null
type ApiRequestInit = RequestInit & { skipAutoRefresh?: boolean }

function shouldAutoRefresh(url: string) {
  return !url.includes("/api/v1/auth/login") &&
    !url.includes("/api/v1/auth/register") &&
    !url.includes("/api/v1/auth/refresh")
}

export async function tryRefreshSession() {
  if (!refreshRequest) {
    refreshRequest = fetch("/api/v1/auth/refresh", {
      method: "POST",
      credentials: "include",
    })
      .then((response) => response.ok)
      .catch(() => false)
      .finally(() => {
        refreshRequest = null
      })
  }

  return refreshRequest
}

export async function apiFetch(input: string, init: ApiRequestInit = {}) {
  const { skipAutoRefresh = false, ...requestInit } = init
  const headers = new Headers(requestInit.headers)
  const hasBody = requestInit.body !== undefined && requestInit.body !== null

  if (hasBody && !(requestInit.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }

  const response = await fetch(input, {
    ...requestInit,
    headers,
    credentials: "include",
  })

  if (response.status === 401 && !skipAutoRefresh && shouldAutoRefresh(input)) {
    const refreshed = await tryRefreshSession()
    if (refreshed) {
      return fetch(input, {
        ...requestInit,
        headers,
        credentials: "include",
      })
    }
  }

  return response
}

export async function apiJson<T>(input: string, init: ApiRequestInit = {}) {
  const response = await apiFetch(input, init)
  const text = await response.text()
  const data = text ? JSON.parse(text) : null

  if (!response.ok) {
    throw new Error(data?.detail || data?.message || "Request failed")
  }

  return data as T
}

export async function apiVoid(input: string, init: ApiRequestInit = {}) {
  const response = await apiFetch(input, init)
  const text = await response.text()
  const data = text ? JSON.parse(text) : null

  if (!response.ok) {
    throw new Error(data?.detail || data?.message || "Request failed")
  }
}

export function buildWebSocketUrl(path: string) {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws"
  return `${protocol}://${window.location.host}${path}`
}
