"""The six rules. Written by hand, never generated — physics does not vary by line.

R1–R5 are electrical. R6 is sourcing, and it flows through the identical resolution
loop, which is the architectural claim: one loop handling a sold-out part and an
overheating regulator the same way.

Every rule is a pure function `Board -> list[Verdict]`. No I/O, no LLM, no clock. A
rule may only compare fields that were fetched, and every verdict it returns carries
the field name, its verbatim value and where that value came from.

A rule that *cannot* evaluate says `evidence_missing` and names the missing field. It never skips
quietly and it never substitutes a default — an unchecked constraint reported as a
satisfied result is the one failure mode that would make the whole engine untrustworthy.
"""

from __future__ import annotations

from . import draw as rail_current
from . import efficiency
from . import format as fmt
from . import buses
from . import packages
from .models import (
    AMBIENT_DEFAULT_SOURCE,
    ASSUMED_EFFICIENCY,
    ASSUMED_EFFICIENCY_SOURCE,
    DOSSIER_SOURCE,
    Board,
    Evidence,
    PartSpec,
    Rail,
    Verdict,
)

# thresholds — every one of these is an advisory band, not a physical limit
DERATING_THRESHOLD = 0.80
"""Warn once a rail draws this fraction of its regulator's rating."""

THERMAL_RISE_WARN_C = 60.0
"""Warn on this much junction rise even when the absolute limit is met."""

BOARD_SUBJECT = "board"
"""Subject for verdicts that belong to the whole board rather than to any component.

Deliberately not a slot id. A rule with nothing to blame must not blame the first part
it finds — see `not_applicable`, which is what a rule returns when it had nothing to look
at on this board.
"""

MAX_EVIDENCE_ROWS = 4
"""Beyond this the drawer stops being readable."""


def _not_applicable(rule: str, board: Board, detail: str) -> Verdict:
    """Make an absent rule subject visible without pretending its constraint held.

    A rule whose operand is not present did not pass and did not lack evidence; it simply
    had nothing to evaluate.

    `BOARD_SUBJECT` rather than a slot, and the distinction is not cosmetic: this took
    `next(iter(board.slots))` at first, which is a real component, so "this board has no
    buses to check" arrived attributed to whichever part was placed first and appeared in
    that part's caption. Nothing on a board is at fault for a rule having no subject.
    """
    return Verdict(
        rule=rule, status="not_applicable", detail=detail, subject=BOARD_SUBJECT, scope="board"
    )

def efficiency_evidence(
    part: PartSpec, subject: str, band: tuple[float, float] | None
) -> tuple[Evidence, ...]:
    """One row saying whether efficiency came from the payload or an engine band."""
    if part.efficiency is not None:
        return part.cite(subject, "efficiency")
    if band is None:
        return ()
    low, high = band
    return (
        Evidence(
            subject,
            "efficiency (bounded)",
            f"{fmt.percent(low)}–{fmt.percent(high)}",
            f"{efficiency.BAND_SOURCE}, {efficiency.band_label(part)}",
        ),
    )


def _supply_evidence(rail: Rail, subject: str, *, current: bool = False) -> tuple[Evidence, ...]:
    """Cite where a rail's own numbers came from, when the rail is the operand.

    Silent for a rail fed by a regulator: its voltage comes from that part's datasheet
    and the verdict already quotes it. Only the board input rail carries a `basis`,
    because only its numbers come from outside the parts list — a published standard,
    or the user's own sentence. Those are not equally trustworthy and the screen should
    not present them as if they were.
    """
    if not rail.basis:
        return ()
    value = fmt.milliamps(rail.i_limit) if current and rail.i_limit is not None else fmt.volts(rail.voltage)
    label = f"{rail.id} supply {'current' if current else 'voltage'}"
    return (Evidence(subject, label, value, rail.basis),)


def _load_evidence(rail: Rail, subject: str) -> tuple[Evidence, ...]:
    """Cite a rail load the design stated, so it can never read as a sum of parts.

    A declared load and a summed one are different claims and a verdict must not blur
    them. Summing cites each consumer's `i_peak` and inherits our own caveats about
    coincident peaks; a declared figure cites the document it came from and carries none
    of that, because none of it applies.
    """
    if rail.i_load is None:
        return ()
    return (
        Evidence(subject, f"{rail.id} load (declared)", fmt.milliamps(rail.i_load), rail.i_load_basis),
    )


CURRENT_BASIS_SOURCE = "no duty cycle is published by any distributor"
"""Why R5 sizes heat from peak current rather than an average.

A radio's 500 mA peak is a transmit burst, and a package heats on average power, so
the physically exact figure would be `peak × duty cycle`. No distributor publishes a
duty cycle, and inventing one would be precisely the unsourced inference this engine
exists to avoid. Peak is the conservative reading and it is the one we can actually
cite, so that is what R5 uses — and it says so on screen rather than implying a
duty-cycle model it does not have.
"""


# ── R1 · voltage_overlap ──────────────────────────────────────────────────────


def voltage_overlap(board: Board) -> list[Verdict]:
    """Every part on a rail must tolerate it, and whatever sources a rail must make it.

    FAIL unless `part.vmin <= rail.voltage <= part.vmax` for each member, and unless the
    rail's source can actually be set to `rail.voltage`.
    """
    verdicts: list[Verdict] = []
    for rail in board.rails.values():
        for slot_id in rail.members:
            part = board.part(slot_id)
            if part is None:
                continue
            verdicts.append(_check_one_supply(board, rail, slot_id, part))

        if rail.source and board.placed(rail.source):
            verdicts.append(
                _check_source(board, rail, rail.source, board.part(rail.source))  # type: ignore[arg-type]
            )
    return verdicts


def _check_source(board: Board, rail: Rail, slot_id: str, part: PartSpec) -> Verdict:
    """Can the part feeding this rail actually produce it?

    Every regulator used to be checked only as a *load* — it is a member of the rail
    feeding it, and the source of the rail it makes, and only the first was examined. So
    nothing noticed an LDO asked to turn 3.0 V into 3.3 V, or a fixed 5 V buck declared
    as the source of a 3V3 rail. Two live battery boards shipped with `0 conflict`.
    """
    at = f"{rail.id} at {fmt.volts(rail.voltage)}"
    evidence = part.cite(slot_id, "vout_min", "vout_max")
    involved = (slot_id, *rail.members)

    def verdict(status: str, detail: str, extra: tuple[Evidence, ...] = ()) -> Verdict:
        return Verdict(
            rule="voltage_overlap",
            scope=rail.id,
            status=status,
            detail=detail,
            subject=slot_id,
            involved=involved,
            evidence=evidence + extra,
        )

    reaches = part.produces(rail.voltage)
    if reaches is None:
        return verdict(
            "evidence_missing",
            f"{part.mpn} states no output voltage — that it can supply {at} is unchecked.",
        )
    if reaches is False:
        return verdict("failed", f"{part.mpn} outputs {_output_span(part)}; {at} is outside that.")

    # A linear regulator burns the difference as heat, so it cannot produce more than it
    # is given. Only asserted when the part says it is linear: a switcher that states no
    # topology must not be failed for something we cannot show it does.
    if part.regulation == "linear":
        upstream = board.input_rail(slot_id)
        if upstream is not None and upstream.voltage <= rail.voltage:
            return verdict(
                "failed",
                f"{part.mpn} is a linear regulator and cannot step up — "
                f"{at} is above its {fmt.volts(upstream.voltage)} input.",
                _supply_evidence(upstream, slot_id),
            )

    return verdict("satisfied", f"{part.mpn} supplies {_output_span(part)}, covering {at}.")


def _output_span(part: PartSpec) -> str:
    if part.vout_min == part.vout_max:
        return fmt.volts(part.vout_min)  # type: ignore[arg-type]
    return f"{fmt.volts(part.vout_min)}–{fmt.volts(part.vout_max)}"  # type: ignore[arg-type]


