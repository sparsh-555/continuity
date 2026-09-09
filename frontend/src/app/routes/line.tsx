import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router'

import { ComponentGraph } from '../design/ComponentGraph'
import { BoardPane } from '../review/BoardPane'
import { LineBom } from '../review/LineBom'
import { NoticePanel } from '../review/NoticePanel'
import { RequestCard } from '../review/RequestCard'
import { ReviewTrace } from '../review/ReviewTrace'
import { SidePanel } from '../review/SidePanel'
import { useLineReview } from '../review/useLineReview'
import { Wordmark } from '../shell/Wordmark'
import {
  ApiError,
  boardRender,
  checkLine,
  getLineOverview,
  listLineReviews,
  type LineCheck,
  type LineNotice,
  type LineOverview,
  type LineRequest,
  type StoredReview,
} from '../lib/api'

const EMPTY = new Set<string>()

function railSummary(overview: LineOverview): string {
  const rails = (overview.line.profile?.rails ?? {}) as Record<
    string,
    { voltage?: number | null; i_load?: number | null }
  >
  return Object.entries(rails)
    .map(([name, rail]) => {
      const volts = typeof rail.voltage === 'number' ? `${rail.voltage} V` : name.toUpperCase()
      const load = typeof rail.i_load === 'number' ? ` at ${Math.round(rail.i_load * 1000)} mA` : ''
      return `${volts}${load}`
    })
    .join(' · ')
}

/** COMPONENTS or BOARD, in the middle pane's own header where a pane's controls belong. */
function Toggle({
  value,
  onChange,
}: {
  value: 'components' | 'board'
  onChange: (next: 'components' | 'board') => void
}) {
  return (
    <div className="flex gap-1">
      {(['components', 'board'] as const).map((which) => (
        <button
          className={`h-6 px-sm border rounded font-data-tabular text-[10px] transition-colors ${
            value === which
              ? 'border-primary-container text-primary-container bg-surface-container'
              : 'border-outline-variant text-on-surface-variant hover:bg-surface-variant'
          }`}
          key={which}
          onClick={() => onChange(which)}
          type="button"
        >
          {which === 'components' ? 'COMPONENTS' : 'BOARD'}
        </button>
      ))}
    </div>
  )
}

/** What the right-hand pane is showing. The bill is the resting state; the other two take
 *  its place exactly as `design/ConflictPanel` takes `design/BomTable`'s. */
type Drawer =
  | { kind: 'bom' }
  | { kind: 'notice' }
  | { kind: 'request'; request: LineRequest }

/**
 * A product line, as the company has it, and where its review runs.
 *
 * **This is the design workspace, pointed at a product that already exists.** Same shell,
 * same three panes, same proportions, same height lock: the trace on the left, the picture in
 * the middle, the bill on the right — and, where a design run puts its conflict, the notice
 * that is coming for this product.
 *
 * Everything here is stored except the review and the per-visit check.
 */
