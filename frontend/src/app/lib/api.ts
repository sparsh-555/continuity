import type { BomRow, DesignEvent, Edge, QuestionEvent, Slot, SupplyNode } from './types'

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
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
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
    throw new ApiError(response.status)
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