def _check_one_supply(board: Board, rail: Rail, slot_id: str, part: PartSpec) -> Verdict:
    """Check what can be checked.

    Real distributor data is one-sided far more often than it is complete: a regulator
    listing `"Voltage - Supply": "15V"` has stated a maximum and no minimum. Demanding
    both before evaluating anything would report *unchecked* on a part sitting at twice
    its rated voltage — a definite failure, silently downgraded to a shrug.

    So each bound is judged on its own. Either one being violated fails regardless of
    the other; a bound that is satisfied while the other is unknown is evidence missing
    rather than a clean satisfied result.
    """
    involved = (slot_id, rail.source) if rail.source else (slot_id,)
    evidence = part.cite(slot_id, "vmin", "vmax") + _supply_evidence(rail, slot_id)
    at = f"{rail.id} at {fmt.volts(rail.voltage)}"

    def verdict(status: str, detail: str) -> Verdict:
        return Verdict(
            rule="voltage_overlap",
            scope=rail.id,
            status=status,
            detail=detail,
            subject=slot_id,
            involved=involved,
            evidence=evidence,
        )

    if part.vmax is not None and rail.voltage > part.vmax:
        return verdict(
            "failed",
            f"{part.mpn} is rated to {fmt.volts(part.vmax)} — {at} is above that.",
        )

    if part.vmin is not None and rail.voltage < part.vmin:
        return verdict(
            "failed",
            f"{part.mpn} needs at least {fmt.volts(part.vmin)} — {at} is below that.",
        )

    if part.vmin is not None and part.vmax is not None:
        span = f"{fmt.volts(part.vmin)}–{fmt.volts(part.vmax)}"
        return verdict("satisfied", f"{part.mpn} accepts {span}; {rail.id} is {fmt.volts(rail.voltage)}.")

    if part.vmax is not None:
        return verdict(
            "evidence_missing",
            f"{at} is within the {fmt.volts(part.vmax)} maximum {part.mpn} states, "
            f"but it publishes no minimum.",
        )

    if part.vmin is not None:
        return verdict(
            "evidence_missing",
            f"{at} clears the {fmt.volts(part.vmin)} minimum {part.mpn} states, "
            f"but it publishes no maximum.",
        )

    return verdict(
        "evidence_missing",
        f"{part.mpn} does not state a supply range — {at} could not be checked.",
    )


# ── R2 · interface_role_match ─────────────────────────────────────────────────


def interface_role_match(board: Board) -> list[Verdict]:
    """A peripheral's bus must be offered by a master, with compatible roles.

    Fail unless a bus is shared; fail if two parts drive the same bus as master; and
    fail if there are more SPI peripherals than free GPIO for their chip selects.
    """
    masters = _by_role(board, "master")
    peripherals = _by_role(board, "peripheral")
    verdicts: list[Verdict] = []

    # A board mid-placement is not a board with parts missing. R2 is the one rule whose
    # verdict depends on evaluation *order*: a peripheral placed before its controller
    # has no master to talk to, which is true at that instant and not a fault. Reporting
    # it as a definite failure sent whole runs into repair loops over nothing.
    incomplete = any(slot.part is None for slot in board.slots.values())

    verdicts.extend(_bus_contention(masters))
    for slot_id, part in peripherals:
        verdicts.append(_check_one_bus(slot_id, part, masters, incomplete))
    verdicts.extend(_chip_select_pressure(masters, peripherals))
    verdicts.extend(_unplaceable_on_a_bus(board))
    return verdicts or [_not_applicable("interface_role_match", board, "This board has no buses to check.")]


def _by_role(board: Board, role: str) -> list[tuple[str, PartSpec]]:
    return [
        (slot_id, slot.part)
        for slot_id, slot in board.slots.items()
        if slot.part is not None and slot.part.role == role
    ]


def _unplaceable_on_a_bus(board: Board) -> list[Verdict]:
    """Parts that speak a bus but sit in neither role, so no other check can see them.

    `role` is a normalised field, which means a model fills it. `_by_role` collects only
    `master` and `peripheral`, so a part left `None` — or filed `passive` while still
    advertising interfaces — is not checked, not reported, simply absent. A rule the
    engine owns is switched off by a field the engine did not compute, which is the one
    arrangement this design exists to prevent.

    Measured 13 Aug on `CAN gateway bridging two buses, 12V automotive supply`, which
    passed 4/4 with no conflicts:

        mcu                ATMEGA328P-AU      role=master   ['I2C', 'SPI', 'UART']
        can_transceiver_1  UJA1075ATW/5V0/WD  role=None     ['LIN', 'CAN']
        can_transceiver_2  UJA1075ATW/5V0/WD  role=None     ['LIN', 'CAN']

    The ATmega328P has no CAN controller. Two CAN transceivers hung off a part that
    cannot drive them and R2 said nothing at all.

    **Evidence missing, not a failure.** Which side the part sits on is unknown, so whether
    the board is wrong is also unknown — and a `failed` verdict would start a repair loop
    against a question no replacement answers. Silence was the bug; a named coverage gap is
    the fix.
    Parts with no interfaces are untouched: a regulator is legitimately `passive`, and
    there is nothing about it for this rule to check.
    """
    return [
        Verdict(
            rule="interface_role_match",
            status="evidence_missing",
            detail=(
                f"{part.mpn} offers {fmt.listing(sorted({buses.canonical_bus(b) for b in part.interfaces}))} "
                f"but is filed as {part.role or 'no role'}, so it was not checked against "
                f"any controller on this board."
            ),
            subject=slot_id,
            involved=(slot_id,),
            evidence=tuple(part.cite(slot_id, "interfaces")),
        )
        for slot_id, slot in board.slots.items()
        if (part := slot.part) is not None
        and part.interfaces
        and part.role not in ("master", "peripheral")
    ]


def _bus_contention(masters: list[tuple[str, PartSpec]]) -> list[Verdict]:
    owners: dict[str, list[tuple[str, PartSpec]]] = {}
    for slot_id, part in masters:
        offered: set[str] = set()
        for bus in part.interfaces:
            canonical = buses.canonical_bus(bus)
            if canonical in offered:
                continue
            offered.add(canonical)
            owners.setdefault(canonical, []).append((slot_id, part))

    verdicts: list[Verdict] = []
    for bus, holders in owners.items():
        if len(holders) < 2:
            continue
        names = fmt.listing([p.mpn for _, p in holders])
        verdicts.append(
            Verdict(
                rule="interface_role_match",
                status="failed",
                detail=f"{names} both drive {bus} as master — only one may.",
                subject=holders[0][0],
                involved=tuple(slot_id for slot_id, _ in holders),
                evidence=tuple(
                    row for slot_id, part in holders for row in part.cite(slot_id, "interfaces")
                ),
            )
        )
    return verdicts


def _check_one_bus(
    slot_id: str,
    part: PartSpec,
    masters: list[tuple[str, PartSpec]],
    incomplete: bool = False,
) -> Verdict:
    evidence = part.cite(slot_id, "interfaces")
    involved = (slot_id, *(m_id for m_id, _ in masters))

    if not part.interfaces:
        return Verdict(
            rule="interface_role_match",
            status="evidence_missing",
            detail=f"{part.mpn} does not state an interface — its bus could not be checked.",
            subject=slot_id,
            involved=involved,
            evidence=evidence,
        )

    if not masters:
        # Only a fault once the board is complete. Until then it is a slot still to come.
        return Verdict(
            rule="interface_role_match",
            status="evidence_missing" if incomplete else "failed",
            detail=(
                f"{part.mpn} needs {fmt.listing(list(part.interfaces))}; "
                f"no controller has been chosen yet."
                if incomplete
                else f"{part.mpn} needs {fmt.listing(list(part.interfaces))} "
                f"but the board has no controller to drive it."
            ),
            subject=slot_id,
            involved=involved,
            evidence=evidence,
        )

    for master_id, master in masters:
        for peripheral_bus in part.interfaces:
            for master_bus in master.interfaces:
                if not buses.master_satisfies_bus(peripheral_bus, master_bus):
                    continue
                detail = f"{part.mpn} on {peripheral_bus}, offered by {master.mpn}."
                if buses.canonical_bus(peripheral_bus) != buses.canonical_bus(master_bus):
                    detail = (
                        f"{part.mpn} on {peripheral_bus}, offered by {master.mpn} "
                        f"as {master_bus}."
                    )
                return Verdict(
                    rule="interface_role_match",
                    status="satisfied",
                    detail=detail,
                    subject=slot_id,
                    involved=(slot_id, master_id),
                    evidence=evidence + master.cite(master_id, "interfaces"),
                )

    offered = fmt.listing(sorted({bus for _, m in masters for bus in m.interfaces}))
    return Verdict(
        rule="interface_role_match",
        status="failed",
        detail=(
            f"{part.mpn} speaks {fmt.listing(list(part.interfaces))}; "
            f"the controller offers {offered} — no shared bus."
        ),
        subject=slot_id,
        involved=involved,
        evidence=evidence + tuple(r for m_id, m in masters for r in m.cite(m_id, "interfaces")),
    )


def _chip_select_pressure(
    masters: list[tuple[str, PartSpec]], peripherals: list[tuple[str, PartSpec]]
) -> list[Verdict]:
    spi = [(s, p) for s, p in peripherals if any(buses.canonical_bus(bus) == "SPI" for bus in p.interfaces)]
    if not spi or not masters:
        return []
    master_id, master = masters[0]
    if master.pins_available is None:
        return []

    used = sum(p.pins_required or 0 for _, p in peripherals)
    free = master.pins_available - used
    if len(spi) <= free:
        return []
    return [
        Verdict(
            rule="interface_role_match",
            status="failed",
            detail=(
                f"{fmt.plural(len(spi), 'SPI peripheral')} need a chip select each, "
                f"but only {fmt.plural(free, 'GPIO')} remain on {master.mpn}."
            ),
            subject=master_id,
            involved=(master_id, *(s for s, _ in spi)),
            evidence=master.cite(master_id, "pins_available"),
        )
    ]


