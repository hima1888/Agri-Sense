import { lazy } from 'react'

/**
 * Code-split pages: each signed-in page is downloaded when first opened, so the landing page and sign-in load
 * only the app shell. three.js + React Three Fiber (the twin) and Recharts stay out of the first download.
 */
const named = <K extends string>(load: () => Promise<Record<K, React.ComponentType>>, key: K) =>
  lazy(() => load().then((m) => ({ default: m[key] })))

export const TwinPage = lazy(() => import('@/pages/TwinPage'))
export const DashboardPage = named(() => import('@/pages/DashboardPage'), 'DashboardPage')
export const LivePage = named(() => import('@/pages/LivePage'), 'LivePage')
export const SoilPage = named(() => import('@/pages/SoilPage'), 'SoilPage')
export const VisionPage = named(() => import('@/pages/VisionPage'), 'VisionPage')
export const RecommendationsPage = named(() => import('@/pages/RecommendationsPage'), 'RecommendationsPage')
export const IrrigationPage = named(() => import('@/pages/IrrigationPage'), 'IrrigationPage')
export const NutrientsPage = named(() => import('@/pages/NutrientsPage'), 'NutrientsPage')
export const YieldPage = named(() => import('@/pages/YieldPage'), 'YieldPage')
export const GrowthPage = named(() => import('@/pages/GrowthPage'), 'GrowthPage')
export const FederatedPage = named(() => import('@/pages/FederatedPage'), 'FederatedPage')
export const AnalyticsPage = named(() => import('@/pages/AnalyticsPage'), 'AnalyticsPage')
export const ReportPage = named(() => import('@/pages/AnalyticsPage'), 'ReportPage')
export const AlertsPage = named(() => import('@/pages/AlertsPage'), 'AlertsPage')
export const FarmsPage = named(() => import('@/pages/FarmsPage'), 'FarmsPage')
export const FarmSettingsPage = named(() => import('@/pages/FarmsPage'), 'FarmSettingsPage')
export const DiseaseReportPage = named(() => import('@/pages/DiseaseReportPage'), 'DiseaseReportPage')
