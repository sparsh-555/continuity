import type {
  BomRow,
  DesignEvent,
  Edge,
  EventStatus,
  GraphSlot,
  QuestionEvent,
  Slot,
  SupplyNode,
} from './types'

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type PublicUser = {
  id: string
  email: string
  onboarded: boolean
  org_id: string

  /** The hats this person wears, from the server's `ROLES`.
   *
   *  Declared now because `/auth/me` returns it now, and a wire field the client type
   *  does not mention is a field nothing can be built on. Item 13's gates are what make
   *  it visible; nothing renders it yet, and no screen should pretend to gate on it
   *  until something does. */
  roles: string[]
}

export type Line = {
  id: string
  name: string
  created_at: string
  updated_at: string
  revision: string | null
  profile: {
    ambient_c: number
    ambient_source: string
    mounting?: string | null
    rails?: Record<string, Rail>
  } | null
  part_count: number
  /** How many change notices reach a part this product has fitted. The only thing on a
   *  dashboard of shipping products that is about to change. */
  exposed_count: number
}

/** One supply rail as the product line states it: what makes it, what it feeds, and what
 *  it is expected to carry. `source` is absent on the rail that arrives from outside. */
export type Rail = {
  source?: string | null
  members?: string[]
  voltage?: number | null
  i_load?: number | null
  i_limit?: number | null
  basis?: string | null
  i_load_basis?: string | null
}

export type ThreadSummary = {
  slots: number
  placed: number
  conflicts_resolved: number
  elapsed_s: number
}

export type LineThread = {
  id: string
  prompt: string
  status: string
  summary: ThreadSummary | null
}

export type ThreadBoard = {
  status: string
  summary: ThreadSummary | null
  slots: Slot[]
  edges: Edge[]
  /** Null when the restored board predates the supply node, or its source is unknown. */
  supply?: SupplyNode | null
  bom: {
    rows: BomRow[]
    total: number
    currency: string
  } | null
  checkpoint: 'available' | 'unavailable' | 'not_loaded'
  trace: DesignEvent[]
  question: QuestionEvent | null
  resumable: boolean
}

/** One frame of a review stream. Every frame carries the product line it belongs to, or
 *  `null` where it belongs to the whole review — discovery happens once, not once per
 *  board. */
export type ReviewFrame =
  | {
      type: 'review_started'
      seq: number
      notice_id: string
      mpn: string
      lines: Array<{ line_id: string; name: string }>
    }
  | { type: 'reasoning'; seq: number; line_id: string | null; slot: string | null; text: string }
  | { type: 'candidate'; seq: number; line_id: string; slot: string; part: { mpn: string } }
  | {
      type: 'check'
      seq: number
      line_id: string
      slot: string
      rule: string
      /** What the rule was applied to, when one rule speaks about several things. */
      scope: string | null
      status: EventStatus
      detail: string
      margin: string | null
      /** The desks that own this rule. Derived server-side from one routing table, so the
       *  live stream and a replayed one cannot disagree about who owns what. */
      departments: string[]
      /** A failure somebody has already decided to live with. */
      accepted: boolean
    }
  | {
      type: 'question'
      seq: number
      line_id: string
      question_id: string
      text: string
      suggestions: string[]
      roles: string[]
    }
  | {
      type: 'line_done'
      seq: number
      line_id: string
      line_name: string
      /** Null when nothing offered clears this product line, which is the finding. */
      proposal: string | null
      /** The decision waiting for a desk, when there is one to make. */
      decision_id: string | null
      reason: string
      conditional: boolean
      roles: string[]
    }
  | { type: 'error'; seq: number; line_id: string | null; message: string; recoverable: boolean }

export type DecisionAnswer = {
  /** `pending` means this desk signed and the change is waiting on the others. A
   *  substitution on a released design is signed by every department that examined it, in
   *  any order, and applies when the last one signs. */
  state: 'approved' | 'declined' | 'pending'
  line_id: string
  mpn?: string
  refdes?: string
  revision?: string | null
  /** Desks that have signed so far, and desks still to sign. Empty on a decline. */
  signed?: string[]
  outstanding?: string[]
}

export type LinePart = {
  refdes: string
  mpn: string
  manufacturer: string | null
  footprint: string | null
  populated: boolean
}