# ── R3 · pin_budget ───────────────────────────────────────────────────────────


BUS_PINS: dict[str, tuple[int, int]] = {
    # bus → (pins the bus costs once, pins each additional device costs)
    "I2C": (2, 0),  # SDA + SCL, shared by every device on the bus
    "SPI": (3, 1),  # SCK/MOSI/MISO shared, one chip select per device
    "UART": (0, 2),  # TX + RX, point to point — nothing is shared
    "CAN": (2, 0),  # TX + RX to one transceiver
    "1-WIRE": (1, 0),
}
"""What a bus costs a controller in pins.

R3 used to sum `pins_required` over peripherals. That field was populated on 4 of 33
live parts and all four were *masters*, so the sum was always zero and the failing
branch was unreachable — R3 reported "checks passed" having measured nothing.

Distributors do not publish a peripheral's pin count, but they do publish its bus, and a
bus has a known cost. Three I²C sensors are still two pins; three SPI devices are three
shared lines plus a chip select each. That is arithmetic the engine owns, over a field
that is actually present.
"""


def _pin_demand(consumers: list[tuple[str, PartSpec]]) -> tuple[int, list[str]]:
    """(GPIO the peripherals need, slots that state neither a count nor a bus).

    A stated `pins_required` always wins — it is a measurement, and the bus cost is an
    estimate. Everything else is priced by the bus it sits on, once for the bus and
    again per device where the bus needs it.
    """
    total = 0
    devices_per_bus: dict[str, int] = {}
    silent: list[str] = []

    for slot_id, part in consumers:
        if part.pins_required is not None:
            total += part.pins_required
            continue
        bus = next(
            (canonical for raw in part.interfaces if (canonical := buses.canonical_bus(raw)) in BUS_PINS),
            None,
        )
        if bus is None:
            silent.append(slot_id)
            continue
        devices_per_bus[bus] = devices_per_bus.get(bus, 0) + 1

    for bus, count in devices_per_bus.items():
        shared, per_device = BUS_PINS[bus]
        total += shared + per_device * count

    return total, silent


def pin_budget(board: Board) -> list[Verdict]:
    """FAIL if the peripherals ask for more GPIO than the controller offers."""
    masters = _by_role(board, "master")
    if not masters:
        return [_not_applicable("pin_budget", board, "This board has no controller with a GPIO budget.")]
    master_id, master = masters[0]

    # Every peripheral counts, including the ones that state no pin requirement — they
    # are exactly what makes the budget a floor rather than a total, and filtering them
    # out here is what made them invisible to the check below.
    consumers = _by_role(board, "peripheral")
    involved = (master_id, *(slot_id for slot_id, _ in consumers))
    evidence = master.cite(master_id, "pins_available")

    if master.pins_available is None:
        return [
            Verdict(
                rule="pin_budget",
                status="evidence_missing",
                detail=f"{master.mpn} does not state a GPIO count — pin budget unchecked.",
                subject=master_id,
                involved=involved,
                evidence=evidence,
            )
        ]

    required, silent = _pin_demand(consumers)
    detail_tail = (
        f"{fmt.plural(len(consumers), 'peripheral')} on {master.mpn} "
        f"({master.pins_available} GPIO)"
    )

    if required > master.pins_available:
        return [
            Verdict(
                rule="pin_budget",
                status="failed",
                detail=f"{detail_tail} need {required} GPIO — {required - master.pins_available} short.",
                subject=master_id,
                involved=involved,
                evidence=evidence
                + tuple(r for s, p in consumers for r in p.cite(s, "pins_required"))[
                    :MAX_EVIDENCE_ROWS
                ],
            )
        ]

    if silent:
        # Counting an unstated pin requirement as zero is how a full board reports
        # room to spare. Say it is a floor instead.
        names = fmt.listing([board.slots[s].label for s in silent])
        return [
            Verdict(
                rule="pin_budget",
                status="evidence_missing",
                detail=(
                    f"At least {required} of {master.pins_available} GPIO used by "
                    f"{detail_tail} — {names} state no pin count."
                ),
                subject=master_id,
                involved=involved,
                evidence=evidence,
            )
        ]

    return [
        Verdict(
            rule="pin_budget",
            status="satisfied",
            detail=f"{required} of {master.pins_available} GPIO used by {detail_tail}.",
            subject=master_id,
            involved=involved,
            evidence=evidence,
        )
    ]


# ── R4 · current_budget ───────────────────────────────────────────────────────


def current_budget(board: Board) -> list[Verdict]:
    """Worst-case draw on a rail, with design margin, against what feeds it.

    `draw` sums every part's *peak*, i.e. it already assumes all peaks coincide.
    `current_margin` is headroom on top of that worst case — see `Requirements`.
    """
    verdicts: list[Verdict] = []
    for rail in board.rails.values():
        verdict = _check_rail_current(board, rail)
        if verdict is not None:
            verdicts.append(verdict)
    return verdicts or [_not_applicable("current_budget", board, "This board has no rails with a current budget to check.")]



def _check_rail_current(board: Board, rail: Rail) -> Verdict | None:
    consumers = rail_current.consumers(board, rail)
    if not consumers:
        return None

    draw, unstated = rail_current.rail_draw(board, rail, consumers)
    limit, source = rail_current.rail_limit(board, rail)
    subject = rail_current.current_subject(board, rail, consumers)
    involved = (subject, *(s for s, _ in consumers))
    supply = source.mpn if source else f"the {rail.id} supply"

    evidence: tuple[Evidence, ...] = ()
    if source and rail.source:
        evidence += source.cite(rail.source, "i_max")
    else:
        evidence += _supply_evidence(rail, subject, current=True)
    if rail.i_load is not None:
        evidence += _load_evidence(rail, subject)
    else:
        evidence += tuple(
            row
            for slot_id, part in sorted(consumers, key=lambda p: -(p[1].draw or 0.0))
            for row in part.cite(slot_id, "i_peak")
        )[:MAX_EVIDENCE_ROWS]

    if limit is None:
        return Verdict(
            rule="current_budget",
            scope=rail.id,
            status="evidence_missing",
            detail=f"{supply} does not state a current rating — {rail.id} budget unchecked.",
            subject=subject,
            involved=involved,
            evidence=evidence,
        )

    margin = board.requirements.current_margin
    required = draw * (1 + margin)

    # A rail can be over budget on the parts that *did* state a draw. Waiting for
    # complete data before deciding would report "unchecked" on a board that is already
    # provably over — the unknown parts can only make it worse, never better.
    if unstated and required > limit:
        names = fmt.listing([board.part(s).mpn for s in unstated])  # type: ignore[union-attr]
        verb = "states" if len(unstated) == 1 else "state"
        return Verdict(
            rule="current_budget",
            scope=rail.id,
            status="failed",
            detail=(
                f"{fmt.milliamps(draw)} on {rail.id} plus {fmt.percent(margin)} margin "
                f"= {fmt.milliamps(required)}, above the {fmt.milliamps(limit)} rating of "
                f"{supply} — and that is a floor, because {names} {verb} no draw."
            ),
            subject=subject,
            involved=involved,
            evidence=evidence,
        )

    if unstated:
        names = fmt.listing([board.part(s).mpn for s in unstated])  # type: ignore[union-attr]
        verb = "states" if len(unstated) == 1 else "state"
        headroom = fmt.percent(1 - draw / limit) if limit else "?"
        return Verdict(
            rule="current_budget",
            scope=rail.id,
            status="evidence_missing",
            detail=(
                f"At least {fmt.milliamps(draw)} of {fmt.milliamps(limit)} on {rail.id}, "
                f"leaving {headroom} — but {names} {verb} no draw, so the real figure is higher."
            ),
            subject=subject,
            involved=involved,
            evidence=evidence,
        )
    headline = f"{fmt.milliamps(draw)} of {fmt.milliamps(limit)} ({fmt.percent(draw / limit)})"

    if required > limit:
        return Verdict(
            rule="current_budget",
            scope=rail.id,
            status="failed",
            detail=(
                f"{fmt.milliamps(draw)} on {rail.id} plus {fmt.percent(margin)} margin "
                f"= {fmt.milliamps(required)}, above the {fmt.milliamps(limit)} "
                f"rating of {supply}."
            ),
            subject=subject,
            involved=involved,
            evidence=evidence,
        )

    if draw > DERATING_THRESHOLD * limit:
        headroom = fmt.percent(1 - DERATING_THRESHOLD)
        return Verdict(
            rule="current_budget",
            scope=rail.id,
            status="satisfied",
            margin=f"{fmt.percent(1 - draw / limit)} of rating",
            detail=f"{headline} — inside the {headroom} derating band.",
            subject=subject,
            involved=involved,
            evidence=evidence,
        )

    return Verdict(
        rule="current_budget",
        scope=rail.id,
        status="satisfied",
        detail=headline,
        subject=subject,
        involved=involved,
        evidence=evidence,
    )


