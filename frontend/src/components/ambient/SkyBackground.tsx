import { useEffect, useRef } from 'react'
import { usePrefersReducedMotion } from '@/lib/use-reduced-motion'

/**
 * Atmospheric background: dawn sky gradient, slow drifting clouds,
 * sparse floating particles (pollen/dust) and a wind-swayed grass line.
 * CSS/SVG plus one small canvas. The canvas pauses when the tab is hidden
 * and renders a single still frame when the user prefers reduced motion.
 */
export function SkyBackground({ className = '' }: { className?: string }) {
  return (
    <div aria-hidden className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}>
      <div className="absolute inset-0 bg-[radial-gradient(120%_80%_at_70%_0%,#2b4a4f_0%,#162a24_45%,#0d1712_80%)]" />
      <div className="absolute inset-x-0 bottom-0 h-2/3 bg-[radial-gradient(60%_50%_at_30%_100%,rgb(216_196_138/0.16),transparent_70%)]" />
      <Clouds />
      <Particles />
      <GrassLine />
      <div className="absolute inset-0 bg-[linear-gradient(to_bottom,transparent_60%,#0d1712_100%)]" />
    </div>
  )
}

const CLOUDS = [
  { top: '8%', scale: 1.2, anim: 'animate-drift-slow', delay: '-20s' },
  { top: '22%', scale: 0.8, anim: 'animate-drift', delay: '-55s' },
  { top: '14%', scale: 1, anim: 'animate-drift-slow', delay: '-95s' },
]

function Clouds() {
  return (
    <div className="absolute inset-x-0 top-0 h-1/2 opacity-40">
      {CLOUDS.map((c, i) => (
        <svg
          key={i}
          viewBox="0 0 200 60"
          className={`absolute left-0 w-[28rem] ${c.anim}`}
          style={{ top: c.top, animationDelay: c.delay, scale: String(c.scale) }}
        >
          <defs>
            <filter id={`cloud-blur-${i}`}>
              <feGaussianBlur stdDeviation="6" />
            </filter>
          </defs>
          <g filter={`url(#cloud-blur-${i})`} fill="#cfe3ea" fillOpacity="0.35">
            <ellipse cx="60" cy="38" rx="50" ry="14" />
            <ellipse cx="105" cy="30" rx="42" ry="18" />
            <ellipse cx="145" cy="40" rx="40" ry="12" />
          </g>
        </svg>
      ))}
    </div>
  )
}

function Particles() {
  const ref = useRef<HTMLCanvasElement>(null)
  const reduced = usePrefersReducedMotion()

  useEffect(() => {
    const canvas = ref.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return

    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    let w = 0
    let h = 0
    const resize = () => {
      w = canvas.clientWidth
      h = canvas.clientHeight
      canvas.width = w * dpr
      canvas.height = h * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()

    const count = Math.round(Math.min(60, (w * h) / 22000))
    const ps = Array.from({ length: count }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      r: Math.random() * 1.4 + 0.4,
      vx: Math.random() * 0.25 + 0.05,
      vy: (Math.random() - 0.5) * 0.08,
      a: Math.random() * 0.5 + 0.15,
    }))

    const draw = () => {
      ctx.clearRect(0, 0, w, h)
      for (const p of ps) {
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(226, 207, 152, ${p.a})`
        ctx.fill()
      }
    }

    let raf = 0
    const tick = () => {
      for (const p of ps) {
        p.x += p.vx
        p.y += p.vy
        if (p.x > w + 4) p.x = -4
        if (p.y < -4) p.y = h + 4
        if (p.y > h + 4) p.y = -4
      }
      draw()
      raf = requestAnimationFrame(tick)
    }

    const start = () => {
      cancelAnimationFrame(raf)
      if (reduced || document.hidden) draw()
      else raf = requestAnimationFrame(tick)
    }
    start()

    window.addEventListener('resize', resize)
    document.addEventListener('visibilitychange', start)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
      document.removeEventListener('visibilitychange', start)
    }
  }, [reduced])

  return <canvas ref={ref} className="absolute inset-0 h-full w-full" />
}

const BLADES = Array.from({ length: 90 }, (_, i) => ({
  x: (i / 90) * 1200 + ((i * 37) % 11),
  hgt: 18 + ((i * 53) % 26),
  lean: ((i * 29) % 9) - 4,
  delay: `${-((i * 0.37) % 6)}s`,
  tone: i % 3 === 0 ? '#4f7f43' : '#2a4232',
}))

function GrassLine() {
  return (
    <svg viewBox="0 0 1200 60" preserveAspectRatio="none" className="absolute inset-x-0 bottom-0 h-16 w-full">
      {BLADES.map((b, i) => (
        <path
          key={i}
          d={`M${b.x} 60 Q${b.x + b.lean / 2} ${60 - b.hgt / 2} ${b.x + b.lean} ${60 - b.hgt}`}
          stroke={b.tone}
          strokeWidth="2"
          fill="none"
          className="animate-sway"
          style={{ animationDelay: b.delay, transformBox: 'fill-box', transformOrigin: 'bottom' }}
        />
      ))}
    </svg>
  )
}
