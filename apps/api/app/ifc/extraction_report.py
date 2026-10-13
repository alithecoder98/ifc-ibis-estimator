"""Phase 2.7 — compares extracted elements/quantities against a ground-truth CSV:
element coverage, missing elements by class, and quantity deviation per expected code.

Ground-truth CSV format follows docs/PROMPTS.md's 0.3 spec (that sub-phase's loader
was never built - Phase 0 is blocked on client data - so this ships its own minimal
Pydantic-validated loader rather than wait for a separate phase, same call as 2.6 not
waiting on a standalone fragments service):
    file, global_id, expected_ibis_code, expected_internal_element, expected_quantity,
    unit, notes

For a missing element, the ground-truth format has no `ifc_class` column, so the only
honest way to report "missing by class" is to look the GlobalId up in the raw IFC file
itself (open once per referenced file) - not guess a class from the expected code.

Self-tested only (see tests/test_extraction_report.py) - there is no real ground truth
yet. njderidder's reference data would unblock this the same way it would P.4.
"""

import csv
from collections import Counter
from pathlib import Path

import ifcopenshell
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import Element, IfcFile, Quantity
from app.storage import download_to_path


class GroundTruthRow(BaseModel):
    file: str
    global_id: str
    expected_ibis_code: str | None = None
    expected_internal_element: str | None = None
    expected_quantity: float | None = None
    unit: str | None = None
    notes: str | None = None


def load_ground_truth(path: Path) -> list[GroundTruthRow]:
    # csv.DictReader gives "" for empty cells, not None - normalise before validation
    # so optional fields (expected_quantity in particular) don't fail float parsing on
    # an empty string.
    with open(path, newline="", encoding="utf-8") as fh:
        return [
            GroundTruthRow(**{k: (v or None) for k, v in row.items()})
            for row in csv.DictReader(fh)
        ]


def _lookup_ifc_class(ifc_file: IfcFile, global_id: str, tmp_dir: Path) -> str | None:
    """Opens the raw IFC file to find a missing element's class. Returns None if the
    GlobalId doesn't exist in the file at all - a ground-truth data error, not an
    extraction bug.
    """
    local_path = tmp_dir / f"{ifc_file.id}.ifc"
    if not local_path.exists():
        download_to_path(ifc_file.storage_key, local_path)
    opened = ifcopenshell.open(str(local_path))
    try:
        return opened.by_guid(global_id).is_a()
    except RuntimeError:
        return None


def compare_extraction(
    db: Session, project_id: int, ground_truth: list[GroundTruthRow], tmp_dir: Path
) -> dict:
    ifc_files = db.query(IfcFile).filter(IfcFile.project_id == project_id).all()
    ifc_file_by_filename = {f.filename: f for f in ifc_files}

    unmatched_files: list[str] = []
    missing: list[dict] = []
    deviations: list[dict] = []
    matched = 0

    for row in ground_truth:
        ifc_file = ifc_file_by_filename.get(row.file)
        if ifc_file is None:
            unmatched_files.append(row.file)
            continue

        element = (
            db.query(Element)
            .filter(
                Element.ifc_file_id == ifc_file.id, Element.global_id == row.global_id
            )
            .first()
        )
        if element is None:
            missing.append(
                {
                    "file": row.file,
                    "global_id": row.global_id,
                    "ifc_class": _lookup_ifc_class(ifc_file, row.global_id, tmp_dir),
                }
            )
            continue

        matched += 1
        if row.expected_quantity is not None and row.unit is not None:
            quantities = (
                db.query(Quantity).filter(Quantity.element_id == element.id).all()
            )
            quantity = next(
                (
                    q
                    for q in quantities
                    if q.unit.strip().lower() == row.unit.strip().lower()
                ),
                None,
            )
            if quantity is None:
                deviations.append(
                    {
                        "global_id": row.global_id,
                        "expected_ibis_code": row.expected_ibis_code,
                        "expected_quantity": row.expected_quantity,
                        "actual_quantity": None,
                        "unit": row.unit,
                        "deviation_percent": None,
                    }
                )
            else:
                actual = float(quantity.value)
                deviation_percent = (
                    (actual - row.expected_quantity) / row.expected_quantity * 100
                    if row.expected_quantity != 0
                    else None
                )
                deviations.append(
                    {
                        "global_id": row.global_id,
                        "expected_ibis_code": row.expected_ibis_code,
                        "expected_quantity": row.expected_quantity,
                        "actual_quantity": actual,
                        "unit": row.unit,
                        "deviation_percent": deviation_percent,
                    }
                )

    comparable = len(ground_truth) - len(unmatched_files)
    missing_by_class = Counter(m["ifc_class"] or "not in IFC file" for m in missing)

    deviation_by_code: dict[str, list[float]] = {}
    for d in deviations:
        if d["deviation_percent"] is not None:
            code = d["expected_ibis_code"] or "(no code)"
            deviation_by_code.setdefault(code, []).append(abs(d["deviation_percent"]))
    avg_deviation_by_code = {
        code: sum(values) / len(values) for code, values in deviation_by_code.items()
    }

    return {
        "total_rows": len(ground_truth),
        "unmatched_files": unmatched_files,
        "comparable_rows": comparable,
        "matched": matched,
        "element_coverage_percent": (matched / comparable * 100) if comparable else 0.0,
        "missing": missing,
        "missing_by_class": dict(missing_by_class),
        "deviations": deviations,
        "avg_deviation_percent_by_code": avg_deviation_by_code,
    }


def render_markdown_report(report: dict, project_id: int) -> str:
    lines = [
        f"# Extraction report — project {project_id}",
        "",
        f"- Ground-truth rows: {report['total_rows']}",
        f"- Comparable rows (file matched a project IFC file): {report['comparable_rows']}",
        f"- Element coverage: {report['element_coverage_percent']:.1f}% "
        f"({report['matched']}/{report['comparable_rows']})",
    ]
    if report["unmatched_files"]:
        lines.append(
            f"- Ground-truth rows referencing files not in this project: "
            f"{len(report['unmatched_files'])}"
        )

    lines += ["", "## Missing elements by class", ""]
    if report["missing_by_class"]:
        lines += ["| Class | Count |", "|---|---|"]
        for ifc_class, count in sorted(
            report["missing_by_class"].items(), key=lambda kv: -kv[1]
        ):
            lines.append(f"| {ifc_class} | {count} |")
    else:
        lines.append("None.")

    lines += ["", "## Quantity deviation per expected code", ""]
    if report["avg_deviation_percent_by_code"]:
        lines += ["| Code | Avg abs deviation % |", "|---|---|"]
        for code, avg in sorted(report["avg_deviation_percent_by_code"].items()):
            lines.append(f"| {code} | {avg:.1f}% |")
    else:
        lines.append("No comparable quantities.")

    return "\n".join(lines) + "\n"
