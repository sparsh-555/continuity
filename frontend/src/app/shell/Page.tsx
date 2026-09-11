import type { ReactNode } from 'react'
import { useNavigate } from 'react-router'

import { useAuth } from '../hooks/useAuth'
import { departmentLabel } from '../review/Departments'
import { Wordmark } from './Wordmark'

/**
 * The chrome every screen inside the rail wears.
 *
 * `/lines` had this and nothing else did, so the change notices and the substitution matrix
 * rendered jammed into the top-left of the viewport with no header and no container — three
 * capabilities that look like three products. The rail is not chrome; it is navigation. This
 * is the page.
 *
 * Keep this the only definition, for the same reason `Wordmark` is the only wordmark: a
 * layout copied inline is a layout that drifts.
 */
export function Page({
  title,
  subtitle,
  actions,
  back,
  children,
  width = 'wide',
  fill = false,
}: {
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
  /** Where the back arrow goes. Omitted on the screens the rail reaches directly. */
  back?: { to: string; label: string }
  children: ReactNode
  width?: 'wide' | 'reading'
  /** Hold the viewport instead of growing with the content.
   *
   *  The screens in `ownsTheViewport` are sets of panes: the header stays where it is and
   *  each pane scrolls inside itself, which is what lets a notice sit beside the review it
   *  raised instead of a screen above it. A page that grows is the other shape and is still
   *  the default; this is opted into, not inherited from the route, so that a screen says
   *  which of the two it is rather than being quietly changed by where it is mounted. */
  fill?: boolean
}) {
  const navigate = useNavigate()
  const { user } = useAuth()

  return (
    <div
      className={`text-on-background font-body-md antialiased ${
        fill ? 'h-full flex flex-col overflow-hidden bg-background' : 'bg-transparent min-h-screen'
      }`}
    >
      <header className="flex items-center justify-between w-full px-lg h-12 shrink-0 bg-surface-container-low border-b border-outline-variant shadow-[0_1px_0_0_rgba(255,255,255,0.05)]">
        {back ? (
          <button
            className="flex items-center gap-xs font-label-caps text-label-caps uppercase text-on-surface-variant hover:text-on-surface transition-colors"
            onClick={() => navigate(back.to)}
            type="button"
          >
            <span className="material-symbols-outlined text-[18px]">arrow_back</span>
            {back.label}
          </button>
        ) : (
          <span />
        )}
        <div className="flex items-center gap-md">
          {/* **Whose eyes these are, on every page the rail reaches.** Four desks are
              demonstrated from one browser, and the documented failure of a multi-persona
              demonstration is the audience losing track of which one is on screen. The rail's
              four-letter chip answers it at the corner; this says it in words, in the header,
              where the eye already is. Deliberately not a colour: green, amber, violet and
              cyan already mean satisfied, accepted, changed and working here. */}
          {user?.roles.length ? (
            <span className="font-data-tabular text-[10px] px-sm py-0.5 border border-outline-variant rounded text-on-surface-variant uppercase">
              {user.roles.map(departmentLabel).join(' + ')}
            </span>
          ) : null}
          <Wordmark />
        </div>
      </header>

      <main
        className={`${fill ? 'flex-1 w-full min-h-0 overflow-hidden py-md' : 'min-h-[calc(100vh-48px)] py-xl'} ${
          fill ? 'max-w-none' : width === 'wide' ? 'max-w-[1200px]' : 'max-w-[900px]'
        } mx-auto px-lg flex flex-col gap-md`}
      >
        <div className="flex items-start justify-between gap-md border-b border-outline-variant pb-sm shrink-0">
          <div className="min-w-0">
            <h1 className="font-label-caps text-label-caps tracking-[0.1em] uppercase text-on-surface">
              {title}
            </h1>
            {subtitle ? (
              <div className="font-data-tabular text-[11px] text-on-surface-variant mt-1">
                {subtitle}
              </div>
            ) : null}
          </div>
          {actions ? <div className="flex items-center gap-sm shrink-0">{actions}</div> : null}
        </div>

        {children}
      </main>
    </div>
  )
}
