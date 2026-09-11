import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'

import { BriefEntry } from '../design/BriefEntry'
import { Workspace, WorkspaceView } from '../design/Workspace'
import { useDesignSession } from '../hooks/useDesignSession'
import { ApiError, getThreadBoard, listLineThreads, type LineThread } from '../lib/api'

type LineMode = 'loading' | 'none' | 'brief' | 'workspace'

/**
 * A product line reached from DESIGN RUNS that has never had one.
 *
 * The brief screen used to render here, which asked *"What are you building?"* about a
 * product that ships today, has a revision, a bill of materials and a KiCad project. Every
 * seeded product line is in exactly that state, so the menu item looked broken. Seeding a
 * design thread for a shipping product would be worse — it would be inventing a synthesis
 * run that never happened — so the honest answer is that there are none, and a way to start
 * one for somebody who actually wants to.
 */
function NoRuns({ lineId, onStart }: { lineId: string; onStart: () => void }) {
  return (
    <div className="min-h-screen bg-transparent text-on-background flex items-center justify-center p-lg">
      <div className="border border-outline-variant bg-surface-container rounded-lg p-lg max-w-md space-y-md">
        <p className="m-0 font-label-caps text-label-caps uppercase text-on-surface">
          NO DESIGN RUNS ON THIS PRODUCT LINE
        </p>
        <p className="font-data-tabular text-[11px] text-on-surface-variant leading-relaxed">
          A design run synthesises a board from a brief. This product line was described by
          its bill of materials and its operating profile instead, which is how a product
          that already ships gets here.
        </p>
        <div className="flex gap-sm">
          <button
            className="h-8 px-md border border-primary-container rounded font-data-tabular text-[11px] text-primary-container hover:bg-surface-variant transition-colors"
            onClick={onStart}
            type="button"
          >
            START ONE
          </button>
          <Link
            className="h-8 px-md border border-outline-variant rounded font-data-tabular text-[11px] text-on-surface-variant hover:bg-surface-variant transition-colors flex items-center"
            to={`/lines/${lineId}`}
          >
            THE PRODUCT LINE
          </Link>
        </div>
      </div>
    </div>
  )
}

type StartedRequest = {
  brief: string
  bom?: string
}

function StartedWorkspace({ lineId, request }: { lineId: string; request: StartedRequest }) {
  const session = useDesignSession()

  useEffect(() => {
    if (request.bom !== undefined) {
      session.startBom(request.bom, request.brief || undefined, lineId)
      return
    }

    session.start(request.brief, lineId)
  }, [lineId, request, session.start, session.startBom])

  return <WorkspaceView lineId={lineId} session={session} />
}

type RestoreState = 'loading' | 'ready' | 'live' | 'empty' | 'error'

function RestoredWorkspace({ lineId, thread }: { lineId: string; thread: LineThread }) {
  const navigate = useNavigate()
  const session = useDesignSession()
  const [restoreState, setRestoreState] = useState<RestoreState>('loading')

  useEffect(() => {
    let active = true

    async function restore() {
      try {
        const board = await getThreadBoard(thread.id)
        if (!active) {
          return
        }

        if (board.status === 'running') {
          setRestoreState('live')
          return
        }

        if (board.slots.length === 0 && board.bom?.rows.length === 0 && board.trace.length === 0 && !board.question) {
          setRestoreState('empty')
          return
        }

        session.hydrate(board, thread.id)
        setRestoreState('ready')
      } catch (error) {
        if (!active) {
          return
        }

        if (error instanceof ApiError && error.status === 401) {
          navigate('/login', { replace: true })
          return
        }

        if (error instanceof ApiError && error.status === 404) {
          navigate('/lines', { replace: true })
          return
        }

        setRestoreState('error')
      }
    }

    restore()

    return () => {
      active = false
    }
  }, [navigate, session.hydrate, thread.id])

  if (restoreState === 'loading') {
    return null
  }

  if (restoreState === 'live') {
    return <Workspace lineId={lineId} />
  }

  if (restoreState === 'empty' || restoreState === 'error') {
    return (
      <div className="min-h-screen bg-background text-on-background flex items-center justify-center p-lg">
        <div className="border border-outline-variant bg-surface-container p-lg max-w-md">
          <p className="m-0 font-headline-sm text-headline-sm">
            {restoreState === 'empty' ? 'THIS RUN HAS NO BOARD TO RESTORE' : 'BOARD COULD NOT LOAD'}
          </p>
          <p className="mt-sm text-on-surface-variant">
            {restoreState === 'empty'
              ? 'Its saved run contains neither a graph checkpoint nor a bill of materials.'
              : 'The saved board could not be retrieved. Please try again.'}
          </p>
        </div>
      </div>
    )
  }

  return <WorkspaceView lineId={lineId} session={session} />
}

