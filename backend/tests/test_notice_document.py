"""The constructed change notices, as documents.

Every notice test before this one fed the reader a few lines of typed text. A real PCN
is a page of letterhead with numbered sections, three dates that are not the one you
want, and a recommendation written by somebody who never saw your board. These tests run
against the actual PDFs the demonstration uses, extracted by the same `pypdf` path a real
attachment takes.

Two properties, which are the two halves of the build item. **Every field the reader
declares is stated in the document and survives extraction**, so a correct reading is
possible at all. And **the fields a document withholds come back absent**, rather than
filled from the issue date or from the word sitting where a part number would be.

The model itself is exercised under `CONTINUITY_LIVE=1`; offline the reading is stubbed
and the verification the module exists to do runs for real.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from continuity import notices
from tools.make_notice import DOCUMENTS, FULL, PRELIMINARY

LIVE = os.environ.get("CONTINUITY_LIVE") == "1"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def model(monkeypatch):
    """Stub the reading, keeping every check that stands between it and a Notice."""
    def answer_with(payload):
        async def complete(_system, _user, **_kwargs):
            return payload

        monkeypatch.setattr(notices.llm, "available", lambda: True)
        monkeypatch.setattr(notices.llm, "complete_json", complete)

    return answer_with


LINE_FOR = {
    "mpn": "mpn_line",
    "effective_date": "effective_date_line",
    "replacement_mpn": "replacement_line",
}
"""Which quoted-line field sources which value. The reader's schema, not ours."""


def reading_of(document, **overrides):
    """What a correct reading of a document says, assembled from what it states."""
    payload = {
        "mpn": None,
        "mpn_line": None,
        "manufacturer": "Advanced Monolithic Systems",
        "effective_date": None,
        "effective_date_line": None,
        "replacement_mpn": None,
        "replacement_line": None,
        "reason": "Closure of the wafer fabrication line that supplies this device.",
    }
    for field, (value, line) in document.stated.items():
        payload[field] = value
        payload[LINE_FOR[field]] = line
    payload.update(overrides)
    return payload


# ── the document ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda d: d.slug)
def test_the_document_says_it_is_a_constructed_example(document):
    """The label is the point of the item: this is not passed off as a real notice."""
    text = notices.text_of(document.pdf())

    assert text.splitlines()[0] == "CONSTRUCTED EXAMPLE. NOT A REAL MANUFACTURER NOTICE."
    assert "issued no" in text, "the disclaimer has to name what did not happen"
    assert text.rstrip().splitlines()[-1].startswith("CONSTRUCTED EXAMPLE."), (
        "a reader who starts at the signature must meet the label there too"
    )


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda d: d.slug)
def test_the_committed_pdf_is_the_one_the_generator_produces(document):
    """Otherwise the demo uploads one document and the suite tests another."""
    assert document.path.exists(), f"run tools/make_notice.py to write {document.path}"
    assert document.path.read_bytes() == document.pdf()


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda d: d.slug)
def test_every_line_survives_extraction(document):
    """The verification quotes lines, so a line mangled by the PDF is a line refused."""
    text = notices.text_of(document.path.read_bytes())

    for line in document.text().splitlines():
        assert line in text, f"{line!r} did not survive extraction"


@pytest.mark.parametrize("document", DOCUMENTS, ids=lambda d: d.slug)
def test_every_field_the_document_states_is_sourceable_from_it(document):
    """A field can only be read if a line of the document actually carries it."""
    text = notices.text_of(document.path.read_bytes())

    for field, (value, line) in document.stated.items():
        assert line in text, f"{field}: {line!r} is not in the document"
        assert value in line, f"{field}: {value!r} is not on the line quoted for it"


def test_the_withheld_fields_are_stated_by_no_line():
    """The preliminary notice is only a test if it genuinely lacks what it withholds."""
    text = notices.text_of(PRELIMINARY.path.read_bytes())

    assert "2027-" not in text, "a last-order date would defeat the withheld case"
    assert "NCP1117" not in text and "LD1117" not in text
    assert PRELIMINARY.withheld == {"effective_date", "replacement_mpn"}


# ── reading it ────────────────────────────────────────────────────────────────


