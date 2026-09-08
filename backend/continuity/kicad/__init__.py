"""KiCad, as the source of two facts nothing else in this system can produce.

A **bill of materials** that came out of the design rather than off a spreadsheet, and the
**footprint consequence** of a substitution: which connections a different package breaks on
this particular board. Both are computed by KiCad itself and read back here, which is the
same division the engine lives under — the tool that owns the question answers it.

Nothing in this package is required. Without a configured KiCad every entry point reports
the capability as unavailable, and the rest of the product is unaffected.
"""

from .runner import Unavailable, available, configured, require  # noqa: F401