/**
 * One route, three states.
 *
 * A line with runs shows the workspace. A line with none says so — see `NoRuns`, and note
 * that it used to open the brief screen, which asked what somebody was building about a
 * product that already ships. Asking for a brief is now something a person chooses from
 * there rather than something a menu item does to them.
 *
 * The started brief is held *here* rather than inside `BriefEntry` on purpose. Starting
 * the run in the child and then swapping components would unmount `Workspace` a moment
 * after it opened the SSE connection, and the run would vanish with no error — the
 * stream would simply stop. Holding it at this level means `Workspace` mounts exactly
 * once and keeps its connection.
 */
export default function DesignRoute() {
  const navigate = useNavigate()
  const { lineId } = useParams<{ lineId: string }>()
  const [params] = useSearchParams()

  // Which run to open. This route is keyed by the **line**, so an older run is named in the
  // query rather than in the path: `/design/{line}?thread={run}`. Arriving without one opens
  // the newest, which is what somebody coming from the dashboard means by *open the board*.
  const wanted = params.get('thread')

  const [mode, setMode] = useState<LineMode>(lineId ? 'loading' : 'workspace')
  const [startedRequest, setStartedRequest] = useState<StartedRequest | null>(null)
  const [thread, setThread] = useState<LineThread | null>(null)

  useEffect(() => {
    if (!lineId) {
      // Single-user local mode: no accounts, no lines, nothing to look up.
      setMode('workspace')
      setStartedRequest(null)
      setThread(null)
      return
    }

    // Captured so the async closure below has a `string` rather than `string | undefined`.
    const id = lineId
    let active = true

    setMode('loading')
    setStartedRequest(null)
    setThread(null)

    async function decide() {
      try {
        // One request, not two: the threads endpoint already 404s for a line that
        // does not exist *or* belongs to somebody else, so a separate existence check
        // would only be a second round trip to learn the same thing.
        const threads = await listLineThreads(id)
        if (active) {
          // A thread asked for by id, or the newest. An id naming a run this line does not
          // have falls back to the newest rather than to an error: the link came from
          // somewhere, and the honest answer to "that run is gone" is the current board.
          setThread(threads.find((run) => run.id === wanted) ?? threads[0] ?? null)
          setMode(threads.length === 0 ? 'none' : 'workspace')
        }
      } catch {
        // 404 means it is not this user's line. Anything else means we cannot tell
        // which screen is correct, and guessing would either hide an existing run behind
        // the brief screen or open an empty workspace. The dashboard is the honest place
        // to land, and it has its own error state.
        if (active) {
          navigate('/lines', { replace: true })
        }
      }
    }

    decide()

    return () => {
      active = false
    }
  }, [navigate, lineId, wanted])

  if (!lineId) {
    return <Workspace />
  }

  // Render nothing until the answer arrives — flashing the brief screen at somebody who
  // already has a board is worse than a beat of blankness.
  if (mode === 'loading') {
    return null
  }

  if (mode === 'none') {
    return <NoRuns lineId={lineId} onStart={() => setMode('brief')} />
  }

  if (mode === 'brief') {
    return (
      <BriefEntry
        onStarted={(brief, bom) => {
          setStartedRequest({ brief, bom })
          setMode('workspace')
        }}
        lineId={lineId}
      />
    )
  }

  return startedRequest ? (
    <StartedWorkspace lineId={lineId} request={startedRequest} />
  ) : thread && thread.status !== 'running' ? (
    <RestoredWorkspace lineId={lineId} thread={thread} />
  ) : (
    <Workspace lineId={lineId} />
  )
}
