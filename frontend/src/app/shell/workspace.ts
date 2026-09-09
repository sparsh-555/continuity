/**
 * Which routes are locked to the viewport rather than laid out as a page.
 *
 * Two files ask this — `AppFrame` decides whether to paint the animated board background
 * and `AppShell` decides whether to lock the height — and they held one copy of the answer
 * each. They have to agree: the frame using `min-h-screen` (100vh) while the shell used
 * `100dvh` is a bug this codebase has already had, and it put the header back under the
 * browser chrome. One definition, for the same reason there is one `Wordmark`.
 */
export function isWorkspacePath(pathname: string): boolean {
  if (pathname === '/design' || pathname.startsWith('/design/')) {
    return true
  }
  // A product line page is a workspace: three panes and a review running in them, not a
  // column of cards on a scrolling page. `/lines` itself is a list and is not one, which is
  // what the trailing slash is doing here.
  return pathname.startsWith('/lines/')
}
