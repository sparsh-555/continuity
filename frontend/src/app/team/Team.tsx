import { useCallback, useState } from 'react'

import { departmentLabel, DEPARTMENT_ORDER } from '../review/Departments'
import { ApiError, inviteTeammate } from '../lib/api'
import { Modal } from '../design/Modal'

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
