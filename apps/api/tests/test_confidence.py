"""Phase 3.6: confidence combination and routing.

Pure unit tests over plain (unpersisted) Element/CodeList/Quantity instances - no DB
needed, matching app/ai/rules.py's test style.
"""

from app.ai.confidence import (
    agreement_score,
    completeness_score,
    compute_confidence,
    hard_flags,
    shortlist_rank_score,
)
from app.db.models import CodeList, Element, Quantity

CANDIDATES = [
    CodeList(ibis_code="21.10", internal_element="A", family="wall"),
    CodeList(ibis_code="21.20", internal_element="B", family="wall"),
    CodeList(ibis_code="21.30", internal_element="C", family="wall"),
]


def _complete_element(**overrides) -> Element:
    defaults = dict(
        ifc_class="IfcWall",
        is_external=True,
        materials=[{"material": "Concrete", "thickness_mm": 200.0}],
    )
    defaults.update(overrides)
    return Element(**defaults)


def _quantity() -> list[Quantity]:
    return [Quantity(quantity_type="area_net", value=10.0, unit="m2", source="qto")]


def test_agreement_score() -> None:
    assert agreement_score(True) == 1.0
    assert agreement_score(False) == 0.0
    assert agreement_score(None) == 0.5


def test_shortlist_rank_score_best_match() -> None:
    assert shortlist_rank_score("21.10", CANDIDATES) == 1.0


def test_shortlist_rank_score_worst_match() -> None:
    assert shortlist_rank_score("21.30", CANDIDATES) == 0.0


def test_shortlist_rank_score_middle_match() -> None:
    assert shortlist_rank_score("21.20", CANDIDATES) == 0.5


def test_shortlist_rank_score_code_not_in_candidates() -> None:
    assert shortlist_rank_score("99.99", CANDIDATES) == 0.0


def test_shortlist_rank_score_none_code() -> None:
    assert shortlist_rank_score(None, CANDIDATES) == 0.0


def test_shortlist_rank_score_candidates_not_computed_is_neutral() -> None:
    # None (not []) means retrieval wasn't run for this engine at all (jev-only) -
    # there's no shortlist to have been ranked within, so this isn't the same as a
    # real 0.0 "code wasn't in the list that was checked".
    assert shortlist_rank_score("21.10", None) == 0.5


def test_shortlist_rank_score_single_candidate() -> None:
    assert shortlist_rank_score("21.10", [CANDIDATES[0]]) == 1.0


def test_completeness_score_full_marks() -> None:
    assert completeness_score(_complete_element(), _quantity()) == 1.0


def test_completeness_score_missing_everything() -> None:
    element = Element(ifc_class="IfcBuildingElementProxy")
    assert completeness_score(element, []) == 0.0


def test_completeness_score_partial() -> None:
    element = Element(ifc_class="IfcWall", is_external=True, materials=None)
    assert completeness_score(element, _quantity()) == 0.75


def test_hard_flags_proxy_element() -> None:
    element = _complete_element(ifc_class="IfcBuildingElementProxy")
    assert "proxy_element" in hard_flags(element, _quantity(), "21.10")


def test_hard_flags_missing_quantity() -> None:
    element = _complete_element()
    assert "missing_quantity" in hard_flags(element, [], "21.10")


def test_hard_flags_composite_element() -> None:
    element = _complete_element(
        materials=[
            {"material": "Concrete", "thickness_mm": 150.0},
            {"material": "Insulation", "thickness_mm": 50.0},
        ]
    )
    assert "composite_element" in hard_flags(element, _quantity(), "21.10")


def test_hard_flags_unknown_material() -> None:
    element = _complete_element(materials=None)
    assert "unknown_material" in hard_flags(element, _quantity(), "21.10")


def test_hard_flags_code_none() -> None:
    element = _complete_element()
    assert "code_none" in hard_flags(element, _quantity(), None)


def test_hard_flags_clean_element_has_none() -> None:
    element = _complete_element()
    assert hard_flags(element, _quantity(), "21.10") == []


def test_compute_confidence_clean_high_score_auto_accepts() -> None:
    result = compute_confidence(
        self_score=0.95,
        agreement=True,
        ibis_code="21.10",
        candidates=CANDIDATES,
        element=_complete_element(),
        quantities=_quantity(),
        threshold=0.8,
    )
    assert result.flags == []
    assert result.status == "auto_accepted"
    assert 0.0 <= result.final_score <= 1.0


def test_compute_confidence_hard_flag_forces_review_despite_high_score() -> None:
    result = compute_confidence(
        self_score=0.99,
        agreement=True,
        ibis_code="21.10",
        candidates=CANDIDATES,
        element=_complete_element(ifc_class="IfcBuildingElementProxy"),
        quantities=_quantity(),
        threshold=0.8,
    )
    assert "proxy_element" in result.flags
    assert result.status == "needs_review"


def test_compute_confidence_low_score_needs_review() -> None:
    result = compute_confidence(
        self_score=0.1,
        agreement=False,
        ibis_code="21.30",
        candidates=CANDIDATES,
        element=_complete_element(),
        quantities=_quantity(),
        threshold=0.8,
    )
    assert result.status == "needs_review"


def test_compute_confidence_uses_settings_default_threshold() -> None:
    # No threshold passed - falls back to settings.auto_accept_threshold (0.8 by
    # default), not an error or a different hardcoded value.
    result = compute_confidence(
        self_score=0.95,
        agreement=True,
        ibis_code="21.10",
        candidates=CANDIDATES,
        element=_complete_element(),
        quantities=_quantity(),
    )
    assert result.status == "auto_accepted"
