import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router'

import { AuthProvider } from './app/hooks/useAuth'
import { RequireAuth } from './app/routes/RequireAuth'
import DesignRoute from './app/routes/design'
import { SignInRoute, SignUpRoute } from './app/routes/auth'
import LandingRoute from './app/routes/landing'
import LineRoute from './app/routes/line'
import LinesRoute from './app/routes/lines'
import MemoryRoute from './app/routes/memory'
import PolicyRoute from './app/routes/policy'
import ChangesRoute from './app/routes/changes'
import { AppFrame } from './app/shell/AppFrame'
import { AppShell } from './app/shell/AppShell'
import './index.css'

const router = createBrowserRouter([
  {
    element: <AppFrame />,
    children: [
      {
        path: '/',
        element: <LandingRoute />,
      },
      {
        path: '/login',
        element: <SignInRoute />,
      },
      {
        path: '/signup',
        element: <SignUpRoute />,
      },
      {
        element: <AppShell />,
        children: [
          {
            path: '/lines',
            element: (
              <RequireAuth>
                <LinesRoute />
              </RequireAuth>
            ),
          },
          {
            path: '/lines/:lineId',
            element: (
              <RequireAuth>
                <LineRoute />
              </RequireAuth>
            ),
          },
          {
            path: '/changes',
            element: (
              <RequireAuth>
                <ChangesRoute />
              </RequireAuth>
            ),
          },
          {
            path: '/memory',
            element: (
              <RequireAuth>
                <MemoryRoute />
              </RequireAuth>
            ),
          },
          {
            path: '/policy',
            element: (
              <RequireAuth>
                <PolicyRoute />
              </RequireAuth>
            ),
          },
          {
            path: '/design',
            element: <DesignRoute />,
          },
          {
            // Guarded, unlike the bare /design above: a line belongs to somebody. Without
            // this a signed-out visitor gets the whole workspace shell — the API refuses every
            // call behind it, so nothing leaks, but it renders a broken page where a redirect
            // belongs.
            path: '/design/:lineId',
            element: (
              <RequireAuth>
                <DesignRoute />
              </RequireAuth>
            ),
          },
        ],
      },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  </StrictMode>,
)
