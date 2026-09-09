import type { ReviewFrame } from './api'

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const STALL_TIMEOUT_MS = 45_000
/** Longer than the design client's thirty seconds. A review searches a distributor and
 *  normalises what it finds before the first board is touched, and that opening stretch is
 *  legitimately quiet for half a minute. */

/**
 * Read one review's stream.
 *
 * A separate reader from `sseClient` on purpose, not by accident: that one is a singleton
 * holding the current design session — one listener, one abort controller, one thread id —
 * and a review running beside a design run would take its place. This owns nothing global,
 * so a caller can start one, abandon it, and start another.
 *
 * Frames are separated by a blank line and can be split across chunk boundaries, so the tail
 * of the buffer is held back until its terminator arrives. `:` comment lines are the
 * heartbeat and are skipped — but they still prove the connection is alive, which is the one
 * job they have.
 */
export type ReviewRequest = {
  noticeId: string
  candidates: string[]
  /** One product line rather than every line the notice reaches. The product line page
   *  asks the same question about itself; the change page asks it about the company. */
  lineId?: string
}

export function runReview(
  { noticeId, candidates, lineId }: ReviewRequest,
  onFrame: (frame: ReviewFrame) => void,
  onError: (message: string) => void,
  onClose: () => void,
): () => void {
  const controller = new AbortController()

  void (async () => {
    let stall: ReturnType<typeof setInterval> | undefined
    try {
      const response = await fetch(
        `${API_BASE}/notices/${encodeURIComponent(noticeId)}/review/run`,
        {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ candidates, line_id: lineId ?? null }),
          signal: controller.signal,
        },
      )

      if (!response.ok) {
        let detail: string | undefined
        try {
          detail = ((await response.json()) as { detail?: string }).detail
        } catch {
          // no body, the status carries the answer
        }
        onError(detail ?? `The review could not be started (${response.status}).`)
        return
      }

      const body = response.body
      if (!body) {
        onError('The server returned no stream.')
        return
      }

      const reader = body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let lastFrameAt = Date.now()

      stall = setInterval(() => {
        if (Date.now() - lastFrameAt > STALL_TIMEOUT_MS) {
          reader.cancel().catch(() => undefined)
          onError('The connection went quiet. The review may still be going on the server.')
        }
      }, 5_000)

      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        lastFrameAt = Date.now()
        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split('\n\n')
        buffer = blocks.pop() ?? ''
        for (const block of blocks) {
          for (const line of block.split('\n')) {
            if (!line.startsWith('data: ')) continue
            try {
              onFrame(JSON.parse(line.slice(6)) as ReviewFrame)
            } catch {
              // A malformed frame is not worth killing a review over.
            }
          }
        }
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        onError(error instanceof Error ? error.message : 'The review stream failed.')
      }
    } finally {
      if (stall) clearInterval(stall)
      onClose()
    }
  })()

  return () => controller.abort()
}
