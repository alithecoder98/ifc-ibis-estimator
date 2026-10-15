"""Phase 6.5 — "repeated correction patterns become suggested rules an admin
approves" (charter step 5). Scans every "correct" review, groups corrections by
(element.group_hash, resulting ibis_code) - group_hash already encodes "same
construction type" (ifc_class/predefined_type/materials/is_external/load_bearing,
see app/ifc/profile.py's compute_group_hash) - and once a pattern has been
corrected to the same code MIN_OCCURRENCES+ times, proposes a new Rule with
status="suggested" for an admin to review in the existing Rules tab (built in
4.6, which already renders "suggested" rules - this only needed something to
populate them, not new UI).

Deliberately admin-triggered (POST /rules/suggest), not a background scan on every
correction - same "simple, no new job infra" reasoning as scripts/load_initial_rules.py
being a one-off script rather than automatic.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import Classification, Element, Review, Rule

# How many times the same construction-type-pattern must be corrected to the
# same code before it's worth proposing as a rule. Low enough to catch real
# repetition within a single mid-size project, high enough that one or two
# one-off corrections (which may just be mistakes, not a pattern) don't spam
# suggestions - a tunable constant, not a measured/calibrated threshold (no
# real correction history exists yet to calibrate against).
MIN_OCCURRENCES = 3


@dataclass
class RuleSuggestionResult:
    created: list[Rule]
    # Patterns that met the occurrence threshold but were skipped because an
    # existing rule (any status) already covers the same conditions+result -
    # surfaced so the admin-triggered endpoint can report "N created, M
    # already covered" instead of silently doing nothing on a second run.
    already_covered_count: int


def _build_conditions(element: Element) -> list[dict]:
    """Same {field, operator, value} shape app/ai/rules.py's engine evaluates.
    Deliberately conservative: ifc_class always, predefined_type and the
    first material's name only when present - narrow enough to avoid
    over-matching unrelated elements, not so narrow (e.g. exact thickness)
    that it only ever matches the exact elements that triggered it.
    """
    conditions = [{"field": "ifc_class", "operator": "==", "value": element.ifc_class}]
    if element.predefined_type:
        conditions.append(
            {
                "field": "predefined_type",
                "operator": "==",
                "value": element.predefined_type,
            }
        )
    materials = element.materials or []
    if materials and materials[0].get("material"):
        conditions.append(
            {
                "field": "material_keyword",
                "operator": "contains",
                "value": materials[0]["material"],
            }
        )
    return conditions


def generate_rule_suggestions(db: Session) -> RuleSuggestionResult:
    corrections = (
        db.query(Review, Classification, Element)
        .join(Classification, Review.classification_id == Classification.id)
        .join(Element, Classification.element_id == Element.id)
        .filter(Review.action == "correct")
        .all()
    )

    groups: dict[tuple[str, str], list[tuple[Review, Classification, Element]]] = {}
    for review, classification, element in corrections:
        if not element.group_hash or not classification.ibis_code:
            continue
        key = (element.group_hash, classification.ibis_code)
        groups.setdefault(key, []).append((review, classification, element))

    existing_rules = db.query(Rule).all()

    created: list[Rule] = []
    already_covered_count = 0
    for (_group_hash, ibis_code), items in groups.items():
        if len(items) < MIN_OCCURRENCES:
            continue

        sample_element = items[0][2]
        conditions = _build_conditions(sample_element)

        covered = any(
            r.conditions == conditions and r.result_ibis_code == ibis_code
            for r in existing_rules
        )
        if covered:
            already_covered_count += 1
            continue

        internal_element = items[0][1].internal_element or ""
        rule = Rule(
            conditions=conditions,
            result_ibis_code=ibis_code,
            result_internal_element=internal_element,
            priority=0,
            status="suggested",
            source_corrections=[review.id for review, _, _ in items],
        )
        db.add(rule)
        created.append(rule)

    db.flush()
    return RuleSuggestionResult(
        created=created, already_covered_count=already_covered_count
    )
