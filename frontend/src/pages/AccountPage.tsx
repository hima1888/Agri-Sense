import { Link } from 'react-router'
import { useState, type FormEvent } from 'react'
import { FormAlert, SubmitButton, TextField } from '@/components/ui/form'
import { Pill, SectionHeading } from '@/components/ui/primitives'
import { useMe, useMyFarms, useUpdateMe } from '@/features/account/api'
import { useAuth } from '@/features/auth/auth-context'
import { FullPageSpinner } from '@/features/auth/RequireAuth'

export function AccountPage() {
  const { signOut } = useAuth()
  const me = useMe()
  const farms = useMyFarms()

  if (me.isPending) return <FullPageSpinner />
  if (me.isError) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 sm:px-6">
        <FormAlert>Could not load your profile: {me.error.message}</FormAlert>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
      <SectionHeading eyebrow="Account" title={me.data.full_name ? `Hello, ${me.data.full_name}` : 'Your account'}>
        Signed in as {me.data.email}. Your profile and farms below come live from the AGRI-SENSE API.
      </SectionHeading>

      <div className="mt-10 grid gap-6 md:grid-cols-2">
        <section aria-labelledby="profile-h" className="glass rounded-2xl p-6">
          <div className="flex items-center justify-between">
            <h2 id="profile-h" className="font-display text-xl text-paper">
              Profile
            </h2>
            <Pill tone={me.data.role === 'admin' ? 'warn' : 'muted'}>{me.data.role}</Pill>
          </div>
          <ProfileForm key={me.data.updated_at} initialName={me.data.full_name ?? ''} />
          <dl className="mt-6 space-y-2 border-t border-white/5 pt-4 text-xs text-sage-400">
            <div className="flex justify-between gap-4">
              <dt>User ID</dt>
              <dd className="truncate font-mono">{me.data.id}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt>Member since</dt>
              <dd>{new Date(me.data.created_at).toLocaleDateString()}</dd>
            </div>
          </dl>
        </section>

        <section aria-labelledby="farms-h" className="glass rounded-2xl p-6">
          <h2 id="farms-h" className="font-display text-xl text-paper">
            Your farms
          </h2>
          {farms.isPending && <p className="mt-4 text-sm text-sage-400">Loading…</p>}
          {farms.isError && <p className="mt-4 text-sm text-signal-alert">{farms.error.message}</p>}
          {farms.isSuccess &&
            (farms.data.total === 0 ? (
              <p className="mt-4 text-sm text-sage-300">
                You have no farms yet. <Link to="/farms" className="text-wheat-300 hover:underline">Create your first farm</Link>.
              </p>
            ) : (
              <ul className="mt-4 divide-y divide-white/5">
                {farms.data.items.map((f) => (
                  <li key={f.id} className="flex justify-between py-2.5 text-sm">
                    <span className="text-paper">{f.name}</span>
                    <span className="font-mono text-sage-400">
                      {f.area_hectares != null ? `${f.area_hectares} ha` : '—'}
                    </span>
                  </li>
                ))}
              </ul>
            ))}
        </section>
      </div>

      <button
        type="button"
        onClick={() => void signOut()}
        className="mt-10 rounded-full border border-white/15 px-5 py-2 text-sm text-sage-100 transition-colors hover:border-white/30"
      >
        Sign out
      </button>
    </div>
  )
}

function ProfileForm({ initialName }: { initialName: string }) {
  const update = useUpdateMe()
  const [name, setName] = useState(initialName)
  const [error, setError] = useState<string | undefined>()

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (trimmed.length > 200) return setError('Use at most 200 characters.')
    setError(undefined)
    update.mutate({ full_name: trimmed || null })
  }

  return (
    <form onSubmit={onSubmit} className="mt-5 space-y-3">
      <TextField
        label="Full name"
        name="full_name"
        autoComplete="name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        error={error}
      />
      {update.isError && <FormAlert>{update.error.message}</FormAlert>}
      {update.isSuccess && <FormAlert tone="ok">Saved.</FormAlert>}
      <SubmitButton busy={update.isPending}>Save</SubmitButton>
    </form>
  )
}
