"""Classifies elements: deterministic rules first (Phase 3.2), then the project's
configured AI engine(s) for anything a rule didn't cover - jev (Phase P.2), the LLM
(Phase 3.4), or both in parallel (Phase 3.5). Engine calls are one per unique
`group_hash`, not per element, since elements sharing a group are, by construction,
the same type of thing (app/ifc/profile.py) - njderidder is paying for jev API usage
out of pocket, and even the free local LLM costs real wall-clock time per call.
"""

from sqlalchemy.orm import Session

from app.ai.embedder import get_embedder
from app.ai.jev import get_jev_client
from app.ai.llm import classify_with_llm, get_llm_client, load_estimating_rules
from app.ai.retrieval import shortlist_and_examples
from app.ai.rules import match_rule
from app.db.models import Classification, Element, IfcFile, Project, Rule

# No real confidence calibration yet (that's the full plan's Phase 3.6) - a plain
# threshold is a reasonable placeholder. The stub jev client always returns
# confidence 0.0, so everything from it correctly routes to needs_review until jev
# is for-real wired up.
AUTO_ACCEPT_THRESHOLD = 0.8


def _route_status(confidence: float | None) -> str:
    return (
        "auto_accepted"
        if confidence is not None and confidence >= AUTO_ACCEPT_THRESHOLD
        else "needs_review"
    )


def classify_elements(db: Session, elements: list[Element]) -> None:
    """Rules are evaluated per element (not per group_hash like the AI engines below
    - group_hash excludes storey, so a storey_keyword rule can still split a group).
    Elements matching an active rule skip the AI engines entirely. Everything else
    groups by group_hash; the project's classification_engine ("llm" | "jev" |
    "both") decides which engine(s) run once per group, writing one Classification
    row per element per engine that ran (two rows per element when "both", with
    `agreement` set on each to whether their ibis_codes matched).
    """
    if not elements:
        return

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

    if not remaining:
        return

    ifc_file = db.get(IfcFile, remaining[0].ifc_file_id)
    project = db.get(Project, ifc_file.project_id)
    engine = project.classification_engine

    use_llm = engine in ("llm", "both")
    use_jev = engine in ("jev", "both")

    embedder = get_embedder() if use_llm else None
    llm_client = get_llm_client() if use_llm else None
    rules_text = load_estimating_rules() if use_llm else None
    jev_client = get_jev_client() if use_jev else None

    elements_by_group: dict[str, list[Element]] = {}
    for element in remaining:
        elements_by_group.setdefault(element.group_hash, []).append(element)

    for group_elements in elements_by_group.values():
        representative = group_elements[0]

        llm_result = None
        if use_llm:
            candidates, examples = shortlist_and_examples(
                db,
                embedder,
                representative.group_hash,
                representative.profile_text,
                representative.ifc_class,
                representative.predefined_type,
            )
            llm_result = classify_with_llm(
                llm_client,
                representative.profile_text,
                candidates,
                examples,
                rules_text,
            )

        jev_result = None
        if use_jev:
            jev_result = jev_client.classify(representative.profile_text)

        agreement = (
            llm_result.ibis_code == jev_result.ibis_code
            if llm_result is not None and jev_result is not None
            else None
        )

        for element in group_elements:
            if llm_result is not None:
                db.add(
                    Classification(
                        element_id=element.id,
                        ibis_code=llm_result.ibis_code,
                        internal_element=llm_result.internal_element,
                        reasoning=llm_result.reasoning,
                        self_score=llm_result.self_score,
                        confidence=llm_result.self_score,
                        flags=llm_result.flags or None,
                        status=_route_status(llm_result.self_score),
                        source="llm",
                        agreement=agreement,
                    )
                )
            if jev_result is not None:
                flags = ["jev_stub"] if jev_result.is_stub else None
                db.add(
                    Classification(
                        element_id=element.id,
                        ibis_code=jev_result.ibis_code,
                        internal_element=jev_result.internal_element,
                        reasoning=jev_result.reasoning,
                        self_score=jev_result.confidence,
                        confidence=jev_result.confidence,
                        flags=flags,
                        status=_route_status(jev_result.confidence),
                        source="jev",
                        agreement=agreement,
                    )
                )
