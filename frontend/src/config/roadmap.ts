export type PhaseStatus = 'done' | 'in_progress' | 'planned'

export interface Phase {
  id: number
  title: string
  status: PhaseStatus
}

/** Single source of truth for build progress shown in the UI. Update as phases are approved. */
export const PHASES: Phase[] = [
  { id: 1, title: 'Project foundation', status: 'done' },
  { id: 2, title: 'Database + migrations', status: 'done' },
  { id: 3, title: 'Backend REST API', status: 'done' },
  { id: 4, title: 'Authentication', status: 'done' },
  { id: 5, title: 'Real-time sensor simulator', status: 'done' },
  { id: 6, title: 'Main dashboard', status: 'done' },
  { id: 7, title: '3D digital twin', status: 'done' },
  { id: 8, title: 'Soil intelligence', status: 'done' },
  { id: 9, title: 'Plant & produce recognition', status: 'done' },
  { id: 10, title: 'Disease detection', status: 'done' },
  { id: 11, title: 'AI recommendations', status: 'done' },
  { id: 12, title: 'Smart irrigation', status: 'done' },
  { id: 13, title: 'Fertilizer & chemical reduction', status: 'done' },
  { id: 14, title: 'Yield prediction', status: 'done' },
  { id: 15, title: 'Federated learning', status: 'done' },
  { id: 16, title: 'Analytics + reports', status: 'done' },
  { id: 17, title: 'Alerts', status: 'done' },
  { id: 18, title: 'Testing', status: 'done' },
  { id: 19, title: 'Security + performance', status: 'done' },
  { id: 20, title: 'Deployment', status: 'done' },
  { id: 21, title: 'Documentation + demo', status: 'done' },
]

export const VISION_LOOP = ['See', 'Sense', 'Analyze', 'Predict', 'Recommend', 'Act', 'Learn'] as const

export interface ModuleDef {
  slug: string
  title: string
  phase: number
  summary: string
  /** App route once the module is built. */
  route?: string
}

/** Product modules; each becomes a real route once its phase is built. */
export const MODULES: ModuleDef[] = [
  { slug: 'dashboard', title: 'Farm Dashboard', phase: 6, summary: 'Live sensor streams, weather and farm health at a glance.', route: '/dashboard' },
  { slug: 'twin', title: 'Digital Twin', phase: 7, summary: 'An interactive 3D model of the farm, driven by real application data.', route: '/twin' },
  { slug: 'soil', title: 'Soil Intelligence', phase: 8, summary: 'FAO-56 root-zone water balance, pH, NPK and salinity per zone, with explainable scoring.', route: '/soil' },
  { slug: 'vision', title: 'Plant Vision', phase: 9, summary: 'Recognise 25 fruit, vegetable and crop classes from a photo, with a heat-map of what the model used.', route: '/vision' },
  { slug: 'disease', title: 'Disease Detection', phase: 10, summary: 'Leaf-disease screening with two models, crop routing, refusal rules, confidence and limits.', route: '/vision?tab=disease' },
  { slug: 'advice', title: 'Recommendations', phase: 11, summary: 'Explainable advice from soil, weather, disease checks and sensors, with evidence, confidence and limits.', route: '/advice' },
  { slug: 'irrigation', title: 'Smart Irrigation', phase: 12, summary: 'Seven-day, rain-aware irrigation plans from the FAO-56 water balance, with scheduling and water-use tracking.', route: '/irrigation' },
  { slug: 'nutrients', title: 'Nutrients & Chemicals', phase: 13, summary: 'Soil-test-adjusted fertilizer plans, a pre-spray check and pesticide-use tracking per crop cycle.', route: '/nutrients' },
  { slug: 'growth', title: 'Crop Growth', phase: 14, summary: "Seed to harvest in eight stages from FAO-56 stage lengths, with where each zone's crop is today.", route: '/growth' },
  { slug: 'yield', title: 'Yield Prediction', phase: 14, summary: 'Water-limited yield range (FAO-33) from moisture history, with back-testing against real harvests.', route: '/yield' },
  { slug: 'federated', title: 'Federated Learning', phase: 15, summary: 'FedAvg across opted-in farms: each farm trains on its own data, only model weights are shared.', route: '/federated' },
  { slug: 'alerts', title: 'Alerts', phase: 17, summary: 'Automatic alerts from soil, sensors, forecast and disease checks: no duplicates, auto-resolve, live updates.', route: '/alerts' },
  { slug: 'analytics', title: 'Analytics & Reports', phase: 16, summary: 'Period analytics, sustainability indicators vs the previous period, saved report snapshots, CSV and print.', route: '/analytics' },
]

export function findModule(slug: string | undefined): ModuleDef | undefined {
  return MODULES.find((m) => m.slug === slug)
}
