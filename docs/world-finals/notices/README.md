# The change notices

Two constructed product change notices, and the generator that writes them.

**These are not real manufacturer notices.** Advanced Monolithic Systems has issued no
notice of this kind. The reference numbers, the dates and the response instructions were
invented for the demonstration, and both documents say so on their first line and their
last. The part numbers are real, because a notice naming invented parts would exercise
none of the sourcing this system exists to do.

| File | What it is |
| --- | --- |
| `PCN-2026-114.pdf` | The full notice. Retires AMS1117-3.3, recommends NCP1117ST33T3G, gives a last time buy of 2027-03-31. This is the document the demonstration uploads. |
| `PCN-2026-118.pdf` | The preliminary notice. Same part, no last-order date and no recommendation, in the way a real early notice arrives. |

Both are written by `backend/tools/make_notice.py`, which holds the text, and
`backend/tools/pdf.py`, which is a very small PDF writer added so the project can produce
one without taking a dependency. Regenerate them with:

    cd backend && PYTHONPATH=. python tools/make_notice.py

`tests/test_notice_document.py` asserts the committed files are byte-identical to what the
generator produces, so a document edited and not regenerated fails the suite rather than
quietly leaving the demonstration on an older file.

## What the documents are for

`PCN-2026-114` is the reader's positive case, and it is deliberately awkward. Four dates
are on the page and only one of them ends ordering: the issue date, a customer response
date, a last time buy and a last time ship. A reader that quotes its source is still free
to quote the wrong one, which is exactly what happened. Against the real model the reader
returned **2027-09-30, the last time ship date**, sourced honestly from a real line, and a
review would have run on six months of runway the notice does not give. The reading
instruction in `continuity/notices.py` now names which date is wanted and which are not,
and the live test in `tests/test_notice_document.py` holds it.

`PCN-2026-118` is the harder one. It withholds the two fields a reader is most tempted to
fill, and it leaves plausible material in both places: an issue date on the page, and the
word `none` sitting where the part number would be. Both would have passed every check the
system had, because both are quoted from lines that genuinely exist. A part number is now
refused when it is a word a notice uses for absence, and a recommended part is refused
unless the line quoted for it actually prints it.
