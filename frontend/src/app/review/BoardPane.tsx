import { useCallback, useEffect, useState } from 'react'

import { BoardConsequence } from '../board/BoardConsequence'
import { BoardPicture } from '../board/BoardPicture'
import { ApiError, boardRender, type BoardPicture as Picture } from '../lib/api'

/**
 * The board, in the middle pane, wearing the same chrome the graph wears.
 *
 * Two things live here and the difference between them is whether there is a part to place.
 * With one — a review's proposal, or the part an earlier decision settled on — this is the
 * before and after, cropped to the change, with KiCad's own account of what it broke.
 * Without one it is the board itself.
 *
 * That second case is why this exists. The toggle used to appear only once a review had
 * produced a candidate and to vanish again on reload, so *show me the board* was a question
 * the product could answer for about a minute a day.
 */
export function BoardPane({
  lineId,
  retiring,
  candidate,
  project,
  action,
}: {
  lineId: string
  /** The part a notice retires, used to point at a position on the board. */
  retiring: string | null
  /** What to place, when anything has been proposed. */
  candidate: string | null
  /** The KiCad project this product line is built from. It reads here rather than in the
   *  page header, where it was one more clause on a line that already carried the
   *  product's name, revision, ambient and rails. */
  project: string
  action: React.ReactNode
}) {
  const [picture, setPicture] = useState<Picture | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setBusy(true)
    setMessage(null)
    try {
      setPicture(await boardRender(lineId, retiring))
    } catch (caught) {
      // Each of these is a different true sentence, and collapsing them into "that failed"
      // would hide the only one the reader can act on.
      setMessage(
        caught instanceof ApiError
          ? caught.status === 404
            ? 'No KiCad project is attached to this product line.'
            : caught.status === 503
              ? 'This instance has no KiCad configured.'
              : (caught.message ?? 'That board could not be drawn.')
          : 'That board could not be drawn.',
      )
    } finally {
      setBusy(false)
    }
  }, [lineId, retiring])

  useEffect(() => {
    if (!candidate) void load()
  }, [candidate, load])

  return (
    <section className="flex-1 min-w-0 flex flex-col panel-border rounded-lg overflow-hidden">
      <header className="h-10 px-md flex items-center justify-between border-b border-outline-variant bg-surface-container-high flex-shrink-0 z-10">
        <div className="flex items-center gap-sm text-on-surface">
          <span className="material-symbols-outlined text-[16px]">developer_board</span>
          <h2 className="font-headline-sm text-[14px] font-semibold tracking-wide">
            {project}
            <span className="text-on-surface-variant font-normal">
              {candidate ? ' · before and after' : ''}
            </span>
          </h2>
        </div>
        {action}
      </header>

      <div className="flex-1 min-h-0 overflow-y-auto bg-[#0B0C0E]">
        {candidate && retiring ? (
          <div className="p-md">
            <BoardConsequence auto candidate={candidate} lineId={lineId} retiring={retiring} />
          </div>
        ) : message ? (
          <p className="p-md font-data-tabular text-[11px] text-tertiary-container leading-relaxed">
            {message}
          </p>
        ) : picture ? (
          <BoardPicture
            content={picture.content}
            crop={picture.crop}
            page={picture.page}
            svg={picture.svg}
          />
        ) : (
          <p className="p-md font-data-tabular text-[11px] text-on-surface-variant">
            {busy ? 'Loading the board…' : ''}
          </p>
        )}
      </div>
    </section>
  )
}
