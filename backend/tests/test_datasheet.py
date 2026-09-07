"""Datasheet-only θJA extraction stays evidence-bound and offline."""

from __future__ import annotations

import asyncio

import pytest

from continuity.parts import datasheet


TPS54331_THERMAL = """6.4 Thermal Information
THERMAL METRIC(1) D DDA
UNIT
8 PINS 8 PINS
RθJA Junction-to-ambient thermal resistance 116.3 48.7
°C/W
RθJC(top) Junction-to-case (top) thermal resistance 53.7 52.4
RθJB Junction-to-board thermal resistance 57.1 25.5
ψJT Junction-to-top characterization parameter 12.9 8.4
ψJB Junction-to-board characterization parameter 56.5 25.2
RθJC(bot) Junction-to-case (bottom) thermal resistance — 2.3"""

THETA_LINE = "RθJA Junction-to-ambient thermal resistance 116.3 48.7"
JC_LINE = "RθJC(top) Junction-to-case (top) thermal resistance 53.7 52.4"

LD1117_REV_38 = """DocID2572 Rev 38
Symbol Parameter SOT-223 SO-8 DPAK TO-220 Unit
RthJA Thermal resistance junction-ambient 110 55 100 50 °C/W"""
LD1117_REV_38_LINE = "RthJA Thermal resistance junction-ambient 110 55 100 50 °C/W"
LD1117_REV_26 = """DocID2572 Rev 26
Symbol Parameter SOT-223 SO-8 DPAK TO-220 Unit
RthJA Thermal resistance junction-ambient 50 °C/W"""
TLV1117_THERMAL = """THERMAL METRIC TLV1117LV DCY (SOT-223) 4 PINS UNIT
RθJA Junction-to-ambient thermal resistance 62.9 °C/W"""
TLV1117_LINE = "RθJA Junction-to-ambient thermal resistance 62.9 °C/W"


def _column_claim(
    theta_ja, columns, column_index, source_line, *, mounting=None, revision=None
):
    """Express a model table reading so each binding test changes only its claim."""
    return {
        "theta_ja": theta_ja,
        "source_line": source_line,
        "columns": columns,
        "column_index": column_index,
        "mounting": mounting,
        "revision": revision,
    }


def test_rev_38_binds_the_shared_row_to_the_requested_sot_223_column():
    fact = datasheet._fact_from_reply(
        _column_claim(
            110,
            ["SOT-223", "SO-8", "DPAK", "TO-220"],
            0,
            LD1117_REV_38_LINE,
            mounting="ST Table 2",
            revision="DocID2572 Rev 38",
        ),
        LD1117_REV_38,
        "SOT-223",
    )

    assert fact == datasheet.ThermalFact(
        110.0, LD1117_REV_38_LINE, "SOT-223", "ST Table 2", "DocID2572 Rev 38"
    )


def test_rev_38_binds_the_same_row_to_to_220_when_that_is_the_part_package():
    fact = datasheet._fact_from_reply(
        _column_claim(
            50, ["SOT-223", "SO-8", "DPAK", "TO-220"], 3, LD1117_REV_38_LINE
        ),
        LD1117_REV_38,
        "TO-220",
    )

    assert fact is not None
    assert (fact.theta_ja, fact.package_column) == (50.0, "TO-220")


def test_rev_26_declines_one_value_claimed_against_four_columns():
    assert datasheet._fact_from_reply(
        _column_claim(50, ["SOT-223", "SO-8", "DPAK", "TO-220"], 3, LD1117_REV_26.splitlines()[-1]),
        LD1117_REV_26,
        "TO-220",
    ) is None


def test_single_column_ti_table_uses_the_parenthetical_package_alias():
    fact = datasheet._fact_from_reply(
        _column_claim(62.9, ["DCY (SOT-223) 4 PINS"], 0, TLV1117_LINE),
        TLV1117_THERMAL,
        "SOT-223",
    )

    assert fact is not None
    assert (fact.theta_ja, fact.package_column) == (62.9, "DCY (SOT-223) 4 PINS")


def test_value_from_another_column_is_rejected_even_when_the_row_is_real():
    assert datasheet._fact_from_reply(
        _column_claim(55, ["SOT-223", "SO-8", "DPAK", "TO-220"], 0, LD1117_REV_38_LINE),
        LD1117_REV_38,
        "SOT-223",
    ) is None


def test_fabricated_column_header_is_rejected_even_when_its_number_is_real():
    assert datasheet._fact_from_reply(
        _column_claim(110, ["INVENTED", "SO-8", "DPAK", "TO-220"], 0, LD1117_REV_38_LINE),
        LD1117_REV_38,
        "SOT-223",
    ) is None


def test_cache_keeps_different_documents_for_one_mpn_separate(monkeypatch, tmp_path):
    """A corrected revision must not inherit the first document's SOT-223 figure."""
    monkeypatch.setattr(datasheet, "CACHE_DIR", tmp_path)
    old = datasheet.ThermalFact(50.0, LD1117_REV_26.splitlines()[-1], "TO-220")
    current = datasheet.ThermalFact(110.0, LD1117_REV_38_LINE, "SOT-223")

    datasheet._save("LD1117S33TR", LD1117_REV_26, old)
    datasheet._save("LD1117S33TR", LD1117_REV_38, current)

    assert datasheet._load(LD1117_REV_26) == old
    assert datasheet._load(LD1117_REV_38) == current