# ── R5 · thermal_dissipation ──────────────────────────────────────────────────


def thermal_dissipation(board: Board) -> list[Verdict]:
    """How much heat the part making a rail has to shed, and whether it can.

    linear:    P = (vin − vout) × draw
    switching: P = vout × draw × (1/η − 1)
    ΔT = P × θJA, and θJA is an approximation — see `packages`.

    The junction temperature is checked against the part's own maximum, not against
    `requirements.temp_range`. That range is a component *grade* — commercial 0–70,
    industrial −40–85 — describing the ambient conditions a part must be rated for.
    Comparing a junction temperature to it is a category error: it would fail every
    regulator that runs warm inside a commercial-grade product, which is all of them.
    """
    verdicts: list[Verdict] = []
    for rail in board.rails.values():
        verdict = _check_rail_thermal(board, rail)
        if verdict is not None:
            verdicts.append(verdict)
    return verdicts or [_not_applicable("thermal_dissipation", board, "This board has no regulator to assess for thermal dissipation.")]


def _dissipation(
    board: Board, rail: Rail, regulator: PartSpec, draw: float
) -> tuple[float | None, float | None, str, str, tuple[float, float] | None]:
    """Returns (low watts, high watts, topology label, reason, efficiency band).

    The output voltage is the *rail*, not anything on the regulator's datasheet. A
    regulator is chosen to make the rail it sources; whether it can be set that low is
    R1's business, and reading a range maximum here produced `(5.0 − 32.04) × draw` —
    negative watts, which passes every ceiling.
    """
    if regulator.regulation == "switching":
        band = (regulator.efficiency, regulator.efficiency)
        if regulator.efficiency is None:
            band = efficiency.band_for(regulator)
        if band is None:
            return None, None, regulator.topology or "switching", "has no efficiency band", None
        low_efficiency, high_efficiency = band
        output_power = rail.voltage * draw
        return (
            output_power * (1 / high_efficiency - 1),
            output_power * (1 / low_efficiency - 1),
            regulator.topology or "switching",
            "",
            None if regulator.efficiency is not None else band,
        )

    if regulator.regulation is None:
        return (
            None,
            None,
            "unknown",
            "states no topology and its category does not imply a regulation type",
            None,
        )

    input_rail = board.input_rail(rail.source) if rail.source else None
    if input_rail is None:
        return None, None, "linear", "has no known input rail", None
    power = (input_rail.voltage - rail.voltage) * draw
    return power, power, "linear", "", None


def _power_range(low: float, high: float) -> str:
    """One power value when exact, otherwise the interval it can occupy."""
    if low == high:
        return fmt.watts(low)
    return f"{fmt.watts(low)}–{fmt.watts(high)}"


def _check_rail_thermal(board: Board, rail: Rail) -> Verdict | None:
    if not rail.source:
        return None
    regulator = board.part(rail.source)
    if regulator is None:
        return None

    consumers = rail_current.consumers(board, rail)
    draw, unstated = rail_current.rail_draw(board, rail, consumers)
    if not consumers or draw <= 0:
        return None

    # Heat computed from a partial draw is a *floor*: the parts that stated nothing can
    # only add to it. A regulator already over its junction limit on the known load is
    # over it, and declining to say so would be the quietest way to miss a dead board.
    partial = bool(unstated)

    subject = rail.source
    involved = (subject, *(s for s, _ in consumers))
    requirements = board.requirements
    evidence = regulator.cite(subject, "package", "temp_max")
    input_rail = board.input_rail(subject)
    if input_rail is not None:
        evidence += _supply_evidence(input_rail, subject)
    evidence += _load_evidence(rail, subject)
    power_low, power_high, topology, blocked, band = _dissipation(board, rail, regulator, draw)
    if regulator.is_switching:
        evidence += efficiency_evidence(regulator, subject, band)
    if power_low is None or power_high is None:
        return Verdict(
            rule="thermal_dissipation",
            scope=rail.id,
            status="evidence_missing",
            detail=f"{regulator.mpn} {blocked} — dissipation could not be computed.",
            subject=subject,
            involved=involved,
            evidence=evidence,
        )

    theta = regulator.theta_ja or packages.theta_ja(regulator.package)
    if theta is None:
        return Verdict(
            rule="thermal_dissipation",
            scope=rail.id,
            status="evidence_missing",
            detail=(
                f"{regulator.mpn} dissipates {_power_range(power_low, power_high)}, but no θJA is known "
                f"for {regulator.package or 'its package'} — temperature rise unchecked."
            ),
            subject=subject,
            involved=involved,
            evidence=evidence,
        )

    # A θJA carried forward from an earlier run is still a datasheet reading, but *this*
    # run never opened that datasheet. Labelling it "(datasheet)" and putting the quoted
    # line in `source` would tell the screen a datasheet was consulted here and print the
    # quote twice. Name the dossier instead, exactly as the package table names itself.
    theta_from_dossier = regulator.provenance.get("theta_ja", "").startswith(DOSSIER_SOURCE)
    theta_evidence = (
        Evidence(
            subject,
            "θJA (dossier)" if theta_from_dossier else "θJA (datasheet)",
            f'{fmt.ohms_per_watt(theta)} — "{regulator.theta_ja_source_line}"',
            DOSSIER_SOURCE if theta_from_dossier else regulator.datasheet,
        )
        if regulator.theta_ja is not None and regulator.theta_ja_source_line is not None
        else Evidence(subject, "θJA (package table)", fmt.ohms_per_watt(theta), packages.THETA_JA_SOURCE)
    )
    evidence += (theta_evidence,)
    # θJA is a property of the installation, so the two conditions travel together: what
    # the manufacturer measured on, and what this board actually is. A reader comparing
    # 160 °C/W at a minimum pad against 60 °C/W at 1000 mm² of copper can only see that
    # they are different questions if both rows are on the screen.
    if regulator.theta_ja_mounting:
        evidence += (
            Evidence(subject, "θJA measured on", regulator.theta_ja_mounting, regulator.datasheet),
        )
    if regulator.theta_ja_revision:
        evidence += (
            Evidence(subject, "θJA document revision", regulator.theta_ja_revision, regulator.datasheet),
        )
    if requirements.mounting:
        evidence += (Evidence(subject, "board mounting", requirements.mounting),)
    # Last of the thermal operands, and deliberately after θJA rather than before it:
    # the rise is what θJA produces and the ambient is what the rise is added to, so
    # reading them in that order is reading the arithmetic in the order it happens.
    evidence += (
        Evidence(
            subject,
            "ambient",
            fmt.celsius(requirements.ambient_c),
            requirements.ambient_source or AMBIENT_DEFAULT_SOURCE,
        ),
        Evidence(subject, "current basis", "peak, assumed continuous", CURRENT_BASIS_SOURCE),
    )

    # The junction limit, which is not the ambient grade. See `PartSpec.t_j_max`.
    limit = regulator.t_j_max if regulator.t_j_max is not None else regulator.temp_max

    if limit is None:
        rise = f"{fmt.celsius(power_high * theta)} {'worst-case ' if band is not None else ''}rise"
        return Verdict(
            rule="thermal_dissipation",
            scope=rail.id,
            status="evidence_missing",
            detail=(
                f"{regulator.mpn} dissipates {_power_range(power_low, power_high)} — "
                f"{rise}, but it states no maximum temperature to check that against."
            ),
            subject=subject,
            involved=involved,
            evidence=evidence,
        )

    rise_low = power_low * theta
    rise_high = power_high * theta
    junction_low = requirements.ambient_c + rise_low
    junction_high = requirements.ambient_c + rise_high
    sum_line = _thermal_sum(board, rail, regulator, draw, topology, band)

    floor = " at least" if partial else ""
    caveat = (
        f" This is a floor — {fmt.plural(len(unstated), 'part')} on the rail state no draw."
        if partial
        else ""
    )

    # A θJA from the package table does NOT downgrade the verdict, and that was tried.
    # The evidence row already names the table rather than a datasheet — "the screen never
    # implies a datasheet said something it did not" — and that disclosure is the honesty
    # mechanism. Reporting `evidence_missing` on top of it removes information rather than
    # adding it: "323 °C against a 125 °C limit, on our own package figure" is worth more
    # to a reader than "could not check". It also silently retired the demo's central
    # beat, whose overheating regulator is computed from exactly such a figure.
    if junction_high <= limit:
        worst_case = (
            f" at worst case ({fmt.percent(band[0])} efficiency)" if band is not None else ""
        )
        if rise_high > THERMAL_RISE_WARN_C:
            return Verdict(
                rule="thermal_dissipation",
                scope=rail.id,
                status="satisfied",
                margin=fmt.celsius_fine(limit - junction_high),
                detail=(
                    f"{sum_line} = {fmt.watts(power_high)}{worst_case} — "
                    f"{fmt.celsius(rise_high)} rise from "
                    f"{fmt.celsius(requirements.ambient_c)} ambient runs hot even though "
                    f"{fmt.celsius(junction_high)} clears the {fmt.celsius(limit)} limit.{caveat}"
                ),
                subject=subject,
                involved=involved,
                evidence=evidence,
            )

        return Verdict(
            rule="thermal_dissipation",
            scope=rail.id,
            status="evidence_missing" if partial else "satisfied",
            margin=None if partial else fmt.celsius_fine(limit - junction_high),
            detail=(
                f"{sum_line} ={floor} {fmt.watts(power_high)}{worst_case} — "
                f"{fmt.celsius(rise_high)} rise from {fmt.celsius(requirements.ambient_c)} ambient "
                f"in {regulator.package or 'its package'}, "
                f"{fmt.celsius(junction_high)} junction.{caveat}"
            ),
            subject=subject,
            involved=involved,
            evidence=evidence,
        )

    if junction_low > limit:
        best_case = (
            f" at best case ({fmt.percent(band[1])} efficiency)" if band is not None else ""
        )
        return Verdict(
            rule="thermal_dissipation",
            scope=rail.id,
            status="failed",
            detail=(
                f"{sum_line} ={floor} {fmt.watts(power_low)}{best_case} in "
                f"{regulator.package or 'its package'} — {fmt.celsius(rise_low)} rise from "
                f"{fmt.celsius(requirements.ambient_c)} ambient, {fmt.celsius(junction_low)} junction "
                f"against a {fmt.celsius(limit)} limit."
                f"{caveat}"
            ),
            subject=subject,
            involved=involved,
            evidence=evidence,
        )

    critical_power = (limit - requirements.ambient_c) / theta
    critical_efficiency = 1 / (critical_power / (rail.voltage * draw) + 1)
    return Verdict(
        rule="thermal_dissipation",
        scope=rail.id,
        status="evidence_missing",
        detail=(
            f"{sum_line} spans {_power_range(power_low, power_high)} — passes at or above "
            f"~{fmt.percent(critical_efficiency)} efficiency, fails below it; the datasheet's "
            f"efficiency curve at {fmt.volts(rail.voltage)} and {fmt.milliamps(draw)} would settle it."
            f" This uses {fmt.celsius(requirements.ambient_c)} ambient."
            f"{caveat}"
        ),
        subject=subject,
        involved=involved,
        evidence=evidence,
    )


