import { useCallback, useEffect, useState } from 'react'

import { useAuth } from '../hooks/useAuth'
import {
  ApiError,
  approveVendor,
  getPolicy,
  keepLists,
  qualifyFromBill,
  qualifyPart,
  releasePart,
  releaseVendor,
  type Policy,
} from '../lib/api'
import { Page } from '../shell/Page'

/**
 * Where a company states its own policy.
 *
 * The two lists have gated every board since they were built, and nothing but the seed could
 * write them — a company could not say which parts it had qualified, or which sources it buys
 * from, without a Python shell.
 *
 * **The half that mattered more is the AML's.** Switching it on reports every fitted part
 * that is not on it, which is correct, and means that for a company which ships anything,
 * declaring a policy fails every board it has until somebody qualifies the lot. `QUALIFY
 * EVERYTHING WE SHIP` is that step, taken from the bills the company has already given us,
 * and it is what makes the switch usable rather than merely honest.
 *
 * The lists are kept by different desks, so each half says whose it is and refuses the other
 * desk with the same sentence the server would use.
 */
export default function PolicyRoute() {
  const { user } = useAuth()
  const [policy, setPolicy] = useState<Policy | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [part, setPart] = useState('')
  const [vendor, setVendor] = useState('')

  const load = useCallback(async () => {
    try {
      setPolicy(await getPolicy())
      setError(null)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'The lists could not be read.')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  /** One place that runs a change, reloads, and says what the server said when it refused. */
  const act = useCallback(
    async (change: () => Promise<unknown>) => {
      setBusy(true)
      try {
        await change()
        setError(null)
      } catch (caught) {
        setError(
          caught instanceof ApiError
            ? caught.message
            : 'That change was not accepted. Nothing was written.',
        )
      } finally {
        setBusy(false)
        await load()
      }
    },
    [load],
  )

  const roles = user?.roles ?? []
  const keeps = (desks: string[]) => desks.some((desk) => roles.includes(desk))
  const mayKeepParts = keeps(policy?.desks.parts ?? [])
  const mayKeepVendors = keeps(policy?.desks.vendors ?? [])

  return (
    <Page
      subtitle={
        policy
          ? `Parts are qualified by ${policy.desks.parts.join(' and ')}; sources are approved by ${policy.desks.vendors.join(' and ')}.`
          : undefined
      }
      title="APPROVED LISTS"
    >
      {error ? <p className="font-data-tabular text-[11px] text-error">{error}</p> : null}

      <div className="flex flex-col gap-lg">
        {policy ? (
          <>
            <List
              addPlaceholder="MPN"
              busy={busy}
              desks={policy.desks.parts}
              entries={policy.parts.entries.map((entry) => ({
                key: entry.mpn,
                name: entry.mpn,
                detail: entry.manufacturer ?? 'manufacturer not recorded',
                note: entry.note,
                by: entry.by,
                at: entry.created_at,
              }))}
              kept={policy.parts.kept}
              mayEdit={mayKeepParts}
              onAdd={() =>
                void act(async () => {
                  await qualifyPart({ mpn: part.trim() })
                  setPart('')
                })
              }
              onRemove={(name) => void act(() => releasePart(name))}
              onToggle={(next) => void act(() => keepLists({ parts: next }))}
              title="APPROVED MANUFACTURER LIST"
              typed={part}
              what="parts this company has qualified"
              onTyped={setPart}
            >
              {/* The number that makes the switch usable, and the action that clears it. */}
              {policy.parts.kept && policy.parts.missing.length > 0 ? (
                <div className="border border-tertiary-container rounded p-sm flex flex-col gap-sm">
                  <p className="m-0 font-data-tabular text-[11px] text-tertiary-container leading-relaxed">
                    {policy.parts.missing.length} of the {policy.parts.shipping} parts your
                    boards carry{' '}
                    {policy.parts.missing.length === 1 ? 'is' : 'are'} not on this list, so
                    every product line carrying{' '}
                    {policy.parts.missing.length === 1 ? 'it' : 'one'} fails
                    part qualification today:{' '}
                    {policy.parts.missing.map((row) => row.mpn).join(', ')}.
                  </p>
                  <button
                    className="h-8 px-md self-start border border-primary-container rounded font-data-tabular text-[11px] text-primary-container hover:bg-surface-variant transition-colors disabled:opacity-40"
                    disabled={busy || !mayKeepParts}
                    onClick={() => void act(() => qualifyFromBill())}
                    type="button"
                  >
                    QUALIFY EVERYTHING WE SHIP ({policy.parts.missing.length})
                  </button>
                </div>
              ) : null}
            </List>

            <List
              addPlaceholder="Distributor"
              busy={busy}
              desks={policy.desks.vendors}
              entries={policy.vendors.entries.map((entry) => ({
                key: entry.distributor,
                name: entry.distributor,
                // **Not a placeholder.** This said `an approved source` on every row, which
                // is a constant dressed as data, while the note, the approver and the date
                // were fetched and thrown away. A row that reads the same for every entry is
                // what made this list look like a settings screen with nothing in it.
                detail: entry.note ?? 'no note was recorded when this source was approved',
                note: null,
                by: entry.by,
                at: entry.created_at,
              }))}
              kept={policy.vendors.kept}
              mayEdit={mayKeepVendors}
              onAdd={() =>
                void act(async () => {
                  await approveVendor({ distributor: vendor.trim() })
                  setVendor('')
                })
              }
              onRemove={(name) => void act(() => releaseVendor(name))}
              onToggle={(next) => void act(() => keepLists({ vendors: next }))}
              title="APPROVED VENDOR LIST"
              typed={vendor}
              what="sources this company will buy from"
              onTyped={setVendor}
            >
              {/* **What the list actually holds back**, which the AML says for itself and
                  this one never did. Kept and empty is not the same as not kept: an empty
                  AML fails nothing, and an empty AVL fails every candidate whose source
                  nobody has approved. That asymmetry is why the two are separate lists, so
                  the screen states it rather than leaving a company to find out from a
                  review. */}
              {policy.vendors.kept && policy.vendors.entries.length === 0 ? (
                <div className="border border-tertiary-container rounded p-sm">
                  <p className="m-0 font-data-tabular text-[12px] text-tertiary-container leading-relaxed">
                    This list is kept and nothing is on it, so every candidate the review
                    checks fails procurement&rsquo;s source approval — including the part
                    already fitted.
                  </p>
                </div>
              ) : (
                <p className="m-0 font-data-tabular text-[12px] text-on-surface-variant leading-relaxed">
                  Procurement&rsquo;s source approval holds every part the review checks
                  against this list. A part with no source at all is reported as unknown
                  rather than as a breach, because nobody has said where it would come from,
                  and reporting that as a policy failure would put a decision in front of
                  somebody the data does not support.
                </p>
              )}
            </List>
          </>
        ) : (
          <p className="font-data-tabular text-[11px] text-on-surface-variant">Loading…</p>
        )}
      </div>
    </Page>
  )
}

type Entry = {
  key: string
  name: string
  detail: string
  note: string | null
  /** Who put it there, and when. Both have been on the wire since the endpoint existed. */
  by: string | null
  at: string
}

/** One list: the switch that turns its gate on, what is on it, and how to change it. */
function List({
  title,
  what,
  kept,
  desks,
  mayEdit,
  entries,
  typed,
  onTyped,
  onAdd,
  onRemove,
  onToggle,
  busy,
  addPlaceholder,
  children,
}: {
  title: string
  what: string
  kept: boolean
  desks: string[]
  mayEdit: boolean
  entries: Entry[]
  typed: string
  onTyped: (next: string) => void
  onAdd: () => void
  onRemove: (name: string) => void
  onToggle: (next: boolean) => void
  busy: boolean
  addPlaceholder: string
  children?: React.ReactNode
}) {
  return (
    <section className="border border-outline-variant rounded bg-surface-container-low">
      <div className="flex items-center justify-between gap-md px-md py-sm border-b border-outline-variant">
        <div className="min-w-0">
          <h2 className="m-0 font-label-caps text-label-caps tracking-[0.1em] text-on-surface">
            {title}
          </h2>
          <p className="m-0 font-data-tabular text-[10px] text-on-surface-variant">
            {what} · kept by {desks.join(' and ')}
          </p>
        </div>
        {/* The switch, and the reason it is off limits to the other desks. A control that
            cannot be used says whose it is rather than disappearing. */}
        <label
          className={`flex items-center gap-xs font-data-tabular text-[11px] ${
            mayEdit ? 'text-on-surface cursor-pointer' : 'text-on-surface-variant/60'
          }`}
          title={mayEdit ? undefined : `kept by ${desks.join(' and ')}`}
        >
          <input
            checked={kept}
            disabled={busy || !mayEdit}
            onChange={(event) => onToggle(event.target.checked)}
            type="checkbox"
          />
          {kept ? 'kept' : 'not kept'}
        </label>
      </div>

      <div className="p-md flex flex-col gap-sm">
        {children}

        {entries.length > 0 ? (
          <ul className="m-0 p-0 list-none flex flex-col">
            {entries.map((entry) => (
              <li
                className="flex items-start justify-between gap-md border-b border-outline-variant/50 py-1.5 last:border-b-0"
                key={entry.key}
              >
                <span className="min-w-0 flex flex-col">
                  <span className="font-data-tabular text-[13px] text-on-surface">
                    {entry.name}
                    <span className="text-on-surface-variant text-[12px] ml-sm">
                      {entry.detail}
                    </span>
                  </span>
                  {/* **Who put it there, and when.** Three facts were stored for every entry
                      and the row rendered a constant instead: the screen a company uses to
                      state its own policy could not say who stated it. An entry with nobody
                      behind it is worth knowing about too, so the absence is said rather
                      than hidden. */}
                  <span className="font-data-tabular text-[11px] text-on-surface-variant/70">
                    {entry.by ? `approved by ${entry.by}` : 'no approver recorded'} ·{' '}
                    {new Date(entry.at).toLocaleDateString(undefined, {
                      day: 'numeric',
                      month: 'short',
                      year: 'numeric',
                    })}
                  </span>
                </span>
                <button
                  className="font-data-tabular text-[11px] text-on-surface-variant hover:text-error transition-colors disabled:hidden shrink-0"
                  disabled={busy || !mayEdit}
                  onClick={() => onRemove(entry.name)}
                  type="button"
                >
                  REMOVE
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="m-0 font-data-tabular text-[12px] text-on-surface-variant">
            Nothing on this list. A company that keeps an empty one has qualified nothing, and
            every part on every board fails it.
          </p>
        )}

        <div className="flex gap-sm items-center">
          <input
            className="input-field px-sm h-8 flex-1 max-w-[320px] font-data-tabular text-[12px]"
            disabled={busy || !mayEdit}
            onChange={(event) => onTyped(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && typed.trim()) onAdd()
            }}
            placeholder={addPlaceholder}
            value={typed}
          />
          <button
            className="h-8 px-md border border-primary-container rounded font-data-tabular text-[11px] text-primary-container hover:bg-surface-variant transition-colors disabled:opacity-40"
            disabled={busy || !mayEdit || !typed.trim()}
            onClick={onAdd}
            type="button"
          >
            ADD
          </button>
        </div>
      </div>
    </section>
  )
}
