"""Read a cited θJA measurement from a regulator datasheet.

Datasheet hosts are unreliable, and a package's θJA is not safely knowable from its
name.  This module therefore treats both downloading and extraction as best-effort
operations that return a fact only when its quoted source text can be checked.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

import httpx
from pypdf import PdfReader

from .. import env, llm
from ..engine import packages

log = logging.getLogger(__name__)

CACHE_DIR = env.cache_dir("datasheets")
MAX_PDF_BYTES = 12 * 1024 * 1024
FETCH_TIMEOUT_S = 10.0
MAX_REDIRECTS = 5

MAX_PDF_PAGES = 40
"""How deep to read before giving up on finding a thermal table.

TI puts *Thermal Information* in section 6.4 — page 5 of the TPS54331 — and 12 pages was
chosen from that one example. Measured 11 Aug against other vendors, 12 is too shallow:
neither NXP's UJA1075A nor Espressif's ESP32-WROOM states a thermal resistance anywhere in
its first 12 pages. Datasheet section order is a house style, not a standard.

Reading deeper costs nothing but local CPU. What it must not do is put forty pages of
application notes in front of the model, which is what `thermal_window` is for.
"""

MAX_PROMPT_CHARS = 6000
"""Above this, only the region around a thermal keyword is sent."""


@dataclass(frozen=True)
class ThermalFact:
    """A θJA figure and the checked claim that binds it to one table column.

    `package_column` is deliberately the document's spelling rather than the package the
    caller requested. The distinction is evidence: it records which printed column was
    verified, including vendor wording such as ``DCY (SOT-223) 4 PINS``.
    """

    theta_ja: float
    source_line: str
    package_column: str
    mounting: str | None = None
    revision: str | None = None


SYSTEM = """You extract one thermal measurement from supplied datasheet text.

Return ONE JSON object with ONLY these keys: theta_ja, source_line, columns, column_index,
mounting, revision.

Rules:
- theta_ja is junction-to-ambient thermal resistance RθJA, in °C/W, as a number with
  no unit suffix. source_line is the exact full datasheet line from which it was read.
- columns lists every value column in that table, left to right, verbatim as printed.
  column_index is the zero-based index of the column containing theta_ja. For a
  single-column table, return its one column and 0.
- mounting is the measurement condition verbatim, or null if the document does not say.
  revision is the printed document revision verbatim, or null if it is not printed.
- The part MPN and package are supplied. A thermal table may have several package
  columns, sometimes with the same pin count. Select only the column that matches the
  supplied package. Return null for both fields if the matching column is unclear.
- RθJC, RθJB, ψJT and ψJB are NOT θJA and must never be returned.
- MEASUREMENTS must be READ from the datasheet text. Use null when it does not state
  one. Never guess, never infer a typical value, never copy a number from a similar
  part you know. This applies without exception.

Return the JSON object and nothing else."""


def text_from_pdf(data: bytes) -> str | None:
    """Extract at most the opening datasheet pages, or return no text on any failure."""
    if not data or len(data) > MAX_PDF_BYTES or not data.startswith(b"%PDF-"):
        return None
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages[:MAX_PDF_PAGES])
    except Exception as error:  # malformed PDFs are an ordinary missing fact
        log.debug("could not read PDF text: %s", error)
        return None


def _prompt(text: str, mpn: str, package: str) -> str:
    return json.dumps(
        {"mpn": mpn, "package": package, "datasheet_text": text},
        ensure_ascii=False,
        indent=1,
    )


def _collapsed(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


_THETA_JA_NAMES = re.compile(
    r"\bR?\s*(?:θ|Θ|THETA)\s*[-_]?\s*JA\b"
    r"|\bR\s*th\s*[-_]?\s*JA\b"
    r"|junction[\s\-–—−]*(?:to[\s\-–—−]*)?ambient",
    re.IGNORECASE,
)
"""Both halves of this were extended after being measured against real documents.

