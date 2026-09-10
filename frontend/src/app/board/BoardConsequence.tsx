import { useCallback, useEffect, useMemo, useState } from 'react'

import { ApiError, boardConsequence, type BoardConsequence as Consequence } from '../lib/api'
import { recallPlacement, rememberPlacement } from './placements'

type CropPhase = 'before' | 'after'

export function cropTreatment(phase: CropPhase) {
  return phase === 'after'
    ? { overlay: '#a78bfa', stroke: '#c4b5fd' }
    : { overlay: 'none', stroke: '#e5e7eb' }
}

export function cropBox(crop: string) {
  const [x, y, width, height] = crop.split(/\s+/).map(Number)
  return { x, y, width, height }
}

export function boardChangeCaption({
  footprint,
  retiring,
  candidate,
}: Pick<Consequence, 'footprint' | 'retiring' | 'candidate'>) {
  const dropIn = footprint.from === footprint.to ? ' (DROP-IN)' : ''
  return `FOOTPRINT: ${footprint.from} → ${footprint.to}${dropIn} · FITTED PART: ${retiring} → ${candidate}`
}

/** The same rectangle of the board, before and after.
 *
 *  Both pictures are the whole page, rendered in board millimetres, and both are cropped to
 *  the identical viewBox around the part that changed. That is the entire reason the render
 *  is done in page coordinates rather than fitted to the board: fitted, the two pictures
 *  would need aligning by eye, and a reader comparing two pictures by eye is a reader who
 *  cannot tell whether anything moved. */
function Crop({ svg, crop, page, label, phase }: {
  svg: string
  crop: string
  page: { width: number; height: number }
  label: string
  phase: CropPhase
}) {
  // Created and revoked in **one** effect, so the two always pair up.
  //
  // It used to be a `useMemo` creating the URL and an effect revoking it, and those have
  // different lifecycles: React runs an effect, cleans it up and runs it again on mount in
  // development, while a memo runs once — so the cleanup revoked the only URL there was and
  // the `<image>` pointed at a blob the browser no longer had. **Both board pictures came up
  // blank**, with `net::ERR_FILE_NOT_FOUND` in the console and nothing on screen saying
  // anything was wrong. `./demo.sh` serves the UI through Vite with `StrictMode` on, so this
  // was the demo, not a development-only curiosity.
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    const created = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }))
    setUrl(created)
    return () => URL.revokeObjectURL(created)
  }, [svg])

  // The crop is built around the part, so its centre is the part. Derived rather than
  // sent again: two fields that have to agree are two fields that can disagree.
  const box = useMemo(() => cropBox(crop), [crop])
  const centre = { x: box.x + box.width / 2, y: box.y + box.height / 2 }
  const treatment = cropTreatment(phase)

  return (
    <figure className="flex-1 min-w-[200px] space-y-1">
      <figcaption className={`font-data-tabular text-[10px] ${phase === 'after' ? 'text-[#c4b5fd]' : 'text-on-surface-variant'}`}>
        {label}
      </figcaption>
      <svg
        className={`w-full aspect-square bg-black border rounded ${phase === 'after' ? 'border-[#c4b5fd]' : 'border-outline-variant'}`}
        viewBox={crop}
      >
        {url ? <image href={url} x="0" y="0" width={page.width} height={page.height} /> : null}
        {treatment.overlay !== 'none' ? (
          <rect
            fill={treatment.overlay}
            height={box.height}
            opacity={0.14}
            width={box.width}
            x={box.x}
            y={box.y}
          />
        ) : null}
        {/* Where to look. The crop is centred on the part, and on a board with a copper
            pour under it a regulator is otherwise one red shape among many. */}
        <rect
          fill="none"
          height={7}
          stroke={treatment.stroke}
          strokeDasharray="0.6 0.6"
          strokeWidth={0.15}
          width={7}
          x={centre.x - 3.5}
          y={centre.y - 3.5}
        />
      </svg>
    </figure>
  )
}

/** What a substitute does to the board this product line is actually built from.
 *
 *  Nothing here decides anything. KiCad places the part where the retired one sits, runs its
 *  own design rule check before and after, and this renders the difference — which is the
 *  fact a change request cannot get anywhere else: the cheap part costs a layout revision on
 *  this board and none on that one. */
