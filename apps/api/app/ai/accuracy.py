"""Phase P.4 — compares jev's suggested IBIS codes against manually-verified reference
calculations. Scoped down from the full plan's 2.7/3.8 evaluation harness per Phase P:
just an accuracy % and a mismatch list, not cost tracking or per-family breakdowns.

Pure DB-querying function, same pattern as app/ai/export.py; the thin CLI lives in
scripts/compare_accuracy.py.

Self-tested against our own fixtures only (see tests/test_accuracy.py) - there is no
real ground truth yet. njderidder said he's gathering manually-verified reference
calculations; until those arrive, this script has nothing real to measure against.
"""

import csv
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Classification, Element, IfcFile


def load_ground_truth(path: Path) -> dict[str, str]:
    """Reads a minimal 2-column CSV: global_id,expected_ibis_code."""
    with open(path, newline="", encoding="utf-8") as fh:
        return {
            row["global_id"]: row["expected_ibis_code"] for row in csv.DictReader(fh)
        }


def compare_accuracy(
    db: Session, project_id: int, ground_truth: dict[str, str]
) -> dict:
    ifc_file_ids = [
        f.id for f in db.query(IfcFile).filter(IfcFile.project_id == project_id)
    ]
    elements = (
        db.query(Element).filter(Element.ifc_file_id.in_(ifc_file_ids)).all()
        if ifc_file_ids
        else []
    )

    compared = 0
    correct = 0
    mismatches = []
    not_in_ground_truth = []

    for element in elements:
        if element.global_id not in ground_truth:
            not_in_ground_truth.append(element.global_id)
            continue

        expected = ground_truth[element.global_id]
        classification = (
            db.query(Classification)
            .filter(Classification.element_id == element.id)
            .order_by(Classification.created_at.desc())
            .first()
        )
        actual = classification.ibis_code if classification else None

        compared += 1
        if actual == expected:
            correct += 1
        else:
            mismatches.append(
                {
                    "global_id": element.global_id,
                    "name": element.name,
                    "ifc_class": element.ifc_class,
                    "expected_ibis_code": expected,
                    "actual_ibis_code": actual,
                }
            )

    return {
        "compared": compared,
        "correct": correct,
        "accuracy_percent": (correct / compared * 100) if compared else 0.0,
        "mismatches": mismatches,
        "elements_not_in_ground_truth": not_in_ground_truth,
    }
