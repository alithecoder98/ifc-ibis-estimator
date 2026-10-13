"""Phase 3.6 — combines self_score, rule/LLM/jev agreement, the chosen code's rank
within 3.3's shortlist, and element data completeness into one final confidence
score; hard flags force needs_review regardless of that score.

The combination weights below are a reasoned placeholder, not calibrated - only the
*threshold* applied to the resulting score is calibrated against ground truth
(scripts/calibrate.py). Recalibrating the weights themselves needs enough real
labeled data to do a proper regression, not just a threshold sweep; deferred until
there's enough of it to do that honestly, same blocked-on-client-data status as the
threshold's own real calibration run.
"""

from dataclasses import dataclass

from app.core.config import get_settings
from app.db.models import CodeList, Element, Quantity

SELF_SCORE_WEIGHT = 0.5
AGREEMENT_WEIGHT = 0.2
SHORTLIST_RANK_WEIGHT = 0.15
COMPLETENESS_WEIGHT = 0.15


def agreement_score(agreement: bool | None) -> float:
    if agreement is True:
        return 1.0
    if agreement is False:
        return 0.0
    return 0.5  # single-engine run - nothing to agree or disagree with


def shortlist_rank_score(
    ibis_code: str | None, candidates: list[CodeList] | None
) -> float:
    """candidates is None (not just empty) when retrieval wasn't run for this engine
    at all - jev-only runs don't compute a shortlist, since jev doesn't consume one
    to produce its own answer, so there's no rank to be penalised for lacking.
    Scored neutral (0.5) in that case, not 0.0.
    """
    if candidates is None:
        return 0.5
    if ibis_code is None:
        return 0.0
    codes = [c.ibis_code for c in candidates]
    if ibis_code not in codes:
        return 0.0
    if len(codes) <= 1:
        return 1.0
    rank = codes.index(ibis_code)
    return 1.0 - (rank / (len(codes) - 1))


def completeness_score(element: Element, quantities: list[Quantity]) -> float:
    score = 0.0
    if quantities:
        score += 0.25
    if element.materials:
        score += 0.25
    if element.is_external is not None:
        score += 0.25
    if element.ifc_class != "IfcBuildingElementProxy":
        score += 0.25
    return score


def hard_flags(
    element: Element, quantities: list[Quantity], ibis_code: str | None
) -> list[str]:
    flags = []
    if element.ifc_class == "IfcBuildingElementProxy":
        flags.append("proxy_element")
    if not quantities:
        flags.append("missing_quantity")
    if element.materials and len(element.materials) > 1:
        flags.append("composite_element")
    if not element.materials:
        flags.append("unknown_material")
    if ibis_code is None:
        flags.append("code_none")
    return flags


@dataclass
class ConfidenceResult:
    final_score: float
    flags: list[str]
    status: str  # auto_accepted | needs_review


def compute_confidence(
    self_score: float | None,
    agreement: bool | None,
    ibis_code: str | None,
    candidates: list[CodeList] | None,
    element: Element,
    quantities: list[Quantity],
    threshold: float | None = None,
) -> ConfidenceResult:
    if threshold is None:
        threshold = get_settings().auto_accept_threshold

    final_score = (
        SELF_SCORE_WEIGHT * (self_score or 0.0)
        + AGREEMENT_WEIGHT * agreement_score(agreement)
        + SHORTLIST_RANK_WEIGHT * shortlist_rank_score(ibis_code, candidates)
        + COMPLETENESS_WEIGHT * completeness_score(element, quantities)
    )
    flags = hard_flags(element, quantities, ibis_code)
    status = (
        "needs_review"
        if flags
        else ("auto_accepted" if final_score >= threshold else "needs_review")
    )
    return ConfidenceResult(final_score=final_score, flags=flags, status=status)
