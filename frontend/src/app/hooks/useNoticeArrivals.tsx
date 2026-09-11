import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'

import { exposureTo, listNotices } from '../lib/api'
import { useAuth } from './useAuth'

const ARRIVALS_MS = 10_000

export type NoticeArrival = { id: string; mpn: string; affected: number }
type NoticeArrivals = { arrival: number }

const NoticeArrivalContext = createContext<NoticeArrivals>({ arrival: 0 })

/** Return notices that are neither announced nor currently being assembled. The caller records
 * success separately, so a transient exposure failure retries without duplicate toasts. */
export function newlyArrivedNotices<T extends { id: string }>(
  known: Set<string>,
  inFlight: Set<string>,
  notices: T[],
): T[] {
  return notices.filter((notice) => !known.has(notice.id) && !inFlight.has(notice.id))
}

function ArrivalToast({ arrival, onDismiss }: { arrival: NoticeArrival; onDismiss: () => void }) {
  return (
    <div className="flex items-start gap-sm rounded border border-error/60 bg-surface-container-high px-md py-sm shadow-lg">
      <span aria-hidden="true" className="material-symbols-outlined text-[18px] text-error">warning</span>
      <p className="font-data-tabular text-[11px] text-on-surface">
        {arrival.mpn} affects {arrival.affected} product line{arrival.affected === 1 ? '' : 's'}.
      </p>
      <button aria-label={`Dismiss ${arrival.mpn} arrival`} className="-mr-1 -mt-1 h-5 w-5 text-on-surface-variant hover:text-on-surface" onClick={onDismiss} type="button">
        <span aria-hidden="true" className="material-symbols-outlined text-[16px]">close</span>
      </button>
    </div>
  )
}

export function NoticeArrivalProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const known = useRef<Set<string> | null>(null)
  const inFlight = useRef(new Set<string>())
  const [arrival, setArrival] = useState(0)
  const [toasts, setToasts] = useState<NoticeArrival[]>([])

  const dismiss = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  useEffect(() => {
    if (!user) {
      known.current = null
      inFlight.current.clear()
      setToasts([])
      return
    }

    let alive = true
    known.current = null
    inFlight.current.clear()
    const poll = async () => {
      try {
        const notices = await listNotices()
        if (!alive) return
        if (known.current === null) {
          known.current = new Set(notices.map((notice) => notice.id))
          return
        }
        const newNotices = newlyArrivedNotices(known.current, inFlight.current, notices)
        if (newNotices.length === 0) return
        newNotices.forEach((notice) => inFlight.current.add(notice.id))
        try {
          const announcements = await Promise.all(newNotices.map(async (notice) => ({
            id: notice.id,
            mpn: notice.mpn,
            affected: (await exposureTo(notice.mpn)).length,
          })))
          if (!alive) return
          newNotices.forEach((notice) => known.current?.add(notice.id))
          chime()
          setToasts((current) => [...announcements, ...current])
          setArrival((current) => current + 1)
        } finally {
          newNotices.forEach((notice) => inFlight.current.delete(notice.id))
        }
      } catch {
        // A refresh hint must not replace a working product screen with an error.
      }
    }
    void poll()
    const timer = setInterval(() => void poll(), ARRIVALS_MS)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [user?.id])

  return (
    <NoticeArrivalContext.Provider value={{ arrival }}>
      {children}
      {toasts.length > 0 ? (
        <div aria-live="polite" className="fixed right-lg top-lg z-[60] flex w-[min(360px,calc(100vw-2rem))] flex-col gap-sm">
          {toasts.map((toast) => <ArrivalToast arrival={toast} key={toast.id} onDismiss={() => dismiss(toast.id)} />)}
        </div>
      ) : null}
    </NoticeArrivalContext.Provider>
  )
}

/**
 * A short tone when a notice arrives.
 *
 * **The whole point of the arrival notification is that it reaches somebody who is looking
 * at something else**, and a toast in the corner of a screen nobody is watching is silent in
 * every sense. Synthesised rather than shipped as a file: two oscillators and an envelope are
 * smaller than an audio asset and cannot 404.
 *
 * It fires where the toast fires and nowhere else — never on the first poll, which seeds what
 * is already known — so a page load with notices present is silent and a notice that actually
 * lands is not. A browser that blocks audio until a gesture has happened refuses silently,
 * which is the right failure for a sound.
 */
function chime() {
  try {
    const maker = window.AudioContext
    if (!maker) return
    const context = new maker()
    const start = context.currentTime
    for (const [index, frequency] of [880, 1318.5].entries()) {
      const at = start + index * 0.09
      const oscillator = context.createOscillator()
      const gain = context.createGain()
      oscillator.type = 'sine'
      oscillator.frequency.value = frequency
      gain.gain.setValueAtTime(0.0001, at)
      gain.gain.exponentialRampToValueAtTime(0.05, at + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.28)
      oscillator.connect(gain)
      gain.connect(context.destination)
      oscillator.start(at)
      oscillator.stop(at + 0.3)
    }
    void context.resume?.()
    setTimeout(() => void context.close(), 800)
  } catch {
    // A sound that cannot play is not worth a broken notification.
  }
}

export function useNoticeArrivals() {
  return useContext(NoticeArrivalContext)
}
