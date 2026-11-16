import { Suspense, type ReactNode } from 'react'
import { createBrowserRouter, type RouteObject } from 'react-router'
import { AppShell } from '@/components/layout/AppShell'
import { FullPageSpinner, RequireAuth } from '@/features/auth/RequireAuth'
import {
  AlertsPage,
  AnalyticsPage,
  DashboardPage,
  FarmSettingsPage,
  FarmsPage,
  FederatedPage,
  IrrigationPage,
  LivePage,
  NutrientsPage,
  RecommendationsPage,
  ReportPage,
  SoilPage,
  TwinPage,
  VisionPage,
  YieldPage,
  GrowthPage,
  DiseaseReportPage,
} from './lazy-pages'
import { AccountPage } from '@/pages/AccountPage'
import { LoginPage, SignupPage } from '@/pages/AuthPages'
import { LandingPage } from '@/pages/LandingPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { StatusPage } from '@/pages/StatusPage'

/** Signed-in page: requires a session, and shows a spinner while its code chunk downloads. */
function guarded(page: ReactNode) {
  return (
    <RequireAuth>
      <Suspense fallback={<FullPageSpinner />}>{page}</Suspense>
    </RequireAuth>
  )
}

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <LandingPage /> },
      { path: 'status', element: <StatusPage /> },
      { path: 'login', element: <LoginPage /> },
      { path: 'signup', element: <SignupPage /> },
      { path: 'account', element: guarded(<AccountPage />) },
      { path: 'dashboard', element: guarded(<DashboardPage />) },
      { path: 'twin', element: guarded(<TwinPage />) },
      { path: 'soil', element: guarded(<SoilPage />) },
      { path: 'vision', element: guarded(<VisionPage />) },
      { path: 'advice', element: guarded(<RecommendationsPage />) },
      { path: 'irrigation', element: guarded(<IrrigationPage />) },
      { path: 'nutrients', element: guarded(<NutrientsPage />) },
      { path: 'yield', element: guarded(<YieldPage />) },
      { path: 'growth', element: guarded(<GrowthPage />) },
      { path: 'vision/disease-checks/:checkId/report', element: guarded(<DiseaseReportPage />) },
      { path: 'federated', element: guarded(<FederatedPage />) },
      { path: 'analytics', element: guarded(<AnalyticsPage />) },
      { path: 'alerts', element: guarded(<AlertsPage />) },
      { path: 'reports/:reportId', element: guarded(<ReportPage />) },
      { path: 'farms', element: guarded(<FarmsPage />) },
      { path: 'farms/:farmId', element: guarded(<FarmSettingsPage />) },
      { path: 'live', element: guarded(<LivePage />) },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]

export const createRouter = () => createBrowserRouter(routes)