export function BoardConsequence({
  lineId,
  retiring,
  candidate,
  auto = false,
}: {
  lineId: string
  retiring: string
  candidate: string | null
  /** Place it as soon as this is on screen. The change request asks first, because it is a
   *  document somebody is reading; a toggle on the product line page has already asked —
   *  choosing BOARD *is* the request, and a second button inside it would be the same
   *  question twice. */
  auto?: boolean
}) {
  // Straight out of the session's placements when this board has been placed before, so a
  // remount paints the picture rather than starting a KiCad run behind a **PLACING…**.
  const [outcome, setOutcome] = useState<Consequence | null>(() =>
    recallPlacement(lineId, retiring, candidate),
  )
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const check = useCallback(async () => {
    if (!candidate) return
    const known = recallPlacement(lineId, retiring, candidate)
    if (known) {
      setOutcome(known)
      setMessage(null)
      return
    }
    setBusy(true)
    setMessage(null)
    setOutcome(null)
    try {
      const placed = await boardConsequence(lineId, retiring, candidate)
      rememberPlacement(lineId, retiring, candidate, placed)
      setOutcome(placed)
    } catch (caught) {
      // Each of these is a different true sentence, and collapsing them into "that
      // failed" would hide the only one the reader can act on.
      setMessage(
        caught instanceof ApiError
          ? caught.status === 404
            ? 'No KiCad project is attached to this product line, so there is no board to check.'
            : caught.status === 503
              ? 'This instance has no KiCad configured, so a board cannot be checked here.'
              : (caught.message ?? 'That board could not be checked.')
          : 'That board could not be checked.',
      )
    } finally {
      setBusy(false)
    }
  }, [candidate, lineId, retiring])

  // Guarded on the part rather than on a "have run" flag: `check` changes identity when the
  // candidate does, which is exactly when the board should be placed again. A board already
  // placed in this session comes back from `placements` without another KiCad run, so a
  // refetch behind the BOARD view no longer takes the picture away and puts PLACING… there.
  useEffect(() => {
    if (auto) void check()
  }, [auto, check])

  if (!candidate) return null

  return (
    <section className={auto ? 'space-y-sm' : 'space-y-sm border-t border-outline-variant pt-md'}>
      <div className="flex items-center justify-between gap-md">
        {/* Not when `auto`: the caller is a pane that has already named this, and two
            headings for one picture is what a change request and a product line page
            printed side by side. */}
        {auto ? <span /> : (
          <h4 className="font-data-tabular text-[10px] text-on-surface-variant">THE BOARD</h4>
        )}
        <button
          className="h-7 px-md border border-outline-variant rounded font-data-tabular text-[10px] text-on-surface-variant hover:bg-surface-variant transition-colors disabled:opacity-40"
          disabled={busy}
          onClick={() => void check()}
          type="button"
        >
          {busy ? 'PLACING…' : auto ? 'PLACE IT AGAIN' : `PLACE ${candidate} ON THIS BOARD`}
        </button>
      </div>

      {message ? (
        <p className="font-data-tabular text-[10px] text-tertiary-container leading-relaxed">
          {message}
        </p>
      ) : null}

      {outcome ? (
        <div className="space-y-sm">
          <p className="font-data-tabular text-[11px] leading-relaxed">
            <span className={outcome.broke_connections ? 'text-error' : 'text-[#4ade80]'}>
              {outcome.broke_connections
                ? `${outcome.added.filter((f) => f.rule === 'unconnected_items').length} connections break`
                : 'No connections break'}
            </span>{' '}
            <span className="text-on-surface-variant">
              at {outcome.refdes}, {outcome.package.from} → {outcome.package.to}.
              {outcome.broke_connections
                ? ' This board needs layout work before the substitution can ship.'
                : ' The pads it lands on are the pads that are already there.'}
            </span>
          </p>

          <p className="font-data-tabular text-[10px] text-on-surface-variant leading-relaxed">
            {boardChangeCaption(outcome)}
          </p>

          <div className="flex gap-md">
            <Crop
              crop={outcome.crop}
              label={`BEFORE · ${outcome.retiring}`}
              page={outcome.page}
              phase="before"
              svg={outcome.before_svg}
            />
            <Crop
              crop={outcome.crop}
              label={`AFTER · ${outcome.candidate}`}
              page={outcome.page}
              phase="after"
              svg={outcome.after_svg}
            />
          </div>

          {outcome.added.length > 0 ? (
            <div className="space-y-1">
              <h5 className="font-data-tabular text-[10px] text-on-surface-variant">
                WHAT THE DESIGN RULE CHECK FOUND THAT IT DID NOT FIND BEFORE
              </h5>
              {/* KiCad's own words, and both ends of each complaint. The board already
                  carried findings of its own before anything was touched, so only the
                  difference is shown — a count would be meaningless. */}
              {outcome.added.slice(0, 12).map((finding, index) => (
                <p
                  key={`${finding.rule}:${index}`}
                  className="font-data-tabular text-[10px] text-on-surface-variant leading-relaxed"
                >
                  <span className={finding.severity === 'error' ? 'text-error' : 'text-on-surface'}>
                    {finding.rule.replace(/_/g, ' ')}
                  </span>{' '}
                  — {finding.items.join(' / ') || finding.description}
                </p>
              ))}
              {outcome.added.length > 12 ? (
                <p className="font-data-tabular text-[10px] text-on-surface-variant/70">
                  and {outcome.added.length - 12} more.
                </p>
              ) : null}
            </div>
          ) : null}

          {outcome.wiring.unwired_pads.length > 0 || outcome.wiring.stranded.length > 0 ? (
            <div className="space-y-1">
              {outcome.wiring.unwired_pads.length > 0 ? (
                <p className="font-data-tabular text-[10px] text-tertiary-container">
                  Left unconnected: pad{outcome.wiring.unwired_pads.length === 1 ? '' : 's'}{' '}
                  {outcome.wiring.unwired_pads.join(', ')} of {outcome.candidate}. The board
                  has no net for them, and nothing was invented to fill them.
                </p>
              ) : null}
              {outcome.wiring.stranded.length > 0 ? (
                <p className="font-data-tabular text-[10px] text-error">
                  Nowhere to go: {outcome.wiring.stranded.join(', ')}. The substitute has no
                  pin for a net the retired part carried.
                </p>
              ) : null}
            </div>
          ) : null}

          <p className="font-data-tabular text-[10px] text-on-surface-variant/70 leading-relaxed">
            pins read from: {outcome.pinout_source}
          </p>
        </div>
      ) : null}
    </section>
  )
}
