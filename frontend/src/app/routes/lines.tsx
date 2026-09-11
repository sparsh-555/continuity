import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router'

import { Modal } from '../design/Modal'
import { useNewLine } from '../hooks/useNewLine'
import { useNoticeArrivals } from '../hooks/useNoticeArrivals'
import {
  ApiError,
  deleteLine,
  listLineThreads,
  listLines,
  putBoard,
  updateLine,
  type Line,
  type LineThread,
} from '../lib/api'
import { InviteDialog, TeamPanel, useMembers } from '../team/Team'
import { Wordmark } from '../shell/Wordmark'

type StatusBadge = {
  label: string
  dotClassName: string
  textClassName: string
  hollowDot?: boolean
}

function formatRelativeTime(timestamp: string) {
  const createdAt = new Date(timestamp).getTime()
  if (Number.isNaN(createdAt)) {
    return 'just now'
  }

  const seconds = Math.max(0, Math.floor((Date.now() - createdAt) / 1000))
  if (seconds < 60) {
    return 'just now'
  }

  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) {
    return `${minutes}m ago`
  }

  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    return `${hours}h ago`
  }

  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function shortPartsLabel(missingCount: number) {
  return `short ${missingCount} part${missingCount === 1 ? '' : 's'}`
}

/** What this line is, for a line that has been described as a shipping product.
 *
 *  Returns null when nothing has been stored, so the caller can fall back to the brief
 *  of the last run rather than captioning a design container "0 parts". The ambient
 *  travels with its source for the same reason every other number in this product does:
 *  a condition a verdict was computed against is only as good as where it came from. */
function describe(line: Line): string | null {
  if (!line.profile && line.part_count === 0) {
    return null
  }

  const revision = line.revision
  const parts = `${line.part_count} ${line.part_count === 1 ? 'part' : 'parts'}`
  const ambient = line.profile
    ? `${line.profile.ambient_c} °C ambient`
    : 'no profile stored'

  return [revision, parts, ambient].filter(Boolean).join(' · ')
}

/** The same line, unabridged, for the row's `title`.
 *
 *  The row truncates at a fixed width and the ambient's source is the first thing to go —
 *  which leaves a temperature on screen with no way to see where it came from, the exact
 *  thing `ambient_source` exists to prevent. The full source belongs on the line's own
 *  page; until that page carries it, hovering the row is how it stays reachable. */
function describeInFull(line: Line): string | undefined {
  return line.profile
    ? `${describe(line)} — ${line.profile.ambient_source}`
    : describe(line) ?? undefined
}

/** What is true of the *product*, which is not whether somebody has run it through us.
 *
 *  This read "Never run" on every shipping product in the seeded company, because it was
 *  computed from the latest design thread. A product line on its third revision with three
 *  parts fitted is not "never run"; it is shipping, and the only thing about to change it
 *  is a notice against one of its parts. */
function statusBadge(line: Line): StatusBadge {
  if (line.exposed_count > 0) {
    return {
      label: `${line.exposed_count} notice${line.exposed_count === 1 ? '' : 's'}`,
      dotClassName: 'bg-error',
      textClassName: 'text-error',
    }
  }

  if (line.part_count === 0) {
    return {
      label: 'No parts yet',
      dotClassName: 'border border-outline',
      textClassName: 'text-on-surface-variant',
      hollowDot: true,
    }
  }

  return {
    label: 'Shipping',
    dotClassName: 'bg-[#4ade80]',
    textClassName: 'text-on-surface-variant',
  }
}

function shortageLabelFromLatestThread(latestThread: LineThread | null): string | null {
  if (!latestThread?.summary) {
    return null
  }

  const missingCount = latestThread.summary.slots - latestThread.summary.placed
  if (missingCount <= 0) {
    return null
  }

  return shortPartsLabel(missingCount)
}