def _thermal_sum(
    board: Board,
    rail: Rail,
    regulator: PartSpec,
    draw: float,
    topology: str,
    band: tuple[float, float] | None,
) -> str:
    """The arithmetic, shown. A judge should be able to check it from the screen."""
    vout = regulator.vout if regulator.vout is not None else rail.voltage
    if regulator.is_switching and regulator.efficiency is not None:
        return (
            f"{fmt.percent(regulator.efficiency)} efficient at "
            f"{fmt.volts(vout)} × {fmt.milliamps(draw)}"
        )
    if regulator.is_switching and band is not None:
        return (
            f"{efficiency.band_label(regulator)} {fmt.percent(band[0])}–{fmt.percent(band[1])} "
            f"efficient at {fmt.volts(vout)} × {fmt.milliamps(draw)}"
        )
    input_rail = board.input_rail(rail.source) if rail.source else None
    vin = input_rail.voltage if input_rail else 0.0
    return f"({fmt.volts(vin)} − {fmt.volts(vout)}) × {fmt.milliamps(draw)}"


# ── R6 · availability ─────────────────────────────────────────────────────────


def part_qualification(board: Board) -> list[Verdict]:
    """Is every part on this board one the company has qualified? — the AML gate.

    **This gate does not depend on anything being electrically wrong**, and that is the
    whole reason it exists as its own rule. A part can pass every check on this board and
    still be one nobody has qualified to ship, which is a question for engineering and
    quality rather than a consequence of a conflict. A design that only ever asked about
    qualification when something else had already failed would clear an unqualified part
    the moment it happened to be electrically fine — which is most of the time.

    Silent when the organisation keeps no AML. An empty list means nothing is approved and
    is reported as such; *no* list means the question has not been asked here, and the two
    must not look alike.
    """
    approved = board.approved.parts
    if approved is None:
        return [
            _not_applicable(
                "part_qualification",
                board,
                "This organisation keeps no approved-manufacturer list, so there is "
                "nothing to check a part against.",
            )
        ]

    verdicts: list[Verdict] = []
    for slot_id, slot in board.slots.items():
        if slot.part is None:
            continue
        part = slot.part
        if part.mpn.upper() in approved:
            verdicts.append(
                Verdict(
                    rule="part_qualification",
                    status="satisfied",
                    detail=f"{part.mpn} is on the approved manufacturer list.",
                    subject=slot_id,
                    involved=(slot_id,),
                )
            )
        else:
            verdicts.append(
                Verdict(
                    rule="part_qualification",
                    status="failed",
                    detail=(
                        f"{part.mpn} is not on the approved manufacturer list, so it has "
                        "not been qualified for use on a shipping product."
                    ),
                    subject=slot_id,
                    involved=(slot_id,),
                )
            )
    return verdicts


def source_approval(board: Board) -> list[Verdict]:
    """Is every part being bought from a source procurement approves? — the AVL gate.

    Separate from the AML because it is a different question kept by different people, and
    the interesting cases are the mismatches: a qualified part available only from a vendor
    nobody has approved, and an approved vendor stocking a part nobody has qualified. One
    combined list cannot express either.

    A part with no distributor is `evidence_missing` rather than a failure. Nobody has said
    it comes from an unapproved source; we simply do not know where it would come from, and
    reporting that as a policy breach would put a decision in front of somebody that the
    data does not support.
    """
    approved = board.approved.vendors
    if approved is None:
        return [
            _not_applicable(
                "source_approval",
                board,
                "This organisation keeps no approved-vendor list, so there is nothing to "
                "check a source against.",
            )
        ]

    verdicts: list[Verdict] = []
    for slot_id, slot in board.slots.items():
        if slot.part is None:
            continue
        part = slot.part
        if not part.distributor:
            verdicts.append(
                Verdict(
                    rule="source_approval",
                    status="evidence_missing",
                    detail=f"No source is recorded for {part.mpn}, so it cannot be checked "
                    "against the approved-vendor list.",
                    subject=slot_id,
                    involved=(slot_id,),
                )
            )
        elif part.distributor.upper() in approved:
            verdicts.append(
                Verdict(
                    rule="source_approval",
                    status="satisfied",
                    detail=f"{part.distributor} is an approved source for {part.mpn}.",
                    subject=slot_id,
                    involved=(slot_id,),
                    evidence=part.cite(slot_id, "distributor"),
                )
            )
        else:
            verdicts.append(
                Verdict(
                    rule="source_approval",
                    status="failed",
                    detail=(
                        f"{part.mpn} would be bought from {part.distributor}, which is not "
                        "on the approved-vendor list."
                    ),
                    subject=slot_id,
                    involved=(slot_id,),
                    evidence=part.cite(slot_id, "distributor"),
                )
            )
    return verdicts


def availability(board: Board) -> list[Verdict]:
    """Sourcing, not electrical — and the trigger our interviews said actually bites.

    Fail below the stock floor; a lifecycle concern or long lead time is satisfied with a margin.
    """
    verdicts: list[Verdict] = []
    for slot_id, slot in board.slots.items():
        if slot.part is None:
            continue
        verdicts.append(_check_availability(board, slot_id, slot.part))
    return verdicts


def _check_availability(board: Board, slot_id: str, part: PartSpec) -> Verdict:
    """Cites only the fields that drove the verdict.

    Quoting lifecycle and lead time under a stock failure pads the drawer with rows
    that support nothing — and evidence that does not support the claim it sits under
    trains people to stop reading it.
    """
    requirements = board.requirements

    if part.stock is None:
        return Verdict(
            rule="availability",
            status="evidence_missing",
            detail=f"{part.distributor} reports no stock figure for {part.mpn}.",
            subject=slot_id,
            involved=(slot_id,),
            evidence=part.cite(slot_id, "stock"),
        )

    if requirements.min_stock is not None and part.stock < requirements.min_stock:
        late = part.lead_time_days is not None and part.lead_time_days > requirements.max_lead_days
        return Verdict(
            rule="availability",
            status="failed",
            detail=(
                f"{part.mpn}: {fmt.count(part.stock)} in stock at {part.distributor}, "
                f"below the {fmt.count(requirements.min_stock)} minimum."
            ),
            subject=slot_id,
            involved=(slot_id,),
            evidence=part.cite(slot_id, "stock", *(("lead_time_days",) if late else ())),
        )

    concerns: list[str] = []
    cited = ["stock"]
    if part.lifecycle in {"nrnd", "obsolete"}:
        label = "not recommended for new designs" if part.lifecycle == "nrnd" else "obsolete"
        concerns.append(f"marked {label}")
        cited.append("lifecycle")
    if part.lead_time_days is not None and part.lead_time_days > requirements.max_lead_days:
        concerns.append(f"{part.lead_time_days}-day lead time")
        cited.append("lead_time_days")

    stocked = f"{part.mpn}: {fmt.count(part.stock)} in stock at {part.distributor}"
    if concerns:
        return Verdict(
            rule="availability",
            status="satisfied",
            margin=(
                f"{part.lead_time_days}-day lead time"
                if part.lead_time_days is not None
                else "lifecycle concern"
            ),
            detail=f"{stocked}, but {fmt.listing(concerns)}.",
            subject=slot_id,
            involved=(slot_id,),
            evidence=part.cite(slot_id, *cited),
        )

    return Verdict(
        rule="availability",
        status="satisfied",
        detail=f"{stocked}.",
        subject=slot_id,
        involved=(slot_id,),
        evidence=part.cite(slot_id, "stock"),
    )


