"""Classifies elements: deterministic rules first (Phase 3.2), then jev for anything
a rule didn't cover (Phase P.2) - one jev call per unique `group_hash`, not per
element, since njderidder is paying for jev API usage out of pocket and elements
sharing a group are, by construction, the same type of thing (app/ifc/profile.py).
"""

from sqlalchemy.orm import Session

from app.ai.jev import get_jev_client
from app.ai.rules import match_rule
from app.db.models import Classification, Element, Rule

# No real confidence calibration yet (that's the full plan's Phase 3.6) - a plain
# threshold is a reasonable placeholder. The stub client always returns confidence 0.0,
# so everything correctly routes to needs_review until jev is for-real wired up.
AUTO_ACCEPT_THRESHOLD = 0.8


def classify_elements(db: Session, elements: list[Element]) -> None:
    """Rules are evaluated per element (not per group_hash like jev below -
    group_hash excludes storey, so a storey_keyword rule can still split a jev
    group). Elements matching an active rule skip jev entirely. Everything else
    groups by group_hash, calls jev once per group, and gets one Classification
    row per element, reusing that group's single jev result.
    """
    active_rules = db.query(Rule).filter(Rule.status == "active").all()

    remaining: list[Element] = []
    for element in elements:
        rule = match_rule(element, active_rules)
        if rule is None:
            remaining.append(element)
            continue
        db.add(
            Classification(
                element_id=element.id,
                ibis_code=rule.result_ibis_code,
                internal_element=rule.result_internal_element,
                reasoning=f"matched rule #{rule.id} (priority {rule.priority})",
                self_score=1.0,
                confidence=1.0,
                status="auto_accepted",
                source="rule",
            )
        )

    jev_client = get_jev_client()

    elements_by_group: dict[str, list[Element]] = {}
    for element in remaining:
        elements_by_group.setdefault(element.group_hash, []).append(element)

    for group_elements in elements_by_group.values():
        representative = group_elements[0]
        result = jev_client.classify(representative.profile_text)

        status = (
            "auto_accepted"
            if result.confidence is not None
            and result.confidence >= AUTO_ACCEPT_THRESHOLD
            else "needs_review"
        )
        flags = ["jev_stub"] if result.is_stub else None

        db.add_all(
            Classification(
                element_id=element.id,
                ibis_code=result.ibis_code,
                internal_element=result.internal_element,
                reasoning=result.reasoning,
                self_score=result.confidence,
                confidence=result.confidence,
                flags=flags,
                status=status,
                source="jev",
            )
            for element in group_elements
        )
