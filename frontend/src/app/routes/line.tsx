import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { BoardConsequence } from '../board/BoardConsequence'
import { ComponentGraph } from '../design/ComponentGraph'
import { ReviewTrace } from '../review/ReviewTrace'
import { useLineReview } from '../review/useLineReview'
import { Wordmark } from '../shell/Wordmark'
import {
  ApiError,
  checkLine,
  getLineOverview,
  putBoard,
  type LineCheck,
  type LineNotice,
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
  return Object.entries(rails)
    .map(([name, rail]) => {
      const volts = typeof rail.voltage === 'number' ? `${rail.voltage} V` : name.toUpperCase()
      const load = typeof rail.i_load === 'number' ? ` at ${Math.round(rail.i_load * 1000)} mA` : ''
      return `${volts}${load}`
    })
    .join(' · ')
}

/** One pane of the workspace, wearing the chrome every other pane wears. */
function Pane({
  title,
  action,
  children,
  className = '',
}: {
  title: string
  action?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <section
      className={`flex flex-col min-h-0 panel-border rounded-lg overflow-hidden bg-surface-container-low ${className}`}
    >
      <header className="h-10 px-md flex items-center justify-between gap-sm border-b border-outline-variant bg-surface-container-high flex-shrink-0">
        <h2 className="font-label-caps text-label-caps uppercase text-on-surface-variant">
          {title}
        </h2>
        {action}
      </header>
      {children}
    </section>
  )
}

/**
 * A product line, as the company has it, and where its review runs.
 *
 * **This is the design workspace, pointed at a product that already exists.** Same shell,
 * same three panes, same height lock: the trace on the left, the picture in the middle, what
 * the product is made of on the right. It was briefly a column of cards on a scrolling page,
 * which on a wide screen was a narrow strip of content in the middle of an empty field — and
 * a second implementation of a layout this application already had.
 *
 * Everything here is stored except the review and the per-visit check.
 */