export default function LineRoute() {
  const { lineId } = useParams<{ lineId: string }>()

  const [overview, setOverview] = useState<LineOverview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [check, setCheck] = useState<LineCheck | null>(null)
  const [view, setView] = useState<'components' | 'board'>('components')
  const [drawer, setDrawer] = useState<Drawer>({ kind: 'bom' })
  const [selectedSlotId, setSelectedSlotId] = useState<string | null>(null)

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
  // takes a few seconds, so it must not sit in front of the render.
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
  // is joined on the fitted bill, so an applied substitution takes it away, and guessing
  // that in the client would be a second implementation of a join the server already does.
  const applied = useCallback(() => {
    void load()
    void run()
  }, [load, run])

  const review = useLineReview({ lineId: lineId ?? '', onApplied: applied })

  // What this product line has already been through. A review used to keep only its
  // conclusions, so reopening a line showed a part number and a date where a design run
  // would have shown its whole trace. `api/replay` rebuilds the frames from the decision
  // the run wrote, and they go through the same reducer a live run goes through.
  const [stored, setStored] = useState<StoredReview[]>([])
  const hydrate = review.hydrate

  useEffect(() => {
    if (!lineId) return
    let live = true
    void listLineReviews(lineId)
      .then((found) => {
        if (!live) return
        setStored(found)
        const newest = found[0]
        if (newest) {
          hydrate(
            newest.frames,
            newest.state === 'pending' ? null : (newest.state as 'approved' | 'declined'),
          )
        }
      })
      .catch(() => undefined)
    return () => {
      live = false
    }
    // Deliberately not depending on `hydrate`: it is stable, and a run started by hand must
    // not be overwritten by a fetch that resolves a moment later.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lineId])

  const { line, parts, graph, board, notices, requests } = overview ?? {}

  // A shipping product line is green. These products are in production, the engine checks
  // them on every visit, and a part is repainted only when something is actually wrong with
  // it: red where a notice retires it, red where a check fails it.
  //
  // Cyan while the review runs, at the position being re-checked. That is not a verdict and
  // does not claim to be: it says work is happening here, which is the middle act.
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

  const revealed = useMemo(() => new Set(slots.map((slot) => slot.id)), [slots])

  // Draw the board before anybody asks for it. A render is three KiCad invocations and
  // about three seconds; the server caches the answer, so warming it on arrival turns the
  // BOARD toggle from a wait into a switch. Failures are ignored on purpose — this is a
  // head start, and `BoardPane` reports anything that is actually wrong when it asks.
  useEffect(() => {
    if (!lineId || !overview?.board) return
    void boardRender(lineId, overview.notices[0]?.mpn ?? null).catch(() => undefined)
  }, [lineId, overview?.board, overview?.notices])

  if (!overview || !line || !parts || !graph || !notices || !requests) {
    return (
      <div className="h-full w-full flex items-center justify-center bg-background">
        <p className="font-data-tabular text-[11px] text-on-surface-variant">
          {error ?? 'Loading…'}
        </p>
      </div>
    )
  }

  const profile = line.profile
  const fitted = parts.filter((part) => part.populated)
  const retiring = notices[0]?.mpn ?? null
  // What the board pane places: what the run settled on, what it is trying, or — with no run
  // this session — whatever an earlier decision on this notice settled on.
  const placing =
    review.proposal ??
    review.trying ??
    stored.find((entry) => entry.notice_id === notices[0]?.id)?.proposal ??
    requests.find((request) => request.notice_id === notices[0]?.id)?.proposal ??
    null

  const startOn = (notice: LineNotice) => {
    setView('components')
    setDrawer({ kind: 'bom' })
    review.start(notice.id, notice.refdes)
  }

  const toggle = board ? <Toggle onChange={setView} value={view} /> : null

  return (
    <div className="h-full min-h-0 w-full overflow-hidden flex flex-col font-body-md antialiased bg-background text-on-background">
      {/* Taller than the design workspace's, and deliberately. That one carries a wordmark
          and two chips; this one carries the product's identity — the name somebody is
          demonstrating, its revision, and the conditions every verdict below is graded
          against. At 48 px with a 10 px subtitle it was a strip of grey nobody could read
          across a room. The board's project name is not here: it belongs to the board, and
          the pane that draws the board says it. */}
      <header className="flex items-center justify-between gap-md w-full px-lg h-16 flex-shrink-0 bg-surface-container-low border-b border-outline-variant shadow-[0_1px_0_0_rgba(255,255,255,0.05)]">
        <div className="flex items-center gap-md min-w-0">
          <Link
            className="h-8 w-8 -ml-1 rounded flex items-center justify-center text-on-surface-variant hover:text-primary-container hover:bg-surface-container-high transition-colors flex-shrink-0"
            to="/lines"
          >
            <span className="material-symbols-outlined text-[20px]">arrow_back</span>
          </Link>
          <div className="min-w-0">
            <h1 className="font-headline-sm text-[16px] font-semibold tracking-wide text-on-surface truncate">
              {line.name}
            </h1>
            <p className="font-data-tabular text-[11px] text-on-surface-variant truncate">
              {line.revision ? `${line.revision} · ` : ''}
              {fitted.length} part{fitted.length === 1 ? '' : 's'}
              {profile ? ` · ${profile.ambient_c} °C ambient` : ''}
              {railSummary(overview) ? ` · ${railSummary(overview)}` : ''}
            </p>
          </div>
        </div>

        {/* The same chip the design workspace carries, saying the two things about this
            board that are worth knowing at a glance. */}
        <div className="hidden md:flex items-center bg-surface-container-high rounded px-sm py-1 border border-outline-variant">
          <div className="flex items-center gap-xs">
            <span
              className={`w-2 h-2 rounded-pill ${
                notices.length > 0 ? 'bg-error animate-pulse' : 'border border-outline-variant'
              }`}
            />
            <span
              className={`font-body-sm text-body-sm ${
                notices.length > 0 ? 'text-error font-medium' : 'text-on-surface-variant'
              }`}
            >
              {notices.length} end of life
            </span>
          </div>
          <span className="text-on-surface-variant mx-1 text-[10px]">•</span>
          <span className="font-body-sm text-body-sm text-on-surface-variant">
            {check ? `${check.checked} checks` : 'checking…'}
          </span>
        </div>

        <div className="flex items-center gap-md flex-shrink-0">
          {error ? (
            <span className="font-data-tabular text-[10px] text-error">{error}</span>
          ) : null}
          <button
            className={`h-8 px-md font-body-sm text-body-sm font-bold rounded transition-colors duration-75 flex items-center gap-sm disabled:cursor-not-allowed ${
              notices.length === 0
                ? 'bg-surface-container-high text-on-surface-variant border border-outline-variant'
                : 'bg-error text-on-error hover:bg-opacity-90 active:scale-95 glow-error'
            }`}
            disabled={notices.length === 0}
            onClick={() =>
              setDrawer((current) => (current.kind === 'notice' ? { kind: 'bom' } : { kind: 'notice' }))
            }
            type="button"
          >
            <span className="material-symbols-outlined text-[16px]">warning</span>
            End of life ({notices.length})
          </button>
          <Wordmark />
        </div>
      </header>

      <main className="flex flex-1 min-h-0 p-gutter gap-gutter overflow-hidden">
        <ReviewTrace
          check={check}
          onOpenRequest={(request) => setDrawer({ kind: 'request', request })}
          requests={requests}
          review={review}
        />

        {view === 'board' && board && lineId ? (
          <BoardPane
            action={toggle}
            candidate={placing}
            lineId={lineId}
            project={board.project}
            retiring={retiring}
          />
        ) : (
          <ComponentGraph
            action={toggle}
            activeRepair={null}
            animateEdges={false}
            // Never the working slot: this plays a 240 ms entrance animation for a slot that
            // has just appeared, and nothing appears on a board that already ships.
            animatedSlotIds={EMPTY}
            conflict={null}
            edges={graph.edges}
            onReleaseRepairHold={() => undefined}
            revealedSlotIds={revealed}
            slotConflictVariant={{}}
            slots={slots}
            supply={graph.supply}
            selectedSlotId={selectedSlotId}
            onSelectSlot={setSelectedSlotId}
          />
        )}

        {drawer.kind === 'notice' ? (
          <NoticePanel
            notices={notices}
            onClose={() => setDrawer({ kind: 'bom' })}
            onOpenRequest={(request) => setDrawer({ kind: 'request', request })}
            onStart={startOn}
            requests={requests}
            reviewed={review.trace.length > 0}
            running={review.status === 'running'}
          />
        ) : drawer.kind === 'request' ? (
          <SidePanel onClose={() => setDrawer({ kind: 'bom' })} title="CHANGE REQUEST">
            <div className="p-md">
              <RequestCard request={drawer.request.document} />
            </div>
          </SidePanel>
        ) : (
          <LineBom
            parts={parts}
            slots={slots}
            selectedSlotId={selectedSlotId}
            onSelectSlot={setSelectedSlotId}
          />
        )}
      </main>
    </div>
  )
}