def test_the_full_notice_reads_into_every_declared_field(model):
    """A correct reading of the real PDF passes every check on the way to a Notice."""
    model(reading_of(FULL))

    notice = run(notices.read(FULL.path.read_bytes()))

    assert notice is not None, "the constructed notice was refused"
    assert notice.mpn == "AMS1117-3.3"
    assert notice.mpn_line == "Affected part: AMS1117-3.3 (SOT-223)"
    assert notice.effective_date == "2027-03-31"
    assert notice.effective_date_line == "Last time buy: 2027-03-31"
    assert notice.replacement_mpn == "NCP1117ST33T3G"
    assert notice.replacement_line == "Recommended replacement: NCP1117ST33T3G."
    assert notice.manufacturer == "Advanced Monolithic Systems"
    assert notice.reason


def test_the_preliminary_notice_reads_without_what_it_withholds(model):
    """Two absent fields are not a failed reading. The part number is the notice."""
    model(reading_of(PRELIMINARY))

    notice = run(notices.read(PRELIMINARY.path.read_bytes()))

    assert notice is not None
    assert notice.mpn == "AMS1117-3.3"
    assert notice.effective_date is None
    assert notice.replacement_mpn is None


def test_the_word_where_a_part_number_belongs_is_not_a_part_number(model):
    """`Recommended replacement: none.` is a real line, quoted honestly, and a trap.

    It passes the shape test and it passes containment, because the notice really does
    print that word there. Believed, it opens a review of a part called "none" and
    searches every distributor for it.
    """
    model(
        reading_of(
            PRELIMINARY,
            replacement_mpn="none",
            replacement_line="Recommended replacement: none.",
        )
    )

    notice = run(notices.read(PRELIMINARY.path.read_bytes()))

    assert notice is not None, "an unusable recommendation must not lose the notice"
    assert notice.replacement_mpn is None
    assert notice.replacement_line is None


def test_a_replacement_the_quoted_line_does_not_print_is_refused(model):
    """The rule the affected part already lived under, extended to the recommendation.

    Quoting *a* line is not sourcing *this* value: without this the reply cites the real
    recommendation line and names a different part on it, and the change request then
    proposes a part the manufacturer never mentioned.
    """
    model(
        reading_of(
            FULL,
            replacement_mpn="LM317T",
            replacement_line="Recommended replacement: NCP1117ST33T3G.",
        )
    )

    notice = run(notices.read(FULL.path.read_bytes()))

    assert notice is not None
    assert notice.replacement_mpn is None, "a part the notice never printed was believed"


def test_a_date_the_document_does_not_carry_is_refused(model):
    """The decoys are real lines; an invented date is not."""
    model(reading_of(FULL, effective_date="2027-01-31",
                     effective_date_line="Last time buy: 2027-01-31"))

    notice = run(notices.read(FULL.path.read_bytes()))

    assert notice.effective_date is None
    assert notice.mpn == "AMS1117-3.3"


# ── and with a real model behind it ───────────────────────────────────────────


@pytest.mark.skipif(not LIVE, reason="set CONTINUITY_LIVE=1 to read with a real model")
def test_a_model_reads_every_declared_field_from_the_document():
    """The build item's own test, run against the model that will read it on the day."""
    notice = run(notices.read(FULL.path.read_bytes()))

    assert notice is not None, "the model could not read the constructed notice"
    assert notice.mpn == "AMS1117-3.3"
    assert notice.effective_date == "2027-03-31", (
        "the issue date, the response-by date and the last-ship date are all decoys"
    )
    assert notice.replacement_mpn == "NCP1117ST33T3G"
    assert notice.manufacturer and "monolithic" in notice.manufacturer.lower()
    assert notice.reason


@pytest.mark.skipif(not LIVE, reason="set CONTINUITY_LIVE=1 to read with a real model")
def test_a_model_reports_what_the_preliminary_notice_withholds():
    notice = run(notices.read(PRELIMINARY.path.read_bytes()))

    assert notice is not None
    assert notice.mpn == "AMS1117-3.3"
    assert notice.effective_date is None, "the issue date is not the last-order date"
    assert notice.replacement_mpn is None, '"none" is not a part number'