The dash class carries `−` U+2212 MINUS SIGN as well as hyphen and en-dash, because
onsemi typesets `Junction−to−Ambient` with it. That matters most in the *negative*
pattern: without it `Junction−to−Case` is not recognised as the row to avoid, and
junction-to-case is a fraction of junction-to-ambient — 15 against 160 on the NCP1117.

`RθJA` is Texas Instruments house style and was all this matched. **ST writes `RthJA`** —
a Latin `th` rather than the symbol — **and prints the parameter as "junction-ambient"
with no "to"**, so LD1117's thermal table failed both alternatives and the whole document
was refused. That is the one datasheet this extractor was rebuilt to read correctly, and a
test fixture that quietly inserted the missing "to" passed while the real file did not.

The optional `to` and the `Rth` spelling are therefore load-bearing, not tidying.
"""

_OTHER_METRICS = re.compile(
    r"junction[\s\-–—−]*(?:to[\s\-–—−]*)?(?:case|board|top)"
    r"|\bR?\s*(?:θ|Θ|THETA)\s*[-_]?\s*J[CB]\b"
    r"|\bR\s*th\s*[-_]?\s*J[CB]\b"
    r"|[ψΨ]\s*J[TB]\b",
    re.IGNORECASE,
)
"""Widened in step with the positive pattern, and it has to be.

