import { createBrowserRouter, Navigate } from 'react-router';
import MainLayout from './layouts/MainLayout';
import AuthLayout from './layouts/AuthLayout';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';

import HomePage from './pages/HomePage';
import DashboardPage from './pages/DashboardPage';
import RecordsPage from './pages/RecordsPage';
import UserManagementPage from './pages/UserManagementPage';
import ProfilePage from './pages/ProfilePage';
import AnalyticsPage from './pages/AnalyticsPage';
import SettingsPage from './pages/SettingsPage';
import StaffRecordsPage from './pages/StaffRecordsPage';
import LLMAssistantPage from './pages/LLMAssistantPage';
import NotFoundPage from './pages/NotFoundPage';
import ProtectedRoute from './components/ProtectedRoute';
import DocumentsPage from '@/features/documents/pages/DocumentsPage';

/**
 * Resolve a Capacitor-safe router basename from the current location.
 *
 * In the packaged Android app (Capacitor local server) the SPA is served at
 * the server root (`http://localhost`), so the basename must be `/`.
 * On GitHub Pages the app lives under a sub-path (e.g. `/health-react`), so we
 * keep that prefix. Deriving it from the live pathname lets a single build work
 * in both contexts without hard-coding a deployment path.
 */
function resolveBasename() {
  if (typeof window === 'undefined') return '/';
  const { pathname } = window.location;
  if (!pathname || pathname === '/') return '/';
  if (pathname.endsWith('/')) {
    // e.g. "/health-react/" → "/health-react" (root "/" is handled above)
    return pathname.slice(0, -1);
  }
  // e.g. "/index.html" (Capacitor) → drop the trailing file segment → "/"
  const trimmed = pathname.replace(/\/[^/]*$/, '');
  return trimmed || '/';
}

export const router = createBrowserRouter(
  [
    {
      path: '/login',
      element: <AuthLayout />,
      children: [{ index: true, element: <LoginPage /> }],
    },
    {
      path: '/register',
      element: <AuthLayout />,
      children: [{ index: true, element: <RegisterPage /> }],
    },

    {
      path: '/',
      element: (
        <ProtectedRoute>
          <MainLayout />
        </ProtectedRoute>
      ),
      children: [
        { index: true, element: <Navigate to="/home" replace /> },
        { path: 'home', element: <HomePage /> },
        {
          path: 'dashboard',
          element: (
            <ProtectedRoute requiredRole="Admin">
              <DashboardPage />
            </ProtectedRoute>
          ),
        },
        { path: 'records', element: <RecordsPage /> },
        {
          path: 'analytics',
          element: (
            <ProtectedRoute requiredRole="Admin">
              <AnalyticsPage />
            </ProtectedRoute>
          ),
        },
        { path: 'profile', element: <ProfilePage /> },
        { path: 'settings', element: <SettingsPage /> },
        {
          path: 'admin/users',
          element: (
            <ProtectedRoute requiredRole="Admin">
              <UserManagementPage />
            </ProtectedRoute>
          ),
        },
        {
          path: 'staff/records',
          element: (
            <ProtectedRoute requiredRole={['Staff', 'Admin']}>
              <StaffRecordsPage />
            </ProtectedRoute>
          ),
        },
        { path: 'llm', element: <LLMAssistantPage /> },
        { path: 'documents', element: <DocumentsPage /> },
      ],
    },
    {
      path: '*',
      element: <NotFoundPage />,
    },
  ],
  {
    basename: resolveBasename(),
  },
);

