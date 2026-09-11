"""Recompute every copper zone on a board, and save it. Inside KiCad's Python.

A zone's fill is derived geometry, computed against the pads that were there when it was
last filled. DRC on a board with stale fills reports pads that reach each other *through*
copper as unconnected, so a substitution appears to break a connection it never touched.
KiCad's own DRC dialog warns about this.

Both boards in a before-and-after go through here, not just the modified one, so the two
runs are computed by the same filler. Comparing a designer's saved fills against ours would
put the difference between two fillers into the delta as though our change had caused it.

**One board per process.** This is a separate script from `swap_footprint.py` rather than a
function inside it because `pcbnew` keeps global state: loading two boards in one
interpreter produced a *different* set of unconnected items on each run of the same input,
which is worse than the bug it was fixing. Found on OpenJBOD, 687 zones, 9 Sep.
"""

import sys

# Resolves inside KiCad's own Python and nowhere else; see `inspect_board.py`.
import pcbnew  # type: ignore[import-not-found]


def main():
    board_path, out_path = sys.argv[1:3]
    board = pcbnew.LoadBoard(board_path)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.BuildConnectivity()
    board.Save(out_path)


main()