`RthJC` sits directly above `RthJA` in ST's table and junction-to-case is a fraction of
junction-to-ambient — 15 against 110 on the LD1117. Loosening the positive match without
loosening this one would let the row above be read as the row wanted, understating the
temperature rise, which is the direction that passes a board that cooks.
"""

_NUMERIC_VALUE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?")
"""Decimal table entries, excluding digits embedded in package or metric names."""


def thermal_window(text: str) -> str:
    """The region of a datasheet worth putting in front of the model.

    A forty-page document is mostly application notes, and burying one table in them
    costs tokens and dilutes attention. When the text is long, keep only what surrounds a
    thermal keyword.
    """
    if len(text) <= MAX_PROMPT_CHARS:
        return text
    hits = [match.start() for match in _THETA_JA_NAMES.finditer(text)]
    if not hits:
        return text[:MAX_PROMPT_CHARS]
    half = MAX_PROMPT_CHARS // 2
    start = max(0, hits[0] - half)
    return text[start : start + MAX_PROMPT_CHARS]


def _is_theta_ja_line(source_line: str) -> bool:
    """Require the cited row to identify junction-to-ambient, and nothing else.

    `RθJA` is Texas Instruments house style. Other vendors write `θJA`, `Theta-JA`, or
    spell out "junction-to-ambient thermal resistance" with no symbol at all, so keying
    on TI's exact spelling silently drops every one of them.

    The negative check carries the safety. `RθJC`, `RθJB`, `ψJT` and `ψJB` sit directly
    beneath θJA in the same table and are a *fraction* of it — junction-to-case on the
    TPS54331 is 53.7 against 116.3 — so mistaking one understates the temperature rise,
    which is the direction that passes a board that cooks.
    """
    if _OTHER_METRICS.search(source_line):
        return False
    return bool(_THETA_JA_NAMES.search(source_line))


def _fact_from_reply(
    reply: Mapping[str, Any], text: str, package: str
) -> ThermalFact | None:
    value = reply.get("theta_ja")
    source_line = reply.get("source_line")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not 5 <= value <= 500 or not isinstance(source_line, str) or not source_line.strip():
        return None
    if not _is_theta_ja_line(source_line):
        return None
    if _collapsed(source_line) not in _collapsed(text):
        return None
    columns = reply.get("columns")
    column_index = reply.get("column_index")
    mounting = reply.get("mounting")
    revision = reply.get("revision")
    if (
        not isinstance(columns, list)
        or not columns
        or any(not isinstance(column, str) or not column.strip() for column in columns)
        or isinstance(column_index, bool)
        or not isinstance(column_index, int)
        or not 0 <= column_index < len(columns)
        or mounting is not None and (not isinstance(mounting, str) or not mounting.strip())
        or revision is not None and (not isinstance(revision, str) or not revision.strip())
    ):
        return None

    # A row's numbers are the only arithmetic we can safely check without pretending to
    # understand each vendor's layout. Rev 26's one value beneath four printed columns
    # fails here, rather than being silently assigned to the column a model prefers.
    values = [float(match.group()) for match in _NUMERIC_VALUE.finditer(source_line)]
    if len(values) != len(columns) or values[column_index] != float(value):
        return None
    # The package check only applies where a header actually names a package. ST prints
    # `SOT-223 SO-8 DPAK TO-220` and we can and must verify the choice against it. TI's
    # TPS54331 prints its package *suffixes*, `D` and `DDA`, which share no text with the
    # distributor's `SOIC-8` — demanding an overlap there would reject a large part of one
    # vendor's catalogue for being tersely typeset.
    #
    # So: if any column in the set is recognisably a package, the chosen one has to be the
    # right package. If none of them are, the binding cannot be verified from the text and
    # the column is recorded verbatim instead, where a reader can check it.
    if any(_names_a_package(column) for column in columns):
        if not _packages_overlap(columns[column_index], package):
            return None
    if any(_collapsed(column) not in _collapsed(text) for column in columns):
        return None
    return ThermalFact(
        float(value),
        source_line.strip(),
        columns[column_index].strip(),
        mounting.strip() if isinstance(mounting, str) else None,
        revision.strip() if isinstance(revision, str) else None,
    )


def _names_a_package(column: str) -> bool:
    """Whether a printed column heading contains something the package tables recognise."""
    return any(packages.theta_ja(token) is not None or packages.body_mm(token) is not None
               for token in re.findall(r"[A-Za-z0-9\-]+", column))


def _packages_overlap(column: str, package: str) -> bool:
    """Whether the printed column and distributor package share a folded package token.

    This deliberately delegates spelling folding to ``engine.packages`` rather than
    growing a second package normaliser here. A TI heading can contain ``DCY (SOT-223)
    4 PINS`` while the catalogue says merely ``SOT-223``; their candidate-key sets meet
    at ``SOT223``. An empty intersection declines, because selecting a nearby column is
    exactly the unsafe substitution this extractor exists to prevent.
    """
    return bool(set(packages._candidate_keys(column)) & set(packages._candidate_keys(package)))


async def theta_ja_from_text(text: str, *, mpn: str, package: str) -> ThermalFact | None:
    """Extract and evidence-check one θJA figure for an MPN/package pair."""
    cached = _load(text)
    if cached is not None:
        return cached
    if not llm.available():
        log.debug("θJA extraction skipped for %s: no LLM configured", mpn)
        return None
    try:
        reply = await llm.complete_json(SYSTEM, _prompt(thermal_window(text), mpn, package))
    except (llm.LLMUnavailable, ValueError, json.JSONDecodeError) as error:
        log.debug("θJA extraction failed for %s: %s", mpn, error)
        return None
    fact = _fact_from_reply(reply, text, package)
    if fact is not None:
        _save(mpn, text, fact)
    return fact


async def fetch(url: str) -> bytes | None:
    """Fetch one bounded HTTPS PDF, returning no data for ordinary host failures."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        log.debug("datasheet URL rejected: %r", url)
        return None
    try:
        # Redirects are followed, and bounded. Measured 11 Aug: Espressif answers 301 on
        # its own datasheet URL and 200 `application/pdf` one hop later, so refusing to
        # follow drops a vendor whose parts are on real boards here. The final body still
        # has to begin with a PDF magic number, which is what actually guarantees this is
        # a document rather than a login wall.
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT_S, follow_redirects=True, max_redirects=MAX_REDIRECTS
        ) as http:
            async with http.stream("GET", url) as response:
                if response.status_code < 200 or response.status_code >= 300:
                    log.debug("datasheet fetch returned HTTP %s: %s", response.status_code, url)
                    return None
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                # Only markup is rejected outright — that is the shape of the interstitial
                # `datasheet.lcsc.com` serves instead of a PDF, and it can be large. Every
                # other content type is left to the magic-number check, because a host
                # labelling a PDF `application/octet-stream` is still serving a PDF.
                if content_type.startswith("text/"):
                    log.debug("datasheet fetch returned markup, not a PDF: %s", url)
                    return None
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_PDF_BYTES:
                        log.debug("datasheet PDF exceeded size limit: %s", url)
                        return None
                    chunks.append(chunk)
    except Exception as error:  # DNS, TLS, timeout, malformed response: all expected sometimes
        log.debug("datasheet fetch failed for %s: %s", url, error)
        return None

    data = b"".join(chunks)
    if not data.startswith(b"%PDF-"):
        log.debug("datasheet body lacked PDF magic number: %s", url)
        return None
    return data


