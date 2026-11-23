import { AnimatePresence, motion } from 'framer-motion'
import { useState } from 'react'
import { NavLink, useLocation, useOutlet } from 'react-router'
import { Logo, StatusDot } from '@/components/ui/primitives'
import { useAuth } from '@/features/auth/auth-context'
import { useHealth } from '@/features/system/api'

// The three project objectives come first: disease detection, federated learning and explainable advice.
// Supporting tools sit under "More". The mobile menu lists all.
const PRIMARY = [
  { to: '/dashboard', label: 'Dashboard', end: false },
  { to: '/vision?tab=disease', label: 'Disease detection', end: false },
  { to: '/federated', label: 'Federated learning', end: false },
  { to: '/advice', label: 'Explainable advice', end: false },
  { to: '/twin', label: 'Digital twin', end: false },
  { to: '/farms', label: 'Farms', end: false },
]
const SECONDARY = [
  { to: '/live', label: 'Live sensors', end: false },
  { to: '/growth', label: 'Crop growth', end: false },
  { to: '/soil', label: 'Soil', end: false },
  { to: '/irrigation', label: 'Irrigation', end: false },
  { to: '/nutrients', label: 'Fertilizer', end: false },
  { to: '/alerts', label: 'Alerts', end: false },
]
const NAV = [...PRIMARY, ...SECONDARY]

export function AppShell() {
  const location = useLocation()
  const outlet = useOutlet()

  return (
    <div className="relative flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-ink-800 focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <Header />
      <main id="main" className="flex-1">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          >
            {outlet}
          </motion.div>
        </AnimatePresence>
      </main>
      <Footer />
    </div>
  )
}

function Header() {
  const [open, setOpen] = useState(false)
  return (
    <header className="sticky top-0 z-40 border-b border-white/5 bg-ink-900/70 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
        <NavLink to="/" aria-label="AGRI-SENSE home" onClick={() => setOpen(false)}>
          <Logo />
        </NavLink>

        <nav aria-label="Primary" className="hidden items-center gap-0.5 xl:flex">
          {PRIMARY.map((n) => (
            <NavItem key={n.to} {...n} />
          ))}
          <MoreMenu />
          <span className="mx-2 h-5 w-px bg-white/10" />
          <AuthNav />
        </nav>

        <button
          type="button"
          className="rounded-md p-2 text-sage-200 xl:hidden"
          aria-expanded={open}
          aria-controls="mobile-nav"
          aria-label="Toggle navigation"
          onClick={() => setOpen((o) => !o)}
        >
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6">
            {open ? <path d="M6 6l12 12M18 6 6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
          </svg>
        </button>
      </div>

      {open && (
        <nav id="mobile-nav" aria-label="Mobile" className="border-t border-white/5 px-4 pb-4 xl:hidden">
          <div className="flex flex-col gap-1 pt-2">
            {NAV.map((n) => (
              <NavItem key={n.to} {...n} onClick={() => setOpen(false)} />
            ))}
            <div className="px-3 pt-3" onClick={() => setOpen(false)}>
              <AuthNav />
            </div>
          </div>
        </nav>
      )}
    </header>
  )
}

function MoreMenu() {
  const location = useLocation()
  const [open, setOpen] = useState(false)
  const active = SECONDARY.some((n) => (n.end ? location.pathname === n.to : location.pathname.startsWith(n.to)))
  return (
    <div className="relative" onBlur={(e) => !e.currentTarget.contains(e.relatedTarget) && setOpen(false)}>
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((o) => !o)}
        className={`rounded-md px-2.5 py-2 text-sm transition-colors ${active ? 'bg-white/6 text-paper' : 'text-sage-300 hover:text-paper'}`}
      >
        More ▾
      </button>
      {open && (
        <div className="glass absolute right-0 mt-2 flex w-40 flex-col rounded-xl p-1.5 shadow-xl">
          {SECONDARY.map((n) => (
            <NavItem key={n.to} {...n} onClick={() => setOpen(false)} />
          ))}
        </div>
      )}
    </div>
  )
}

function NavItem({ to, label, end, onClick }: { to: string; label: string; end: boolean; onClick?: () => void }) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onClick}
      className={({ isActive }) =>
        `rounded-md px-2.5 py-2 text-sm transition-colors ${
          isActive ? 'bg-white/6 text-paper' : 'text-sage-300 hover:text-paper'
        }`
      }
    >
      {label}
    </NavLink>
  )
}

function AuthNav() {
  const { status, user } = useAuth()
  if (status === 'unconfigured' || status === 'loading') return null
  if (status === 'signed_in') {
    return (
      <NavLink
        to="/account"
        className="inline-flex max-w-[11rem] items-center gap-2 rounded-full border border-white/10 px-3 py-1.5 text-xs text-sage-100 transition-colors hover:border-white/25"
      >
        <span aria-hidden className="grid h-5 w-5 place-items-center rounded-full bg-moss-500/30 text-[0.65rem] uppercase text-moss-300">
          {user?.email?.[0] ?? '?'}
        </span>
        <span className="truncate">{user?.email}</span>
      </NavLink>
    )
  }
  return (
    <NavLink
      to="/login"
      className="rounded-full bg-paper px-4 py-1.5 text-xs font-medium text-ink-900 transition-transform hover:-translate-y-px"
    >
      Sign in
    </NavLink>
  )
}

/** Live backend connectivity indicator, polled via TanStack Query. */
function ApiIndicator() {
  const { isSuccess, isError, isPending } = useHealth()
  const tone = isSuccess ? 'ok' : isError ? 'alert' : 'muted'
  const text = isSuccess ? 'All systems operational' : isError ? 'Service unavailable' : 'Checking status'
  return (
    <NavLink to="/status" className="inline-flex items-center gap-2 text-xs text-sage-400 hover:text-sage-200">
      <StatusDot tone={tone} pulse={isSuccess || isPending} />
      <span aria-live="polite">{text}</span>
    </NavLink>
  )
}

function Footer() {
  return (
    <footer className="border-t border-white/5">
      <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-8 text-xs text-sage-400 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <span className="font-mono tracking-wider">© AGRI-SENSE · v1.0.0</span>
        <span>Sensor data comes from a simulator and is labelled “simulated” wherever it appears.</span>
        <ApiIndicator />
      </div>
    </footer>
  )
}