# ── R7 · temperature_rating ──────────────────────────────────────────────────


# ── R11 · capacitor_requirements ──────────────────────────────────────────────


def capacitor_requirements(board: Board) -> list[Verdict]:
    """Does the output capacitor on this rail conflict with what the regulator requires?

    Named by the research as the first thing a hardware engineer attacks on an LDO
    substitution, and the four datasheets behind the demo disagree with each other, which
    is the point: TI requires ≥1.0 µF ceramic in X5R or X7R for the TLV1117LV and says the
    part is stable with no ESR at all, AMS asks for 22 µF solid tantalum, and NCP1117 and
    LD1117 characterise at 10 µF. A substitute that inherits the board's existing capacitor
    inherits a decision made for a different part.

    **This does not assess stability, and must never appear to.** Proving a regulator is
    stable with a given capacitor needs simulation, and no signature can stand in for it.
    What is checkable without simulation is an explicit conflict with a *published*
    requirement, which is a narrower claim and a real one: a regulator that stated a
    condition and a board that breaks it is a failure, and a regulator that stated nothing
    is `evidence_missing` rather than a quiet pass.

    The asymmetry between "required" and "recommended" decides verdicts here, so the model
    keeps them apart: `cout_dielectrics` holds what a datasheet *requires*, and a
    recommendation that a different type "will ensure stability" leaves it empty. A ceramic
    where AMS suggested tantalum is a question its datasheet does not answer. A ceramic
    outside TI's stated X5R/X7R is a violation of one it does.
    """
    verdicts: list[Verdict] = []
    for rail in board.rails.values():
        if not rail.source or not board.placed(rail.source):
            continue
        verdicts.append(_check_output_capacitors(board, rail))
    return verdicts or [
        _not_applicable(
            "capacitor_requirements",
            board,
            "No rail on this board is fed by a regulator, so there is no output capacitor to check.",
        )
    ]


def _check_output_capacitors(board: Board, rail: Rail) -> Verdict:
    subject = rail.source
    regulator = board.part(subject)  # type: ignore[arg-type]
    capacitors = [
        (slot_id, part)
        for slot_id in rail.members
        if (part := board.part(slot_id)) is not None and part.capacitance_uf is not None
    ]
    involved = (subject, *(slot_id for slot_id, _ in capacitors))

    def verdict(status: str, detail: str, extra: tuple[Evidence, ...] = ()) -> Verdict:
        return Verdict(
            rule="capacitor_requirements",
            scope=rail.id,
            status=status,
            detail=detail,
            subject=subject,  # type: ignore[arg-type]
            involved=involved,
            evidence=extra,
        )

    if regulator.cout_min_uf is None and not regulator.cout_dielectrics:
        return verdict(
            "evidence_missing",
            f"{regulator.mpn} publishes no output-capacitor requirement, so whether "
            f"{rail.id}'s capacitor suits it could not be checked.",
        )

    requirement = Evidence(
        subject,  # type: ignore[arg-type]
        "output capacitor required",
        _requirement_text(regulator),
        regulator.cout_source_line or regulator.datasheet,
    )

    if not capacitors:
        return verdict(
            "evidence_missing",
            f"{regulator.mpn} requires {_requirement_text(regulator)} on {rail.id}, and no "
            f"capacitor is modelled there — absent from the board and absent from our model "
            f"look the same from here.",
            (requirement,),
        )

    total = sum(part.capacitance_uf or 0.0 for _, part in capacitors)
    fitted = tuple(
        Evidence(slot_id, "capacitance", fmt.microfarads(part.capacitance_uf), part.product_url)
        for slot_id, part in capacitors
    )[:MAX_EVIDENCE_ROWS]

    if regulator.cout_min_uf is not None and total < regulator.cout_min_uf:
        return verdict(
            "failed",
            f"{rail.id} carries {fmt.microfarads(total)} where {regulator.mpn} requires at "
            f"least {fmt.microfarads(regulator.cout_min_uf)}.",
            (requirement, *fitted),
        )

    wrong = [
        (slot_id, part)
        for slot_id, part in capacitors
        if regulator.cout_dielectrics
        and part.dielectric
        and part.dielectric.upper() not in {d.upper() for d in regulator.cout_dielectrics}
    ]
    if wrong:
        names = fmt.listing([f"{part.mpn} is {part.dielectric}" for _, part in wrong])
        return verdict(
            "failed",
            f"{regulator.mpn} requires {fmt.listing(list(regulator.cout_dielectrics))}; {names}.",
            (requirement, *fitted),
        )

    return verdict(
        "satisfied",
        f"{rail.id} carries {fmt.microfarads(total)}, meeting {regulator.mpn}'s stated "
        f"{_requirement_text(regulator)}.",
        (requirement, *fitted),
    )


# ── R11b · output_capacitor_stability ────────────────────────────────────────


def output_capacitor_stability(board: Board) -> list[Verdict]:
    """Check each regulator's published output-capacitor stability conditions.

    A failure requires an explicit regulator condition and an incompatible stated
    capacitor value. ESR is never inferred from another capacitor characteristic.
    """
    verdicts: list[Verdict] = []
    for rail in board.rails.values():
        if rail.source and board.placed(rail.source):
            verdicts.append(_check_output_stability(board, rail))
    return verdicts or [_not_applicable(
        "output_capacitor_stability", board,
        "No rail on this board is fed by a regulator, so there is no output stability condition to check.",
    )]


def _check_output_stability(board: Board, rail: Rail) -> Verdict:
    subject = rail.source
    regulator = board.part(subject)  # type: ignore[arg-type]
    capacitors = [(slot_id, part) for slot_id in rail.members if (part := board.part(slot_id)) is not None and part.capacitance_uf is not None]
    involved = (subject, *(slot_id for slot_id, _ in capacitors))

    def verdict(status: str, detail: str, evidence: tuple[Evidence, ...] = ()) -> Verdict:
        return Verdict("output_capacitor_stability", status, detail, subject, involved, evidence, scope=rail.id)  # type: ignore[arg-type]

    if regulator.cout_min_uf is None and regulator.esr_stable_from_ohms is None and regulator.esr_stable_to_ohms is None:
        return verdict("evidence_missing", f"{regulator.mpn} publishes no output-capacitor stability condition for {rail.id}.")

    requirement = Evidence(
        subject, "output capacitor stability", regulator.esr_source_line or regulator.cout_source_line or "published condition",
        regulator.esr_source_line or regulator.cout_source_line or regulator.datasheet,
    )
    if not capacitors:
        return verdict("failed", f"{regulator.mpn} states an output-capacitor stability condition on {rail.id}, but no capacitor is modelled there.", (requirement,))

    total = sum(part.capacitance_uf or 0.0 for _, part in capacitors)
    if regulator.cout_min_uf is not None and total < regulator.cout_min_uf:
        return verdict("failed", f"{rail.id} carries {fmt.microfarads(total)} where {regulator.mpn} needs at least {fmt.microfarads(regulator.cout_min_uf)} for stability.", (requirement,))

    lower, upper = regulator.esr_stable_from_ohms, regulator.esr_stable_to_ohms
    for slot_id, capacitor in capacitors:
        esr = capacitor.esr_ohms
        if esr is not None and ((lower is not None and esr < lower) or (upper is not None and esr > upper)):
            return verdict("failed", f"{capacitor.mpn} publishes {fmt.ohms(esr)} ESR; {regulator.mpn} requires {_esr_window(lower, upper)} on {rail.id}.", (requirement, *capacitor.cite(slot_id, "esr_ohms")))

    if lower is not None or upper is not None:
        return verdict("satisfied", f"{rail.id} carries {fmt.microfarads(total)}, meeting {regulator.mpn}'s published stability condition; no fitted capacitor publishes ESR outside {_esr_window(lower, upper)}.", (requirement,))
    return verdict("satisfied", f"{rail.id} carries {fmt.microfarads(total)}, meeting {regulator.mpn}'s published stability minimum of {fmt.microfarads(regulator.cout_min_uf)}.", (requirement,))  # type: ignore[arg-type]


