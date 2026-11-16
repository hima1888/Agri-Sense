import { Pill, SectionHeading, StatusDot, type Tone } from '@/components/ui/primitives'
import { useHealth, useSystemInfo, type ServiceStateValue } from '@/features/system/api'
import { apiUrl } from '@/lib/api-client'

const STATE_TONE: Record<ServiceStateValue, Tone> = {
  ok: 'ok',
  degraded: 'warn',
  not_configured: 'muted',
  planned: 'info',
}

const STATE_LABEL: Record<ServiceStateValue, string> = {
  ok: 'ok',
  degraded: 'degraded',
  not_configured: 'not configured',
  planned: 'planned',
}

export function StatusPage() {
  const health = useHealth()
  const info = useSystemInfo()

  return (
    <div className="mx-auto max-w-5xl px-4 py-16 sm:px-6">
      <SectionHeading eyebrow="System" title="Live system status">
        This page calls the FastAPI backend directly and validates every response against a typed contract. Nothing
        here is hard-coded.
      </SectionHeading>

      <section aria-labelledby="api-heading" className="glass mt-10 rounded-2xl p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <StatusDot tone={health.isSuccess ? 'ok' : health.isError ? 'alert' : 'muted'} pulse />
            <h3 id="api-heading" className="font-display text-xl text-paper">
              Backend API
            </h3>
          </div>
          <code className="font-mono text-xs text-sage-400">GET {apiUrl('/health')}</code>
        </div>

        {health.isPending && <p className="mt-4 text-sm text-sage-300">Contacting backend…</p>}

        {health.isError && (
          <div role="alert" className="mt-4 rounded-lg border border-signal-alert/30 bg-signal-alert/10 p-4 text-sm">
            <p className="text-paper">{health.error.message}</p>
            <p className="mt-1 text-sage-300">
              Start it with <code className="font-mono">uvicorn app.main:app --reload</code> from the{' '}
              <code className="font-mono">backend</code> folder.
            </p>
          </div>
        )}

        {health.isSuccess && (
          <dl className="mt-5 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            <Field label="Status" value={health.data.status} />
            <Field label="Service" value={health.data.service} />
            <Field label="Version" value={health.data.version} />
            <Field label="Server time" value={new Date(health.data.timestamp).toLocaleTimeString()} />
          </dl>
        )}
      </section>

      {info.isSuccess && (
        <>
          <section aria-labelledby="data-heading" className="mt-6 rounded-2xl border border-wheat-400/20 bg-wheat-400/5 p-6">
            <div className="flex items-center gap-3">
              <h3 id="data-heading" className="font-display text-xl text-paper">
                Sensor data mode
              </h3>
              <Pill tone="warn">{info.data.data_mode.sensors}</Pill>
            </div>
            <p className="mt-2 text-sm text-sage-200">{info.data.data_mode.note}</p>
          </section>

          <section aria-labelledby="svc-heading" className="mt-6">
            <h3 id="svc-heading" className="eyebrow">
              Services · environment: {info.data.environment}
            </h3>
            <ul className="mt-4 divide-y divide-white/5 overflow-hidden rounded-2xl border border-white/8">
              {info.data.services.map((s) => (
                <li key={s.key} className="flex flex-col gap-1 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm text-paper">{s.label}</p>
                    <p className="text-xs text-sage-400">{s.detail}</p>
                  </div>
                  <Pill tone={STATE_TONE[s.state]}>{STATE_LABEL[s.state]}</Pill>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="eyebrow">{label}</dt>
      <dd className="mt-1 font-mono text-paper">{value}</dd>
    </div>
  )
}
