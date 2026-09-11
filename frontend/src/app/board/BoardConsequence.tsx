import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { streamBoardConsequence, type BoardStep, type BoardConsequence as Consequence } from '../lib/api'
import { kicadMissing, noteKicadMissing, recallPlacement, rememberPlacement } from './placements'

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
  stored = null,
}: {
  lineId: string
  retiring: string
  candidate: string | null
  /** Place it as soon as this is on screen. The change request asks first, because it is a
   *  document somebody is reading; a toggle on the product line page has already asked —
   *  choosing BOARD *is* the request, and a second button inside it would be the same
   *  question twice. */
  auto?: boolean
  /** The consequence the run already computed, if it landed. See `attach_board_consequence`.
   *
   *  A change request carries this once the background placement finishes, so the card opens
   *  with the pictures on it rather than behind a button nobody presses. A request without
   *  one — a world with no KiCad, or a run whose placement has not landed yet — keeps the
   *  button, which is the honest degradation this surface already renders. */
  stored?: Consequence | null
}) {
  // Straight out of the session's placements when this board has been placed before, so a
  // remount paints the picture rather than starting a KiCad run behind a **PLACING…**. What
  // the document carries wins over the session, because it came from the run itself.
  const [outcome, setOutcome] = useState<Consequence | null>(
    () => stored ?? recallPlacement(lineId, retiring, candidate),
  )
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // **Which candidate the pane is currently asking about.** A placement takes seconds, and
  // the candidate can change while one is in flight — a replayed review walks `trying`
  // through every part it tried, and the product line page feeds this component from that.
  // Without this the last response to *arrive* wins rather than the last one *asked for*,
  // so an intermediate candidate can be the picture on a board the review settled elsewhere.
  const wanted = useRef<string | null>(candidate)
  wanted.current = candidate

  /** The operations this placement has finished, as it finishes them. */
  const [steps, setSteps] = useState<BoardStep[]>([])
  const running = useRef<(() => void) | null>(null)

  // A stream outlives the component that opened it unless it is closed, and a board being
  // placed is ten seconds of a worker thread writing into a callback.
  useEffect(() => () => running.current?.(), [])

  const check = useCallback(() => {
    if (!candidate) return
    const known = recallPlacement(lineId, retiring, candidate)
    if (known) {
      setOutcome(known)
      setMessage(null)
      setSteps([])
      return
    }
    running.current?.()
    setBusy(true)
    setMessage(null)
    setSteps([])
    // **Said while it happens.** A cold board takes ten seconds, and the pane used to sit on
    // *PLACING…* for all of it and then put everything on screen at once. The same five
    // operations the WHAT RAN block lists are sent as each one finishes, so the wait is the
    // work being reported rather than a spinner over it.
    //
    // **The picture stays until its replacement lands.** It used to be cleared the moment a
    // placement started, so the pane said nothing at all while KiCad worked — and on a board
    // being placed for a second candidate, the caption and the crops disappeared and came
    // back. A stale picture with the work beside it is a truer screen than an empty one.
    running.current = streamBoardConsequence(lineId, retiring, candidate, {
      onStep: (step) => {
        if (wanted.current !== candidate) return
        setSteps((current) => [...current, step])
      },
      onDone: (placed) => {
        rememberPlacement(lineId, retiring, candidate, placed)
        // A placement that was superseded while it ran paints nothing: the call that
        // replaced it owns the pane now, and this one's picture is about a part nobody is
        // looking at.
        if (wanted.current !== candidate) return
        setOutcome(placed)
        setSteps([])
        setBusy(false)
      },
      onError: (message, status) => {
        // **A 503 is remembered, and then nothing is drawn.** On an instance with no KiCad
        // every document would otherwise place itself, fail, and print the same sentence,
        // which reads as a broken feature. The capability is absent rather than broken, so
        // after the server has said so once the pane simply carries no board section.
        if (status === 503) noteKicadMissing()
        if (wanted.current !== candidate) return
        // Each of these is a different true sentence, and collapsing them into "that
        // failed" would hide the only one the reader can act on.
        setMessage(
          status === 404
            ? 'No KiCad project is attached to this product line, so there is no board to check.'
            : status === 503
              ? 'This instance has no KiCad configured, so a board cannot be checked here.'
              : message,
        )
        setBusy(false)
      },
    })
  }, [candidate, lineId, retiring])

  // Guarded on the part rather than on a "have run" flag: `check` changes identity when the
  // candidate does, which is exactly when the board should be placed again. A board already
  // placed in this session comes back from `placements` without another KiCad run, so a
  // refetch behind the BOARD view no longer takes the picture away and puts PLACING… there.
  useEffect(() => {
    // **Not when the document already carries the picture.** `auto` is what makes the pane
    // place a substitute without being asked, and the run fires one per line in the
    // background, so most of the time the answer is already here. Placing again would spend
    // eleven seconds of KiCad to redraw a picture that is on screen.
    if (auto && !stored && !kicadMissing()) void check()
  }, [auto, check, stored])

  if (!candidate) return null

  // Read from the payload rather than written here: which pads were carried and what DRC
  // changed are facts about *this* board, and the pane that describes the substitution has
  // never had them.
  const wired = outcome
    ? Object.entries(outcome.wiring.wired)
        .map(([pad, net]) => `pad ${pad} \u2192 ${net}`)
        .join(', ')
    : ''
  const changed = Object.entries(outcome?.counts ?? {})

  return (
    <section className={auto ? 'space-y-sm' : 'space-y-sm border-t border-outline-variant pt-md'}>
      <div className="flex items-center justify-between gap-md">
        {/* Not when `auto`: the caller is a pane that has already named this, and two
            headings for one picture is what a change request and a product line page
            printed side by side. */}
        {auto ? <span /> : (
          <h4 className="font-data-tabular text-[10px] text-on-surface-variant">THE BOARD</h4>
        )}
        {/* **No button when the document already carries the board.** The run computed this
            one and stored it, so a control offering to compute it again is an affordance with
            nothing to do — and the whole point of storing it was that the card opens with the
            picture on it. A request without one keeps the button, which is the honest
            degradation for a world with no KiCad. */}
        {stored ? null : (
          <button
            className="h-7 px-md border border-outline-variant rounded font-data-tabular text-[10px] text-on-surface-variant hover:bg-surface-variant transition-colors disabled:opacity-40"
            disabled={busy}
            onClick={() => void check()}
            type="button"
          >
            {busy ? 'PLACING…' : auto ? 'PLACE IT AGAIN' : `PLACE ${candidate} ON THIS BOARD`}
          </button>
        )}
      </div>

      {message ? (
        <p className="font-data-tabular text-[10px] text-tertiary-container leading-relaxed">
          {message}
        </p>
      ) : null}

      {/* **What ran, said while it runs.** Drawn from the outcome once there is one and from
          the stream until then, so the block is the same block and the same five sentences
          whether it was watched or read afterwards. The last line is the one in progress,
          which is the whole difference between a wait and a spinner. */}
      {busy ? (
        <div className="space-y-0.5">
          <p className="m-0 font-data-tabular text-[10px] text-on-surface-variant">WHAT RAN</p>
          {steps.map((step, index) => (
            <p
              className={`m-0 font-data-tabular text-[10px] leading-relaxed ${
                index === steps.length - 1 ? 'text-on-surface' : 'text-on-surface-variant/80'
              }`}
              key={`${step.name}:${index}`}
            >
              {step.name} ·{' '}
              {step.ms >= 1000 ? `${(step.ms / 1000).toFixed(1)} s` : `${step.ms} ms`}
            </p>
          ))}
          <p className="m-0 font-data-tabular text-[10px] text-primary-container">
            working · this is real KiCad, and it takes a few seconds
          </p>
        </div>
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

          {/* **What was carried, and by function.** The swap maps the substitute's pads onto
              the nets those functions already sat on, and that mapping is the electrical work.
              It has been on the wire since the endpoint existed and went unread, while this
              pane recited one hand-written sentence about every board in the demonstration. */}
          {wired ? (
            <p className="font-data-tabular text-[10px] text-on-surface-variant leading-relaxed">
              Carried by function: {wired}.
            </p>
          ) : null}

          {/* What DRC found before and after, in the run's own numbers rather than a claim
              that it ran. On every board in this demonstration the answer is "nothing
              changed", and saying so is the point: a check that ran and found nothing is not
              the same as a check nobody performed. */}
          <p className="font-data-tabular text-[10px] text-on-surface-variant leading-relaxed">
            {changed.length === 0
              ? 'DRC before and after: nothing changed.'
              : `DRC before and after: ${changed
                  .map(([rule, counts]) => `${rule.replace(/_/g, ' ')} ${counts.before} → ${counts.after}`)
                  .join(', ')}.`}
          </p>

          {/* **What ran, and what it cost.** Five operations, timed with a clock inside the
              container rather than narrated: the same pane used to describe this work in one
              sentence nobody could check. Not while a placement is running — the block above
              is the live one, and two of them would be the same list twice. */}
          {!busy && outcome.steps?.length ? (
            <div className="space-y-0.5">
              <p className="m-0 font-data-tabular text-[10px] text-on-surface-variant">WHAT RAN</p>
              {outcome.steps.map((step) => (
                <p
                  className="m-0 font-data-tabular text-[10px] text-on-surface-variant/80 leading-relaxed"
                  key={step.name}
                >
                  {step.name} ·{' '}
                  {step.ms >= 1000 ? `${(step.ms / 1000).toFixed(1)} s` : `${step.ms} ms`}
                </p>
              ))}
            </div>
          ) : null}

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