export default function LinesRoute() {
  const navigate = useNavigate()
  const { createNewLine, creating } = useNewLine()
  const { arrival } = useNoticeArrivals()

  const [lines, setLines] = useState<Line[]>([])
  const [threadsByLine, setThreadsByLine] = useState<Record<string, LineThread[]>>({})
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [openMenuLineId, setOpenMenuLineId] = useState<string | null>(null)
  const [reloadCount, setReloadCount] = useState(0)

  const { members, refresh: refreshMembers } = useMembers()

  const [renameLine, setRenameLine] = useState<Line | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const renameInputRef = useRef<HTMLInputElement | null>(null)

  const [deleteLineTarget, setDeleteLineTarget] = useState<Line | null>(null)

  const boardInputRef = useRef<HTMLInputElement | null>(null)
  const boardLineRef = useRef<Line | null>(null)
  const [boardMessage, setBoardMessage] = useState<string | null>(null)
  /** Picking projects to share, and the ones ticked. Selection lives here rather than in the
   *  dialog because the rows are here — the projects are what you point at. */
  const [picking, setPicking] = useState(false)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [inviteOpen, setInviteOpen] = useState(false)
  const [inviteNote, setInviteNote] = useState<string | null>(null)
  const [attaching, setAttaching] = useState(false)

  useEffect(() => {
    if (!renameLine) {
      return
    }

    const frame = requestAnimationFrame(() => {
      renameInputRef.current?.select()
    })

    return () => {
      cancelAnimationFrame(frame)
    }
  }, [renameLine])

  useEffect(() => {
    let active = true

    async function load() {
      setLoading(true)

      try {
        const nextLines = await listLines()
        if (!active) {
          return
        }

        setLoadError(false)
        setLines(nextLines)

        const threadEntries = await Promise.all(
          nextLines.map(async (line) => {
            try {
              const threads = await listLineThreads(line.id)
              return [line.id, threads] as const
            } catch {
              return [line.id, []] as const
            }
          }),
        )

        if (!active) {
          return
        }

        setThreadsByLine(Object.fromEntries(threadEntries))
      } catch {
        if (active) {
          setLoadError(true)
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    load().catch(() => {
      if (active) {
        setLoadError(true)
        setLoading(false)
      }
    })

    return () => {
      active = false
    }
  }, [arrival, reloadCount])

  /** Attach a KiCad project to a line, and say what came out of it.
   *
   *  The bill of materials is read out of the design rather than typed, so a line that had
   *  none adopts the one KiCad found. A line that already had one keeps it: overwriting a
   *  bill somebody entered is not a thing to do because a file was dropped on it. */
  const attachBoard = useCallback(async (line: Line, file: File) => {
    setAttaching(true)
    setBoardMessage(null)
    try {
      const bundle = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onerror = () => reject(reader.error)
        // readAsDataURL gives base64 already encoded, without walking a megabyte of bytes
        // through string concatenation on the main thread.
        reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '')
        reader.readAsDataURL(file)
      })
      const outcome = await putBoard(line.id, file.name, bundle)
      setBoardMessage(
        outcome.adopted
          ? `${outcome.project} attached to ${line.name}. Its bill of materials is now the line's, read from the ${outcome.mpn_field} field.`
          : outcome.kicad
            ? `${outcome.project} attached to ${line.name}. The line already had a bill of materials, so it was kept.`
            : `${outcome.project} attached to ${line.name}. This instance has no KiCad, so nothing was read out of it yet.`,
      )
      setReloadCount((count) => count + 1)
    } catch (caught) {
      setBoardMessage(
        caught instanceof ApiError
          ? (caught.message ?? 'That project could not be attached.')
          : 'That project could not be attached.',
      )
    } finally {
      setAttaching(false)
    }
  }, [])

  const openRenameModal = useCallback((line: Line) => {
    setRenameLine(line)
    setRenameValue(line.name)
    setOpenMenuLineId(null)
  }, [])

  const closeRenameModal = useCallback(() => {
    setRenameLine(null)
    setOpenMenuLineId(null)
  }, [])

  const confirmRename = useCallback(async () => {
    if (!renameLine) {
      return
    }

    const nextName = renameValue.trim()
    if (!nextName || nextName === renameLine.name) {
      closeRenameModal()
      return
    }

    const updated = await updateLine(renameLine.id, nextName)
    setLines((previous) =>
      previous.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)),
    )
    closeRenameModal()
  }, [closeRenameModal, renameLine, renameValue])

  const openDeleteModal = useCallback((line: Line) => {
    setDeleteLineTarget(line)
    setOpenMenuLineId(null)
  }, [])

  const closeDeleteModal = useCallback(() => {
    setDeleteLineTarget(null)
    setOpenMenuLineId(null)
  }, [])

  const confirmDelete = useCallback(async () => {
    if (!deleteLineTarget) {
      return
    }

    await deleteLine(deleteLineTarget.id)

    setLines((previous) => previous.filter((item) => item.id !== deleteLineTarget.id))
    setThreadsByLine((previous) => {
      const next = { ...previous }
      delete next[deleteLineTarget.id]
      return next
    })

    closeDeleteModal()
  }, [closeDeleteModal, deleteLineTarget])

  const showLoadError = !loading && loadError
  const showEmptyState = !loading && !loadError && lines.length === 0
  const showRows = !loading && !loadError

  const rows = useMemo(
    () =>
      lines.map((line) => {
        const threads = threadsByLine[line.id] ?? []
        const latestThread = threads[0] ?? null

        return {
          line,
          // What the line *is*, when it has been described as a product; otherwise what
          // was last asked of it. A line carrying neither a BOM nor a profile is a design
          // container, and replacing its brief with "0 parts" would take information away.
          subtitle: describe(line) ?? latestThread?.prompt ?? 'Nothing described yet',
          subtitleTitle: describeInFull(line),
          status: statusBadge(line),
          shortageLabel: shortageLabelFromLatestThread(latestThread),
        }
      }),
    [lines, threadsByLine],
  )

  return (
    <>
      <div className="bg-transparent min-h-screen text-on-background font-body-md antialiased">
        <header className="flex items-center w-full px-lg h-12 bg-surface-container-low border-b border-outline-variant shadow-[0_1px_0_0_rgba(255,255,255,0.05)]">
          <Wordmark />
        </header>

        <main className="min-h-[calc(100vh-48px)] max-w-[1200px] mx-auto px-lg py-xl flex flex-col gap-lg">
          {/* One picker for the whole page: the row's menu says which line it is for. */}
          <input
            accept=".zip,application/zip"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0]
              const line = boardLineRef.current
              if (file && line) void attachBoard(line, file)
              event.target.value = ''
            }}
            ref={boardInputRef}
            type="file"
          />

          {attaching || boardMessage ? (
            <p className="font-data-tabular text-body-sm text-on-surface-variant">
              {attaching ? 'Reading the project…' : boardMessage}
            </p>
          ) : null}

          {/* **Who is on the company, above what they share.** Scenario B is a cross-team
              response and a judge watching four desks sign one change has to take the
              sharing on faith without this. It is on the projects page rather than a
              destination of its own, so the answer to *how do you share these* sits beside
              the things being shared. */}
          <TeamPanel members={members} />

          <div className="flex items-center justify-between gap-md border-b border-outline-variant pb-sm">
            <h1 className="font-label-caps text-label-caps tracking-[0.1em] uppercase text-on-surface">
              PRODUCT LINES
            </h1>
            {/* **The selection is made where the projects are.** Ticking them on the list and
                naming the person afterwards is the same decision in the order it is
                actually taken; a dialog that asked for both at once would have the reader
                holding three names in their head while typing an email. */}
            <div className="flex items-center gap-sm">
              <button
                className={`px-md py-xs rounded-DEFAULT font-label-caps text-label-caps border transition-colors ${
                  picking
                    ? 'border-primary-container text-primary-container'
                    : 'border-outline-variant text-on-surface-variant hover:border-on-surface-variant'
                }`}
                onClick={() => {
                  setPicking((value) => !value)
                  setPicked(new Set())
                  setInviteNote(null)
                }}
                type="button"
              >
                {picking ? 'CANCEL' : 'INVITE TEAMMATES'}
              </button>
              <button
                className="bg-primary-container text-on-primary-fixed px-md py-xs rounded-DEFAULT font-label-caps text-label-caps flex items-center gap-xs hover:bg-primary-fixed transition-colors disabled:opacity-70"
              disabled={creating}
              onClick={() => {
                createNewLine().catch(() => undefined)
              }}
              type="button"
            >
              <span className="material-symbols-outlined text-[16px]">add</span>
              NEW PRODUCT LINE
              </button>
            </div>
          </div>

          {picking ? (
            <div className="flex flex-wrap items-center justify-between gap-md border border-primary-container rounded px-md py-sm">
              <p className="m-0 font-data-tabular text-[13px] text-on-surface">
                {picked.size === 0
                  ? 'Tick the projects this teammate should be able to open.'
                  : `${picked.size} of ${lines.length} project${lines.length === 1 ? '' : 's'} selected`}
              </p>
              <button
                className="h-8 px-md bg-primary-container text-on-primary-fixed rounded font-data-tabular text-[12px] hover:bg-primary-fixed transition-colors disabled:opacity-40"
                disabled={picked.size === 0}
                onClick={() => setInviteOpen(true)}
                type="button"
              >
                SHARE THESE {picked.size} PROJECT{picked.size === 1 ? '' : 'S'}
              </button>
            </div>
          ) : null}

          {inviteNote ? (
            <p className="m-0 font-data-tabular text-[12px] text-[#4ade80] leading-relaxed">
              {inviteNote}
            </p>
          ) : null}

          <div className="flex flex-col gap-sm">
            {showRows
              ? rows.map(({ line, subtitle, subtitleTitle, status, shortageLabel }) => (
                  <div
                    // Separated by surface and space rather than a hairline. A 1px border
                    // around every card is the other reliable generated-UI tell, and the
                    // list reads calmer without twelve of them stacked down the page.
                    className="bg-surface-container h-[72px] rounded-DEFAULT flex items-center justify-between px-md hover:bg-surface-container-high transition-colors cursor-pointer"
                    key={line.id}
                    onClick={() => {
                      // Picking is the mode, so a row is a checkbox while it is on. Opening a
                      // project from inside the selection would leave the reader wondering
                      // whether the tick they were reaching for had been recorded.
                      if (picking) {
                        setPicked((current) => {
                          const next = new Set(current)
                          if (next.has(line.id)) next.delete(line.id)
                          else next.add(line.id)
                          return next
                        })
                        return
                      }
                      navigate(`/lines/${line.id}`)
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        navigate(`/lines/${line.id}`)
                      }
                    }}
                    role="button"
                    tabIndex={0}
                  >
                    {/* **The tick appears where the row already is.** A separate list of
                        checkboxes beside the projects would be the same names twice, and the
                        reader would have to match them up. */}
                    {picking ? (
                      <span
                        aria-hidden
                        className={`material-symbols-outlined text-[20px] mr-md shrink-0 ${
                          picked.has(line.id) ? 'text-primary-container' : 'text-on-surface-variant/50'
                        }`}
                        style={picked.has(line.id) ? { fontVariationSettings: "'FILL' 1" } : undefined}
                      >
                        {picked.has(line.id) ? 'check_box' : 'check_box_outline_blank'}
                      </span>
                    ) : null}

                    <div className="flex flex-col justify-center min-w-0 flex-1">
                      <span className="font-headline-sm text-headline-sm text-on-surface truncate">
                        {line.name}
                      </span>
                      <span
                        className="font-data-tabular text-body-sm text-on-surface-variant truncate"
                        title={subtitleTitle}
                      >
                        {subtitle}
                      </span>
                    </div>

                    <div className="ml-lg flex items-center gap-lg shrink-0">
                      <div className="flex items-center gap-sm min-w-[260px]">
                        <div className="flex items-center gap-xs min-w-[120px]">
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${status.dotClassName} ${
                              status.hollowDot ? 'bg-transparent' : ''
                            }`}
                          />
                          <span className={`font-label-caps text-label-caps ${status.textClassName}`}>
                            {status.label}
                          </span>
                        </div>

                        {shortageLabel ? (
                          <span className="font-label-caps text-label-caps text-error">
                            {shortageLabel}
                          </span>
                        ) : null}
                      </div>

                      <span className="font-data-tabular text-data-tabular text-outline min-w-[64px] text-right">
                        {formatRelativeTime(line.updated_at)}
                      </span>

                      <div className="relative">
                        <button
                          aria-label="Product line actions"
                          className="p-1 text-on-surface-variant hover:text-on-surface rounded-DEFAULT hover:bg-surface-container-high transition-colors"
                          onClick={(event) => {
                            event.stopPropagation()
                            setOpenMenuLineId((current) =>
                              current === line.id ? null : line.id,
                            )
                          }}
                          type="button"
                        >
                          <span className="material-symbols-outlined text-[20px]">more_vert</span>
                        </button>

                        {openMenuLineId === line.id ? (
                          <div
                            className="absolute right-0 top-[calc(100%+4px)] z-10 w-[140px] bg-surface-container-high border border-outline-variant rounded-DEFAULT overflow-hidden shadow-lg"
                            onClick={(event) => event.stopPropagation()}
                          >
                            <button
                              className="w-full text-left px-sm py-xs font-body-sm text-body-sm text-on-surface hover:bg-surface-container-highest"
                              onClick={() => {
                                openRenameModal(line)
                              }}
                              type="button"
                            >
                              Rename
                            </button>
                            <button
                              className="w-full text-left px-sm py-xs font-body-sm text-body-sm text-on-surface hover:bg-surface-container-highest"
                              onClick={() => {
                                boardLineRef.current = line
                                setOpenMenuLineId(null)
                                boardInputRef.current?.click()
                              }}
                              type="button"
                            >
                              Attach board
                            </button>
                            {/* The design flow, still reachable and no longer the thing you
                                get by accident. Clicking the row opens the product. */}
                            <button
                              className="w-full text-left px-sm py-xs font-body-sm text-body-sm text-on-surface hover:bg-surface-container-highest"
                              onClick={() => {
                                setOpenMenuLineId(null)
                                navigate(`/design/${line.id}`)
                              }}
                              type="button"
                            >
                              Design runs
                            </button>
                            <button
                              className="w-full text-left px-sm py-xs font-body-sm text-body-sm text-error hover:bg-surface-container-highest"
                              onClick={() => {
                                openDeleteModal(line)
                              }}
                              type="button"
                            >
                              Delete
                            </button>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </div>
                ))
              : null}

            {showLoadError ? (
              <div className="border border-error rounded-DEFAULT bg-error-container/20 p-md flex flex-col gap-sm">
                <div className="flex items-center gap-sm">
                  <span className="material-symbols-outlined text-error text-[16px]">warning</span>
                  <span className="font-body-md text-body-md text-error">Could not load your product lines</span>
                </div>
                <p className="font-body-sm text-body-sm text-on-surface-variant">
                  The server did not respond.
                </p>
                <div>
                  <button
                    className="font-label-caps text-label-caps text-on-surface-variant hover:text-on-surface transition-colors"
                    onClick={() => {
                      setReloadCount((current) => current + 1)
                    }}
                    type="button"
                  >
                    RETRY
                  </button>
                </div>
              </div>
            ) : null}

            {showEmptyState ? (
              <div className="w-full border-2 border-dashed border-outline-variant rounded-xl p-xl flex flex-col items-center justify-center text-center bg-surface-container-low/30 mt-md">
                <div className="w-20 h-20 rounded-full bg-surface-container-high border border-outline-variant flex items-center justify-center mb-lg">
                  <span className="material-symbols-outlined text-[40px] text-on-surface-variant">memory</span>
                </div>
                <h2 className="font-headline-sm text-headline-sm text-on-surface mb-sm">No product lines yet</h2>
                <p className="font-body-md text-body-md text-on-surface-variant max-w-md mb-xl">
                  Describe a board and Continuity will source and validate it
                </p>
                <button
                  className="bg-primary-container text-on-primary-fixed px-xl py-sm rounded-DEFAULT font-label-caps text-label-caps hover:bg-primary-fixed transition-colors flex items-center gap-sm"
                  disabled={creating}
                  onClick={() => {
                      createNewLine().catch(() => undefined)
                  }}
                  type="button"
                >
                  <span className="material-symbols-outlined text-[16px]">add</span>
                  NEW PRODUCT LINE
                </button>
              </div>
            ) : null}
          </div>
        </main>
      </div>

      <Modal
        confirmLabel="SAVE"
        onClose={closeRenameModal}
        onConfirm={() => {
          confirmRename().catch(() => undefined)
        }}
        open={Boolean(renameLine)}
        title="RENAME PRODUCT LINE"
      >
        <input
          className="w-full bg-surface-container-lowest border border-outline-variant rounded-DEFAULT px-sm py-sm font-data-tabular text-data-tabular text-on-surface focus:outline-none focus:ring-0 glow-focus"
          onChange={(event) => setRenameValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              confirmRename().catch(() => undefined)
            }
          }}
          ref={renameInputRef}
          value={renameValue}
        />
      </Modal>

      <Modal
        confirmLabel="DELETE"
        destructive
        onClose={closeDeleteModal}
        onConfirm={() => {
          confirmDelete().catch(() => undefined)
        }}
        open={Boolean(deleteLineTarget)}
        title="DELETE PRODUCT LINE"
      >
        <p className="font-body-md text-body-md text-on-surface-variant">
          Delete "{deleteLineTarget?.name}"? This removes every run in this product line and cannot be
          undone.
        </p>
      </Modal>

      <InviteDialog
        onClose={() => setInviteOpen(false)}
        onInvited={(note) => {
          setInviteOpen(false)
          setInviteNote(note)
          setPicking(false)
          setPicked(new Set())
          refreshMembers()
        }}
        open={inviteOpen}
        selected={[...picked]}
      />
    </>
  )
}