def _esr_window(lower: float | None, upper: float | None) -> str:
    if lower is None:
        return f"at most {fmt.ohms(upper)}"  # type: ignore[arg-type]
    if upper is None:
        return f"at least {fmt.ohms(lower)}"
    return f"{fmt.ohms(lower)}–{fmt.ohms(upper)}"


# ── R11c · EMC and signal integrity ─────────────────────────────────────────


def emc(board: Board) -> list[Verdict]:
    """Reject a substitution that changes the regulator's emissions character."""
    verdicts: list[Verdict] = []
    for slot_id, slot in board.slots.items():
        if slot.part is None or slot.baseline is None:
            continue
        before, after = slot.baseline.regulation, slot.part.regulation
        if before is None or after is None:
            verdicts.append(Verdict("emc", "evidence_missing", f"The regulation type of {slot.baseline.mpn if before is None else slot.part.mpn} is not published, so its emissions character could not be compared.", slot_id, (slot_id,)))
        elif before != after:
            verdicts.append(Verdict("emc", "failed", f"{slot.part.mpn} is {after}; it changes {slot.baseline.mpn}'s {before} regulation and its emissions character.", slot_id, (slot_id,)))
        else:
            verdicts.append(Verdict("emc", "satisfied", f"{slot.part.mpn} and {slot.baseline.mpn} are both {after} regulators; the substitution keeps the board's emissions character.", slot_id, (slot_id,)))
    return verdicts or [_not_applicable("emc", board, "No placed part on this board is a substitution, so no emissions character changes.")]


def signal_integrity(board: Board) -> list[Verdict]:
    """Check regulator output error against every load's published supply window."""
    verdicts: list[Verdict] = []
    for rail in board.rails.values():
        if not rail.source or not board.placed(rail.source):
            continue
        regulator = board.part(rail.source)
        assert regulator is not None
        for slot_id in rail.members:
            load = board.part(slot_id)
            if load is None or load.capacitance_uf is not None:
                continue
            verdicts.append(_check_signal_integrity(rail, regulator, rail.source, slot_id, load))
    return verdicts or [_not_applicable("signal_integrity", board, "No regulated rail has a modelled load supply window to check.")]


def _check_signal_integrity(rail: Rail, regulator: PartSpec, regulator_slot: str, load_slot: str, load: PartSpec) -> Verdict:
    evidence = regulator.cite(regulator_slot, "vout_accuracy_pct", "load_regulation_pct") + load.cite(load_slot, "vmin", "vmax")
    involved = (regulator_slot, load_slot)
    if regulator.vout_accuracy_pct is None or regulator.load_regulation_pct is None:
        missing = fmt.listing([name for name, value in (("vout_accuracy_pct", regulator.vout_accuracy_pct), ("load_regulation_pct", regulator.load_regulation_pct)) if value is None])
        return Verdict("signal_integrity", "evidence_missing", f"{regulator.mpn} publishes no {missing}, so {rail.id}'s worst output deviation could not be checked.", load_slot, involved, evidence, scope=rail.id)
    if load.vmin is None or load.vmax is None:
        return Verdict("signal_integrity", "evidence_missing", f"{load.mpn} publishes no complete supply window, so {rail.id}'s output deviation could not be checked.", load_slot, involved, evidence, scope=rail.id)
    deviation = rail.voltage * (regulator.vout_accuracy_pct + regulator.load_regulation_pct) / 100
    low, high = rail.voltage - deviation, rail.voltage + deviation
    detail = f"{regulator.mpn}'s worst {rail.id} output is {fmt.volts(low)}–{fmt.volts(high)} from {fmt.num(regulator.vout_accuracy_pct)}% accuracy plus {fmt.num(regulator.load_regulation_pct)}% load regulation."
    if low < load.vmin or high > load.vmax:
        return Verdict("signal_integrity", "failed", f"{detail} It exceeds {load.mpn}'s {fmt.volts(load.vmin)}–{fmt.volts(load.vmax)} supply window.", load_slot, involved, evidence, scope=rail.id)
    margin = min(low - load.vmin, load.vmax - high)
    return Verdict("signal_integrity", "satisfied", f"{detail} It stays within {load.mpn}'s {fmt.volts(load.vmin)}–{fmt.volts(load.vmax)} supply window.", load_slot, involved, evidence, margin=fmt.millivolts(margin), scope=rail.id)


def _requirement_text(part: PartSpec) -> str:
    pieces: list[str] = []
    if part.cout_min_uf is not None:
        pieces.append(f"at least {fmt.microfarads(part.cout_min_uf)}")
    if part.cout_dielectrics:
        pieces.append(fmt.listing(list(part.cout_dielectrics)))
    return fmt.listing(pieces) if pieces else "no stated requirement"


# ── R7b · footprint_compatibility ─────────────────────────────────────────────


def footprint_compatibility(board: Board) -> list[Verdict]:
    """Does the replacement fit the land pattern the outgoing part leaves behind?

    Distinct from `footprint`, which asks whether a part is under a size target the brief
    named. This asks a substitution question — *does this drop into that* — and it is the
    first rule that needs `Slot.baseline`, because "fits where the old one was" cannot be
    answered from the new part alone.

    A differing land pattern is a **failure**, not a note. The question a change request
    answers is whether the replacement is a drop-in, and SOT-23-5 into a SOT-223 land
    pattern is not one at any price — it is a board revision, new stencils and a new
    qualification. Saying so is the difference between a substitution a buyer can action
    and a suggestion they have to go and check.

    This deliberately checks the land pattern and not pin function. Pin names reach the
    system only for bus masters and only to count GPIOs — `PartSpec` keeps the count, not
    the names — so comparing pinouts would mean a distributor call for every part on every
    board. The package answers the decisive question here and the pin map is recorded as
    unbuilt rather than half-done.
    """
    verdicts: list[Verdict] = []
    for slot_id, slot in board.slots.items():
        if slot.part is None or slot.baseline is None:
            continue
        verdicts.append(_check_footprint_swap(board, slot_id, slot.part, slot.baseline))
    return verdicts or [
        _not_applicable(
            "footprint_compatibility",
            board,
            "No part on this board is replacing another, so there is no land pattern to match.",
        )
    ]


def _check_footprint_swap(
    board: Board, slot_id: str, part: PartSpec, baseline: PartSpec
) -> Verdict:
    evidence = part.cite(slot_id, "package") + (
        Evidence(slot_id, "replacing", f"{baseline.mpn} in {baseline.package}", baseline.datasheet),
    )

    def verdict(status: str, detail: str) -> Verdict:
        return Verdict(
            rule="footprint_compatibility",
            status=status,
            detail=detail,
            subject=slot_id,
            involved=(slot_id,),
            evidence=evidence,
        )

    if not part.package or not baseline.package:
        missing = part.mpn if not part.package else baseline.mpn
        return verdict(
            "evidence_missing",
            f"{missing} states no package, so whether {part.mpn} drops into "
            f"{baseline.mpn}'s land pattern could not be checked.",
        )

    if packages.same_land_pattern(part.package, baseline.package):
        return verdict(
            "satisfied",
            f"{part.mpn} is {part.package}, the same land pattern as {baseline.mpn} — "
            f"a drop-in, with no layout change.",
        )

    return verdict(
        "failed",
        f"{part.mpn} is {part.package} where {baseline.mpn} is {baseline.package}. "
        f"Not a drop-in: the footprint differs, so the board needs a layout revision.",
    )


def temperature_rating(board: Board) -> list[Verdict]:
    """Every placed part must cover the board's required ambient temperature range."""
    verdicts: list[Verdict] = []
    for slot_id, slot in board.slots.items():
        if slot.part is None:
            continue
        verdicts.append(_check_temperature_rating(board, slot_id, slot.part))
    return verdicts


def _check_temperature_rating(board: Board, slot_id: str, part: PartSpec) -> Verdict:
    """Judge each temperature bound independently, citing only the decisive fields."""
    required_min, required_max = board.requirements.temp_range
    cold_failure = part.temp_min is not None and part.temp_min > required_min
    hot_failure = part.temp_max is not None and part.temp_max < required_max

    if cold_failure or hot_failure:
        failed_ends: list[str] = []
        cited: list[str] = []
        if part.temp_min is not None and part.temp_min > required_min:
            failed_ends.append(
                f"the cold end by {fmt.celsius(part.temp_min - required_min)} "
                f"({fmt.celsius(part.temp_min)} versus {fmt.celsius(required_min)})"
            )
            cited.append("temp_min")
        if part.temp_max is not None and part.temp_max < required_max:
            failed_ends.append(
                f"the hot end by {fmt.celsius(required_max - part.temp_max)} "
                f"({fmt.celsius(part.temp_max)} versus {fmt.celsius(required_max)})"
            )
            cited.append("temp_max")
        return Verdict(
            rule="temperature_rating",
            status="failed",
            detail=f"{part.mpn} misses {fmt.listing(failed_ends)}.",
            subject=slot_id,
            involved=(slot_id,),
            evidence=part.cite(slot_id, *cited),
        )

    missing = [
        name
        for name, value in (("temp_min", part.temp_min), ("temp_max", part.temp_max))
        if value is None
    ]
    if missing:
        return Verdict(
            rule="temperature_rating",
            status="evidence_missing",
            detail=(
                f"{part.mpn} states no {fmt.listing(missing)} — its temperature grade "
                "could not be checked."
            ),
            subject=slot_id,
            involved=(slot_id,),
            evidence=part.cite(slot_id, "temp_min", "temp_max"),
        )

    return Verdict(
        rule="temperature_rating",
        status="satisfied",
        detail=(
            f"{part.mpn} is rated {fmt.celsius(part.temp_min)}–{fmt.celsius(part.temp_max)}, "
            f"covering {fmt.celsius(required_min)}–{fmt.celsius(required_max)}."
        ),
        subject=slot_id,
        involved=(slot_id,),
        evidence=part.cite(slot_id, "temp_min", "temp_max"),
    )


