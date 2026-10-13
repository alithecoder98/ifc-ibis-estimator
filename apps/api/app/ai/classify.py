"""Classifies elements: deterministic rules first (Phase 3.2), then the project's
configured AI engine(s) for anything a rule didn't cover - jev (Phase P.2), the LLM
(Phase 3.4), or both in parallel (Phase 3.5), each row's final confidence/status
combined by Phase 3.6's compute_confidence(). Engine calls are one per unique
`group_hash`, not per element, since elements sharing a group are, by construction,
the same type of thing (app/ifc/profile.py) - njderidder is paying for jev API usage
out of pocket, and even the free local LLM costs real wall-clock time per call.
"""

from sqlalchemy.orm import Session

from app.ai.confidence import compute_confidence
from app.ai.embedder import get_embedder
from app.ai.jev import get_jev_client
from app.ai.llm import classify_with_llm, get_llm_client, load_estimating_rules
from app.ai.retrieval import shortlist_and_examples
from app.ai.rules import match_rule
from app.db.models import Classification, Element, IfcFile, Project, Quantity, Rule


def _merge_flags(
    engine_flags: list[str] | None, hard_flags: list[str]
) -> list[str] | None:
    """The engine (especially the LLM, which has its own judgment and the same
    flag vocabulary suggested in docs/estimating_rules.md) and Phase 3.6's
    hard_flags() can both independently notice the same thing - e.g. both calling
    an IfcBuildingElementProxy "proxy_element". dict.fromkeys dedupes while
    preserving first-seen order, unlike a set (whose order isn't meaningful here).
    """
    merged = list(dict.fromkeys((engine_flags or []) + hard_flags))
    return merged or None


def classify_elements(db: Session, elements: list[Element]) -> None:
    """Rules are evaluated per element (not per group_hash like the AI engines below
    - group_hash excludes storey, so a storey_keyword rule can still split a group).
    Elements matching an active rule skip the AI engines entirely. Everything else
    groups by group_hash; the project's classification_engine ("llm" | "jev" |
    "both") decides which engine(s) run once per group, writing one Classification
    row per element per engine that ran (two rows per element when "both", with
    `agreement` set on each to whether their ibis_codes matched). Retrieval (and the
    real Ollama embedding call it needs) only runs when the engine uses the LLM -
    jev-only stays fully offline, which every existing worker-integration test (and
    CI, which has no Ollama service at all) relies on for the default "jev" engine.
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

    quantities_by_element: dict[int, list[Quantity]] = {}
    for quantity in (
        db.query(Quantity)
        .filter(Quantity.element_id.in_([e.id for e in remaining]))
        .all()
    ):
        quantities_by_element.setdefault(quantity.element_id, []).append(quantity)

    elements_by_group: dict[str, list[Element]] = {}
    for element in remaining:
        elements_by_group.setdefault(element.group_hash, []).append(element)

    # Scoped to this call only - group_hash is purely content-based, so a
    # module-level cache would hand a *later* job CodeList/ExampleMemory instances
    # still bound to *this* call's session once it closes (see app/ai/retrieval.py).
    retrieval_cache: dict = {}

    for group_elements in elements_by_group.values():
        representative = group_elements[0]

        candidates = None
        llm_result = None
        if use_llm:
            candidates, examples = shortlist_and_examples(
                db,
                embedder,
                representative.group_hash,
                representative.profile_text,
                representative.ifc_class,
                representative.predefined_type,
                retrieval_cache,
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
            quantities = quantities_by_element.get(element.id, [])

            if llm_result is not None:
                confidence = compute_confidence(
                    llm_result.self_score,
                    agreement,
                    llm_result.ibis_code,
                    candidates,
                    element,
                    quantities,
                )
                db.add(
                    Classification(
                        element_id=element.id,
                        ibis_code=llm_result.ibis_code,
                        internal_element=llm_result.internal_element,
                        reasoning=llm_result.reasoning,
                        self_score=llm_result.self_score,
                        confidence=confidence.final_score,
                        flags=_merge_flags(llm_result.flags, confidence.flags),
                        status=confidence.status,
                        source="llm",
                        agreement=agreement,
                    )
                )
            if jev_result is not None:
                confidence = compute_confidence(
                    jev_result.confidence,
                    agreement,
                    jev_result.ibis_code,
                    candidates,
                    element,
                    quantities,
                )
                engine_flags = ["jev_stub"] if jev_result.is_stub else []
                db.add(
                    Classification(
                        element_id=element.id,
                        ibis_code=jev_result.ibis_code,
                        internal_element=jev_result.internal_element,
                        reasoning=jev_result.reasoning,
                        self_score=jev_result.confidence,
                        confidence=confidence.final_score,
                        flags=_merge_flags(engine_flags, confidence.flags),
                        status=confidence.status,
                        source="jev",
                        agreement=agreement,
                    )
                )
