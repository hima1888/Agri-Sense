import type { z } from 'zod'
import { env } from './env'

export class ApiError extends Error {
  readonly status: number | null
  readonly kind: 'network' | 'http' | 'validation'
  readonly code: string | null

  constructor(message: string, kind: ApiError['kind'], status: number | null = null, code: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.code = code
  }
}

export function apiUrl(path: string, baseUrl: string = env.apiBaseUrl): string {
  const clean = path.startsWith('/') ? path : `/${path}`
  return `${baseUrl}/api/v1${clean}`
}

type TokenProvider = () => Promise<string | null>
let tokenProvider: TokenProvider = async () => null

/** Registered by the auth layer so every request carries the current Supabase access token. */
export function setAccessTokenProvider(provider: TokenProvider): void {
  tokenProvider = provider
}

let tokenRefresher: TokenProvider = async () => null

/** Registered by the auth layer: force a token refresh (used once when the API answers 401). */
export function setAccessTokenRefresher(refresher: TokenProvider): void {
  tokenRefresher = refresher
}

/** Current access token (refreshed by Supabase when needed), or null when signed out. */
export function getAccessToken(): Promise<string | null> {
  return tokenProvider()
}

async function request<T>(
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  path: string,
  schema: z.ZodType<T>,
  body?: unknown,
  init?: RequestInit,
): Promise<T> {
  const isForm = body instanceof FormData
  const send = async (token: string | null): Promise<Response> => {
    const headers: Record<string, string> = { Accept: 'application/json' }
    // FormData sets its own multipart boundary header.
    if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json'
    if (token) headers.Authorization = `Bearer ${token}`
    try {
      return await fetch(apiUrl(path), {
        ...init,
        method,
        headers: { ...headers, ...(init?.headers as Record<string, string> | undefined) },
        body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
      })
    } catch {
      throw new ApiError('Backend unreachable. Is the API server running?', 'network')
    }
  }

  const token = await tokenProvider()
  let res = await send(token)
  // A token can expire between Supabase handing it out and the API checking it (or while a background
  // tab's refresh timer was paused). Refresh once and retry; a second 401 is reported as usual.
  if (res.status === 401 && token) {
    const fresh = await tokenRefresher().catch(() => null)
    if (fresh && fresh !== token) res = await send(fresh)
  }

  if (!res.ok) {
    // The backend always answers {"error": {code, message}}; surface its message.
    let message = `Request failed with HTTP ${res.status}`
    let code: string | null = null
    try {
      const err = (await res.json()) as { error?: { code?: string; message?: string } }
      if (err.error?.message) message = err.error.message
      code = err.error?.code ?? null
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(message, 'http', res.status, code)
  }

  const data: unknown = res.status === 204 ? null : await res.json()
  const result = schema.safeParse(data)
  if (!result.success) {
    throw new ApiError('Backend response did not match the expected contract', 'validation', res.status)
  }
  return result.data
}

/** GET a JSON resource and validate it against a Zod schema. */
export function apiGet<T>(path: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
  return request('GET', path, schema, undefined, init)
}

export function apiSend<T>(
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  path: string,
  schema: z.ZodType<T>,
  body?: unknown,
): Promise<T> {
  return request(method, path, schema, body)
}

/** Fetch an authenticated binary resource (e.g. a stored image) as an object URL. Caller revokes it. */
export async function apiBlobUrl(path: string, signal?: AbortSignal): Promise<string> {
  const token = await tokenProvider()
  const res = await fetch(apiUrl(path), { signal, headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!res.ok) throw new ApiError(`Request failed with HTTP ${res.status}`, 'http', res.status)
  return URL.createObjectURL(await res.blob())
}
