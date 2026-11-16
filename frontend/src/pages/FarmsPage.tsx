import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { z } from 'zod'
import { FormAlert, SubmitButton, TextField } from '@/components/ui/form'
import { Pill, SectionHeading } from '@/components/ui/primitives'
import { FullPageSpinner } from '@/features/auth/RequireAuth'
import {
  useCreateFarm,
  useCreateZone,
  useDeleteFarm,
  useDeleteZone,
  useFarmList,
  useUpdateFarm,
  useZoneList,
  type FarmInput,
} from '@/features/dashboard/api'
import type { FarmDetail } from '@/features/dashboard/schemas'
import { LOCAL_TZ, timezoneOptions } from '@/features/dashboard/timezones'
import { NotFoundPage } from './NotFoundPage'

const ZONE_TYPES = ['field', 'greenhouse', 'orchard', 'nursery', 'pasture', 'other'] as const
const IRRIGATION = ['drip', 'sprinkler', 'flood', 'pivot', 'furrow', 'manual', 'none'] as const

const optionalNumber = (min: number, max: number, label: string) =>
  z
    .string()
    .trim()
    .transform((v) => (v === '' ? null : Number(v)))
    .refine((v) => v === null || (Number.isFinite(v) && v >= min && v <= max), `${label} must be between ${min} and ${max}.`)

const FarmFormSchema = z.object({
  name: z.string().trim().min(1, 'Name your farm.').max(200),
  description: z
    .string()
    .trim()
    .max(5000)
    .transform((v) => v || null),
  latitude: optionalNumber(-90, 90, 'Latitude'),
  longitude: optionalNumber(-180, 180, 'Longitude'),
  area_hectares: optionalNumber(0, 1_000_000, 'Area'),
  timezone: z.string().min(1),
})

const ZoneFormSchema = z.object({
  name: z.string().trim().min(1, 'Name the zone.').max(200),
  zone_type: z.enum(ZONE_TYPES),
  area_hectares: optionalNumber(0, 1_000_000, 'Area'),
  irrigation_method: z.enum(IRRIGATION).or(z.literal('')).transform((v) => v || null),
})

function issues(error: z.ZodError): Record<string, string> {
  const out: Record<string, string> = {}
  for (const i of error.issues) out[String(i.path[0])] ??= i.message
  return out
}

function Select({ label, name, defaultValue, children }: { label: string; name: string; defaultValue?: string; children: ReactNode }) {
  return (
    <label className="block text-sm text-sage-200">
      {label}
      <select
        name={name}
        defaultValue={defaultValue}
        className="mt-1.5 block w-full rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2.5 text-sm text-paper focus:border-wheat-300/50 focus:outline-none"
      >
        {children}
      </select>
    </label>
  )
}

function FarmForm({
  initial,
  busy,
  error,
  submitLabel,
  onSubmit,
}: {
  initial?: FarmDetail
  busy: boolean
  error: string | null
  submitLabel: string
  onSubmit: (input: FarmInput) => void
}) {
  const [errors, setErrors] = useState<Record<string, string>>({})
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const parsed = FarmFormSchema.safeParse(Object.fromEntries(new FormData(e.currentTarget)))
    if (!parsed.success) return setErrors(issues(parsed.error))
    setErrors({})
    onSubmit(parsed.data)
  }
  return (
    <form noValidate onSubmit={submit} className="space-y-4">
      {error && <FormAlert>{error}</FormAlert>}
      <TextField label="Farm name" name="name" defaultValue={initial?.name} error={errors.name} />
      <TextField label="Description" name="description" defaultValue={initial?.description ?? ''} error={errors.description} />
      <div className="grid grid-cols-2 gap-4">
        <TextField label="Latitude" name="latitude" inputMode="decimal" defaultValue={initial?.latitude ?? ''} error={errors.latitude} hint="Needed for weather & simulation" />
        <TextField label="Longitude" name="longitude" inputMode="decimal" defaultValue={initial?.longitude ?? ''} error={errors.longitude} />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <TextField label="Area (ha)" name="area_hectares" inputMode="decimal" defaultValue={initial?.area_hectares ?? ''} error={errors.area_hectares} />
        <Select label="Time zone" name="timezone" defaultValue={initial?.timezone ?? LOCAL_TZ}>
          {timezoneOptions(initial?.timezone).map((tz) => (
            <option key={tz} value={tz}>
              {tz}
            </option>
          ))}
        </Select>
      </div>
      <SubmitButton busy={busy}>{submitLabel}</SubmitButton>
    </form>
  )
}