# ── footprint · warning only ──────────────────────────────────────────────────


def footprint(board: Board) -> list[Verdict]:
    """Advisory size check. Never fails a board — it only ever raises a flag.

    Silent unless the prompt actually asked for a size limit, since a warning that
    fires on every part is a warning nobody reads.
    """
    ceiling = board.requirements.max_package_mm
    if ceiling is None:
        return []

    verdicts: list[Verdict] = []
    for slot_id, slot in board.slots.items():
        part = slot.part
        if part is None:
            continue
        side = packages.longest_side_mm(part.package)
        if side is None or side <= ceiling:
            continue
        verdicts.append(
            Verdict(
                rule="footprint",
                status="satisfied",
                margin=f"{fmt.num(side - ceiling, 1)} mm over target",
                detail=(
                    f"{part.mpn} in {part.package} is {fmt.num(side, 1)} mm on its longest "
                    f"side, over the {fmt.num(ceiling, 1)} mm target."
                ),
                subject=slot_id,
                involved=(slot_id,),
                evidence=part.cite(slot_id, "package"),
            )
        )
    return verdicts


def rail_coverage(board: Board) -> list[Verdict]:
    """Report a placed part that no rail mentions, and say which checks it therefore missed.

    Three of the eight rules find their operands through a rail — `voltage_overlap`,
    `current_budget` and `thermal_dissipation` all iterate `board.rails`. A part on no rail
    is invisible to all three, and *silently* so: it appeared on the BOM with every check it
    did receive passing, and nothing said that the ones that matter most for a power part
    had never run.

    That silence is the fault this rule fixes. It cannot fix the coverage — checking a solar
    charge controller needs the panel's voltage, which needs a second externally-sourced rail
    that the model does not have. What it can do is refuse to let an unchecked part look
    like a checked one.

    **Always a warning, never a failure.** Nothing is wrong with the board; something is
    missing from what we know about it. A `fail` here would start a repair loop against a
    part that no rule has found any fault with, and there would be nothing for the loop to
    make better.
    """
    verdicts: list[Verdict] = []
    for slot_id in board.unmodelled_slots():
        part = board.part(slot_id)
        if part is None:
            continue
        verdicts.append(
            Verdict(
                rule="rail_coverage",
                status="evidence_missing",
                detail=(
                    f"{part.mpn} is on no modelled power rail, so voltage, current budget "
                    f"and thermal dissipation could not be checked for it. Every other rule "
                    f"ran as normal."
                ),
                subject=slot_id,
                involved=(slot_id,),
                evidence=part.cite(slot_id, "vmin", "vmax"),
            )
        )
    return verdicts


# ── the suite ─────────────────────────────────────────────────────────────────

def energy_budget(board: Board) -> list[Verdict]:
    """How long the board runs on its supply, against how long the brief said it must.

    Every other rule measures an instant: volts now, amps now, degrees now. A brief that
    says *"must last a year"* is asking about charge, and nothing measured charge — so the
    requirement reached no rule, produced no verdict, and was not even reported unchecked.
    Measured 13 Aug on `e-paper badge on a coin cell with BLE, must last a year`, which
    returned **zero conflicts** over a board carrying an ESP8266 module drawing ~70 mA on
    transmit. The brief's headline requirement was the one thing nobody looked at.

    **What this rule will not do is guess a duty cycle.** Runtime is capacity divided by
    *average* draw, and average draw depends on how often the radio wakes — which no
    datasheet states and no distributor publishes. Inventing a plausible-looking duty
    cycle would produce a confident number resting on a figure this system made up.

    So it computes the one runtime that needs no assumption: **continuous draw**, every
    part awake at once. That is a genuine lower bound on life, and it decides one case
    honestly in each direction.

    - Lasts long enough even flat out → `pass`. Nothing about the duty cycle can make it
      worse than the bound, so the requirement is met outright.
    - Does not → `warn`, carrying both figures. It is not a `fail`, because duty cycling
      is exactly how such boards are built and the gap may well be closable. It is not
      silence either, which is what it used to be.

    A missing capacity or an unstated draw is reported as unchecked, naming what is
    missing, rather than defaulting to a number that would make the board look measured.
    """
    required = board.requirements.lifetime_hours
    if required is None:
        return []

    capacity = board.requirements.supply_capacity_mah
    if capacity is None:
        return [
            Verdict(
                rule="energy_budget",
                status="evidence_missing",
                detail=(
                    f"This board is asked to run for {fmt.duration(required)}, but its supply "
                    f"states no capacity, so how long it lasts cannot be checked."
                ),
                subject=_energy_subject(board),
                scope="board",
            )
        ]

    # Summed on the rails the *supply* feeds, not over every slot. `rail_draw` reflects a
    # regulator's output back through the conversion, so a load is counted once rather
    # than twice — once on its own rail and again inside the regulator above it.
    total = 0.0
    unstated: list[str] = []
    for rail in board.rails.values():
        if rail.source is not None:
            continue
        amps, missing = rail_current.rail_draw(board, rail, rail_current.consumers(board, rail))
        total += amps
        unstated += [f"{s} ({p.mpn})" for s in missing if (p := board.part(s)) is not None]

    if unstated:
        return [
            Verdict(
                rule="energy_budget",
                status="evidence_missing",
                detail=(
                    f"This board is asked to run for {fmt.duration(required)} on "
                    f"{capacity:g} mAh, but {fmt.listing(unstated)} "
                    f"{'state' if len(unstated) > 1 else 'states'} no current draw, so the "
                    f"runtime cannot be computed."
                ),
                subject=_energy_subject(board),
                scope="board",
            )
        ]

    if total <= 0:
        return []

    hours = capacity / (total * 1000.0)
    met = hours >= required
    return [
        Verdict(
            rule="energy_budget",
            status="satisfied" if met else "evidence_missing",
            detail=(
                f"{capacity:g} mAh at {total * 1000:.1f} mA continuous is "
                f"{fmt.duration(hours)}, against the {fmt.duration(required)} asked for"
                + (
                    "."
                    if met
                    else " — reaching it needs duty cycling, which is not modelled here."
                )
            ),
            subject=_energy_subject(board),
            scope="board",
        )
    ]


def _energy_subject(board: Board) -> str:
    """The heaviest placed part, so the finding lands on something a person can act on."""
    placed = [(s, p) for s, slot in board.slots.items() if (p := slot.part) is not None]
    if not placed:
        return next(iter(board.slots), "board")
    return max(placed, key=lambda pair: pair[1].draw or 0.0)[0]


RULES = (
    voltage_overlap,
    interface_role_match,
    pin_budget,
    current_budget,
    thermal_dissipation,
    availability,
    part_qualification,
    source_approval,
    footprint,
    footprint_compatibility,
    capacitor_requirements,
    output_capacitor_stability,
    emc,
    signal_integrity,
    temperature_rating,
    energy_budget,
    rail_coverage,
)


def evaluate(board: Board) -> list[Verdict]:
    """Run every rule. Order is stable, so the event stream is reproducible."""
    return [verdict for rule in RULES for verdict in rule(board)]


def failures(verdicts: list[Verdict]) -> list[Verdict]:
    """Everything that failed, waived or not. What a person is owed on screen."""
    return [v for v in verdicts if v.status == "failed"]


def blocking(verdicts: list[Verdict]) -> list[Verdict]:
    """Failures the run must still act on. What the graph routes and repairs on.

    A waiver does not delete a finding or repaint it; it removes the run's obligation to
    fix it. Keeping those two questions apart is what lets an accepted failure stay
    failed on screen while the board goes on to finish.
    """
    return [v for v in verdicts if v.status == "failed" and not v.accepted]


def passing(verdicts: list[Verdict]) -> list[Verdict]:
    return [v for v in verdicts if v.status == "satisfied"]


def for_subject(verdicts: list[Verdict], slot_id: str) -> list[Verdict]:
    """The checks attributed to one slot — what a `check` event stream for it contains."""
    return [v for v in verdicts if v.subject == slot_id]
