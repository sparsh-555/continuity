import { Outlet, useLocation } from 'react-router'

import { NoticeArrivalProvider } from '../hooks/useNoticeArrivals'
import { SideRail } from './SideRail'
import { ownsTheViewport } from './workspace'

export function AppShell() {
  const location = useLocation()
  const isWorkspace = ownsTheViewport(location.pathname)

  return (
    <NoticeArrivalProvider>
      <div className={isWorkspace ? 'h-[100dvh] overflow-hidden bg-background text-on-background' : 'min-h-screen bg-transparent text-on-background'}>
        <SideRail />
        <div className={isWorkspace ? 'ml-16 h-full w-[calc(100%-4rem)] overflow-hidden' : 'ml-16 min-h-screen w-[calc(100%-4rem)]'}>
          <div className={isWorkspace ? 'h-full overflow-hidden' : 'app-page-transition'} key={location.pathname}>
            <Outlet />
          </div>
        </div>
      </div>
    </NoticeArrivalProvider>
  )
}
