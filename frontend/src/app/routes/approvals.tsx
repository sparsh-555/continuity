import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import { departmentLabel } from '../review/Departments'
import {
  ApiError,
  answerDecision,
  listWaitingDecisions,
  type WaitingDecision,
} from '../lib/api'
import { useAuth } from '../hooks/useAuth'
import { Page } from '../shell/Page'

const REFRESH_MS = 10_000
/** A decision can be raised by somebody else's review, so this list changes without this
 *  browser doing anything. Ten seconds, matching the arrivals poll on `/changes`. */

/**
 * What this desk owes, across every product line.
 *
 * A substitution on a released design is signed by every department that examined it, and
 * three of those four people had no way to find the thing they had to sign: the decision
 * lived on a product line's page and on the notice that raised it. Somebody at the
 * procurement desk would have had to know which product line it was on and navigate there.
 *
 * **It is a queue, not a review.** Each row carries the desk's own reason to care — what is
 * being replaced, on which product, and the rule it is being asked to accept when one
 * failed — and the two buttons. Reading a design trace to sign for procurement is exactly
 * the round trip this product removes.
 */
export default function ApprovalsRoute() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [waiting, setWaiting] = useState<WaitingDecision[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)

  const refresh = useCallback(async () => {
    try {
      setWaiting(await listWaitingDecisions())
    } catch {
      setError('Could not load what is waiting for you.')
    } finally {
      setLoaded(true)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    const timer = setInterval(() => {
      if (!busy) void refresh()
    }, REFRESH_MS)
    return () => clearInterval(timer)
  }, [busy, refresh])

  const answer = useCallback(
    async (decision: WaitingDecision, approve: boolean) => {
      setBusy(decision.id)
      setError(null)
      try {
        await answerDecision(decision.id, approve)
        await refresh()
      } catch (caught) {
        // The server's own sentence. A 403 here names what the caller holds, which is the
        // only useful thing it could say.
        setError(
          caught instanceof ApiError
            ? (caught.message ?? 'That decision could not be answered.')
            : 'That decision could not be answered.',
        )
      } finally {
        setBusy(null)
      }
    },
    [refresh],
  )

  const desks = user?.roles ?? []

  return (
    <Page title="WAITING ON YOU" width="reading">
      {/* Whose eyes these are. A queue that does not say which desk it is for is a queue
          somebody answers from the wrong one. */}
      <p className="font-data-tabular text-[11px] text-on-surface-variant">
        {desks.length > 0
          ? `You hold ${desks.map(departmentLabel).join(' and ')}.`
          : 'You hold no desk, so nothing routes to you.'}
      </p>

      {error ? <p className="font-data-tabular text-[11px] text-error">{error}</p> : null}

      {loaded && waiting.length === 0 ? (
        <p className="font-data-tabular text-[11px] text-on-surface-variant">
          Nothing is waiting for you.
        </p>
      ) : null}

      <div className="flex flex-col gap-md">
        {waiting.map((decision) => {
          const owed = decision.mine.length > 0
          const outstanding = decision.roles.filter((role) => !decision.signed.includes(role))
          return (
            <article
              className="border border-outline-variant rounded p-lg space-y-sm bg-surface-container-low"
              key={decision.id}
            >
              <header className="flex items-start justify-between gap-md">
                <div className="min-w-0">
                  <button
                    className="font-headline-sm text-headline-sm text-on-surface hover:text-primary-container transition-colors text-left"
                    onClick={() => navigate(`/lines/${decision.line_id}`)}
                    type="button"
                  >
                    {decision.line_name}
                  </button>
                  <p className="font-data-tabular text-[11px] text-on-surface-variant mt-0.5">
                    {decision.revision ? `${decision.revision} · ` : ''}
                    {decision.refdes.toUpperCase()} · {decision.retiring} → {decision.proposal}
                  </p>
                </div>
                <span className="font-data-tabular text-[11px] px-sm py-0.5 border border-outline-variant rounded text-[#4ade80] whitespace-nowrap">
                  {decision.proposal}
                </span>
              </header>

              <p className="font-data-tabular text-[11px] text-on-surface leading-relaxed">
                {decision.detail}
              </p>

              {/* What is being asked of this desk specifically. A failed rule is something
                  to accept; everything else is something to approve, and they are different
                  sentences. */}
              {decision.gate_rule ? (
                <p className="font-data-tabular text-[10px] text-tertiary-container">
                  {decision.gate_rule.replace(/_/g, ' ')} failed, and{' '}
                  {departmentLabel(decision.roles[0] ?? '')} is being asked to accept it.
                </p>
              ) : null}

              <p className="font-data-tabular text-[10px] text-on-surface-variant">
                {decision.signed.length > 0
                  ? `Signed by ${decision.signed.map(departmentLabel).join(' and ')}. `
                  : ''}
                Waiting on {outstanding.map(departmentLabel).join(' and ')}.
              </p>

              {/* Drawn only where it can be used. A desk that has already signed sees what
                  it signed and no buttons, rather than buttons that will 409. */}
              {owed ? (
                <div className="flex gap-sm pt-1">
                  <button
                    className="h-7 px-md border border-primary-container rounded font-data-tabular text-[10px] text-primary-container hover:bg-surface-variant transition-colors disabled:opacity-40"
                    disabled={busy === decision.id}
                    onClick={() => void answer(decision, true)}
                    type="button"
                  >
                    {busy === decision.id
                      ? 'SIGNING…'
                      : outstanding.length > 1
                        ? `SIGN FOR ${decision.mine.map(departmentLabel).join(' AND ')}`
                        : 'APPROVE AND APPLY'}
                  </button>
                  <button
                    className="h-7 px-md border border-outline-variant rounded font-data-tabular text-[10px] text-on-surface-variant hover:bg-surface-variant transition-colors disabled:opacity-40"
                    disabled={busy === decision.id}
                    onClick={() => void answer(decision, false)}
                    type="button"
                  >
                    LEAVE IT
                  </button>
                </div>
              ) : (
                <p className="font-data-tabular text-[10px] text-on-surface-variant/70">
                  You have signed this. It is not yours to sign again.
                </p>
              )}
            </article>
          )
        })}
      </div>
    </Page>
  )
}
