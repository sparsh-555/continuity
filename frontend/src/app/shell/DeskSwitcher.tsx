import { useCallback, useEffect, useRef, useState } from 'react'

import { useAuth } from '../hooks/useAuth'
import { listSessions, switchDesk, type HeldSession } from '../lib/api'
import { departmentLabel } from '../review/Departments'

/** Four letters of the desk, because the rail is 64px wide and a desk still has to be
 *  readable at a glance. */
const SHORT: Record<string, string> = {
  engineering: 'DSGN',
  procurement: 'PROC',
  production: 'PROD',
  quality: 'QUAL',
}

function short(roles: string[]): string {
  if (roles.length === 0) return '—'
  if (roles.length > 1) return `${roles.length}×`
  return SHORT[roles[0]] ?? roles[0].slice(0, 4).toUpperCase()
}

/**
 * Which desk you are, and how to be another one.
 *
 * **Always visible, never behind a click.** A substitution is signed by four departments, so
 * a person reading this screen has to be able to see whose eyes they are looking through
 * without opening anything — otherwise they sign from the wrong desk and find out from a
 * 409.
 *
 * **Real sessions, not an impersonation.** The switcher moves between sessions this browser
 * has already authenticated; the tokens stay in an httpOnly cookie and are never sent to
 * the page. A *view as* simulation would be visual only and could not sign, and signing is
 * the entire point.
 */
export function DeskSwitcher() {
  const { user, refresh } = useAuth()
  const [open, setOpen] = useState(false)
  const [held, setHeld] = useState<HeldSession[]>([])
  const [busy, setBusy] = useState(false)
  const box = useRef<HTMLDivElement | null>(null)

  const read = useCallback(() => {
    listSessions()
      .then(setHeld)
      .catch(() => setHeld([]))
  }, [])

  useEffect(() => {
    if (user) read()
  }, [read, user])

  useEffect(() => {
    if (!open) return
    const away = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [open])

  const move = useCallback(
    async (email: string) => {
      setBusy(true)
      try {
        await switchDesk(email)
        await refresh()
        read()
        setOpen(false)
        // Everything on screen is per-desk: what is waiting, which buttons are live, what
        // a 403 would say. Reloading the route is cheaper and more honest than reconciling
        // half a dozen caches by hand.
        window.location.reload()
      } finally {
        setBusy(false)
      }
    },
    [read, refresh],
  )

  if (!user) return null

  const others = held.filter((row) => !row.active)

  return (
    <div className="relative" ref={box}>
      <button
        aria-label={`Signed in as ${user.email}. Switch desk.`}
        className="w-10 h-10 rounded flex items-center justify-center border border-outline-variant text-on-surface-variant hover:text-primary hover:bg-surface-container transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-container"
        onClick={() => setOpen((was) => !was)}
        type="button"
      >
        <span className="font-data-tabular text-[9px] leading-none">{short(user.roles)}</span>
      </button>

      {open ? (
        <div className="absolute bottom-0 left-[calc(100%+10px)] z-50 w-72 border border-outline-variant bg-surface-container-high shadow-lg">
          <p className="m-0 px-md pt-sm font-data-tabular text-[10px] text-on-surface-variant uppercase">
            Signed in as
          </p>
          <p className="m-0 px-md pb-sm font-data-tabular text-[11px] text-on-surface truncate">
            {user.email}
            <span className="block text-on-surface-variant">
              {user.roles.map(departmentLabel).join(' and ') || 'no desk'}
            </span>
          </p>

          {others.length > 0 ? (
            <>
              <p className="m-0 px-md pt-sm border-t border-outline-variant font-data-tabular text-[10px] text-on-surface-variant uppercase">
                Also signed in
              </p>
              {others.map((row) => (
                <button
                  className="w-full text-left px-md py-sm hover:bg-surface-container-highest focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-container disabled:opacity-40"
                  disabled={busy}
                  key={row.email}
                  onClick={() => void move(row.email)}
                  type="button"
                >
                  <span className="block font-data-tabular text-[11px] text-on-surface truncate">
                    {row.email}
                  </span>
                  <span className="block font-data-tabular text-[10px] text-on-surface-variant">
                    {row.roles.map(departmentLabel).join(' and ') || 'no desk'}
                  </span>
                </button>
              ))}
            </>
          ) : (
            /* Said rather than left blank. A switcher with nothing to switch to looks
               broken; the reason it is empty is that nobody else has signed in here. */
            <p className="m-0 px-md py-sm border-t border-outline-variant font-data-tabular text-[10px] text-on-surface-variant leading-relaxed">
              No other desk is signed in on this browser. Sign in as one and both stay live.
            </p>
          )}
        </div>
      ) : null}
    </div>
  )
}
