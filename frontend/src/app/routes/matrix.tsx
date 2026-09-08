import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  ApiError,
  buildMatrix,
  listLines,
  type Line,
  type MatrixCell,
  type MatrixResponse,
} from '../lib/api'
import type { EventStatus } from '../lib/types'
import { Page } from '../shell/Page'

/** The five coverage labels as a reader should see them, in the order they are read.
 *
 *  Satisfied first, then what failed, then the three ways a check can decline to answer.
 *  The zeroes are shown too: a grid that prints a count only when it is non-zero makes a
 *  reader compare cells of different shapes, and "nothing missing here" is worth seeing
 *  beside a cell where three checks had nothing to read. */
const COVERAGE: Array<{ key: EventStatus; label: string; tone: string }> = [
  { key: 'satisfied', label: 'satisfied', tone: 'text-[#4ade80]' },
  { key: 'failed', label: 'failed', tone: 'text-error' },
  { key: 'evidence_missing', label: 'no evidence', tone: 'text-tertiary-container' },
  { key: 'not_assessed', label: 'not assessed', tone: 'text-on-surface-variant' },
  { key: 'not_applicable', label: 'n/a', tone: 'text-on-surface-variant' },
]

/** A margin under this reads as "it holds, and nobody would ship it".
 *
 *  Ten degrees is not a standard; it is the point at which a reader should stop treating a
 *  pass as an answer and start treating it as a question. The number is shown either way —
 *  this only decides whether it is shouted. */
const NARROW_MARGIN_C = 10

function isNarrow(margin: string | null): boolean {
  if (!margin) {
    return false
  }
  const value = Number.parseFloat(margin)
  return Number.isFinite(value) && value < NARROW_MARGIN_C
}

function CellBadge({ cell, onOpen }: { cell: MatrixCell; onOpen: () => void }) {
  const narrow = cell.ok && isNarrow(cell.margin)
  const tone = !cell.ok
    ? 'border-error text-error'
    : narrow
      ? 'border-tertiary-container text-tertiary-container'
      : 'border-outline-variant text-[#4ade80]'

  return (
    <button
      className={`w-full h-full px-sm py-sm border rounded text-left hover:bg-surface-variant transition-colors ${tone}`}
      onClick={onOpen}
      type="button"
    >
      <div className="font-data-tabular text-[12px] font-semibold">
        {cell.ok ? (narrow ? 'HOLDS' : 'PASSES') : 'FAILS'}
      </div>
      <div className="font-data-tabular text-[10px] text-on-surface-variant mt-0.5 truncate">
        {cell.ok
          ? cell.margin
            ? `${cell.margin} to spare`
            : 'no margin reported'
          : cell.checks.find((check) => check.status === 'failed')?.rule.replace(/_/g, ' ')}
      </div>
      {cell.departments.length > 0 ? (
        <div className="font-data-tabular text-[10px] text-on-surface-variant mt-1 truncate">
          {cell.departments.join(' · ')}
        </div>
      ) : null}
    </button>
  )
}