export type LineGraphView = {
  slots: GraphSlot[]
  edges: Edge[]
  supply: SupplyNode | null
  /** Fitted parts on the bill that no rail names: decoupling, pull-ups, a crystal, a
   *  connector. Counted so the picture can say what it left out rather than hiding it. */
  off_tree: number
}

export type LineNotice = {
  id: string
  mpn: string
  manufacturer: string | null
  effective_date: string | null
  replacement_mpn: string | null
  reason: string | null
  source: string
  created_at: string
  /** Where on this board the retired part sits. */
  refdes: string[]
}

export type LineRequest = {
  id: string
  notice_id: string | null
  proposal: string | null
  created_at: string
  document: ChangeRequest
}

export type LineOverview = {
  line: Line
  parts: LinePart[]
  /** The power tree the operating profile states: every edge is a rail feeding a part. */
  graph: LineGraphView
  board: LineBoard | null
  notices: LineNotice[]
  requests: LineRequest[]
}

export type LineBoard = {
  filename: string
  project: string
  bytes: number
  uploaded_at: string
}

export type BoardStatus = {
  board: LineBoard | null
  /** Whether this instance has a KiCad to read the project with. A stored board with no
   *  KiCad is not an error: the file is kept and the reading happens as soon as one is
   *  configured. */
  kicad: boolean
}

export type BoardUploaded = {
  project: string
  filename: string
  bytes: number
  kicad: boolean
  /** Whether the project's bill of materials replaced the line's. Never true when the line
   *  already had one and the caller did not ask. */
  adopted: boolean
  mpn_field?: string
}

export type BoardFinding = {
  rule: string
  description: string
  severity: string
  items: string[]
}

export type BoardConsequence = {
  refdes: string
  retiring: string
  candidate: string
  package: { from: string; to: string }
  footprint: { from: string; to: string }
  /** Where the substitute's pin functions were read from. */
  pinout_source: string
  wiring: {
    wired: Record<string, string>
    /** Pads the substitute has that no net was carried to — an enable pin, a no-connect. */
    unwired_pads: string[]
    /** Roles the old part used that the substitute has no pin for. The loudest case. */
    stranded: string[]
  }
  /** What ran to produce this, and what each operation cost. Absent on a payload stored
   *  before 11 Sep, when nothing was timed. */
  steps?: Array<{ name: string; ms: number }>
  broke_connections: boolean
  /** The page the pictures were drawn on, in millimetres, so a crop means something. */
  page: { width: number; height: number }
  added: BoardFinding[]
  counts: Record<string, { before: number; after: number }>
  /** An SVG viewBox in board millimetres, so both pictures crop to the same rectangle. */
  crop: string
  before_svg: string
  after_svg: string
}

export type Notice = {
  id: string
  reference: string | null
  reference_line: string | null
  mpn: string
  mpn_line: string
  manufacturer: string | null
  effective_date: string | null
  replacement_mpn: string | null
  reason: string | null
  source: string
  created_at: string
  review_skipped: Array<{ mpn: string; reason: string }>
}

export type AffectedLine = {
  line_id: string
  name: string
  revision: string | null
  refdes: string[]
}

export type ReceivedNotice = {
  id: string
  notice: Omit<Notice, 'id' | 'source' | 'created_at'> & {
    effective_date_line: string | null
    replacement_line: string | null
  }
  affected: AffectedLine[]
}

export type ChangeRequestAlternative = {
  mpn: string
  /** The sentence that ruled it out, or null when it survived and simply was not chosen. */
  rejected_because: string | null
  /** Who makes the part this run weighed. An MPN alone does not name one, and a reader
   *  asking for this working again cannot re-source a part this company has never bought. */
  manufacturer?: string | null
  /** **The appendix behind `rejected_because`**: every check this candidate was put through,
   *  in the same shape as the proposal's own `evidence` below, so one renderer draws both.
   *  It is what makes the document auditable without a grid screen of its own. */
  /** **Absent on any document written before 11 Sep**, when the field did not exist.
   *  The stored record is not rewritten — it is a record of what was decided — so a reader
   *  must tolerate its absence rather than throw over it. */
  verdicts?: Array<{
    rule: string
    scope: string | null
    status: EventStatus
    detail: string
    margin: string | null
    accepted: boolean
    /** Whose desk this check lands on. Empty where the check raises no question. */
    departments?: string[]
  }>
}

