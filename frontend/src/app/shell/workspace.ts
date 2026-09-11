/**
 * Which routes own the viewport rather than being laid out as a page.
 *
 * Three files ask this, and they held one copy of the answer each until now. They have to
 * agree: the frame using `min-h-screen` (100vh) while the shell used `100dvh` is a bug this
 * codebase has already had, and it put the header back under the browser chrome. One
 * definition, for the same reason there is one `Wordmark`.
 *
 * **A route is on this list when it is a set of panes rather than a column of cards.** It
 * paints its own ground, locks its own height, and scrolls inside itself. `/changes` joined
 * it on 11 September: a review running on three boards while the notice that raised it sits
 * beside it is a workspace, and laying it out as a scrolling page put the notice and the
 * thing it caused a screen apart.
 *
 * The two consequences are deliberate and they belong together: this is also the list of
 * routes that do **not** get the animated board behind them. Motion behind a column of prose
 * is decoration; motion behind a graph the run is drawing is the product saying it is alive.
 */
export function ownsTheViewport(pathname: string): boolean {
  if (pathname === '/design' || pathname.startsWith('/design/')) {
    return true
  }
  // A product line page is a workspace: three panes and a review running in them, not a
  // column of cards on a scrolling page. `/lines` itself is a list and is not one, which is
  // what the trailing slash is doing here.
  if (pathname.startsWith('/lines/')) {
    return true
  }
  return pathname === '/changes'
}