def _extract(monkeypatch, reply):
    monkeypatch.setattr(datasheet.llm, "available", lambda: True)

    async def complete_json(*_args):
        return reply

    monkeypatch.setattr(datasheet.llm, "complete_json", complete_json)
    return asyncio.run(
        datasheet.theta_ja_from_text(
            TPS54331_THERMAL, mpn="TPS54331DR", package="SOIC-8"
        )
    )


def test_extracts_plain_soic_column_and_keeps_its_real_source_line(monkeypatch, tmp_path):
    monkeypatch.setattr(datasheet, "CACHE_DIR", tmp_path)

    fact = _extract(
        monkeypatch,
        {
            "theta_ja": 116.3,
            "source_line": THETA_LINE,
            "columns": ["D", "DDA"],
            "column_index": 0,
        },
    )

    # TI prints its package *suffixes* here, not package names, so the binding cannot be
    # checked against "SOIC-8" — the column is recorded verbatim for a reader instead.
    assert fact == datasheet.ThermalFact(116.3, THETA_LINE, "D")


def test_a_wrong_column_is_now_refused_rather_than_left_for_review(monkeypatch, tmp_path):
    """This test used to assert the opposite, and inverting it is the point of the change.

    The row carries two values, 116.3 and 48.7. Every check that existed before passed for
    both of them: the quote is verbatim, the row names junction-to-ambient and not
    junction-to-case, and each value is inside the plausible range. So the extractor could
    return the second column's figure for the first column's part and nothing objected —
    which understates temperature rise, the direction that passes a board that cooks.

    Now the claim has to be internally consistent: the model says which columns it read and
    which one it took, and the value must be the one standing at that index.
    """
    monkeypatch.setattr(datasheet, "CACHE_DIR", tmp_path)

    fact = _extract(
        monkeypatch,
        {
            "theta_ja": 48.7,
            "source_line": THETA_LINE,
            "columns": ["D", "DDA"],
            "column_index": 0,
        },
    )

    assert fact is None


def test_invented_source_line_is_dropped(monkeypatch, tmp_path):
    monkeypatch.setattr(datasheet, "CACHE_DIR", tmp_path)

    assert _extract(
        monkeypatch,
        {
            "theta_ja": 116.3,
            "source_line": "invented row",
            "columns": ["D", "DDA"],
            "column_index": 0,
        },
    ) is None


@pytest.mark.parametrize("value", (0, -5, 4.9, 501, "116.3", True))
def test_out_of_band_or_mistyped_theta_ja_is_dropped(monkeypatch, tmp_path, value):
    monkeypatch.setattr(datasheet, "CACHE_DIR", tmp_path)

    assert _extract(monkeypatch, {"theta_ja": value, "source_line": THETA_LINE}) is None


def test_junction_to_case_row_is_dropped_even_when_its_value_is_in_range(monkeypatch, tmp_path):
    """RθJC is a dangerous distractor: 53.7 is plausible, so validation checks the metric too."""
    monkeypatch.setattr(datasheet, "CACHE_DIR", tmp_path)

    assert _extract(monkeypatch, {"theta_ja": 53.7, "source_line": JC_LINE}) is None


@pytest.mark.parametrize("body", (b"<html>blocked</html>", b"", b"%PDF-1.7\ntruncated"))
def test_text_from_pdf_returns_none_for_unparseable_content(body):
    assert datasheet.text_from_pdf(body) is None


@pytest.mark.parametrize("url", ("http://example.com/a.pdf", "file:///tmp/a.pdf", "https:///a.pdf"))
def test_fetch_rejects_unsafe_or_hostless_urls_without_a_request(monkeypatch, url):
    class UnexpectedClient:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("fetch attempted a request")

    monkeypatch.setattr(datasheet.httpx, "AsyncClient", UnexpectedClient)

    assert asyncio.run(datasheet.fetch(url)) is None


