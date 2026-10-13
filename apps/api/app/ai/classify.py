"""Classifies elements via jev (Phase P.2) — one jev call per unique `group_hash`, not
per element, since njderidder is paying for jev API usage out of pocket and elements
sharing a group are, by construction, the same type of thing (app/ifc/profile.py).
"""

from sqlalchemy.orm import Session

from app.ai.jev import get_jev_client
from app.db.models import Classification, Element

# No real confidence calibration yet (that's the full plan's Phase 3.6) - a plain
# threshold is a reasonable placeholder. The stub client always returns confidence 0.0,
# so everything correctly routes to needs_review until jev is for-real wired up.
AUTO_ACCEPT_THRESHOLD = 0.8


def classify_elements(db: Session, elements: list[Element]) -> None:
    """Groups the given elements by group_hash, calls jev once per group, and writes
    one Classification row per element, reusing that group's single jev result.
    """
    jev_client = get_jev_client()

    elements_by_group: dict[str, list[Element]] = {}
    for element in elements:
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
