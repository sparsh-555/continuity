import { Outlet, useLocation } from 'react-router'

import { PcbBackground } from './PcbBackground'
import { ownsTheViewport } from './workspace'

export function AppFrame() {
  const location = useLocation()
  const isWorkspace = ownsTheViewport(location.pathname)

  return (
    // The workspace is locked to the viewport, and `AppShell` locks it with `100dvh`.
    // This wrapper must use the *same* unit: `min-h-screen` is `100vh`, which is 23px
    // taller than `100dvh` here, and the taller outer box reintroduced exactly the page
    // scroll the lock exists to remove — the header slid under the browser chrome again.
    <div className={isWorkspace ? 'h-[100dvh] overflow-hidden' : 'min-h-screen isolate'}>
      {isWorkspace ? null : <PcbBackground pauseAnimation={location.pathname === '/memory'} />}
      <div className={isWorkspace ? undefined : 'relative z-10'}>
        <Outlet />
      </div>
    </div>
  )
}
