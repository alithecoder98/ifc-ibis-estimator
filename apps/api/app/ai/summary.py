"""Phase 4.3 — project-level stats for the frontend's Overview tab: element/status
counts, totals per IBIS code, and a warnings breakdown. Pure DB-querying function,
same pattern as app/ai/export.py.

"corrected" is always 0 today - app/db/models/classification.py's own Review model
docstring says "Phase 6.1"; no review/correction endpoint exists yet. That's an
honest zero (the mechanism is real and will report real counts once 6.1 ships),
not thin test data.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.db.models import Classification, Element, IfcFile, Quantity, Review

# Which single quantity represents one element in the totals table, in order of
# preference - picking exactly one avoids double-counting net+gross measures of
# the same physical quantity (a wall's Qto commonly reports both). Doesn't
# cross-check against the assigned code's own unit (code_list.unit) - a known
# simplification, not a correctness guarantee for elements whose only available
# quantity doesn't match what their code is normally priced by.
QUANTITY_PRECEDENCE = (
    "area_net",
    "area_gross",
    "volume_net",
    "volume_gross",
    "length",
    "count",
)


@dataclass
class CodeTotal:
    ibis_code: str
    internal_element: str
    unit: str | None
    quantity: float
    element_count: int


@dataclass
class ProjectSummary:
    total_elements: int
    auto_accepted: int
    needs_review: int
    corrected: int
    missing_quantity_count: int
    proxy_element_count: int
    unmapped_count: int
    totals_by_code: list[CodeTotal] = field(default_factory=list)


def latest_classifications_by_element(
    db: Session, element_ids: list[int]
) -> dict[int, Classification]:
    """`created_at` alone isn't a reliable tiebreak - an engine="both" run commits
    both its llm and jev rows together, so they share the same timestamp. `id`
    (always unique, always increasing) makes "latest" deterministic.
    """
    if not element_ids:
        return {}
    rows = (
        db.query(Classification)
        .filter(Classification.element_id.in_(element_ids))
        .order_by(
            Classification.element_id,
            Classification.created_at.desc(),
            Classification.id.desc(),
        )
        .all()
    )
    latest: dict[int, Classification] = {}
    for row in rows:
        if row.element_id not in latest:
            latest[row.element_id] = row
    return latest


def primary_quantity(quantities: list[Quantity]) -> tuple[float, str] | None:
    by_type = {q.quantity_type: q for q in quantities}
    for quantity_type in QUANTITY_PRECEDENCE:
        quantity = by_type.get(quantity_type)
        if quantity is not None:
            # Quantity.value is NUMERIC(14,4) - psycopg returns a real
            # decimal.Decimal here despite the Mapped[float] type hint; mixing
            # that with a plain float accumulator raises TypeError.
            return float(quantity.value), quantity.unit
    return None


def compute_summary(db: Session, project_id: int) -> ProjectSummary:
    ifc_file_ids = [
        f.id for f in db.query(IfcFile).filter(IfcFile.project_id == project_id)
    ]
    elements = (
        db.query(Element).filter(Element.ifc_file_id.in_(ifc_file_ids)).all()
        if ifc_file_ids
        else []
    )
    element_ids = [e.id for e in elements]

    latest_by_element = latest_classifications_by_element(db, element_ids)

    quantities_by_element: dict[int, list[Quantity]] = {}
    if element_ids:
        for quantity in (
            db.query(Quantity).filter(Quantity.element_id.in_(element_ids)).all()
        ):
            quantities_by_element.setdefault(quantity.element_id, []).append(quantity)

    auto_accepted = 0
    needs_review = 0
    missing_quantity_count = 0
    proxy_element_count = 0
    unmapped_count = 0
    # (ibis_code, internal_element, unit) -> [quantity_sum, element_count]
    totals: dict[tuple[str, str, str | None], list] = {}

    for element in elements:
        classification = latest_by_element.get(element.id)
        if classification is None:
            continue

        if classification.status == "auto_accepted":
            auto_accepted += 1
        elif classification.status == "needs_review":
            needs_review += 1

        flags = classification.flags or []
        if "missing_quantity" in flags:
            missing_quantity_count += 1
        if "proxy_element" in flags:
            proxy_element_count += 1
        if classification.ibis_code is None:
            unmapped_count += 1
            continue

        primary = primary_quantity(quantities_by_element.get(element.id, []))
        key = (
            classification.ibis_code,
            classification.internal_element or "",
            primary[1] if primary else None,
        )
        entry = totals.setdefault(key, [0.0, 0])
        if primary:
            entry[0] += primary[0]
        entry[1] += 1

    classification_ids = [c.id for c in latest_by_element.values()]
    corrected_classification_ids = (
        {
            row[0]
            for row in db.query(Review.classification_id)
            .filter(
                Review.classification_id.in_(classification_ids),
                Review.action == "correct",
            )
            .distinct()
        }
        if classification_ids
        else set()
    )

    totals_by_code = [
        CodeTotal(
            ibis_code=code,
            internal_element=name,
            unit=unit,
            quantity=round(qty, 3),
            element_count=count,
        )
        for (code, name, unit), (qty, count) in sorted(totals.items())
    ]

    return ProjectSummary(
        total_elements=len(elements),
        auto_accepted=auto_accepted,
        needs_review=needs_review,
        corrected=len(corrected_classification_ids),
        missing_quantity_count=missing_quantity_count,
        proxy_element_count=proxy_element_count,
        unmapped_count=unmapped_count,
        totals_by_code=totals_by_code,
    )
