import type { GraphSlot, Slot } from '../lib/types'

export type PositionedNode = {
  slot: GraphSlot
  x: number
  y: number
  width: number
  height: number
  cx: number
  cy: number
}

export const TIER_ORDER: Array<Slot['tier']> = ['power', 'core', 'peripherals', 'passives']

/** The widest and tallest this diagram is ever drawn, which is the four-tier board it was
 *  laid out for. Both are ceilings now rather than the size: see `buildGraphLayout`. */
export const VIEW_WIDTH = 900
export const VIEW_HEIGHT = 820

export const GRAPH_LEFT = 24
const TOP = 24
const BOTTOM = 28
const NODE_WIDTH = 152
const NODE_HEIGHT = 58

/** One tier's column, at the width four of them plus the supply gutter came to. */
const COLUMN_WIDTH = 195

/** Vertical room per part.
 *
 *  Rows are spaced `contentHeight / (rows + 1)`, so the content box is sized from the pitch
 *  rather than the other way round. A three-part product line laid out in the full 820 put
 *  three nodes at 25%, 50% and 75% of it and left the rest empty. */
const ROW_PITCH = 120

/** Matches `topology.SUPPLY_NODE_ID`. Power edges out of the board input point at it. */
export const SUPPLY_NODE_ID = '__supply'

/** Room at the left for the input bus, taken from the four tier columns rather than
 *  from the viewBox, so a board without a declared supply is laid out exactly as before. */
const SUPPLY_GUTTER = 96
const SUPPLY_BAR_WIDTH = 8

export type SupplyBar = {
  /** Left edge of the bar. Edges leave from `x + width` at their own target's height. */
  x: number
  width: number
  top: number
  bottom: number
  cx: number
}

export function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

export function cubicPoint(
  t: number,
  p0: { x: number; y: number },
  p1: { x: number; y: number },
  p2: { x: number; y: number },
  p3: { x: number; y: number },
) {
  const omt = 1 - t
  const omt2 = omt * omt
  const omt3 = omt2 * omt
  const t2 = t * t
  const t3 = t2 * t

  return {
    x: omt3 * p0.x + 3 * omt2 * t * p1.x + 3 * omt * t2 * p2.x + t3 * p3.x,
    y: omt3 * p0.y + 3 * omt2 * t * p1.y + 3 * omt * t2 * p2.y + t3 * p3.y,
  }
}

function overlapsNode(
  x: number,
  y: number,
  width: number,
  height: number,
  nodes: PositionedNode[],
  padding = 6,
) {
  const left = x - width / 2
  const right = x + width / 2
  const top = y - height / 2
  const bottom = y + height / 2

  return nodes.some((node) => {
    const nodeLeft = node.x - padding
    const nodeRight = node.x + node.width + padding
    const nodeTop = node.y - padding
    const nodeBottom = node.y + node.height + padding

    return !(right < nodeLeft || left > nodeRight || bottom < nodeTop || top > nodeBottom)
  })
}

export function resolveBadgeY(
  preferredY: number,
  centerX: number,
  width: number,
  height: number,
  nodes: PositionedNode[],
  viewHeight: number = VIEW_HEIGHT,
) {
  const candidates = [0, -26, 26, -52, 52, -78, 78]
  const minY = 12 + height / 2
  const maxY = viewHeight - 12 - height / 2

  for (const offset of candidates) {
    const y = clamp(preferredY + offset, minY, maxY)
    if (!overlapsNode(centerX, y, width, height, nodes)) {
      return y
    }
  }

  return clamp(preferredY, minY, maxY)
}

export function tierLabel(tier: Slot['tier']) {
  if (tier === 'power') return 'POWER'
  if (tier === 'core') return 'CORE'
  if (tier === 'peripherals') return 'PERIPHERALS'
  return 'PASSIVES'
}

/**
 * Where every node sits, and how big the picture has to be to hold them.
 *
 * **The size comes from the content.** It used to be a constant 900 × 820 whatever was on
 * the board, which is right for the eight-part design run it was laid out for and wrong for
 * a three-part product line: an entirely empty PERIPHERALS column taking a quarter of the
 * width, and three nodes spread down 820 pixels because the rows divide whatever height
 * they are given. A tier with nothing in it is not drawn, and the height follows the number
 * of rows up to the same ceiling as before — so a full design board is laid out exactly as
 * it always was, and a small board is drawn small instead of drawn sparse.
 */
export function buildGraphLayout(slots: GraphSlot[], hasSupply = false) {
  const slotGroups = TIER_ORDER.map((tier) => ({
    tier,
    slots: slots.filter((slot) => slot.tier === tier),
  })).filter((group) => group.slots.length > 0)

  const left = hasSupply ? SUPPLY_GUTTER : GRAPH_LEFT
  const columnWidth = COLUMN_WIDTH
  const width = left + Math.max(slotGroups.length, 1) * columnWidth + GRAPH_LEFT
  const contentTop = TOP + 34
  const rows = Math.max(slots.length, 1)
  const contentHeight = clamp(
    (rows + 1) * ROW_PITCH,
    ROW_PITCH * 3,
    VIEW_HEIGHT - contentTop - BOTTOM,
  )
  const height = contentTop + contentHeight + BOTTOM
  const orderedSlots = slotGroups.flatMap((group) => group.slots)
  const rowIndexBySlotId = new Map(orderedSlots.map((slot, index) => [slot.id, index]))
  const rowCount = Math.max(orderedSlots.length, 1)

  const positionedNodes: PositionedNode[] = slotGroups.flatMap(({ slots: tierSlots }, tierIndex) => {
    const x = left + tierIndex * columnWidth + (columnWidth - NODE_WIDTH) / 2

    return tierSlots.map((slot) => {
      const rowIndex = rowIndexBySlotId.get(slot.id) ?? 0
      const yCenter = contentTop + ((rowIndex + 1) * contentHeight) / (rowCount + 1)
      const y = yCenter - NODE_HEIGHT / 2

      return {
        slot,
        x,
        y,
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        cx: x + NODE_WIDTH / 2,
        cy: yCenter,
      }
    })
  })

  const nodesById = new Map(positionedNodes.map((node) => [node.slot.id, node]))
  const nodeBandTop =
    positionedNodes.length > 0 ? Math.max(14, Math.min(...positionedNodes.map((node) => node.y)) - 12) : TOP + 26

  // A bar rather than a box: the input is a net, and drawing it as one lets every part it
  // feeds leave at its own height instead of fanning out of a single point.
  const barX = GRAPH_LEFT + 20
  const supply: SupplyBar | null =
    hasSupply && positionedNodes.length > 0
      ? {
          x: barX,
          width: SUPPLY_BAR_WIDTH,
          // Clear of the "INPUT" caption on the tier-label row, and of the voltage
          // that sits just above the bar.
          top: nodeBandTop + 30,
          bottom: Math.max(...positionedNodes.map((node) => node.y + node.height)),
          cx: barX + SUPPLY_BAR_WIDTH / 2,
        }
      : null

  return {
    positionedNodes,
    nodesById,
    nodeBandTop,
    columnWidth,
    left,
    supply,
    width,
    height,
    /** The tiers actually drawn, in order, so the caller can label the columns it has. */
    tiers: slotGroups.map((group) => group.tier),
  }
}
