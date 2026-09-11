import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'

import { useAuth } from '../hooks/useAuth'
import { useNewLine } from '../hooks/useNewLine'
import { DeskSwitcher } from './DeskSwitcher'
import { listWaitingDecisions } from '../lib/api'

const WAITING_MS = 10_000
/** How often the badge asks what this desk owes. Matches the arrivals poll on
 *  `/changes`, so the two do not drift into different ideas of 'recently'. */

type RailButtonProps = {
  active?: boolean
  /** How many things wait behind this entry. Zero draws nothing. */
  badge?: number
  disabled?: boolean
  icon: string
  label: string
  onClick: () => void
}

function RailButton({ active = false, badge = 0, disabled = false, icon, label, onClick }: RailButtonProps) {
  return (
    <button
      aria-current={active ? 'page' : undefined}
      aria-label={label}
      className={`w-10 h-10 rounded flex items-center justify-center group relative focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-container focus-visible:outline-offset-2 disabled:opacity-40 disabled:cursor-not-allowed ${
        active
          ? 'text-primary-container bg-surface-container-high border-l-2 border-primary-container'
          : 'text-on-surface-variant opacity-70 hover:text-primary hover:bg-surface-container transition-colors'
      }`}
      onClick={onClick}
      disabled={disabled}
      type="button"
    >
      <span
        className="material-symbols-outlined text-[20px]"
        style={active ? { fontVariationSettings: "'FILL' 1" } : undefined}
      >
        {icon}
      </span>
      {/* A count, not a dot: how many is the difference between glancing and opening. */}
      {badge > 0 ? (
        <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-tertiary-container text-[#001f24] font-data-tabular text-[10px] leading-4 text-center">
          {badge}
        </span>
      ) : null}
      <span className="pointer-events-none absolute left-[calc(100%+10px)] top-1/2 -translate-y-1/2 whitespace-nowrap bg-surface-container-high border border-outline-variant px-sm py-xs font-label-caps text-label-caps text-on-surface opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100 transition-opacity z-50">
        {label}
      </span>
    </button>
  )
}

export function SideRail() {
  const location = useLocation()
  const navigate = useNavigate()
  const { user, signOut } = useAuth()
  const [waiting, setWaiting] = useState(0)

  // What this desk owes, on the same ten seconds `/changes` watches for arrivals on. A
  // decision can be raised by somebody else's review, so the count changes without this
  // browser doing anything, and a badge that only updates on navigation is a badge that is
  // wrong for as long as somebody stays on one page.
  useEffect(() => {
    if (!user) return
    let alive = true
    const read = () => {
      listWaitingDecisions()
        .then((rows) => {
          if (alive) setWaiting(rows.filter((row) => row.mine.length > 0).length)
        })
        .catch(() => undefined)
    }
    read()
    const timer = setInterval(read, WAITING_MS)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [user, location.pathname])
  const { createNewLine, creating } = useNewLine()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const settingsRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const closeOnOutsidePointer = (event: MouseEvent) => {
      if (!settingsRef.current?.contains(event.target as Node)) {
        setSettingsOpen(false)
      }
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setSettingsOpen(false)
      }
    }
    document.addEventListener('mousedown', closeOnOutsidePointer)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('mousedown', closeOnOutsidePointer)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [])

  const handleSignOut = useCallback(async () => {
    await signOut()
    navigate('/login', { replace: true })
  }, [navigate, signOut])

  return (
    <nav aria-label="Primary navigation" className="fixed left-0 top-0 bottom-0 w-16 flex flex-col items-center py-md z-40 bg-surface-container-lowest dark:bg-surface-container-lowest border-r border-outline-variant transition-all duration-150 ease-in-out">
      <div className="flex flex-col gap-sm w-full items-center">
        <RailButton disabled={creating} icon="add" label="New product line" onClick={() => { createNewLine().catch(() => undefined) }} />
        <RailButton active={location.pathname === '/lines'} icon="folder_open" label="All product lines" onClick={() => navigate('/lines')} />
        {/* `grid_view` — a grid of candidates against product lines, which is what it is. */}
        {/* `change_circle` — the page is a change notice arriving, a change request written
            and a change applied, and `mark_email_unread` described only the first third. It
            was the icon `/notices` had, and it survived the rename by a week. */}
        <RailButton active={location.pathname === '/changes'} icon="change_circle" label="Changes" onClick={() => navigate('/changes')} />
        {/* `how_to_reg` — a person and a tick, which is what signing for a desk is. The
            badge is what this desk owes across every product line: three of the four people
            who must sign a substitution previously had no way to find it. */}
        <RailButton
          active={location.pathname === '/approvals'}
          badge={waiting}
          icon="how_to_reg"
          label="Waiting on you"
          onClick={() => navigate('/approvals')}
        />
        {/* `fact_check` — a list with ticks beside it, which is what an approved list is.
            Both lists have gated every board since they were built and had no writer outside
            the seed, so a company could not state its own policy without a Python shell. */}
        <RailButton
          active={location.pathname === '/policy'}
          icon="fact_check"
          label="Approved lists"
          onClick={() => navigate('/policy')}
        />
        {/* `hub` — nodes and the links between them, which is literally what /memory shows.
            It was `memory`, a chip glyph, sitting one rail away from the wordmark's
            `developer_board` chip: two chips for two unrelated things. */}
        <RailButton active={location.pathname === '/memory'} icon="hub" label="Memory" onClick={() => navigate('/memory')} />
      </div>

      <div className="mt-auto flex flex-col gap-sm w-full items-center border-t border-outline-variant pt-sm">
        {/* Which desk you are, in the chrome rather than behind a click. A substitution is
            signed by four departments, and somebody who cannot see whose eyes they are
            looking through signs from the wrong one and finds out from a 409. */}
        <DeskSwitcher />
        <div className="relative" ref={settingsRef}>
          <RailButton icon="settings" label="Settings" onClick={() => setSettingsOpen((open) => !open)} />
          {settingsOpen ? (
            <div className="absolute bottom-0 left-[calc(100%+10px)] z-50 w-64 border border-outline-variant bg-surface-container-high p-sm shadow-lg">
              <p className="m-0 px-sm py-xs font-data-tabular text-body-sm text-on-surface-variant truncate" title={user?.email}>
                {user?.email}
              </p>
              <button
                className="w-full text-left px-sm py-xs font-label-caps text-label-caps text-on-surface hover:bg-surface-container-highest focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-container"
                onClick={() => { handleSignOut().catch(() => undefined) }}
                type="button"
              >
                SIGN_OUT
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </nav>
  )
}