export type ChangeRequestCost = {
  unit_delta: number | null
  annual_volume: number | null
  /** Null without a stated volume rather than assumed — an assumed volume makes a
   *  plausible number out of nothing. */
  recurring_annual: number | null
  one_time: number
  one_time_basis: string
}

export type ChangeRequestDepartment = {
  role: string
  satisfied: number
  failed: number
  /** The rule's own sentence, never one composed for the screen. */
  headline: string
}

export type ChangeRequest = {
  id?: string
  line_id: string
  line_name: string
  revision: string | null
  baseline_mpn: string | null
  notice_mpn: string
  notice_id: string | null
  /** Null when nothing offered clears this line, which is the finding rather than an
   *  absence of one. */
  proposal: string | null
  proposal_detail: string
  alternatives: ChangeRequestAlternative[]
  evidence: Array<{
    rule: string
    scope: string | null
    status: EventStatus
    detail: string
    margin: string | null
  }>
  /** Rules it tried to answer and could not — a different admission, kept apart. */
  no_evidence: string[]
  cost: ChangeRequestCost
  /** What the round trips that no longer happen are worth, from published constants applied
   *  to this run's own counts. Absent on a document written before 11 Sep. */
  saving?: {
    desk_hours: number
    queue_days: number
    desks: number
    crossings: number
    basis: string
  } | null
  /** What has to happen to the stock the change leaves behind, where that is a decision.
   *  Only present where a line stated a build quantity and its answer is short of it. */
  disposition?: string | null
  effectivity?: string
  approvals_required: string[]
  /** What each desk found, over the same verdicts the evidence is drawn from. A desk that
   *  looked at nothing is absent rather than empty. */
  departments: ChangeRequestDepartment[]
  /** The board this substitution was placed on, once the run has computed it.
   *
   *  Fired in the background when the proposal is chosen, so a request read a moment later
   *  carries the pictures and the card renders them without a button. Absent on a world with
   *  no KiCad, and on a request read in the few seconds before the placement lands. */
  board?: BoardConsequence | null
  /** The size of the sweep this answer came out of. Not a saving — nobody measured one —
   *  but the count of round trips that did not have to happen. */
  checked: {
    candidates: number
    checks: number
    departments: number
    lines: number
  } | null
}

export type Review = {
  notice_id: string
  unresolved: string[]
  ambiguous: Record<string, string>
  requests: ChangeRequest[]
}

export type MemoryLine = {
  id: string
  name: string
  revision: string | null
  /** How many parts the line's bill of materials records. */
  parts: number
}

export type MemoryFinding = {
  thread_id: string
  line_id: string
  line_name: string
  rule: string
  slot: string
  verdict: string
  outcome: 'repaired' | 'accepted' | 'unresolved'
  action: string | null
  replacement_mpn: string | null
}

/** What a change notice said about a part, in the document's own words. */
export type MemoryRetirement = {
  mpn_line: string | null
  manufacturer: string | null
  effective_date: string | null
  effective_date_line: string | null
  replacement_mpn: string | null
  replacement_line: string | null
  reason: string | null
  source: string | null
  at: string | null
}

/** One thing that happened to this part: a board ruled it out, a desk signed for it, a
 *  manufacturer recommended it, or a decision about it is still open. */
export type MemoryEvent = {
  kind: 'worked' | 'rejected' | 'approved' | 'recommended' | 'awaiting' | 'declined'
  line_id?: string | null
  line_name?: string | null
  detail?: string | null
  at?: string | null
  by?: string
  roles?: string[]
  rule?: string | null
  subject?: string | null
  revision?: string | null
  rationale?: string | null
  signature?: string | null
  replaces?: string | null
  for_mpn?: string
  source?: string | null
}

/** A stored part fact. `quote` is the document's own words when the reading captured
 *  them, and `verified` says the reading outranks a distributor's listing either way. */
export type MemoryFact = {
  field: string
  value: string
  verified: boolean
  quote: string | null
}

export type MemoryPart = {
  mpn: string
  manufacturer: string | null
  lifecycle: 'active' | 'nrnd' | 'obsolete' | 'unknown' | null
  used_in: Array<{ line_id: string; line_name: string; refdes: string[] }>
  retirement: MemoryRetirement | null
  history: MemoryEvent[]
  findings: MemoryFinding[]
  facts: MemoryFact[]
}