def test_without_an_llm_extraction_degrades_to_none(monkeypatch, tmp_path):
    monkeypatch.setattr(datasheet, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(datasheet.llm, "available", lambda: False)

    assert asyncio.run(
        datasheet.theta_ja_from_text(TPS54331_THERMAL, mpn="TPS54331DR", package="SOIC-8")
    ) is None


def test_cache_round_trips_and_prompt_change_invalidates_it(monkeypatch, tmp_path):
    monkeypatch.setattr(datasheet, "CACHE_DIR", tmp_path)
    fact = datasheet.ThermalFact(116.3, THETA_LINE, "SOIC-8")

    datasheet._save("TPS54331DR", TPS54331_THERMAL, fact)
    assert datasheet._load(TPS54331_THERMAL) == fact

    monkeypatch.setattr(datasheet, "SYSTEM", datasheet.SYSTEM + "\nchanged")
    assert datasheet._load(TPS54331_THERMAL) is None


def test_a_second_document_for_one_mpn_does_not_return_the_first_ones_answer(tmp_path, monkeypatch):
    """The live-demo hazard the cache rekey exists to remove.

    Keyed by MPN, uploading a corrected datasheet mid-run returned the figure read from
    the superseded one — and LD1117 is exactly two documents for one MPN, Rev 26 printing
    junction-to-ambient for TO-220 alone where Rev 38 prints all four columns.
    """
    monkeypatch.setattr(datasheet, "CACHE_DIR", tmp_path)
    first = datasheet.ThermalFact(50.0, "RthJA ... 50", "TO-220")

    datasheet._save("LD1117S33TR", LD1117_REV_26, first)

    assert datasheet._load(LD1117_REV_26) == first
    assert datasheet._load(LD1117_REV_38) is None


# ── notation and depth, measured against real vendor datasheets 11 Aug ─────────


@pytest.mark.parametrize(
    "line",
    [
        "RθJA Junction-to-ambient thermal resistance 116.3 48.7",
        "θJA Thermal resistance 45.2 °C/W",
        "Theta-JA junction to ambient 60",
        "Junction-to-ambient thermal resistance 88 °C/W",
    ],
)
def test_theta_ja_is_recognised_in_every_vendor_notation(line):
    """`RθJA` is TI house style; keying on it alone drops every other vendor."""
    assert datasheet._is_theta_ja_line(line)


@pytest.mark.parametrize(
    "line",
    [
        "RθJC(top) Junction-to-case (top) thermal resistance 53.7 52.4",
        "RθJB Junction-to-board thermal resistance 57.1 25.5",
        "ψJT Junction-to-top characterization parameter 12.9 8.4",
        "ψJB Junction-to-board characterization parameter 56.5 25.2",
    ],
)
def test_the_neighbouring_thermal_metrics_are_never_accepted(line):
    """These sit directly beneath θJA and are a fraction of it.

    Junction-to-case on the TPS54331 is 53.7 against θJA's 116.3, so mistaking one
    understates the temperature rise — the direction that passes a board which cooks.
    """
    assert not datasheet._is_theta_ja_line(line)


def test_the_prompt_window_keeps_the_thermal_region_of_a_long_document():
    filler = "application note prose. " * 2000
    text = filler + "\nRθJA Junction-to-ambient thermal resistance 116.3 48.7\n" + filler
    window = datasheet.thermal_window(text)

    assert len(window) <= datasheet.MAX_PROMPT_CHARS
    assert "RθJA Junction-to-ambient thermal resistance 116.3 48.7" in window


def test_a_short_document_is_passed_through_whole():
    text = "RθJA Junction-to-ambient thermal resistance 116.3 48.7"
    assert datasheet.thermal_window(text) == text


def test_a_long_document_with_no_thermal_keyword_is_truncated_not_dropped():
    text = "prose. " * 5000
    assert len(datasheet.thermal_window(text)) == datasheet.MAX_PROMPT_CHARS


def test_fetch_follows_redirects_within_a_bound(monkeypatch):
    """Espressif answers 301 on its own datasheet URL and 200 one hop later.

    Measured 11 Aug. Refusing to follow turned a working vendor into a silent `None`,
    and the PDF magic-number check is what actually guarantees the body is a document.
    """
    captured = {}

    class _Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        def stream(self, *_args, **_kwargs):
            raise AssertionError("not reached in this test")

    monkeypatch.setattr(datasheet.httpx, "AsyncClient", _Client)
    asyncio.run(datasheet.fetch("https://www.example.com/ds.pdf"))

    assert captured["follow_redirects"] is True
    assert captured["max_redirects"] == datasheet.MAX_REDIRECTS


def test_st_notation_is_recognised_exactly_as_st_prints_it():
    """`RthJA`, and "junction-ambient" with no "to".

    Both halves differ from TI's house style, and the recogniser matched only TI's until
    this was measured against the real file. A fixture written with the "to" inserted
    passes while the document ST actually publishes is refused outright — which is how a
    green suite can sit on top of an extractor that cannot read the one datasheet the work
    was done for.
    """
    assert datasheet._is_theta_ja_line(
        "RthJA Thermal resistance junction-ambient 110 55 100 50 °C/W"
    )
    # The row directly above it is a fraction of the value and must stay rejected.
    assert not datasheet._is_theta_ja_line(
        "RthJC Thermal resistance junction-case 15 20 8 5 °C/W"
    )


def test_onsemi_minus_sign_notation_is_recognised_in_both_directions():
    """onsemi typesets these with U+2212 MINUS SIGN, not a hyphen.

    Measured against the real NCP1117 datasheet. The negative direction is the one that
    matters: junction-to-case is 15 °C/W where junction-to-ambient is 160, so a dash class
    that misses `Junction−to−Case` lets the row above be read as the row wanted, which
    understates temperature rise.
    """
    assert datasheet._is_theta_ja_line(
        "Thermal Resistance, Junction\u2212to\u2212Ambient, Minimum Size Pad"
    )
    assert not datasheet._is_theta_ja_line("Thermal Resistance, Junction\u2212to\u2212Case")