function CellDetail({ cell, onClose }: { cell: MatrixCell; onClose: () => void }) {
  return (
    <aside className="w-[440px] flex-shrink-0 bg-surface-container-low border-l border-surface-bright flex flex-col overflow-hidden">
      <div className="p-lg border-b border-surface-bright flex justify-between items-start gap-md">
        <div className="min-w-0">
          <h2 className="font-headline-sm text-headline-sm text-on-surface truncate">{cell.mpn}</h2>
          <p className="font-data-tabular text-[11px] text-on-surface-variant mt-1">
            {cell.line_name}
            {cell.is_incumbent ? ' · fitted today' : cell.replaces ? ` · would replace ${cell.replaces}` : ''}
          </p>
        </div>
        <button
          className="font-data-tabular text-[11px] text-on-surface-variant hover:text-on-surface"
          onClick={onClose}
          type="button"
        >
          CLOSE
        </button>
      </div>

      <div className="px-lg py-md border-b border-surface-bright flex flex-wrap gap-x-md gap-y-1">
        {COVERAGE.map(({ key, label, tone }) => (
          <span key={key} className={`font-data-tabular text-[10px] ${cell.counts[key] ? tone : 'text-on-surface-variant/50'}`}>
            {cell.counts[key]} {label}
          </span>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-lg space-y-md">
        {cell.checks.map((check, index) => (
          <div key={`${check.rule}:${check.scope ?? ''}:${index}`} className="space-y-1">
            <div className="flex items-baseline gap-sm">
              <span className="font-data-tabular text-[11px] text-on-surface">
                {check.rule.replace(/_/g, ' ')}
              </span>
              {check.scope ? (
                <span className="font-data-tabular text-[10px] text-on-surface-variant">{check.scope}</span>
              ) : null}
              <span
                className={`font-data-tabular text-[10px] ml-auto ${
                  check.status === 'failed'
                    ? 'text-error'
                    : check.status === 'satisfied'
                      ? 'text-[#4ade80]'
                      : 'text-on-surface-variant'
                }`}
              >
                {check.accepted ? 'FAILED · ACCEPTED' : check.status.replace(/_/g, ' ').toUpperCase()}
                {check.margin ? ` · ${check.margin}` : ''}
              </span>
            </div>
            <p className="font-data-tabular text-[10px] text-on-surface-variant leading-relaxed">
              {check.detail}
            </p>
            {/* Every number a verdict rests on, with where it came from. A thermal result
                is only as good as the θJA under it and the copper that was measured on. */}
            {check.evidence.map((row) => (
              <p key={row.field} className="font-data-tabular text-[10px] text-on-surface-variant/70 pl-md">
                {row.field}: {row.value}
                {row.source ? ` — ${row.source}` : ''}
              </p>
            ))}
          </div>
        ))}
      </div>
    </aside>
  )
}

export default function MatrixRoute() {
  const [lines, setLines] = useState<Line[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [slot, setSlot] = useState('u1')
  const [candidates, setCandidates] = useState('')
  const [matrix, setMatrix] = useState<MatrixResponse | null>(null)
  const [open, setOpen] = useState<MatrixCell | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    let active = true
    listLines()
      .then((next) => {
        if (active) {
          setLines(next)
          setSelected(next.filter((line) => line.profile).map((line) => line.id))
        }
      })
      .catch(() => {
        if (active) {
          setError('Could not load your product lines.')
        }
      })
    return () => {
      active = false
    }
  }, [])

  const run = useCallback(async () => {
    const wanted = candidates
      .split(/[,\n]/)
      .map((mpn) => mpn.trim())
      .filter(Boolean)

    if (selected.length === 0 || wanted.length === 0) {
      setError('Choose at least one product line and one candidate part.')
      return
    }

    setRunning(true)
    setError(null)
    setOpen(null)
    try {
      setMatrix(await buildMatrix(selected, slot.trim(), wanted))
    } catch (caught) {
      // The server's own sentence, when it has one. A 409 here says something specific and
      // actionable — a line with no operating profile, or one that does not carry the part
      // — and replacing it with "something went wrong" throws that away.
      setMatrix(null)
      setError(
        caught instanceof ApiError && caught.status === 404
          ? 'One of those product lines is not yours.'
          : 'That matrix could not be built. Check the position and the product lines you chose.',
      )
    } finally {
      setRunning(false)
    }
  }, [candidates, selected, slot])

  const rows = useMemo(() => {
    if (!matrix) {
      return []
    }
    return matrix.lines.map((lineId) => ({
      lineId,
      name: matrix.cells.find((cell) => cell.line_id === lineId)?.line_name ?? lineId,
      cells: matrix.candidates.map(
        (mpn) => matrix.cells.find((cell) => cell.line_id === lineId && cell.mpn === mpn) ?? null,
      ),
    }))
  }, [matrix])

  return (
    <Page
      back={{ to: '/lines', label: 'PRODUCT LINES' }}
      subtitle="Every candidate against every product line, each under its own stored conditions."
      title="SUBSTITUTION MATRIX"
    >
      <div className="flex flex-col gap-md">

        <div className="px-lg py-md border-b border-surface-bright flex flex-wrap items-end gap-md">
          <label className="flex flex-col gap-1">
            <span className="font-data-tabular text-[10px] text-on-surface-variant">POSITION</span>
            <input
              className="input-field px-sm h-8 w-24 font-data-tabular text-[11px]"
              onChange={(event) => setSlot(event.target.value)}
              value={slot}
            />
          </label>
          <label className="flex flex-col gap-1 flex-1 min-w-[280px]">
            <span className="font-data-tabular text-[10px] text-on-surface-variant">
              CANDIDATE PARTS — one per line, or comma separated
            </span>
            <input
              className="input-field px-sm h-8 w-full font-data-tabular text-[11px]"
              onChange={(event) => setCandidates(event.target.value)}
              placeholder="AMS1117-3.3, NCP1117ST33T3G"
              value={candidates}
            />
          </label>
          <button
            className="h-8 px-md border border-primary-container rounded font-data-tabular text-[11px] text-primary-container hover:bg-surface-variant transition-colors disabled:opacity-40"
            disabled={running}
            onClick={run}
            type="button"
          >
            {running ? 'CHECKING…' : 'CHECK EVERY LINE'}
          </button>
        </div>

        <div className="px-lg py-sm border-b border-surface-bright flex flex-wrap gap-sm">
          {lines.map((line) => {
            const chosen = selected.includes(line.id)
            return (
              <button
                key={line.id}
                className={`px-sm py-0.5 border rounded font-data-tabular text-[10px] transition-colors ${
                  chosen
                    ? 'border-primary-container text-primary-container'
                    : 'border-outline-variant text-on-surface-variant'
                } ${line.profile ? '' : 'opacity-40'}`}
                onClick={() =>
                  setSelected((current) =>
                    current.includes(line.id)
                      ? current.filter((id) => id !== line.id)
                      : [...current, line.id],
                  )
                }
                title={line.profile ? undefined : 'No operating profile stored, so nothing can be checked against it'}
                type="button"
              >
                {line.name}
              </button>
            )
          })}
        </div>

        {error ? (
          <p className="px-lg py-md font-data-tabular text-[11px] text-error">{error}</p>
        ) : null}

        {matrix ? (
          <div className="flex-1 overflow-auto p-lg">
            {matrix.unresolved.length > 0 ? (
              <p className="font-data-tabular text-[11px] text-tertiary-container mb-md">
                Not found at the distributor, so not checked: {matrix.unresolved.join(', ')}
              </p>
            ) : null}

            {Object.entries(matrix.ambiguous).map(([mpn, reason]) => (
              <p key={mpn} className="font-data-tabular text-[11px] text-tertiary-container mb-md">
                {reason}
              </p>
            ))}

            <table className="w-full border-separate border-spacing-1">
              <thead>
                <tr>
                  <th className="text-left font-data-tabular text-[10px] text-on-surface-variant font-normal p-sm">
                    PRODUCT LINE
                  </th>
                  {matrix.candidates.map((mpn) => (
                    <th
                      key={mpn}
                      className="text-left font-data-tabular text-[10px] text-on-surface font-normal p-sm min-w-[150px]"
                    >
                      {mpn}
                      {matrix.viable_everywhere.includes(mpn) ? (
                        <span className="block text-[#4ade80]">clears every line</span>
                      ) : (
                        <span className="block text-on-surface-variant">not viable everywhere</span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.lineId}>
                    <th className="text-left align-top font-data-tabular text-[11px] text-on-surface font-normal p-sm">
                      {row.name}
                    </th>
                    {row.cells.map((cell, index) => (
                      <td key={matrix.candidates[index]} className="align-top">
                        {cell ? <CellBadge cell={cell} onOpen={() => setOpen(cell)} /> : null}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Said once, under the grid, rather than repeated in every cell: a candidate
                that clears two lines of three is not a two-thirds answer, it is a part that
                breaks a product. */}
            <p className="font-data-tabular text-[11px] text-on-surface-variant mt-lg">
              {matrix.viable_everywhere.length > 0
                ? `Clears every product line: ${matrix.viable_everywhere.join(', ')}.`
                : 'No candidate clears every product line.'}
              {matrix.departments.length > 0
                ? ` Decisions here belong to ${matrix.departments.join(' and ')}.`
                : ''}
            </p>
          </div>
        ) : (
          <p className="px-lg py-lg font-data-tabular text-[11px] text-on-surface-variant">
            Name the position the part sits in and the parts you are considering. Every
            product line is checked under its own stored conditions.
          </p>
        )}
      </div>

      {open ? <CellDetail cell={open} onClose={() => setOpen(null)} /> : null}
    </Page>
  )
}