# ── cache ─────────────────────────────────────────────────────────────────────


def _cache_path(text: str) -> Path:
    """A cache location for one document's extracted text, not for one part number.

    A manufacturer can correct a datasheet while retaining its MPN. Hashing the text is
    therefore the identity available to this layer: callers with PDF bytes extract text
    before calling us, and using that text keeps Rev 26 and Rev 38 separate without a
    second PDF parser or a stale MPN-level answer.
    """
    return CACHE_DIR / f"{_document_hash(text)}.json"


def _document_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _prompt_version() -> str:
    return hashlib.sha256(SYSTEM.encode()).hexdigest()[:12]


def _load(text: str) -> ThermalFact | None:
    return _load_by_hash(_document_hash(text))


def _load_by_hash(document_hash: str) -> ThermalFact | None:
    path = CACHE_DIR / f"{document_hash}.json"
    if not path.exists():
        return None
    try:
        stored = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if stored.get("prompt") != _prompt_version():
        return None
    value = stored.get("theta_ja")
    source_line = stored.get("source_line")
    package_column = stored.get("package_column")
    mounting = stored.get("mounting")
    revision = stored.get("revision")
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 5 <= value <= 500
        or not isinstance(source_line, str)
        or not isinstance(package_column, str)
        or mounting is not None and not isinstance(mounting, str)
        or revision is not None and not isinstance(revision, str)
    ):
        return None
    return ThermalFact(float(value), source_line, package_column, mounting, revision)


def _pointer_path(mpn: str) -> Path:
    return CACHE_DIR / "by-mpn" / f"{re.sub(r'[^A-Za-z0-9._-]', '_', mpn)}.json"


def latest_for_mpn(mpn: str) -> ThermalFact | None:
    """The most recently extracted fact for a part, whatever document produced it.

    Two questions are being asked of this cache and only one of them is about a document.
    Keying by document identity answers *"is this fact from this datasheet"*, which is what
    keeps Rev 26 and Rev 38 apart. It cannot answer *"do we already have a figure for this
    part"*, which is what a caller holding only an MPN needs before deciding whether to
    spend a PDF fetch — and rekeying without providing it silently detached every stored
    θJA from the part it belonged to.

    The pointer is overwritten on every save, so a corrected datasheet supersedes the one
    before it rather than losing to a cached answer.
    """
    pointer = _pointer_path(mpn)
    if not pointer.exists():
        return None
    try:
        document = json.loads(pointer.read_text()).get("document")
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(document, str):
        return None
    return _load_by_hash(document)


def _save(mpn: str, text: str, fact: ThermalFact) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _pointer_path(mpn).parent.mkdir(parents=True, exist_ok=True)
    _pointer_path(mpn).write_text(json.dumps({"document": _document_hash(text)}, indent=1))
    _cache_path(text).write_text(
        json.dumps(
            {
                "mpn": mpn,
                "prompt": _prompt_version(),
                "theta_ja": fact.theta_ja,
                "source_line": fact.source_line,
                "package_column": fact.package_column,
                "mounting": fact.mounting,
                "revision": fact.revision,
            },
            indent=1,
        )
    )
