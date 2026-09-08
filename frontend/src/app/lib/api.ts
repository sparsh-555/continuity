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
    rails?: Record<string, unknown>
  } | null
  part_count: number
  /** How many change notices reach a part this product has fitted. The only thing on a
   *  dashboard of shipping products that is about to change. */
  exposed_count: number
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

export type MatrixCheck = {
  rule: string
  scope: string | null
  status: EventStatus
  detail: string
  margin: string | null
  accepted: boolean
  evidence: Array<{ field: string; value: string; source: string | null }>
}

export type MatrixCell = {
  line_id: string
  line_name: string
  mpn: string
  manufacturer: string | null
  /** This board already runs this part — the row that says what it does today, which is
   *  the status quo rather than a proposed change. */
  is_incumbent: boolean
  replaces: string | null
  ok: boolean
  /** The narrowest margin any satisfied check on this cell reports, where one can be
   *  ordered. Satisfied and unshippable is the distinction this carries. */
  margin: string | null
  counts: Record<EventStatus, number>
  /** Whose desks this cell lands on, derived from what actually failed on it. Empty on a
   *  passing cell, because a cell that raises no question owns nobody's time. */
  departments: string[]
  checks: MatrixCheck[]
}

export type MatrixResponse = {
  slot: string
  lines: string[]
  candidates: string[]
  viable_everywhere: string[]
  departments: string[]
  /** Candidates the distributor has never heard of, named rather than dropped. */
  unresolved: string[]

  /** Candidates listed by more than one manufacturer, keyed to an explanation. Distinct
   *  from `unresolved`: "never heard of it" and "heard of it twice" are different answers,
   *  and only the second one has an action attached — say which manufacturer you meant. */
  ambiguous: Record<string, string>
  cells: MatrixCell[]
}

/** One frame of a review stream. Every frame carries the product line it belongs to, or
 *  `null` where it belongs to the whole review — discovery happens once, not once per
 *  board. */
export type ReviewFrame =
  | {
      type: 'review_started'
      seq: number
      line_id: null
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
      rule: string
      status: EventStatus
      detail: string
      margin: string | null
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
  state: 'approved' | 'declined'
  line_id: string
  mpn?: string
  refdes?: string
  revision?: string | null
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
  /** The power tree the operating profile states. Not a netlist: nothing has read a
   *  schematic, so every edge here is a rail feeding a part. */
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
  mpn: string
  mpn_line: string
  manufacturer: string | null
  effective_date: string | null
  replacement_mpn: string | null
  reason: string | null
  source: string
  created_at: string
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
  /** Rules the engine declares it does not answer. */
  not_assessed: string[]
  /** Rules it tried to answer and could not — a different admission, kept apart. */
  no_evidence: string[]
  cost: ChangeRequestCost
  approvals_required: string[]
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
  boards: number
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

export type MemoryPart = {
  mpn: string
  manufacturer: string | null
  lifecycle: 'active' | 'nrnd' | 'obsolete' | 'unknown' | null
  used_in: Array<{ line_id: string; line_name: string }>
  findings: MemoryFinding[]
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

export function buildMatrix(lineIds: string[], slot: string, candidates: string[]) {
  return request<MatrixResponse>('/matrix', {
    method: 'POST',
    body: { line_ids: lineIds, slot, candidates },
  })
}

export function listNotices() {
  return request<Notice[]>('/notices')
}

export function receiveNotice(documentBase64: string) {
  return request<ReceivedNotice>('/notices', {
    method: 'POST',
    body: { document: documentBase64 },
  })
}

export function reviewNotice(
  noticeId: string,
  candidates: string[],
  annualVolume: number | null,
) {
  return request<Review>(`/notices/${encodeURIComponent(noticeId)}/review`, {
    method: 'POST',
    body: { candidates, annual_volume: annualVolume },
  })
}

export function listChangeRequests(noticeId: string) {
  return request<ChangeRequest[]>(`/notices/${encodeURIComponent(noticeId)}/review`)
}

export function answerDecision(decisionId: string, approve: boolean, rationale = '') {
  return request<DecisionAnswer>(`/decisions/${encodeURIComponent(decisionId)}`, {
    method: 'POST',
    body: { approve, rationale },
  })
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

export function boardConsequence(lineId: string, retiring: string, candidate: string) {
  return request<BoardConsequence>(
    `/lines/${encodeURIComponent(lineId)}/board/consequence`,
    { method: 'POST', body: { retiring, candidate } },
  )
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
