import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router'

import { BoardConsequence } from '../board/BoardConsequence'
import { ComponentGraph } from '../design/ComponentGraph'
import { ReviewTrace } from '../review/ReviewTrace'
import { useLineReview } from '../review/useLineReview'
import { Page } from '../shell/Page'
import {
  ApiError,
  checkLine,
  getLineOverview,
  putBoard,
  type LineCheck,
  type LineOverview,
} from '../lib/api'

const EMPTY = new Set<string>()

function bytes(size: number) {
  return size > 1_000_000 ? `${(size / 1_048_576).toFixed(1)} MB` : `${Math.round(size / 1024)} kB`
}

function railSummary(overview: LineOverview): string {
  const rails = (overview.line.profile?.rails ?? {}) as Record<
    string,
    { voltage?: number | null; i_load?: number | null }
  >
  const stated = Object.entries(rails)
    .map(([name, rail]) => {
      const volts = typeof rail.voltage === 'number' ? `${rail.voltage} V` : name.toUpperCase()
      const load = typeof rail.i_load === 'number' ? ` at ${Math.round(rail.i_load * 1000)} mA` : ''
      return `${volts}${load}`
    })
    .join(' · ')
  return stated
}

/** A product line, as the company has it: what it is made of, how it is powered, what board
 *  it is built from, and what is coming for it.
 *
 *  It is also where the review happens. A notice against this product is answered here,
 *  beside the picture of the part being replaced, rather than on a second screen the reader
 *  has to find — the question and **APPROVE AND APPLY** arrive in the trace panel where
 *  somebody is already looking. `POST /notices/{id}/review/run` carries a `line_id` for
 *  exactly this, so the page runs the same review the whole company runs, narrowed to one
 *  board. */
