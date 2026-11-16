import { afterEach, describe, expect, it, vi } from 'vitest'
import { z } from 'zod'
import { jsonResponse } from '@/test/render'
import { ApiError, apiGet, apiUrl, setAccessTokenProvider, setAccessTokenRefresher } from './api-client'

const Schema = z.object({ ok: z.boolean() })

describe('apiUrl', () => {
  it('builds versioned URLs against the configured base', () => {
    expect(apiUrl('/health', '')).toBe('/api/v1/health')
    expect(apiUrl('health', 'https://api.example.com')).toBe('https://api.example.com/api/v1/health')
  })
})

describe('apiGet', () => {
  it('returns parsed data when the response matches the schema', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ ok: true }))
    await expect(apiGet('/x', Schema)).resolves.toEqual({ ok: true })
  })

  it('rejects responses that violate the contract', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ ok: 'yes' }))
    await expect(apiGet('/x', Schema)).rejects.toMatchObject({ kind: 'validation' })
  })

  it('surfaces HTTP errors with the status code', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({}, 503))
    await expect(apiGet('/x', Schema)).rejects.toMatchObject({ kind: 'http', status: 503 })
  })

  it('reports network failures distinctly', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    const err = await apiGet('/x', Schema).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).kind).toBe('network')
  })
})

describe('expired access tokens', () => {
  afterEach(() => {
    setAccessTokenProvider(async () => null)
    setAccessTokenRefresher(async () => null)
  })

  const authOf = (call: unknown[]) => (call[1] as RequestInit).headers as Record<string, string>

  it('refreshes once and retries when the API answers 401', async () => {
    setAccessTokenProvider(async () => 'stale')
    const refresher = vi.fn(async () => 'fresh')
    setAccessTokenRefresher(refresher)
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({ error: { code: 'unauthorized', message: 'Token expired' } }, 401))
      .mockResolvedValueOnce(jsonResponse({ ok: true }))
    await expect(apiGet('/x', Schema)).resolves.toEqual({ ok: true })
    expect(refresher).toHaveBeenCalledTimes(1)
    expect(authOf(fetchSpy.mock.calls[0]!).Authorization).toBe('Bearer stale')
    expect(authOf(fetchSpy.mock.calls[1]!).Authorization).toBe('Bearer fresh')
  })

  it('reports a second 401, and never retries anonymous requests', async () => {
    setAccessTokenProvider(async () => 'stale')
    setAccessTokenRefresher(async () => 'fresh')
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ error: { code: 'unauthorized', message: 'Nope' } }, 401))
    await expect(apiGet('/x', Schema)).rejects.toMatchObject({ status: 401, message: 'Nope' })

    setAccessTokenProvider(async () => null)
    const refresher = vi.fn(async () => 'fresh')
    setAccessTokenRefresher(refresher)
    await expect(apiGet('/y', Schema)).rejects.toMatchObject({ status: 401 })
    expect(refresher).not.toHaveBeenCalled()
  })
})
