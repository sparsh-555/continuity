import { useEffect, useMemo } from 'react'

/**
 * The board this product is built from, as KiCad draws it.
 *
 * No substitution in it and nothing computed about it: this is the picture of the actual
 * PCB, which is a real answer to *show me the board* and the one the page needs before a
 * review has proposed anything to place. `BoardConsequence` is the other half — the same
 * board with a part swapped, cropped to the change.
 *
 * Rendered in page coordinates for the same reason the before-and-after crops are: KiCad is
 * asked for one user unit per millimetre, so a footprint at `(104.24, 52.49)` in the board
 * is at `(104.24, 52.49)` here, and a rectangle can point at it.
 */
export function BoardPicture({
  svg,
  page,
  content,
  crop,
}: {
  svg: string
  page: { width: number; height: number }
  /** What to actually look at. KiCad is asked for the page rather than the board, so the
   *  picture's own coordinates survive a crop — and a 46 mm board on a 297 mm page is a
   *  stamp in the middle of a black rectangle until something says where the board is. */
  content: string
  crop: string | null
}) {
  const url = useMemo(() => URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' })), [svg])
  useEffect(() => () => URL.revokeObjectURL(url), [url])

  const box = useMemo(() => {
    if (!crop) return null
    const [x, y, width, height] = crop.split(/\s+/).map(Number)
    return { x, y, width, height }
  }, [crop])

  return (
    <figure className="h-full w-full flex flex-col gap-sm p-md min-h-0">
      <svg
        className="flex-1 min-h-0 w-full bg-black border border-outline-variant rounded"
        preserveAspectRatio="xMidYMid meet"
        viewBox={content}
      >
        <image href={url} x="0" y="0" width={page.width} height={page.height} />
        {box ? (
          <rect
            fill="none"
            height={box.height}
            stroke="#e5e7eb"
            strokeDasharray="1 1"
            strokeWidth={0.3}
            width={box.width}
            x={box.x}
            y={box.y}
          />
        ) : null}
      </svg>
    </figure>
  )
}
