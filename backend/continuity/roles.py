"""Which desk a decision belongs to.

Shared by the graph, which asks it when a run stops for an answer, and the substitution
matrix, which asks it to say who owns each failing cell. Neither is the natural owner of
the other's copy, and two copies of a routing table is how a rule ends up going to
procurement on one screen and engineering on another.

Deliberately not in `engine/`: the engine knows about circuits and nothing about people,
and a rule that returned a job title would be the first thing in it that did.
"""

from __future__ import annotations


ROLES_BY_RULE: dict[str, tuple[str, ...]] = {
    # Whether a part can be bought, and on what terms, is a buying judgement.
    "availability": ("procurement",),
    # Qualifying a part for a shipping product is engineering's call and quality's record,
    # and it needs both: engineering says the part is right, quality says it is allowed.
    "part_qualification": ("engineering", "quality"),
    # Who we buy from is procurement's alone. The part is already qualified in this case —
    # what is in question is the source, which engineering has no standing to approve.
    "source_approval": ("procurement",),
    # Everything else the engine decides is a question about the circuit.
    "voltage_overlap": ("engineering",),
    "current_budget": ("engineering",),
    "thermal_dissipation": ("engineering",),
    "pin_budget": ("engineering",),
    "interface_role_match": ("engineering",),
    "footprint": ("engineering",),
    "footprint_compatibility": ("engineering",),
    "capacitor_requirements": ("engineering",),
    "temperature_rating": ("engineering",),
    "energy_budget": ("engineering",),
    "rail_coverage": ("engineering",),
    "output_capacitor_stability": ("engineering",),
    "emc": ("engineering",),
    "signal_integrity": ("engineering",),
}
"""Who is qualified to answer when a rule fails and the run stops to ask.

The permission belongs to the *question*, not to the person. Whether an LDO's 159 °C
junction is acceptable is an engineering judgement; whether a distributor is an approved
source is not, and no property of a user can tell those two apart — which is why
organisation membership alone is not enough to authorise an answer.

`tests/test_roles.py` reads the rule names out of `rules.py` and asserts every one appears
here, so a rule added later cannot quietly inherit the fallback and route a circuit
question to the wrong desk.
"""

DEFAULT_DECISION_ROLES = ("engineering",)
"""Where an unmapped rule goes.

Deliberate rather than incidental: an unmapped *electrical* rule reaching procurement is
precisely the failure this exists to prevent, and engineering is the safe direction to be
wrong in. The map is tested for completeness so this should never fire — it is the floor
under a mistake, not a mechanism.
"""


def decision_roles(conflict) -> tuple[str, ...]:
    if conflict is None:
        return DEFAULT_DECISION_ROLES
    return ROLES_BY_RULE.get(conflict.rule, DEFAULT_DECISION_ROLES)