export default function LineRoute() {
  const { lineId } = useParams<{ lineId: string }>()
  const navigate = useNavigate()

  const [overview, setOverview] = useState<LineOverview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [check, setCheck] = useState<LineCheck | null>(null)
  const [busy, setBusy] = useState(false)
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
  // takes a few seconds, so it must not sit in front of the render: the page arrives and
  // settles.
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

  const revealed = useMemo(
    () => new Set((graph?.slots ?? []).map((slot) => slot.id)),
    [graph],
  )

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
  // What the board render places: what the run settled on, or what it is trying right now.
  // Nothing to place means no toggle, rather than a toggle that leads nowhere.
  const placing = review.proposal ?? review.trying
  const retiring = notices[0]?.mpn ?? null
  const showBoard = view === 'board' && placing !== null && retiring !== null && Boolean(lineId)

  const startOn = (notice: LineNotice) => {
    setView('components')
    review.start(notice.id, notice.refdes)
  }

  return (
    <div className="h-full min-h-0 w-full overflow-hidden flex flex-col font-body-md antialiased bg-background text-on-background">
      <header className="flex items-center justify-between gap-md w-full px-lg h-12 flex-shrink-0 bg-surface-container-low border-b border-outline-variant shadow-[0_1px_0_0_rgba(255,255,255,0.05)]">
        <div className="flex items-center gap-md min-w-0">
          <Link
            className="h-8 w-8 -ml-1 rounded flex items-center justify-center text-on-surface-variant hover:text-primary-container hover:bg-surface-container-high transition-colors flex-shrink-0"
            to="/lines"
          >
            <span className="material-symbols-outlined text-[20px]">arrow_back</span>
          </Link>
          <div className="min-w-0">
            <h1 className="font-label-caps text-label-caps tracking-[0.1em] uppercase text-on-surface truncate">
              {line.name}
            </h1>
            <p className="font-data-tabular text-[10px] text-on-surface-variant truncate">
              {line.revision ? `${line.revision} · ` : ''}
              {fitted.length} part{fitted.length === 1 ? '' : 's'}
              {profile ? ` · ${profile.ambient_c} °C ambient` : ''}
              {railSummary(overview) ? ` · ${railSummary(overview)}` : ''}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-md flex-shrink-0">
          {error ? (
            <span className="font-data-tabular text-[10px] text-error">{error}</span>
          ) : null}
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
          <Wordmark />
        </div>
      </header>

      <main className="flex flex-1 min-h-0 p-gutter gap-gutter overflow-hidden">
        <ReviewTrace
          check={check}
          notices={notices}
          onOpenNotice={(id) => navigate(`/changes?notice=${encodeURIComponent(id)}`)}
          onStart={startOn}
          requests={requests}
          review={review}
        />

        <div className="flex-1 min-w-0 flex flex-col min-h-0">
          {showBoard && lineId && retiring && placing ? (
            <Pane
              action={
                <Toggle onChange={setView} value={view} />
              }
              className="flex-1"
              title="THE BOARD"
            >
              <div className="flex-1 min-h-0 overflow-y-auto p-md">
                <BoardConsequence auto candidate={placing} lineId={lineId} retiring={retiring} />
              </div>
            </Pane>
          ) : graph.slots.length > 0 ? (
            <div className="flex-1 min-h-0 flex relative">
              <ComponentGraph
                activeRepair={null}
                animateEdges={false}
                // Never the working slot: this plays a 240 ms entrance animation for a slot
                // that has just appeared, and nothing appears on a board that already ships.
                animatedSlotIds={EMPTY}
                conflict={null}
                edges={graph.edges}
                onReleaseRepairHold={() => undefined}
                revealedSlotIds={revealed}
                slotConflictVariant={{}}
                slots={slots}
                supply={graph.supply}
              />
              {placing ? (
                <div className="absolute right-md top-1.5 z-10">
                  <Toggle onChange={setView} value={view} />
                </div>
              ) : null}
            </div>
          ) : (
            <Pane className="flex-1" title="COMPONENT LOGIC GRAPH">
              <p className="p-md font-data-tabular text-[11px] text-on-surface-variant">
                No parts are recorded against this product line yet.
              </p>
            </Pane>
          )}
        </div>

        <div className="w-[340px] flex-shrink-0 flex flex-col gap-gutter min-h-0">
          <Pane className="flex-1" title="BILL OF MATERIALS">
            <div className="flex-1 min-h-0 overflow-y-auto">
              <table className="w-full font-data-tabular text-[11px]">
                <thead>
                  <tr className="text-on-surface-variant/70">
                    <th className="text-left font-normal px-md py-1">REF</th>
                    <th className="text-left font-normal px-md py-1">PART</th>
                    <th className="text-left font-normal px-md py-1">FOOTPRINT</th>
                  </tr>
                </thead>
                <tbody>
                  {parts.map((part) => (
                    <tr className="border-t border-outline-variant/50 align-top" key={part.refdes}>
                      <td className="px-md py-1 text-on-surface-variant uppercase">
                        {part.refdes}
                      </td>
                      <td className="px-md py-1 text-on-surface">
                        {part.mpn}
                        {part.populated ? '' : ' · not fitted'}
                        <span className="block text-on-surface-variant">
                          {part.manufacturer ?? '—'}
                        </span>
                      </td>
                      <td className="px-md py-1 text-on-surface-variant">
                        {part.footprint ?? '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Pane>

          <Pane className="flex-shrink-0" title="BOARD">
            {board ? (
              <p className="px-md py-sm font-data-tabular text-[11px] text-on-surface">
                {board.project}
                <span className="block text-[10px] text-on-surface-variant">
                  {board.filename} · {bytes(board.bytes)} · attached{' '}
                  {new Date(board.uploaded_at).toLocaleDateString()}
                </span>
              </p>
            ) : (
              <p className="px-md py-sm font-data-tabular text-[11px] text-on-surface-variant">
                No KiCad project is attached. With one, a substitution can be placed on the
                real board and the connections it breaks are reported by KiCad itself.
              </p>
            )}
          </Pane>
        </div>
      </main>
    </div>
  )
}

/** COMPONENTS or BOARD, in one place so the two positions it can sit in cannot disagree. */
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
              ? 'border-primary-container text-primary-container bg-surface-container-high'
              : 'border-outline-variant text-on-surface-variant bg-surface-container-high hover:bg-surface-variant'
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
