"""Phase 3.6 — picks the lowest auto-accept threshold where precision clears a
target (95% per the plan) against ground truth, and reports the resulting
auto-accept rate. Backs scripts/calibrate.py.

Reuses app.ai.accuracy's ground-truth CSV format/loader (global_id,
expected_ibis_code) rather than inventing another one - same client-data blocker as
P.4/2.7, so this is self-tested only until njderidder's reference calculations
arrive (see tests/test_calibrate.py).
"""

from sqlalchemy.orm import Session

from app.db.models import Classification, Element, IfcFile


def gather_scored_rows(
    db: Session, project_id: int, ground_truth: dict[str, str]
) -> list[tuple[float, bool]]:
    """Returns (confidence, is_correct) for every element that has both a ground
    truth row and a stored classification with a confidence value - the raw input
    pick_threshold() sweeps over.
    """
    ifc_file_ids = [
        f.id for f in db.query(IfcFile).filter(IfcFile.project_id == project_id)
    ]
    elements = (
        db.query(Element).filter(Element.ifc_file_id.in_(ifc_file_ids)).all()
        if ifc_file_ids
        else []
    )

    rows = []
    for element in elements:
        if element.global_id not in ground_truth:
            continue
        # id DESC as a tiebreak: an engine="both" run commits its llm and jev
        # rows together, so created_at alone isn't reliably ordered (found in
        # Phase 4.3 while building the same "latest classification" lookup).
        classification = (
            db.query(Classification)
            .filter(Classification.element_id == element.id)
            .order_by(Classification.created_at.desc(), Classification.id.desc())
            .first()
        )
        if classification is None or classification.confidence is None:
            continue
        expected = ground_truth[element.global_id]
        rows.append((classification.confidence, classification.ibis_code == expected))
    return rows


def pick_threshold(
    scored_rows: list[tuple[float, bool]], target_precision: float = 0.95
) -> dict:
    """Scans candidate thresholds (every distinct confidence value present, plus
    the 0.0/1.0 edges) from lowest to highest and returns the first one where
    "would be auto-accepted at this threshold" has precision >= target_precision.
    If none clears it, returns threshold=1.0, achieved=False - nothing would be
    safely auto-acceptable at any threshold on this data.
    """
    if not scored_rows:
        return {
            "threshold": 1.0,
            "precision": None,
            "auto_accept_rate": 0.0,
            "achieved": False,
        }

    candidate_thresholds = sorted({round(c, 4) for c, _ in scored_rows} | {0.0, 1.0})

    for threshold in candidate_thresholds:
        accepted = [
            is_correct
            for confidence, is_correct in scored_rows
            if confidence >= threshold
        ]
        if not accepted:
            continue
        precision = sum(accepted) / len(accepted)
        if precision >= target_precision:
            return {
                "threshold": threshold,
                "precision": precision,
                "auto_accept_rate": len(accepted) / len(scored_rows),
                "achieved": True,
            }

    return {
        "threshold": 1.0,
        "precision": None,
        "auto_accept_rate": 0.0,
        "achieved": False,
    }
