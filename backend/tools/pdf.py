"""The smallest PDF writer that still produces a document a text extractor reads.

Continuity *reads* PDFs everywhere and had no way to write one, so the only change
notice it had ever been fed was a few lines of plain text. That proves nothing about
the reader that will meet a real attachment: a PCN arrives as a PDF, and the whole
verification chain runs against whatever `pypdf` recovers from it, not against the
sentences somebody typed into a fixture.

Rather than take a dependency to produce two demo documents, this emits the file by
hand: one page, Helvetica in two weights, every line absolutely positioned with `Tm`.
Absolute positioning rather than `T*` leading because it lets a heading take more space
above it than below, which is the difference between a page that reads as a notice and
one that reads as a list.

Deliberately not a general writer. No wrapping, no pagination, no images — a caller who
needs those wants a real library, and this file should not grow into one.
"""

from __future__ import annotations

from dataclasses import dataclass

REGULAR = "F1"
BOLD = "F2"

PAGE_WIDTH = 612.0
PAGE_HEIGHT = 792.0


@dataclass(frozen=True)
class Line:
    """One typeset line, and the space left above it."""

    text: str
    size: float = 10.5
    bold: bool = False
    space_before: float = 0.0


def _escaped(text: str) -> str:
    """`(`, `)` and `\\` end or continue a literal string, so they cannot ride raw."""
    out = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    return out


def _encoded(text: str) -> bytes:
    """WinAnsi, which is what the font resource below declares.

    Degrees, en-dashes and typographic quotes all live in cp1252; anything outside it
    would be a silent mojibake in a document whose entire purpose is to be read back
    exactly, so it fails loudly instead.
    """
    return text.encode("cp1252")


def document(lines: list[Line], *, top: float = 756.0, left: float = 56.0,
             leading: float = 15.0) -> bytes:
    """One page of text as a PDF file."""
    body: list[bytes] = []
    y = top
    for line in lines:
        y -= line.space_before + leading
        if not line.text:
            continue
        font = BOLD if line.bold else REGULAR
        body.append(
            _encoded(f"BT /{font} {line.size:g} Tf 1 0 0 1 {left:g} {y:.1f} Tm ")
            + b"(" + _encoded(_escaped(line.text)) + b") Tj ET"
        )
    stream = b"\n".join(body)

    font = (
        b"<< /Type /Font /Subtype /Type1 /Encoding /WinAnsiEncoding /BaseFont /%s >>"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>"
        % (int(PAGE_WIDTH), int(PAGE_HEIGHT)),
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        font % b"Helvetica",
        font % b"Helvetica-Bold",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n".encode()
        + b"%%EOF\n"
    )
    return bytes(out)


def simple(lines: list[str]) -> bytes:
    """Plain lines, one size, no headings — the shape the tests were already using."""
    return document([Line(text) for text in lines])
