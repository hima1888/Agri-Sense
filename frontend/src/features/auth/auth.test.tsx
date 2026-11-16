import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, renderRoute } from '@/test/render'
import { createFakeSupabase, VALID_PASSWORD } from '@/test/fake-supabase'

const fake = vi.hoisted(() => ({ current: null as ReturnType<typeof createFakeSupabase> | null }))
vi.mock('@/lib/supabase', async () => {
  const { createFakeSupabase } = await import('@/test/fake-supabase')
  fake.current = createFakeSupabase()
  return { supabase: fake.current.supabase }
})

const ME = {
  id: '6f1c7a52-6a8e-4d55-9a49-0c1b2d3e4f50',
  email: 'grower@example.com',
  full_name: null,
  role: 'farmer',
  created_at: '2026-11-13T10:00:00Z',
  updated_at: '2026-11-13T10:00:00Z',
}

function mockApi() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const auth = new Headers(init?.headers).get('Authorization')
    if (url.endsWith('/health')) return jsonResponse({ status: 'ok', service: 'x', version: '1', timestamp: '2026-01-01T00:00:00Z' })
    if (!auth) return jsonResponse({ error: { code: 'unauthorized', message: 'Sign in required.' } }, 401)
    if (url.endsWith('/me') && init?.method === 'PATCH') {
      return jsonResponse({ ...ME, ...JSON.parse(String(init.body)), updated_at: '2026-11-13T11:00:00Z' })
    }
    if (url.endsWith('/me')) return jsonResponse(ME)
    if (url.includes('/farms')) {
      return jsonResponse({ total: 1, limit: 50, offset: 0, items: [{ id: 1, name: 'North Farm', area_hectares: 4.5 }] })
    }
    return jsonResponse({ error: { code: 'not_found', message: 'nope' } }, 404)
  })
}

const f = () => fake.current!

describe('authentication', () => {
  beforeEach(() => {
    f().reset()
  })

  it('redirects signed-out visitors from protected pages to sign in, then back', async () => {
    mockApi()
    const user = userEvent.setup()
    renderRoute('/account')
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()

    await user.type(screen.getByLabelText('Email'), 'grower@example.com')
    await user.type(screen.getByLabelText('Password'), VALID_PASSWORD)
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText(/signed in as grower@example.com/i)).toBeInTheDocument()
    expect(f().auth.signInWithPassword).toHaveBeenCalledWith({ email: 'grower@example.com', password: VALID_PASSWORD })
    expect(await screen.findByText('North Farm')).toBeInTheDocument()
  })

  it('sends the Supabase access token to the API', async () => {
    const fetchSpy = mockApi()
    f().signInAs('grower@example.com')
    renderRoute('/account')
    await screen.findByText(/signed in as/i)
    const meCall = fetchSpy.mock.calls.find(([url]) => String(url).endsWith('/me'))
    expect(new Headers(meCall?.[1]?.headers).get('Authorization')).toBe('Bearer token-for-grower@example.com')
  })

  it('validates the sign-in form before contacting the server', async () => {
    mockApi()
    const user = userEvent.setup()
    renderRoute('/login')
    await user.click(await screen.findByRole('button', { name: 'Sign in' }))
    expect(screen.getByText('Enter a valid email address.')).toBeInTheDocument()
    expect(screen.getByText('Enter your password.')).toBeInTheDocument()
    expect(f().auth.signInWithPassword).not.toHaveBeenCalled()
  })

  it('shows a plain-language error for wrong credentials', async () => {
    mockApi()
    const user = userEvent.setup()
    renderRoute('/login')
    await user.type(await screen.findByLabelText('Email'), 'grower@example.com')
    await user.type(screen.getByLabelText('Password'), 'wrong-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Email or password is incorrect.')
  })

  it('enforces the password policy on sign-up', async () => {
    mockApi()
    const user = userEvent.setup()
    renderRoute('/signup')
    await user.type(await screen.findByLabelText('Email'), 'new@example.com')
    await user.type(screen.getByLabelText('Password'), 'short')
    await user.type(screen.getByLabelText('Confirm password'), 'different')
    await user.click(screen.getByRole('button', { name: 'Create account' }))
    expect(screen.getByText('Use at least 8 characters.')).toBeInTheDocument()
    expect(screen.getByText('Passwords do not match.')).toBeInTheDocument()
    expect(f().auth.signUp).not.toHaveBeenCalled()
  })

  it('signs up and lands on the account page, or asks to confirm email', async () => {
    mockApi()
    const user = userEvent.setup()
    renderRoute('/signup')
    await user.type(await screen.findByLabelText('Email'), 'confirm-me@example.com')
    await user.type(screen.getByLabelText('Password'), VALID_PASSWORD)
    await user.type(screen.getByLabelText('Confirm password'), VALID_PASSWORD)
    await user.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByRole('heading', { name: 'Check your email' })).toBeInTheDocument()
  })

  it('reports an existing account on sign-up', async () => {
    mockApi()
    const user = userEvent.setup()
    renderRoute('/signup')
    await user.type(await screen.findByLabelText('Email'), 'taken@example.com')
    await user.type(screen.getByLabelText('Password'), VALID_PASSWORD)
    await user.type(screen.getByLabelText('Confirm password'), VALID_PASSWORD)
    await user.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('An account with this email already exists.')
  })

  it('updates the profile through the API and signs out', async () => {
    mockApi()
    f().signInAs('grower@example.com')
    const user = userEvent.setup()
    renderRoute('/account')
    const nameInput = await screen.findByLabelText('Full name')
    await user.type(nameInput, 'Asha Rao')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('heading', { name: 'Hello, Asha Rao' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Sign out' }))
    await waitFor(() => expect(f().auth.signOut).toHaveBeenCalled())
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('ignores off-site redirect targets after sign-in', async () => {
    mockApi()
    const user = userEvent.setup()
    renderRoute('/login?next=//evil.example.com')
    await user.type(await screen.findByLabelText('Email'), 'grower@example.com')
    await user.type(screen.getByLabelText('Password'), VALID_PASSWORD)
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    // Lands inside the app (the dashboard), never on the external URL.
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Sign in' })).not.toBeInTheDocument())
    expect(f().auth.signInWithPassword).toHaveBeenCalled()
    expect(window.location.href).not.toContain('evil.example.com')
  })
})
