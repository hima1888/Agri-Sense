import { useMemo, useState, type FormEvent } from 'react'
import { z } from 'zod'
import { FormAlert, SubmitButton, TextField } from '@/components/ui/form'
import { SectionHeading } from '@/components/ui/primitives'
import { FullPageSpinner } from '@/features/auth/RequireAuth'
import { useBackfill, useFarms, useProvisionZone, useQuickStartFarm, useSimulatorStatus, useZones } from '@/features/live/api'
import { ConnectionBadge, SensorCard } from '@/features/live/components'
import { SENSOR_TYPES, type Zone } from '@/features/live/schemas'
import { useFarmStream } from '@/features/live/use-farm-stream'
import { useNow } from '@/lib/use-now'
import { LOCAL_TZ } from '@/features/dashboard/timezones'

export function LivePage() {
  const farms = useFarms()
  const [selected, setSelected] = useState<number | null>(null)
  const farmId = selected ?? farms.data?.items[0]?.id ?? null

  if (farms.isPending) return <FullPageSpinner />
  if (farms.isError) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
        <FormAlert>Could not load your farms: {farms.error.message}</FormAlert>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6">
      {farms.data.items.length === 0 ? (
        <QuickStart />
      ) : (
        <>
          {farms.data.items.length > 1 && (
            <label className="mb-6 inline-flex items-center gap-3 text-sm text-sage-300">
              Farm
              <select
                value={farmId ?? ''}
                onChange={(e) => setSelected(Number(e.target.value))}
                className="rounded-lg border border-white/10 bg-ink-950/60 px-3 py-1.5 text-paper"
              >
                {farms.data.items.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {farmId != null && (
            <FarmLive key={farmId} farmId={farmId} farmName={farms.data.items.find((f) => f.id === farmId)?.name ?? ''} />
          )}
        </>
      )}
    </div>
  )
}

function FarmLive({ farmId, farmName }: { farmId: number; farmName: string }) {
  const stream = useFarmStream(farmId)
  const zones = useZones(farmId)
  const sim = useSimulatorStatus(farmId)
  const backfill = useBackfill(farmId)
  const intervalMs = (sim.data?.interval_seconds ?? 10) * 1000
  const now = useNow(5_000)
  const sensors = stream.sensors

  const byZone = useMemo(() => {
    const order = new Map(SENSOR_TYPES.map((t, i) => [t, i]))
    const groups = new Map<number | null, typeof sensors>()
    for (const s of [...sensors].sort((a, b) => order.get(a.sensor_type)! - order.get(b.sensor_type)!)) {
      groups.set(s.zone_id, [...(groups.get(s.zone_id) ?? []), s])
    }
    return groups
  }, [sensors])

  const zoneName = (id: number | null) => zones.data?.items.find((z) => z.id === id)?.name ?? 'Unassigned'
  const simulatedCount = stream.sensors.filter((s) => s.is_simulated).length

  return (
    <>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <SectionHeading eyebrow="Live sensors" title={farmName} />
        <ConnectionBadge status={stream.status} />
      </div>

      {stream.error && (
        <div className="mt-6">
          <FormAlert>{stream.error}</FormAlert>
        </div>
      )}

      {simulatedCount > 0 && (
        <div className="mt-6 flex flex-col gap-3 rounded-xl border border-wheat-400/20 bg-wheat-400/5 p-4 text-sm sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sage-200">
            <strong className="font-medium text-wheat-300">Simulated data.</strong> {simulatedCount} sensor(s) are driven by the
            AGRI-SENSE simulator from this farm&apos;s location, weather physics and your recorded irrigation and fertilizer. No
            physical hardware is connected.
          </p>
          <button
            type="button"
            disabled={backfill.isPending}
            onClick={() => backfill.mutate(24)}
            className="shrink-0 rounded-full border border-white/15 px-4 py-1.5 text-xs text-sage-100 transition-colors hover:border-white/30 disabled:opacity-60"
          >
            {backfill.isPending ? 'Generating…' : backfill.isSuccess ? `Added ${backfill.data.inserted} readings` : 'Generate last 24 h'}
          </button>
        </div>
      )}

      {stream.status !== 'connecting' && stream.sensors.length === 0 && zones.data && (
        <SetupKit farmId={farmId} zones={zones.data.items} />
      )}

      {[...byZone.entries()].map(([zoneId, sensors]) => (
        <section key={zoneId ?? 'none'} className="mt-10" aria-label={`Zone ${zoneName(zoneId)}`}>
          <h2 className="eyebrow">{zoneName(zoneId)}</h2>
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {sensors.map((s) => (
              <SensorCard key={s.id} sensor={s} points={stream.history[s.id] ?? []} staleAfterMs={Math.max(60_000, intervalMs * 4)} now={now} />
            ))}
          </div>
        </section>
      ))}
    </>
  )
}

function SetupKit({ farmId, zones }: { farmId: number; zones: Zone[] }) {
  const provision = useProvisionZone(farmId)
  return (
    <div className="glass mt-8 rounded-2xl p-6">
      <h2 className="font-display text-xl text-paper">No sensors on this farm yet</h2>
      <p className="mt-2 max-w-2xl text-sm text-sage-300">
        No physical hardware is connected. You can add a <strong className="text-paper">simulated</strong> kit of 12 sensors to a
        zone. Its readings start within seconds, stream live, and stay labelled as simulated everywhere.
      </p>
      {provision.isError && (
        <div className="mt-4">
          <FormAlert>{provision.error.message}</FormAlert>
        </div>
      )}
      <ul className="mt-5 divide-y divide-white/5">
        {zones.map((z) => (
          <li key={z.id} className="flex items-center justify-between py-3 text-sm">
            <span className="text-paper">{z.name}</span>
            <button
              type="button"
              disabled={provision.isPending}
              onClick={() => provision.mutate(z.id)}
              className="rounded-full bg-paper px-4 py-1.5 text-xs font-medium text-ink-900 disabled:opacity-60"
            >
              Add simulated sensor kit
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

const QuickStartSchema = z.object({
  name: z.string().trim().min(1, 'Name your farm.').max(200),
  latitude: z.coerce.number({ message: 'Enter a latitude.' }).min(-90, 'Between -90 and 90.').max(90, 'Between -90 and 90.'),
  longitude: z.coerce.number({ message: 'Enter a longitude.' }).min(-180, 'Between -180 and 180.').max(180, 'Between -180 and 180.'),
  zoneName: z.string().trim().min(1, 'Name the first zone.').max(200),
})

function QuickStart() {
  const create = useQuickStartFarm()
  const [errors, setErrors] = useState<Record<string, string>>({})

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const data = Object.fromEntries(new FormData(e.currentTarget))
    const parsed = QuickStartSchema.safeParse({
      ...data,
      latitude: String(data.latitude ?? '').trim() || undefined,
      longitude: String(data.longitude ?? '').trim() || undefined,
    })
    if (!parsed.success) {
      const out: Record<string, string> = {}
      for (const i of parsed.error.issues) out[String(i.path[0])] ??= i.message
      return setErrors(out)
    }
    setErrors({})
    create.mutate({ ...parsed.data, timezone: LOCAL_TZ })
  }

  return (
    <div className="mx-auto max-w-xl">
      <SectionHeading eyebrow="Live sensors" title="Start with your farm">
        Location drives sunrise, temperature and humidity in the simulator, so it needs coordinates. Full farm setup, maps and
        zones arrive with the dashboard.
      </SectionHeading>
      <form noValidate onSubmit={onSubmit} className="glass mt-8 space-y-4 rounded-2xl p-6">
        {create.isError && <FormAlert>{create.error.message}</FormAlert>}
        <TextField label="Farm name" name="name" error={errors.name} />
        <div className="grid grid-cols-2 gap-4">
          <TextField label="Latitude" name="latitude" inputMode="decimal" placeholder="17.385" error={errors.latitude} />
          <TextField label="Longitude" name="longitude" inputMode="decimal" placeholder="78.4867" error={errors.longitude} />
        </div>
        <TextField label="First zone" name="zoneName" defaultValue="North Field" error={errors.zoneName} />
        <SubmitButton busy={create.isPending}>Create farm</SubmitButton>
      </form>
    </div>
  )
}
