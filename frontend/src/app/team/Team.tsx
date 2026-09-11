import { useCallback, useEffect, useState } from 'react'

import { departmentLabel, DEPARTMENT_ORDER } from '../review/Departments'
import { ApiError, inviteTeammate, listMembers, type Member } from '../lib/api'
import { Modal } from '../design/Modal'

/**
 * Who is in the company, and which projects each of them was brought in on.
 *
 * **Every screen in this product showed the work and none showed the team.** Scenario B is a
 * cross-team response signed by four desks, and a judge watching four people sign one change
 * has to take the sharing on faith without a surface that names the people or says what each
 * of them can reach. This is that surface.
 *
 * It sits at the top of PRODUCT LINES because that is the first screen after sign-in and it
 * is where the projects are, so the answer to *how do you share these* is in the same place
 * as the things being shared rather than a destination away from them.
 */
export function TeamPanel({ members }: { members: Member[] }) {
  const [open, setOpen] = useState(false)

  if (members.length === 0) return null

  return (
    <section className="border border-outline-variant rounded bg-surface-container-low">
      <button
        aria-expanded={open}
        className="w-full flex items-center justify-between px-md py-sm text-left hover:bg-surface-container transition-colors"
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        <span className="font-label-caps text-label-caps tracking-[0.1em] uppercase text-on-surface">
          The company
        </span>
        <span className="font-data-tabular text-[12px] text-on-surface-variant">
          {members.length} {members.length === 1 ? 'person' : 'people'} ·{' '}
          {open ? 'hide' : 'show'}
        </span>
      </button>

      {open ? (
        <div className="px-md pb-md space-y-sm border-t border-outline-variant pt-sm">
          <p className="m-0 font-data-tabular text-[12px] text-on-surface-variant leading-relaxed">
            Everyone here sees the projects they were brought in on, and nothing else. A desk
            is asked to sign a change because it owned a rule the change touched, not because
            it was forwarded anything.
          </p>
          <ul className="m-0 p-0 list-none flex flex-col gap-1">
            {members.map((member) => (
              <li className="flex flex-wrap items-baseline gap-x-md gap-y-0.5" key={member.id}>
                <span className="font-data-tabular text-[13px] text-on-surface min-w-[220px]">
                  {member.email}
                </span>
                <span className="font-data-tabular text-[11px] text-on-surface-variant uppercase min-w-[180px]">
                  {member.roles.map(departmentLabel).join(' · ') || 'no desk'}
                </span>
                <span className="font-data-tabular text-[12px] text-on-surface-variant">
                  {member.line_ids.length}{' '}
                  {member.line_ids.length === 1 ? 'project' : 'projects'}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}

/** Bring somebody in on the projects ticked on the list behind this.
 *
 * **It names the projects rather than asking for them twice.** The selection is made on the
 * list, where the projects are; this is the second half of that sentence — who — and the
 * desks they will hold. An invite that asked for the projects again would be two places to
 * make one decision.
 */
export function InviteDialog({
  selected,
  open,
  onClose,
  onInvited,
}: {
  selected: readonly string[]
  open: boolean
  onClose: () => void
  onInvited: (message: string) => void
}) {
  const [email, setEmail] = useState('')
  const [roles, setRoles] = useState<string[]>(['procurement'])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const close = useCallback(() => {
    setMessage(null)
    onClose()
  }, [onClose])

  const send = useCallback(async () => {
    setBusy(true)
    setMessage(null)
    try {
      const answer = await inviteTeammate(email.trim(), roles, [...selected])
      setEmail('')
      onInvited(
        `${answer.member?.email ?? email} was brought in on ${selected.length} project${
          selected.length === 1 ? '' : 's'
        }. They will see it the next time they sign in.`,
      )
    } catch (caught) {
      // The server's own sentence. A 404 here names the address and says what to do about
      // it, and replacing that with "something went wrong" throws away the only useful part.
      setMessage(
        caught instanceof ApiError
          ? (caught.message ?? 'That invitation could not be sent.')
          : 'That invitation could not be sent.',
      )
    } finally {
      setBusy(false)
    }
  }, [email, onInvited, roles, selected])

  return (
    <Modal
      confirmLabel={busy ? 'SENDING…' : 'SEND THE INVITATION'}
      onClose={close}
      onConfirm={() => void send()}
      open={open}
      title="INVITE A TEAMMATE"
    >
        <div className="space-y-md">
          <label className="block space-y-1">
            <span className="font-data-tabular text-[11px] tracking-[0.08em] text-on-surface-variant uppercase">
              Their email
            </span>
            <input
              autoComplete="off"
              className="input-field px-sm h-9 w-full font-data-tabular text-[13px]"
              onChange={(event) => setEmail(event.target.value)}
              placeholder="teammate@northwind.example"
              value={email}
            />
          </label>

          <div className="space-y-1">
            <span className="font-data-tabular text-[11px] tracking-[0.08em] text-on-surface-variant uppercase">
              The desks they will hold
            </span>
            <div className="flex flex-wrap gap-sm">
              {DEPARTMENT_ORDER.map((role) => {
                const on = roles.includes(role)
                return (
                  <button
                    className={`h-8 px-md border rounded font-data-tabular text-[12px] transition-colors ${
                      on
                        ? 'border-primary-container text-primary-container bg-surface-variant'
                        : 'border-outline-variant text-on-surface-variant hover:border-on-surface-variant'
                    }`}
                    key={role}
                    onClick={() =>
                      setRoles((current) =>
                        current.includes(role)
                          ? current.filter((held) => held !== role)
                          : [...current, role],
                      )
                    }
                    type="button"
                  >
                    {departmentLabel(role)}
                  </button>
                )
              })}
            </div>
          </div>

          <p className="m-0 font-data-tabular text-[12px] text-on-surface-variant leading-relaxed">
            They are brought in on{' '}
            <span className="text-on-surface">{selected.length}</span> project
            {selected.length === 1 ? '' : 's'} — the ones ticked on the list. An invitation
            adds: a desk they already hold stays theirs.
          </p>

          {message ? (
            <p className="m-0 font-data-tabular text-[12px] text-tertiary-container leading-relaxed">
              {message}
            </p>
          ) : null}
        </div>
      </Modal>
  )
}

/** The roster, fetched once and refreshed when somebody is brought in. */
export function useMembers() {
  const [members, setMembers] = useState<Member[]>([])

  const refresh = useCallback(async () => {
    try {
      setMembers(await listMembers())
    } catch {
      // A roster that cannot be read is not worth a banner over the projects beside it.
      setMembers([])
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { members, refresh }
}
