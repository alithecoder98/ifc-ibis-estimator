"""Builds the minimal CSV export for Phase P.3 — one row per element: identity,
quantities summary, and its jev classification. Pure function over already-queried
rows, so it's testable without a DB; the thin endpoint lives in app/routers/projects.py.

CSV over an Excel template or a frontend page, deliberately: njderidder needs to open
something and see results without running code — a downloadable CSV satisfies that
with zero new dependencies and zero new frontend pages, both of which would eat into
the 1-2 day budget disproportionately for a trust-based, pre-contract experiment.
"""

import csv
import io

from app.db.models import Classification, Element, Quantity

FIELDNAMES = [
    "ifc_file_id",
    "global_id",
    "ifc_class",
    "name",
    "storey",
    "quantities",
    "suggested_ibis_code",
    "suggested_internal_element",
    "confidence",
    "status",
    "reasoning",
]


def _format_quantities(quantities: list[Quantity]) -> str:
    return ", ".join(
        f"{q.quantity_type}={float(q.value):.2f}{q.unit}"
        for q in sorted(quantities, key=lambda q: q.quantity_type)
    )


def build_export_csv(
    rows: list[tuple[Element, list[Quantity], Classification | None]],
) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDNAMES)
    writer.writeheader()
    for element, quantities, classification in rows:
        writer.writerow(
            {
                "ifc_file_id": element.ifc_file_id,
                "global_id": element.global_id,
                "ifc_class": element.ifc_class,
                "name": element.name or "",
                "storey": element.storey or "",
                "quantities": _format_quantities(quantities),
                "suggested_ibis_code": (
                    classification.ibis_code if classification else ""
                ),
                "suggested_internal_element": (
                    classification.internal_element if classification else ""
                ),
                "confidence": (
                    classification.confidence if classification is not None else ""
                ),
                "status": classification.status if classification else "not_classified",
                "reasoning": classification.reasoning if classification else "",
            }
        )
    return buffer.getvalue()
