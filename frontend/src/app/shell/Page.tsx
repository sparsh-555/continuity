import type { ReactNode } from 'react'
import { useNavigate } from 'react-router'

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
}: {
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
  /** Where the back arrow goes. Omitted on the screens the rail reaches directly. */
  back?: { to: string; label: string }
  children: ReactNode
  width?: 'wide' | 'reading'
}) {
  const navigate = useNavigate()

  return (
    <div className="bg-transparent min-h-screen text-on-background font-body-md antialiased">
      <header className="flex items-center justify-between w-full px-lg h-12 bg-surface-container-low border-b border-outline-variant shadow-[0_1px_0_0_rgba(255,255,255,0.05)]">
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
        <Wordmark />
      </header>

      <main
        className={`min-h-[calc(100vh-48px)] ${
          width === 'wide' ? 'max-w-[1200px]' : 'max-w-[900px]'
        } mx-auto px-lg py-xl flex flex-col gap-lg`}
      >
        <div className="flex items-start justify-between gap-md border-b border-outline-variant pb-sm">
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