export default function LineRoute() {
  const { lineId } = useParams<{ lineId: string }>()
  const navigate = useNavigate()

  const [overview, setOverview] = useState<LineOverview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [check, setCheck] = useState<LineCheck | null>(null)
  const [busy, setBusy] = useState(false)
  const [panelOpen, setPanelOpen] = useState(false)
  const [view, setView] = useState<'components' | 'board'>('components')
  const boardInputRef = useRef<HTMLInputElement | null>(null)

  const load = useCallback(async () => {
    if (!lineId) return
    try {
      setOverview(await getLineOverview(lineId))
      setError(null)
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 404
          ? 'That product line does not exist, or belongs to another company.'
          : 'That product line could not be loaded.',
      )
    }
  }, [lineId])

  useEffect(() => {
    void load()
  }, [load])

  // The engine, after the page is on screen. This resolves parts against a distributor and
  // takes a few seconds, so it must not sit in front of the render: the page arrives grey
  // and settles. A failure leaves it grey, which is the honest picture of a board nothing
  // has looked at, rather than a green nobody computed.
  const run = useCallback(async () => {
    if (!lineId) return
    try {
      setCheck(await checkLine(lineId))
    } catch {
      setCheck(null)
    }
  }, [lineId])

  useEffect(() => {
    setCheck(null)
    void run()
  }, [run])

  // A change was applied, so the bill, the notices and the verdicts on this page are all
  // about a board that no longer exists. Both are reloaded rather than patched: the notice
  // is joined on the fitted bill, so an applied substitution takes the banner and the red
  // slot with it, and guessing that in the client would be a second implementation of a
  // join the server already does.
  const applied = useCallback(() => {
    void load()
    void run()
  }, [load, run])

  const review = useLineReview({ lineId: lineId ?? '', onApplied: applied })

  const attach = useCallback(
    async (file: File) => {
      if (!lineId) return
      setBusy(true)
      setError(null)
      try {
        const bundle = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader()
          reader.onerror = () => reject(reader.error)
          reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '')
          reader.readAsDataURL(file)
        })
        await putBoard(lineId, file.name, bundle)
        await load()
      } catch (caught) {
        setError(
          caught instanceof ApiError
            ? (caught.message ?? 'That project could not be attached.')
            : 'That project could not be attached.',
        )
      } finally {
        setBusy(false)
      }
    },
    [lineId, load],
  )

  const { line, parts, graph, board, notices, requests } = overview ?? {}

  // A shipping product line is green. These products are in production, the engine checks
  // them on every visit, and a part is repainted only when something is actually wrong with
  // it: red where a notice retires it, red where a check fails it. Grey was the state of a
  // board nobody had looked at, and it made five working products read as broken.
  //
  // Cyan while the review runs, at the one position being re-checked. That is not a verdict
  // and does not claim to be: it says work is happening here, which is the middle act of the
  // story this page tells.
  const working = useMemo(
    () => (review.status === 'running' ? new Set(review.positions) : EMPTY),
    [review.positions, review.status],
  )

  const slots = useMemo(() => {
    if (!graph) return []
    return graph.slots.map((slot) => {
      if (working.has(slot.id)) {
        return { ...slot, status: 'searching' as const }
      }
      return slot.status === 'conflict'
        ? slot
        : { ...slot, status: check?.slots[slot.id]?.status ?? ('pass' as const) }
    })
  }, [check, graph, working])

  if (error && !overview) {
    return (
      <Page back={{ to: '/lines', label: 'PRODUCT LINES' }} title="PRODUCT LINE">
        <p className="font-data-tabular text-[11px] text-error">{error}</p>
      </Page>
    )
  }

  if (!overview || !line || !parts || !graph || !notices || !requests) {
    return (
      <Page back={{ to: '/lines', label: 'PRODUCT LINES' }} title="PRODUCT LINE">
        <p className="font-data-tabular text-[11px] text-on-surface-variant">Loading…</p>
      </Page>
    )
  }

  const profile = line.profile
  const fitted = parts.filter((part) => part.populated)
  // What the board render puts on the board: what the run settled on, or what it is trying
  // right now. Nothing to place means no toggle, rather than a toggle that leads nowhere.
  const placing = review.proposal ?? review.trying
  const retiring = notices[0]?.mpn ?? null

  return (
    <Page
      actions={
        <>
          <input
            accept=".zip,application/zip"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) void attach(file)
              event.target.value = ''
            }}
            ref={boardInputRef}
            type="file"
          />
          <button
            className="h-8 px-md border border-outline-variant rounded font-data-tabular text-[11px] text-on-surface-variant hover:bg-surface-variant transition-colors disabled:opacity-40"
            disabled={busy}
            onClick={() => boardInputRef.current?.click()}
            type="button"
          >
            {busy ? 'READING…' : board ? 'REPLACE BOARD' : 'ATTACH BOARD'}
          </button>
        </>
      }
      back={{ to: '/lines', label: 'PRODUCT LINES' }}
      subtitle={
        <>
          {line.revision ? `${line.revision} · ` : ''}
          {fitted.length} part{fitted.length === 1 ? '' : 's'}
          {profile ? ` · ${profile.ambient_c} °C ambient` : ''}
          {railSummary(overview) ? ` · ${railSummary(overview)}` : ''}
        </>
      }
      title={line.name}
    >
      {error ? <p className="font-data-tabular text-[11px] text-error">{error}</p> : null}

      {/* What is coming for this product, first, because it is the only thing on this page
          that is about to change — and the review starts from here rather than from a page
          somebody has to go and find. */}
      {notices.length > 0 ? (
        <section className="space-y-sm">
          {notices.map((notice) => (
            <div
              className="border border-error/60 bg-error-container/10 rounded p-md flex items-start justify-between gap-md"
              key={notice.id}
            >
              <div className="min-w-0">
                <p className="font-data-tabular text-[11px] text-error">
                  {notice.mpn} at {notice.refdes.join(', ')} is end of life
                  {notice.effective_date ? ` · last order ${notice.effective_date}` : ''}
                </p>
                <p className="font-data-tabular text-[10px] text-on-surface-variant mt-1">
                  {notice.manufacturer ?? 'manufacturer not stated'}
                  {notice.replacement_mpn ? ` recommends ${notice.replacement_mpn}` : ''}
                  {' · '}
                  {requests.some((request) => request.notice_id === notice.id)
                    ? `reviewed: ${requests.find((r) => r.notice_id === notice.id)?.proposal ?? 'no viable part'}`
                    : 'not reviewed yet'}
                </p>
              </div>
              <div className="flex items-center gap-sm flex-shrink-0">
                <button
                  className="h-8 px-md border border-primary-container rounded font-data-tabular text-[11px] text-primary-container hover:bg-surface-variant transition-colors disabled:opacity-40"
                  disabled={review.status === 'running'}
                  onClick={() => {
                    setPanelOpen(true)
                    setView('components')
                    review.start(notice.id, notice.refdes)
                  }}
                  type="button"
                >
                  {review.status === 'running' ? 'RUNNING…' : 'REVIEW THIS LINE'}
                </button>
                <button
                  className="h-8 px-md border border-outline-variant rounded font-data-tabular text-[11px] text-on-surface-variant hover:bg-surface-variant transition-colors"
                  onClick={() => navigate(`/changes?notice=${encodeURIComponent(notice.id)}`)}
                  type="button"
                >
                  THE NOTICE
                </button>
              </div>
            </div>
          ))}
        </section>
      ) : null}

      {/* The workspace: the trace beside the board it is about. The panel arrives with the
          run rather than sitting empty beforehand, so a product line nobody is reviewing is
          the picture and nothing else. */}
      <section className="flex gap-md h-[460px]">
        {panelOpen ? (
          <ReviewTrace onDismiss={() => setPanelOpen(false)} review={review} />
        ) : null}

        <div className="flex-1 min-w-0 flex flex-col gap-1">
          {placing && retiring && lineId ? (
            <div className="flex justify-end gap-1">
              {(['components', 'board'] as const).map((which) => (
                <button
                  className={`h-7 px-md border rounded font-data-tabular text-[10px] transition-colors ${
                    view === which
                      ? 'border-primary-container text-primary-container'
                      : 'border-outline-variant text-on-surface-variant hover:bg-surface-variant'
                  }`}
                  key={which}
                  onClick={() => setView(which)}
                  type="button"
                >
                  {which === 'components' ? 'COMPONENTS' : 'BOARD'}
                </button>
              ))}
            </div>
          ) : null}

          {view === 'board' && placing && retiring && lineId ? (
            <div className="flex-1 min-h-0 overflow-y-auto border border-outline-variant rounded bg-surface-container-low p-md">
              <BoardConsequence auto candidate={placing} lineId={lineId} retiring={retiring} />
            </div>
          ) : graph.slots.length > 0 ? (
            <div className="flex-1 min-h-0 flex">
              <ComponentGraph
                activeRepair={null}
                animateEdges={false}
                // Never `working`: this prop plays a 240 ms entrance animation for a slot
                // that has just appeared, and nothing appears on a board that already
                // ships. The position being re-checked says so by being cyan.
                animatedSlotIds={EMPTY}
                conflict={null}
                edges={graph.edges}
                onReleaseRepairHold={() => undefined}
                revealedSlotIds={new Set(graph.slots.map((slot) => slot.id))}
                slotConflictVariant={{}}
                slots={slots}
                supply={graph.supply}
              />
            </div>
          ) : (
            <p className="font-data-tabular text-[11px] text-on-surface-variant border border-outline-variant rounded p-md">
              No parts are recorded against this product line yet.
            </p>
          )}
        </div>
      </section>

      <section className="border border-outline-variant rounded bg-surface-container-low">
        <header className="px-md py-sm border-b border-outline-variant">
          <h2 className="font-label-caps text-label-caps uppercase text-on-surface-variant">
            BILL OF MATERIALS
          </h2>
        </header>
        <table className="w-full font-data-tabular text-[11px]">
          <thead>
            <tr className="text-on-surface-variant/70">
              <th className="text-left font-normal px-md py-1">REF</th>
              <th className="text-left font-normal px-md py-1">PART</th>
              <th className="text-left font-normal px-md py-1">MANUFACTURER</th>
              <th className="text-left font-normal px-md py-1">FOOTPRINT</th>
            </tr>
          </thead>
          <tbody>
            {parts.map((part) => (
              <tr className="border-t border-outline-variant/50" key={part.refdes}>
                <td className="px-md py-1 text-on-surface-variant uppercase">{part.refdes}</td>
                <td className="px-md py-1 text-on-surface">
                  {part.mpn}
                  {part.populated ? '' : ' · not fitted'}
                </td>
                <td className="px-md py-1 text-on-surface-variant">{part.manufacturer ?? '—'}</td>
                <td className="px-md py-1 text-on-surface-variant">{part.footprint ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="border border-outline-variant rounded bg-surface-container-low p-md">
        <h2 className="font-label-caps text-label-caps uppercase text-on-surface-variant">
          BOARD
        </h2>
        {board ? (
          <p className="font-data-tabular text-[11px] text-on-surface mt-1">
            {board.project}{' '}
            <span className="text-on-surface-variant">
              · {board.filename} · {bytes(board.bytes)} · attached{' '}
              {new Date(board.uploaded_at).toLocaleDateString()}
            </span>
          </p>
        ) : (
          <p className="font-data-tabular text-[11px] text-on-surface-variant mt-1">
            No KiCad project is attached. With one, a substitution can be placed on the real
            board and the connections it breaks are reported by KiCad itself.
          </p>
        )}
      </section>
    </Page>
  )
}
