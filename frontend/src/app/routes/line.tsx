import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router'

import { ComponentGraph } from '../design/ComponentGraph'
import { Page } from '../shell/Page'
import {
  ApiError,
  getLineOverview,
  putBoard,
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
 *  This did not exist. Opening a product line went to the brief entry — *"What are you
 *  building?"* — for a product with three parts fitted, an operating profile, a revision and
 *  a live end-of-life notice against it. Everything on this page is stored: nothing is
 *  planned, sourced or fetched to render it. */
export default function LineRoute() {
  const { lineId } = useParams<{ lineId: string }>()
  const navigate = useNavigate()

  const [overview, setOverview] = useState<LineOverview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
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

  if (error && !overview) {
    return (
      <Page back={{ to: '/lines', label: 'PRODUCT LINES' }} title="PRODUCT LINE">
        <p className="font-data-tabular text-[11px] text-error">{error}</p>
      </Page>
    )
  }

  if (!overview) {
    return (
      <Page back={{ to: '/lines', label: 'PRODUCT LINES' }} title="PRODUCT LINE">
        <p className="font-data-tabular text-[11px] text-on-surface-variant">Loading…</p>
      </Page>
    )
  }

  const { line, parts, graph, board, notices, requests } = overview
  const profile = line.profile
  const fitted = parts.filter((part) => part.populated)

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
          that is about to change. */}
      {notices.length > 0 ? (
        <section className="space-y-sm">
          {notices.map((notice) => (
            <button
              className="w-full text-left border border-error/60 bg-error-container/10 rounded p-md hover:bg-error-container/20 transition-colors"
              key={notice.id}
              onClick={() => navigate('/notices')}
              type="button"
            >
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
            </button>
          ))}
        </section>
      ) : null}

      {/* The graph brings its own panel and header, which is the one the workspace uses.
          A second header above it would be two titles for one picture. */}
      <section className="flex flex-col gap-1">
        {graph.slots.length > 0 ? (
          <div className="h-[420px] flex">
            <ComponentGraph
              activeRepair={null}
              animateEdges={false}
              animatedSlotIds={EMPTY}
              conflict={null}
              edges={graph.edges}
              onReleaseRepairHold={() => undefined}
              revealedSlotIds={new Set(graph.slots.map((slot) => slot.id))}
              slotConflictVariant={{}}
              slots={graph.slots}
              supply={graph.supply}
            />
          </div>
        ) : (
          <p className="font-data-tabular text-[11px] text-on-surface-variant border border-outline-variant rounded p-md">
            No parts are recorded against this product line yet.
          </p>
        )}
        {/* Said plainly, because the picture would otherwise be read as the schematic, and
            because a real board leaves thirty parts off this picture. Both omissions are
            stated rather than left for somebody to notice. */}
        <p className="font-data-tabular text-[10px] text-on-surface-variant/70">
          The power tree this product line states: which part makes each rail and what that
          rail feeds. Not a netlist — nothing here has read a schematic.
          {graph.off_tree > 0
            ? ` ${graph.off_tree} more fitted part${graph.off_tree === 1 ? '' : 's'} sit on the bill and on no rail — decoupling, pull-ups and connectors — and are listed below.`
            : ''}
        </p>
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
