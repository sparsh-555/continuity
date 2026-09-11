"""Report what a board says about its placed footprints. Runs inside KiCad's Python.

Kept deliberately small and free of decisions: it reads, it prints JSON, it changes
nothing. Everything that follows — which footprint is the retired part, which net belongs
on which pad of a substitute — happens in `continuity.kicad`, where it can be tested
without a container.
"""

import json
import sys

# `pcbnew` ships with KiCad and exists nowhere else, so it cannot be resolved on a machine
# that is not running KiCad. Every caller here runs this file **inside the pinned container**
# (`kicad/board.py` through `kicad/runner.py`), which is where the import resolves.
import pcbnew  # type: ignore[import-not-found]

NANOMETRES_PER_MM = 1_000_000.0


def main():
    board_path, out_path = sys.argv[1], sys.argv[2]
    board = pcbnew.LoadBoard(board_path)

    footprints = []
    for footprint in board.GetFootprints():
        position = footprint.GetPosition()
        pads = []
        for pad in footprint.Pads():
            pads.append(
                {
                    "number": pad.GetNumber(),
                    "net": pad.GetNetname() or None,
                    "function": pad.GetPinFunction() or None,
                }
            )
        footprints.append(
            {
                "refdes": footprint.GetReference(),
                "value": footprint.GetValue(),
                "footprint": footprint.GetFPIDAsString(),
                "layer": footprint.GetLayerName(),
                "x_mm": position.x / NANOMETRES_PER_MM,
                "y_mm": position.y / NANOMETRES_PER_MM,
                "orientation": footprint.GetOrientationDegrees(),
                "pads": pads,
            }
        )

    with open(out_path, "w") as handle:
        json.dump({"version": pcbnew.GetBuildVersion(), "footprints": footprints}, handle)


main()
