import type { GraphSlot } from '../lib/types'
import type { LinePart } from '../lib/api'

/**
 * What this product is made of, in the workspace's own bill.
 *
 * The same table `design/BomTable` draws — sticky head, zebra rows, and a **conflict row
 * that lights up red with the part it is about** — reading the line's stored bill instead of
 * a design run's selections. The columns differ because the data does: a shipping product
 * line stores a reference designator, a part number, a manufacturer and a footprint, and has
 * no price, stock or datasheet upload to offer.
 *
 * The red row is the point of it being here. A part in conflict on the graph used to be red
 * in the picture and ordinary in the bill, so the two panes disagreed about the same board.
 */
export function LineBom({
  parts,
  slots,
  selectedSlotId = null,
  onSelectSlot,
}: {
  parts: LinePart[]
  slots: GraphSlot[]
  selectedSlotId?: string | null
  onSelectSlot?: (slotId: string) => void
}) {
  const status = new Map(slots.map((slot) => [slot.id, slot.status]))

  return (
    <section className="w-[30%] min-w-[320px] flex flex-col panel-border rounded-lg overflow-hidden flex-shrink-0">
      <header className="h-10 px-md flex items-center justify-between border-b border-outline-variant bg-surface-container-high flex-shrink-0">
        <div className="flex items-center gap-sm text-on-surface">
          <span className="material-symbols-outlined text-[16px]">list_alt</span>
          <h2 className="font-headline-sm text-[14px] font-semibold tracking-wide">
            Bill of Materials
          </h2>
        </div>
      </header>

      <div className="flex-1 overflow-auto bg-[#0B0C0E]">
        <table className="w-full text-left border-collapse whitespace-nowrap">
          <thead className="sticky top-0 bg-[#16181D] z-10 shadow-[0_1px_0_0_#3b494c]">
            <tr>
              <th className="font-label-caps text-label-caps text-on-surface-variant uppercase-label px-sm py-2">
                Ref
              </th>
              <th className="font-label-caps text-label-caps text-on-surface-variant uppercase-label px-sm py-2">
                Part Number
              </th>
              <th className="font-label-caps text-label-caps text-on-surface-variant uppercase-label px-sm py-2">
                Footprint
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/30 font-data-tabular text-[11px] text-on-surface">
            {parts.map((part, index) => {
              const conflict = status.get(part.refdes) === 'conflict'
              const searching = status.get(part.refdes) === 'searching'
              const selected = part.refdes === selectedSlotId
              const zebra = index % 2 === 1
              return (
                <tr
                  className={
                    conflict
                      ? `cursor-pointer bg-error-container/20 border-l-2 border-error hover:bg-error-container/30 transition-colors ${selected ? 'ring-1 ring-inset ring-primary-container' : ''}`
                      : searching
                        ? 'cursor-pointer bg-primary-container/10 border-l-2 border-primary-container transition-colors'
                        : `cursor-pointer hover:bg-surface-variant/30 transition-colors ${zebra ? 'bg-[#121417]' : ''} ${selected ? 'bg-primary-container/15 ring-1 ring-inset ring-primary-container' : ''}`
                  }
                  key={part.refdes}
                  onKeyDown={(event) => {
                    if (onSelectSlot && (event.key === 'Enter' || event.key === ' ')) {
                      event.preventDefault()
                      onSelectSlot(part.refdes)
                    }
                  }}
                  onClick={() => onSelectSlot?.(part.refdes)}
                  tabIndex={onSelectSlot ? 0 : undefined}
                >
                  <td
                    className={`px-sm py-2 uppercase ${
                      conflict ? 'text-error font-bold' : 'text-on-surface-variant'
                    }`}
                  >
                    {part.refdes}
                  </td>
                  <td className={`px-sm py-2 ${conflict ? 'text-error font-bold' : ''}`}>
                    <div className="flex items-center gap-1">
                      {conflict ? (
                        <span className="material-symbols-outlined text-[12px]">warning</span>
                      ) : null}
                      {part.mpn}
                      {part.populated ? '' : ' · not fitted'}
                    </div>
                    <span
                      className={`block ${conflict ? 'text-error/80' : 'text-on-surface-variant'}`}
                    >
                      {part.manufacturer ?? '—'}
                    </span>
                  </td>
                  <td
                    className={`px-sm py-2 ${conflict ? 'text-error' : 'text-on-surface-variant'}`}
                  >
                    {part.footprint ?? '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