export type MemoryResponse = {
  lines: MemoryLine[]
  parts: MemoryPart[]
  parts_capped: boolean
  part_limit: number
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message?: string) {
    super(message ?? `Request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body } = options

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: 'include',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (!response.ok) {
    // The server's own sentence, when it wrote one. Several of these are the whole
    // answer — no pin functions are on file for this part, this board does not carry
    // that one — and a status code alone would throw the actionable half away.
    let detail: string | undefined
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // A response with no JSON body is ordinary. The status still travels.
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export function register(email: string, password: string) {
  return request<PublicUser>('/auth/register', {
    method: 'POST',
    body: { email, password },
  })
}

export function login(email: string, password: string) {
  return request<PublicUser>('/auth/login', {
    method: 'POST',
    body: { email, password },
  })
}

export function logout() {
  return request<void>('/auth/logout', {
    method: 'POST',
  })
}

export function me() {
  return request<PublicUser>('/auth/me')
}

export function listNotices() {
  return request<Notice[]>('/notices')
}

/** Which product lines carry a part, and where on each of them.
 *
 *  The upload reply carries this for a notice somebody just handed us. A notice that
 *  arrived by email has no such reply, and "affects three product lines" is the sentence
 *  the whole screen turns on, so it is asked for rather than shown only to whoever
 *  happened to do the uploading. */
export function exposureTo(mpn: string) {
  return request<AffectedLine[]>(`/exposure?mpn=${encodeURIComponent(mpn)}`)
}

/** `filename` becomes the notice's recorded source, so memory can cite the document a
 *  person actually recognises rather than the word `api`. */
export function receiveNotice(documentBase64: string, filename?: string) {
  return request<ReceivedNotice>('/notices', {
    method: 'POST',
    body: { document: documentBase64, filename },
  })
}

export function reviewNotice(
  noticeId: string,
  candidates: string[],
) {
  return request<Review>(`/notices/${encodeURIComponent(noticeId)}/review`, {
    method: 'POST',
    body: { candidates },
  })
}

export function listChangeRequests(noticeId: string) {
  return request<ChangeRequest[]>(`/notices/${encodeURIComponent(noticeId)}/review`)
}

export type WaitingDecision = {
  id: string
  line_id: string
  line_name: string
  revision: string | null
  notice_id: string | null
  notice_mpn: string | null
  refdes: string
  retiring: string
  proposal: string
  /** The rule a desk is being asked to accept, when one failed. */
  gate_rule: string | null
  detail: string
  /** Every desk that must sign, every desk that has, and what this reader still owes. */
  roles: string[]
  signed: string[]
  mine: string[]
  created_at: string
}

/** Every pending decision one of the signed-in person's desks may answer. */
export function listWaitingDecisions() {
  return request<WaitingDecision[]>('/decisions')
}

export type HeldSession = {
  email: string
  roles: string[]
  active: boolean
}

/** Every desk this browser is signed into. Tokens are never returned. */
export function listSessions() {
  return request<HeldSession[]>('/auth/sessions')
}

/** Make another session this browser already holds the active one.
 *
 *  Not an impersonation: the token has to be in this browser's own httpOnly cookie
 *  already, so this changes which real session is in use rather than granting one. A desk
 *  that has to sign has to be signed in. */
export function switchDesk(email: string) {
  return request<PublicUser>('/auth/switch', { method: 'POST', body: { email } })
}

export function answerDecision(decisionId: string, approve: boolean, rationale = '') {
  return request<DecisionAnswer>(`/decisions/${encodeURIComponent(decisionId)}`, {
    method: 'POST',
    body: { approve, rationale },
  })
}

/** What the engine says about a product line as it stands today.
 *
 *  A separate call from the overview on purpose: this one resolves parts against a
 *  distributor and takes seconds, and the overview promises to render offline and
 *  instantly. The page loads grey and settles. */
/** A review this product line has already been through, with the trace it left. */
export type StoredReview = {
  decision_id: string
  notice_id: string
  state: 'pending' | 'approved' | 'declined'
  proposal: string
  retiring: string
  created_at: string
  /** The run's own frames, rebuilt from what it recorded. See `api/replay`. */
  frames: ReviewFrame[]
}

/** One decision a notice produced, with the trace it left and who has signed it.
 *
 * `frames` is the run's own record reassembled, and for a decision still waiting on a desk
 * it ends with the question the run asked — rebuilt by the same function, so a replay
 * re-raises the identical sentence rather than a second phrasing of it.
 */
export type NoticeReview = {
  decision_id: string
  line_id: string
  line_name: string | null
  state: 'pending' | 'approved' | 'declined'
  proposal: string | null
  gate_rule: string | null
  roles: string[]
  signed: string[]
  outstanding: string[]
  frames: ReviewFrame[]
}

export function noticeReviews(noticeId: string) {
  return request<NoticeReview[]>(`/notices/${encodeURIComponent(noticeId)}/reviews`)
}

export function listLineReviews(lineId: string) {
  return request<StoredReview[]>(`/lines/${encodeURIComponent(lineId)}/reviews`)
}

export function checkLine(lineId: string) {
  return request<LineCheck>(`/lines/${encodeURIComponent(lineId)}/check`, { method: 'POST' })
}

export type LineCheck = {
  slots: Record<string, {
    status: 'pass' | 'accepted' | 'conflict'
    checked: number
    detail: string | null
    /** Failed rules a responsible desk accepted on this candidate and revision. */
    accepted: string[]
  }>
  checked: number
  /** Rules that do not apply to this board, and rules whose inputs nobody has supplied.
   *  Green means nothing failed, not that everything was checkable. */
  evidence_missing: string[]
  /** Fitted parts no distributor listing was found for. They have no verdict, and a slot
   *  with no verdict renders exactly like one nobody got to, so they are named. */
  unresolved: Array<{ refdes: string; mpn: string }>
}

export function getLineOverview(lineId: string) {
  return request<LineOverview>(`/lines/${encodeURIComponent(lineId)}/overview`)
}

export function getBoard(lineId: string) {
  return request<BoardStatus>(`/lines/${encodeURIComponent(lineId)}/board`)
}

export function putBoard(lineId: string, filename: string, bundleBase64: string, adopt?: boolean) {
  return request<BoardUploaded>(`/lines/${encodeURIComponent(lineId)}/board`, {
    method: 'PUT',
    body: { filename, bundle: bundleBase64, adopt: adopt ?? null },
  })
}

export type BoardPicture = {
  svg: string
  page: { width: number; height: number }
  /** The rectangle the placed footprints occupy, in the same millimetres. KiCad draws the
   *  page, not the board, so this is what to actually look at. */
  content: string
  /** The reference designator the board itself gives the part asked about, when it has one.
   *  A board's designators are its own and need not match the company's bill. */
  marked: string | null
  /** A viewBox in board millimetres around that part, for pointing at it. */
  crop: string | null
}

/** The board as it is, with no substitution in it. */
export function boardRender(lineId: string, mark?: string | null) {
  const query = mark ? `?mark=${encodeURIComponent(mark)}` : ''
  return request<BoardPicture>(`/lines/${encodeURIComponent(lineId)}/board/render${query}`)
}

export function boardConsequence(lineId: string, retiring: string, candidate: string) {
  return request<BoardConsequence>(
    `/lines/${encodeURIComponent(lineId)}/board/consequence`,
    { method: 'POST', body: { retiring, candidate } },
  )
}

export type BoardStep = { name: string; ms: number }

/** The same consequence, said while it is being worked out.
 *
 * **A cold board takes ten seconds.** Reading its placements, placing the part and carrying
 * its nets, refilling the zones, running DRC twice and rendering two pictures is real work
 * and none of it can be hurried. What can be fixed is what the pane says during it: the
 * operations were already timed for the WHAT RAN block, and this is the same list arriving as
 * it is taken rather than all of it at the end.
 *
 * A separate reader from `runReview` for the same reason that one is separate from
 * `sseClient`: three streams that share a sequence space silently discard each other's
 * frames. This one owns nothing global, so a caller can start it, abandon it and start
 * another.
 */
export function streamBoardConsequence(
  lineId: string,
  retiring: string,
  candidate: string,
  handlers: {
    onStep: (step: BoardStep) => void
    onDone: (made: BoardConsequence) => void
    /** `status` is absent once the stream is open: everything after that is a frame rather
     *  than a status, because the status was sent before the work began. */
    onError: (message: string, status?: number) => void
  },
): () => void {
  const controller = new AbortController()

  void (async () => {
    try {
      const response = await fetch(
        `${API_BASE}/lines/${encodeURIComponent(lineId)}/board/consequence/stream`,
        {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ retiring, candidate }),
          signal: controller.signal,
        },
      )

      if (!response.ok) {
        // The two refusals that happen before any work starts are still real statuses —
        // no board stored, no KiCad on this instance — and they are the sentences the pane
        // has always shown. Anything after this point arrives as a frame, because the
        // status was sent long before the work finished.
        let detail: string | undefined
        try {
          detail = ((await response.json()) as { detail?: string }).detail
        } catch {
          // no body, the status carries the answer
        }
        handlers.onError(
          detail ?? `That board could not be checked (${response.status}).`,
          response.status,
        )
        return
      }

      const body = response.body
      if (!body) {
        handlers.onError('The server returned no stream.')
        return
      }

      const reader = body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split('\n\n')
        buffer = blocks.pop() ?? ''
        for (const block of blocks) {
          for (const line of block.split('\n')) {
            if (!line.startsWith('data: ')) continue
            try {
              const frame = JSON.parse(line.slice(6)) as
                | { type: 'step'; name: string; ms: number }
                | { type: 'done'; consequence: BoardConsequence }
                | { type: 'error'; message: string }
              if (frame.type === 'step') handlers.onStep({ name: frame.name, ms: frame.ms })
              else if (frame.type === 'done') handlers.onDone(frame.consequence)
              else handlers.onError(frame.message)
            } catch {
              // A malformed frame is not worth killing the run over.
            }
          }
        }
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        handlers.onError(error instanceof Error ? error.message : 'That board could not be checked.')
      }
    }
  })()

  return () => controller.abort()
}

export function listLines() {
  return request<Line[]>('/lines')
}

export function getMemory() {
  return request<MemoryResponse>('/memory')
}

export function getThreadBoard(threadId: string) {
  return request<ThreadBoard>(`/threads/${encodeURIComponent(threadId)}/board`)
}

export function createLine(name: string) {
  return request<Line>('/lines', {
    method: 'POST',
    body: { name },
  })
}

export function getLine(lineId: string) {
  return request<Line>(`/lines/${encodeURIComponent(lineId)}`)
}

export function getLineBom(lineId: string) {
  return request<Array<{ refdes: string; mpn: string; populated: boolean }>>(
    `/lines/${encodeURIComponent(lineId)}/bom`,
  )
}

export function listLineThreads(lineId: string) {
  return request<LineThread[]>(`/lines/${encodeURIComponent(lineId)}/threads`)
}

export function updateLine(lineId: string, name: string) {
  return request<Line>(`/lines/${encodeURIComponent(lineId)}`, {
    method: 'PATCH',
    body: { name },
  })
}

export function deleteLine(lineId: string) {
  return request<void>(`/lines/${encodeURIComponent(lineId)}`, {
    method: 'DELETE',
  })
}

/**
 * The company's standing lists, which gate every board.
 *
 * `missing` is the answer an empty AML cannot give: every part the company already ships
 * that is not on the list. It is empty while the list is not kept, because a company that
 * has never declared a policy is failing nothing.
 */
export type Policy = {
  parts: {
    kept: boolean
    entries: Array<{
      mpn: string
      manufacturer: string | null
      qualified_by: string | null
      note: string | null
      created_at: string
    }>
    missing: Array<{ mpn: string; manufacturer: string | null }>
    shipping: number
  }
  vendors: {
    kept: boolean
    entries: Array<{
      distributor: string
      approved_by: string | null
      note: string | null
      created_at: string
    }>
  }
  desks: { parts: string[]; vendors: string[] }
}

export function getPolicy() {
  return request<Policy>('/policy')
}

export function keepLists(body: { parts?: boolean; vendors?: boolean }) {
  return request<{ parts: boolean | null; vendors: boolean | null }>('/policy/lists', {
    method: 'PUT',
    body,
  })
}

export function qualifyPart(body: { mpn: string; manufacturer?: string }) {
  return request<{ mpn: string }>('/policy/parts', { method: 'POST', body })
}

export function releasePart(mpn: string) {
  return request<void>(`/policy/parts/${encodeURIComponent(mpn)}`, { method: 'DELETE' })
}

export function approveVendor(body: { distributor: string }) {
  return request<{ distributor: string }>('/policy/vendors', { method: 'POST', body })
}

export function releaseVendor(distributor: string) {
  return request<void>(`/policy/vendors/${encodeURIComponent(distributor)}`, { method: 'DELETE' })
}

/** Qualify everything this company already ships, and keep the list. */
export function qualifyFromBill() {
  return request<{ qualified: number }>('/policy/parts/from-bill', { method: 'POST' })
}
