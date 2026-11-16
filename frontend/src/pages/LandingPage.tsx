import { motion } from 'framer-motion'
import { Link } from 'react-router'
import { SkyBackground } from '@/components/ambient/SkyBackground'
import { Pill, SectionHeading } from '@/components/ui/primitives'
import { VISION_LOOP } from '@/config/roadmap'

const ease = [0.22, 1, 0.36, 1] as const

const PILLARS = [
  {
    k: '01',
    title: 'Sense the field',
    body: 'Soil moisture, pH, NPK, temperature, humidity, light, rainfall, leaf wetness and water level — streamed per zone and stored as time series.',
    tags: ['IoT', 'SSE', 'ESP32-ready'],
  },
  {
    k: '02',
    title: 'Understand the crop',
    body: 'Computer vision for plants, leaves and produce; disease detection and yield models that show confidence, key factors and their limitations.',
    tags: ['CV', 'ONNX', 'Explainable'],
  },
  {
    k: '03',
    title: 'Act with less',
    body: 'Irrigation and fertilizer recommendations that aim to cut water and chemical use, with every action logged so models can learn from outcomes.',
    tags: ['Irrigation', 'Nutrients', 'Federated'],
  },
]

export function LandingPage() {
  return (
    <>
      {/* Hero */}
      <section className="relative isolate -mt-16 flex min-h-[92dvh] items-end overflow-hidden pt-16">
        <SkyBackground />
        <div className="relative mx-auto w-full max-w-7xl px-4 pb-24 sm:px-6 sm:pb-32">
          <motion.p
            className="eyebrow"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease }}
          >
            Agricultural intelligence platform
          </motion.p>
          <motion.h1
            className="mt-5 max-w-4xl font-display text-5xl font-light leading-[1.02] tracking-tight text-paper sm:text-7xl lg:text-8xl"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1, ease, delay: 0.1 }}
          >
            A farm that <em className="font-normal text-wheat-300">sees</em>, senses,
            <br className="hidden sm:block" /> and learns.
          </motion.h1>
          <motion.p
            className="mt-7 max-w-xl text-lg leading-relaxed text-sage-200"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1, ease, delay: 0.25 }}
          >
            AGRI-SENSE joins field sensors, plant vision, weather and a 3D digital twin into one explainable system for
            growing more with less water and fewer chemicals.
          </motion.p>
          <motion.div
            className="mt-10 flex flex-wrap items-center gap-3"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1, delay: 0.45 }}
          >
            <Link
              to="/dashboard"
              className="group inline-flex items-center gap-2 rounded-full bg-paper px-5 py-2.5 text-sm font-medium text-ink-900 transition-transform hover:-translate-y-px"
            >
              Open the dashboard
              <span aria-hidden className="transition-transform group-hover:translate-x-0.5">→</span>
            </Link>
            <Link
              to="/vision?tab=disease"
              className="inline-flex items-center gap-2 rounded-full border border-white/15 px-5 py-2.5 text-sm text-sage-100 transition-colors hover:border-white/30"
            >
              Check a leaf
            </Link>
          </motion.div>
        </div>
      </section>

      {/* Vision loop */}
      <section className="mx-auto max-w-7xl px-4 py-24 sm:px-6">
        <SectionHeading eyebrow="The loop" title="Seven steps, one continuous cycle.">
          Every feature in AGRI-SENSE maps to a step in this loop. Outcomes from the field feed back into the models, so
          recommendations improve season over season.
        </SectionHeading>
        <ol className="mt-14 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-white/8 bg-white/5 sm:grid-cols-4 lg:grid-cols-7">
          {VISION_LOOP.map((step, i) => (
            <motion.li
              key={step}
              className="bg-ink-900 p-5"
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ duration: 0.6, ease, delay: i * 0.06 }}
            >
              <span className="font-mono text-xs text-sage-400">{String(i + 1).padStart(2, '0')}</span>
              <p className="mt-6 font-display text-xl text-paper">{step}</p>
            </motion.li>
          ))}
        </ol>
      </section>

      {/* Pillars */}
      <section className="border-y border-white/5 bg-ink-950/40">
        <div className="mx-auto grid max-w-7xl gap-6 px-4 py-24 sm:px-6 lg:grid-cols-3">
          {PILLARS.map((p, i) => (
            <motion.article
              key={p.k}
              className="glass rounded-2xl p-7"
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ duration: 0.7, ease, delay: i * 0.08 }}
            >
              <span className="font-mono text-xs text-wheat-400">{p.k}</span>
              <h3 className="mt-5 font-display text-2xl text-paper">{p.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-sage-300">{p.body}</p>
              <div className="mt-6 flex flex-wrap gap-2">
                {p.tags.map((t) => (
                  <Pill key={t}>{t}</Pill>
                ))}
              </div>
            </motion.article>
          ))}
        </div>
      </section>

    </>
  )
}
