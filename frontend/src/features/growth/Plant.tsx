import { motion, useReducedMotion } from 'framer-motion'
import type { StageKey } from './api'

/**
 * Illustration of a plant at one of the eight stages. Which stage is drawn comes from the API (stage list and,
 * for a crop cycle, today's position); this component only draws it. `form` follows the crop category.
 */
export function PlantIllustration({ stage, form, label }: { stage: StageKey; form: 'cereal' | 'fruit' | 'tuber' | 'other'; label: string }) {
  const reduce = useReducedMotion()
  const i = ['seed', 'germination', 'seedling', 'vegetative', 'flowering', 'formation', 'maturity', 'harvest'].indexOf(stage)
  const height = [0, 18, 42, 92, 120, 130, 128, 0][i] ?? 0
  const leaf = stage === 'maturity' ? '#b49a3c' : '#5f9a3e'
  const t = { duration: reduce ? 0 : 0.6, ease: 'easeOut' as const }
  const leaves = stage === 'seedling' ? 1 : stage === 'germination' || stage === 'seed' || stage === 'harvest' ? 0 : 4
  return (
    <svg viewBox="0 0 200 220" role="img" aria-label={label} className="h-64 w-full">
      <defs>
        <linearGradient id="soil" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#6b4a2f" />
          <stop offset="1" stopColor="#3d2a1b" />
        </linearGradient>
      </defs>
      <rect x="0" y="170" width="200" height="50" fill="url(#soil)" />
      {[18, 52, 90, 128, 166].map((x) => <circle key={x} cx={x} cy={185 + (x % 7)} r="1.6" fill="#8a6a4a" opacity="0.6" />)}

      {/* seed below ground until the shoot takes over */}
      {(stage === 'seed' || stage === 'germination') && <motion.ellipse cx="100" cy="182" rx="7" ry="4.5" fill="#d8b878" initial={false} animate={{ opacity: 1 }} transition={t} />}
      {stage === 'germination' && <motion.path d="M100 182 q-4 8 -8 14 M100 182 q4 9 7 15" stroke="#e8dcc0" strokeWidth="1.5" fill="none" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={t} />}

      {/* stem */}
      {height > 0 && (
        <motion.line x1="100" y1="170" x2="100" initial={false} animate={{ y2: 170 - height }} stroke={stage === 'maturity' ? '#9c8a40' : '#4f8a34'} strokeWidth={form === 'cereal' ? 3 : 4} strokeLinecap="round" transition={t} />
      )}

      {/* leaves */}
      {Array.from({ length: leaves }).map((_, k) => {
        const y = 170 - height * (0.35 + 0.18 * k)
        const side = k % 2 ? 1 : -1
        const len = form === 'cereal' ? 34 : 26
        return (
          <motion.path key={k} d={`M100 ${y} q ${side * len * 0.6} -14 ${side * len} -4 q ${-side * len * 0.5} 10 ${-side * len} 4`} fill={leaf} initial={{ scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} style={{ originX: '100px', originY: `${y}px` }} transition={{ ...t, delay: reduce ? 0 : k * 0.08 }} />
        )
      })}
      {stage === 'seedling' && <motion.path d="M100 128 q -14 -10 -20 0 q 10 6 20 0 M100 128 q 14 -10 20 0 q -10 6 -20 0" fill={leaf} initial={{ scale: 0 }} animate={{ scale: 1 }} style={{ originX: '100px', originY: '128px' }} transition={t} />}

      {/* flowers */}
      {stage === 'flowering' && [0, 1, 2].map((k) => (
        <motion.circle key={k} cx={100 + (k - 1) * 14} cy={170 - height - 4 + Math.abs(k - 1) * 8} r="5" fill={form === 'cereal' ? '#e6d48a' : '#f2d54a'} initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ ...t, delay: reduce ? 0 : 0.2 + k * 0.1 }} />
      ))}

      {/* yield organs */}
      {(stage === 'formation' || stage === 'maturity') && form === 'fruit' && [0, 1, 2].map((k) => (
        <motion.circle key={k} cx={100 + (k - 1) * 16} cy={170 - height * 0.55 + k * 6} r={stage === 'maturity' ? 8 : 6} fill={stage === 'maturity' ? '#c8432b' : '#7fae4a'} initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ ...t, delay: reduce ? 0 : k * 0.1 }} />
      ))}
      {(stage === 'formation' || stage === 'maturity') && form === 'cereal' && (
        <motion.ellipse cx="100" cy={170 - height - 10} rx="6" ry="16" fill={stage === 'maturity' ? '#d6b45a' : '#a9c46a'} initial={{ scaleY: 0 }} animate={{ scaleY: 1 }} transition={t} />
      )}
      {(stage === 'formation' || stage === 'maturity') && form === 'tuber' && [0, 1].map((k) => (
        <motion.ellipse key={k} cx={88 + k * 24} cy={190 + k * 4} rx={stage === 'maturity' ? 11 : 8} ry={stage === 'maturity' ? 8 : 6} fill="#c9a46a" initial={{ scale: 0 }} animate={{ scale: 1 }} transition={t} />
      ))}

      {/* harvest */}
      {stage === 'harvest' && (
        <motion.g initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={t}>
          <path d="M70 168 h60 l-6 -26 h-48 z" fill="#8c5a2e" />
          {[0, 1, 2, 3].map((k) => <circle key={k} cx={84 + k * 10} cy={140} r="6" fill={form === 'cereal' ? '#d6b45a' : form === 'tuber' ? '#c9a46a' : '#c8432b'} />)}
        </motion.g>
      )}
    </svg>
  )
}
