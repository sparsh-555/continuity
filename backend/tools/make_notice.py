"""The change notices the demonstration runs on, as documents rather than fixtures.

Everything upstream of this file was tested against a few lines of typed text. A real
product change notice is a page of letterhead, numbered sections, three or four dates
that are not the one you want, and a recommendation written by somebody who has never
seen your board. Building the document properly is the only way to find out whether the
reader survives one, and it found two things a fixture never would: the reader had no
idea which of three dates ends ordering, and it would take a replacement part number the
notice never printed. Both are fixed in `continuity.notices`.

## These are constructed, and they say so

The affected part is real, the recommended part is real, and the issuer is a real
company, because a notice naming invented parts would exercise none of the sourcing this
system exists to do. So the label is in the document itself, first line and last: this
was written for the demonstration, and Advanced Monolithic Systems has issued no such
notice. Nothing about it should ever be readable as a real end-of-life announcement.

## Two documents, because the second is the harder one

`PCN-2026-114` states every field the reader declares. `PCN-2026-118` withholds two of
them, in the way a real preliminary notice does: the last-order date is *to be advised*
and there is no recommended replacement. It exists to prove the reader reports those as
absent rather than reaching for the issue date and the word "none".

Run it to regenerate the documents:

    PYTHONPATH=. python tools/make_notice.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tools.pdf import Line, document

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "world-finals" / "notices"

LABEL = "CONSTRUCTED EXAMPLE. NOT A REAL MANUFACTURER NOTICE."

DISCLAIMER = [
    "Written for the Continuity demonstration. Advanced Monolithic Systems has issued no",
    "notice of this kind. The reference number, the dates and the response instructions",
    "below were invented. The part numbers are real, so that the document exercises real",
    "sourcing against real distributor data.",
]

FOOTER = "CONSTRUCTED EXAMPLE. Written for the Continuity demonstration, issued by nobody."


@dataclass(frozen=True)
class Document:
    """One constructed notice, and what a correct reading of it says.

    `stated` maps each field the reader declares to the line the document states it on,
    so a test can check the document is self-sufficient without asking a model anything.
    `withheld` names the fields the document deliberately does not state, which is the
    other half: those must come back absent rather than inferred.
    """

    slug: str
    lines: tuple[Line, ...]
    stated: dict[str, tuple[str, str]]
    withheld: frozenset[str]

    def pdf(self) -> bytes:
        return document(list(self.lines))

    def text(self) -> str:
        return "\n".join(line.text for line in self.lines if line.text)

    @property
    def path(self) -> Path:
        return OUTPUT_DIR / f"{self.slug}.pdf"


def _banner() -> list[Line]:
    return [
        Line(LABEL, size=11, bold=True),
        *(Line(text, size=9) for text in DISCLAIMER),
    ]


def _letterhead(reference: str, kind: str) -> list[Line]:
    return [
        Line("ADVANCED MONOLITHIC SYSTEMS", size=15, bold=True, space_before=22),
        Line("PRODUCT CHANGE NOTIFICATION", size=12, bold=True, space_before=2),
        Line(f"PCN reference: {reference}", space_before=14),
        Line("Date of issue: 2026-09-01"),
        Line(f"Notification type: {kind}"),
    ]


def _heading(text: str) -> Line:
    return Line(text, size=11, bold=True, space_before=16)


FULL = Document(
    slug="PCN-2026-114",
    lines=(
        *_banner(),
        *_letterhead("AMS-PCN-2026-114", "product discontinuance (end of life)"),
        Line("Customer response requested by: 2026-11-30"),
        _heading("1. Affected product"),
        Line("Affected part: AMS1117-3.3 (SOT-223)", space_before=4),
        Line("Description: 1 A low dropout linear regulator, fixed 3.3 V output"),
        Line("Ordering codes affected: AMS1117-3.3, AMS1117-3.3 tape and reel"),
        _heading("2. Key dates"),
        Line("Last time buy: 2027-03-31", space_before=4),
        Line("Last time ship: 2027-09-30"),
        Line("Orders placed after the last time buy date cannot be accepted. Last time buy"),
        Line("orders are non-cancellable and non-returnable."),
        _heading("3. Reason for the change"),
        Line("Closure of the wafer fabrication line that supplies this device. No", space_before=4),
        Line("equivalent capacity is available at the remaining sites."),
        _heading("4. Recommended replacement"),
        Line("Recommended replacement: NCP1117ST33T3G.", space_before=4),
        Line("The recommended part is a fixed 3.3 V low dropout linear regulator in the same"),
        Line("SOT-223 outline. This recommendation is made on the part alone. Customers"),
        Line("remain responsible for qualifying it in their own application, and this notice"),
        Line("does not qualify any board."),
        _heading("5. Response"),
        Line("Direct questions and last time buy orders to your usual sales contact.", space_before=4),
        Line(FOOTER, size=9, space_before=26),
    ),
    stated={
        "mpn": ("AMS1117-3.3", "Affected part: AMS1117-3.3 (SOT-223)"),
        "effective_date": ("2027-03-31", "Last time buy: 2027-03-31"),
        "replacement_mpn": ("NCP1117ST33T3G", "Recommended replacement: NCP1117ST33T3G."),
    },
    withheld=frozenset(),
)
"""Every declared field is stated, and two decoy dates sit between them.

The issue date and the response-by date are both real dates on real lines, so a reader
that quotes its source is still free to quote the wrong one. That is the point: the
verification catches invention, and only the instruction catches confusion.
"""

PRELIMINARY = Document(
    slug="PCN-2026-118",
    lines=(
        *_banner(),
        *_letterhead("AMS-PCN-2026-118", "product discontinuance (end of life), preliminary"),
        _heading("1. Affected product"),
        Line("Affected part: AMS1117-3.3 (SOT-223)", space_before=4),
        Line("Description: 1 A low dropout linear regulator, fixed 3.3 V output"),
        _heading("2. Key dates"),
        Line("Last time buy: to be advised.", space_before=4),
        Line("A follow-up notification will set the last time buy and last time ship dates"),
        Line("once the fabrication schedule is fixed. No orders are refused before then."),
        _heading("3. Reason for the change"),
        Line("Closure of the wafer fabrication line that supplies this device.", space_before=4),
        _heading("4. Recommended replacement"),
        Line("Recommended replacement: none.", space_before=4),
        Line("Advanced Monolithic Systems does not identify a drop-in replacement for this"),
        Line("device and makes no recommendation. Customers should select and qualify a"),
        Line("replacement for their own application."),
        _heading("5. Response"),
        Line("Direct questions to your usual sales contact.", space_before=4),
        Line(FOOTER, size=9, space_before=26),
    ),
    stated={"mpn": ("AMS1117-3.3", "Affected part: AMS1117-3.3 (SOT-223)")},
    withheld=frozenset({"effective_date", "replacement_mpn"}),
)
"""The harder document. It withholds the two fields a reader is most tempted to fill.

There is a date on the page and a word after "Recommended replacement", and neither is
the answer. A reader that reports 2026-09-01 and a part called "none" would pass every
verification this system has, because both are quoted from lines that genuinely exist.
"""

DOCUMENTS = (FULL, PRELIMINARY)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for doc in DOCUMENTS:
        doc.path.write_bytes(doc.pdf())
        print(f"wrote {doc.path} ({doc.path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