export function FarmsPage() {
  const farms = useFarmList()
  const create = useCreateFarm()
  const navigate = useNavigate()
  const [showForm, setShowForm] = useState(false)

  if (farms.isPending) return <FullPageSpinner />
  if (farms.isError) return <div className="mx-auto max-w-3xl px-4 py-16"><FormAlert>{farms.error.message}</FormAlert></div>
  const empty = farms.data.items.length === 0

  return (
    <div className="mx-auto max-w-5xl px-4 py-14 sm:px-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <SectionHeading eyebrow="Farms" title="Your farms">
          Each farm has a location (for weather and daylight), a time zone and one or more zones.
        </SectionHeading>
        {!empty && !showForm && (
          <button type="button" onClick={() => setShowForm(true)} className="rounded-full bg-paper px-5 py-2 text-sm font-medium text-ink-900">
            New farm
          </button>
        )}
      </div>

      {(empty || showForm) && (
        <section className="glass mt-8 max-w-xl rounded-2xl p-6" aria-label="Create farm">
          <h2 className="font-display text-xl text-paper">{empty ? 'Create your first farm' : 'New farm'}</h2>
          <div className="mt-5">
            <FarmForm
              busy={create.isPending}
              error={create.isError ? create.error.message : null}
              submitLabel="Create farm"
              onSubmit={(input) => create.mutate(input, { onSuccess: (f) => navigate(`/farms/${f.id}`) })}
            />
          </div>
        </section>
      )}

      <ul className="mt-10 grid gap-4 sm:grid-cols-2">
        {farms.data.items.map((f) => (
          <li key={f.id} className="glass flex flex-col rounded-2xl p-6">
            <div className="flex items-start justify-between gap-3">
              <h3 className="font-display text-xl text-paper">{f.name}</h3>
              {f.latitude == null && <Pill tone="warn">No location</Pill>}
            </div>
            <p className="mt-2 text-sm text-sage-400">
              {f.latitude != null ? `${f.latitude.toFixed(3)}°, ${f.longitude?.toFixed(3)}°` : 'Location not set'} · {f.timezone}
              {f.area_hectares != null && ` · ${f.area_hectares} ha`}
            </p>
            <div className="mt-6 flex gap-3 text-sm">
              <Link to={`/dashboard?farm=${f.id}`} className="rounded-full bg-paper px-4 py-1.5 font-medium text-ink-900">
                Dashboard
              </Link>
              <Link to={`/farms/${f.id}`} className="rounded-full border border-white/15 px-4 py-1.5 text-sage-100 hover:border-white/30">
                Settings & zones
              </Link>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function FarmSettingsPage() {
  const { farmId: raw } = useParams()
  const farmId = Number(raw)
  const farms = useFarmList()
  const farm = farms.data?.items.find((f) => f.id === farmId)
  if (farms.isPending) return <FullPageSpinner />
  if (!farm) return <NotFoundPage />
  return <FarmSettings key={farm.updated_at} farm={farm} />
}

function FarmSettings({ farm }: { farm: FarmDetail }) {
  const update = useUpdateFarm(farm.id)
  const del = useDeleteFarm()
  const navigate = useNavigate()
  const [confirmDelete, setConfirmDelete] = useState(false)

  return (
    <div className="mx-auto max-w-5xl px-4 py-14 sm:px-6">
      <Link to="/farms" className="text-sm text-sage-400 hover:text-paper">
        ← All farms
      </Link>
      <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <SectionHeading eyebrow="Farm settings" title={farm.name} />
        <Link to={`/dashboard?farm=${farm.id}`} className="text-sm text-wheat-300 hover:underline">
          Open dashboard →
        </Link>
      </div>

      <div className="mt-10 grid gap-6 lg:grid-cols-2">
        <section className="glass rounded-2xl p-6" aria-label="Farm details">
          <h2 className="font-display text-xl text-paper">Details</h2>
          <div className="mt-5">
            <FarmForm
              initial={farm}
              busy={update.isPending}
              error={update.isError ? update.error.message : null}
              submitLabel={update.isSuccess ? 'Saved' : 'Save changes'}
              onSubmit={(input) => update.mutate(input)}
            />
          </div>
        </section>
        <ZonesSection farmId={farm.id} />
      </div>

      <section className="mt-10 rounded-2xl border border-signal-alert/25 p-6" aria-label="Danger zone">
        <h2 className="font-display text-lg text-paper">Delete farm</h2>
        <p className="mt-1 text-sm text-sage-300">
          Permanently deletes this farm with all its zones, sensors, readings and records. This cannot be undone.
        </p>
        {del.isError && <div className="mt-3"><FormAlert>{del.error.message}</FormAlert></div>}
        {confirmDelete ? (
          <div className="mt-4 flex gap-3">
            <button
              type="button"
              disabled={del.isPending}
              onClick={() => del.mutate(farm.id, { onSuccess: () => navigate('/farms') })}
              className="rounded-full bg-signal-alert px-4 py-1.5 text-sm font-medium text-ink-950"
            >
              Yes, delete “{farm.name}” permanently
            </button>
            <button type="button" onClick={() => setConfirmDelete(false)} className="rounded-full border border-white/15 px-4 py-1.5 text-sm text-sage-100">
              Cancel
            </button>
          </div>
        ) : (
          <button type="button" onClick={() => setConfirmDelete(true)} className="mt-4 rounded-full border border-signal-alert/40 px-4 py-1.5 text-sm text-signal-alert">
            Delete farm…
          </button>
        )}
      </section>
    </div>
  )
}

function ZonesSection({ farmId }: { farmId: number }) {
  const zones = useZoneList(farmId)
  const create = useCreateZone(farmId)
  const del = useDeleteZone(farmId)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [pendingDelete, setPendingDelete] = useState<number | null>(null)

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    const parsed = ZoneFormSchema.safeParse(Object.fromEntries(new FormData(form)))
    if (!parsed.success) return setErrors(issues(parsed.error))
    setErrors({})
    create.mutate(parsed.data, { onSuccess: () => form.reset() })
  }

  return (
    <section className="glass rounded-2xl p-6" aria-label="Zones">
      <h2 className="font-display text-xl text-paper">Zones</h2>
      {zones.data && zones.data.items.length === 0 && <p className="mt-3 text-sm text-sage-400">No zones yet.</p>}
      <ul className="mt-4 divide-y divide-white/5">
        {zones.data?.items.map((z) => (
          <li key={z.id} className="flex items-center justify-between gap-3 py-3 text-sm">
            <div>
              <p className="text-paper">{z.name}</p>
              <p className="text-xs text-sage-400">
                {z.zone_type}
                {z.area_hectares != null && ` · ${z.area_hectares} ha`}
                {z.irrigation_method && ` · ${z.irrigation_method}`}
              </p>
            </div>
            {pendingDelete === z.id ? (
              <span className="flex gap-2">
                <button type="button" onClick={() => del.mutate(z.id, { onSettled: () => setPendingDelete(null) })} className="rounded-full bg-signal-alert px-3 py-1 text-xs text-ink-950">
                  Delete zone & its data
                </button>
                <button type="button" onClick={() => setPendingDelete(null)} className="text-xs text-sage-300">
                  Cancel
                </button>
              </span>
            ) : (
              <button type="button" onClick={() => setPendingDelete(z.id)} className="text-xs text-sage-400 hover:text-signal-alert" aria-label={`Delete zone ${z.name}`}>
                Delete
              </button>
            )}
          </li>
        ))}
      </ul>
      <form noValidate onSubmit={submit} className="mt-6 space-y-4 border-t border-white/5 pt-5" aria-label="Add zone">
        {create.isError && <FormAlert>{create.error.message}</FormAlert>}
        <TextField label="Zone name" name="name" error={errors.name} />
        <div className="grid grid-cols-3 gap-3">
          <Select label="Type" name="zone_type" defaultValue="field">
            {ZONE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </Select>
          <TextField label="Area (ha)" name="area_hectares" inputMode="decimal" error={errors.area_hectares} />
          <Select label="Irrigation" name="irrigation_method" defaultValue="">
            <option value="">—</option>
            {IRRIGATION.map((t) => <option key={t} value={t}>{t}</option>)}
          </Select>
        </div>
        <SubmitButton busy={create.isPending}>Add zone</SubmitButton>
      </form>
    </section>
  )
}
