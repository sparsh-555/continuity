import type { ReactNode } from 'react'

/**
 * The drawer that takes the bill of materials' place.
 *
 * `design/ConflictPanel` is the same idea and the same position: when a board has something
 * wrong with it, the thing that is wrong replaces the inventory on the right rather than
 * appearing somewhere new. A product line's end-of-life notice is that board's conflict, so
 * it opens here, and so does the change request that answered an earlier one.
 *
 * It is deliberately not a modal. A person reading a notice is comparing it against the
 * graph and the trace beside it, and a modal would cover both.
 */
export function SidePanel({
  title,
  tone = 'normal',
  onClose,
  children,
}: {
  title: string
  tone?: 'normal' | 'error'
  onClose: () => void
  children: ReactNode
}) {
  return (
    <aside className="w-[30%] min-w-[320px] flex-shrink-0 flex flex-col panel-border rounded-lg overflow-hidden bg-surface-container-low shadow-[-4px_0_12px_rgba(0,0,0,0.5)] animate-[slideInRight_0.3s_ease-out]">
      <header className="h-10 px-md flex items-center justify-between gap-sm border-b border-outline-variant bg-surface-container-high flex-shrink-0">
        <div className="flex items-center gap-sm min-w-0">
          <span
            className={`material-symbols-outlined text-[16px] ${
              tone === 'error' ? 'text-error' : 'text-on-surface-variant'
            }`}
          >
            {tone === 'error' ? 'warning' : 'description'}
          </span>
          <h2
            className={`font-headline-sm text-[14px] font-semibold tracking-wide truncate ${
              tone === 'error' ? 'text-error' : 'text-on-surface'
            }`}
          >
            {title}
          </h2>
        </div>
        <button
          aria-label="Close panel"
          className="text-on-surface-variant hover:text-on-surface transition-colors"
          onClick={onClose}
          type="button"
        >
          <span className="material-symbols-outlined text-[20px]">close</span>
        </button>
      </header>
      <div className="flex-1 overflow-y-auto">{children}</div>
    </aside>
  )
}
