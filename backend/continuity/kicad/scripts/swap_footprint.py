"""Replace one placed footprint with another, keeping where it sat. Inside KiCad's Python.

The nets are told to it, pad by pad, by the caller. This script decides nothing about which
net belongs where: it places, it wires what it was given, and it reports every pad it was
given nothing for. A pad wired by a guess here would be invisible in the picture and wrong
in the fabrication.

`pcbnew`'s SWIG bindings are deprecated from KiCad 9 and slated for removal in 11, which is
why they are used *here and nowhere else*: `kicad-cli` 9 has no command that writes a board
at all. The version is pinned by the container, so nothing moves underneath this, and when
the bindings go this one file is what changes.
"""

import json
import sys

import pcbnew


def main():
    board_path, out_path, spec_path, report_path = sys.argv[1:5]
    spec = json.load(open(spec_path))
    board = pcbnew.LoadBoard(board_path)

    old = None
    for footprint in board.GetFootprints():
        if footprint.GetReference() == spec["refdes"]:
            old = footprint
            break
    if old is None:
        raise SystemExit("no footprint with reference %s on this board" % spec["refdes"])

    new = pcbnew.FootprintLoad(spec["library"], spec["footprint"])
    if new is None:
        raise SystemExit(
            "no footprint %s in %s" % (spec["footprint"], spec["library"])
        )

    new.SetParent(board)
    new.SetPosition(old.GetPosition())
    new.SetOrientation(old.GetOrientation())
    new.SetLayer(old.GetLayer())
    new.SetReference(old.GetReference())
    new.SetValue(spec.get("value") or old.GetValue())

    wanted = spec["nets"]  # {pad number: net name}
    wired, bare, missing = {}, [], []
    for pad in new.Pads():
        number = pad.GetNumber()
        name = wanted.get(number)
        if not name:
            bare.append(number)
            continue
        net = board.FindNet(name)
        if net is None:
            missing.append({"pad": number, "net": name})
            continue
        pad.SetNet(net)
        wired[number] = name

    board.Remove(old)
    board.Add(new)
    board.BuildConnectivity()
    board.Save(out_path)

    with open(report_path, "w") as handle:
        json.dump(
            {
                "refdes": spec["refdes"],
                "from": old.GetFPIDAsString(),
                "to": new.GetFPIDAsString(),
                "wired": wired,
                "unwired_pads": bare,
                "missing_nets": missing,
            },
            handle,
        )


main()
