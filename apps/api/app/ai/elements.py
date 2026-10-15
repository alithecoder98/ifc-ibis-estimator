"""Phase 4.4 — one row per element for the frontend's Elements tab (TanStack Table +
virtualisation, entirely client-side filtering/sorting/grouping against this one
full list - see CLAUDE.md's 4.4 entry for why server-side paging isn't built: at
realistic JSON sizes even 5,000+ rows fits comfortably in memory, and
virtualisation, the plan's own first-named solution, is what actually solves the
rendering-performance problem).
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ai.retrieval import guess_family
from app.ai.summary import latest_classifications_by_element, primary_quantity
from app.db.models import Element, IfcFile, Quantity


@dataclass
class ElementRow:
    id: int
    global_id: str
    name: str | None
    ifc_class: str
    storey: str | None
    material: str | None
    quantity: float | None
    unit: str | None
    family: str
    group_hash: str
    suggested_ibis_code: str | None
    internal_element: str | None
    confidence: float | None
    status: str | None
    # True once this element has been split into material layers (Phase
    # 6.2) - still shown in this table for context (an estimator should be
    # able to see that the original row was split, not have it vanish), but
    # its own quantity is excluded from summary/export totals in favor of
    # its new children's, which are real rows in this same list.
    is_split_parent: bool


def _material_summary(materials: list[dict] | None) -> str | None:
    if not materials:
        return None
    names = [m.get("material") for m in materials if m.get("material")]
    return ", ".join(names) if names else None


def list_element_rows(db: Session, project_id: int) -> list[ElementRow]:
    ifc_file_ids = [
        f.id for f in db.query(IfcFile).filter(IfcFile.project_id == project_id)
    ]
    elements = (
        db.query(Element).filter(Element.ifc_file_id.in_(ifc_file_ids)).all()
        if ifc_file_ids
        else []
    )
    element_ids = [e.id for e in elements]

    split_parent_ids = (
        {
            row[0]
            for row in db.query(Element.parent_element_id)
            .filter(Element.parent_element_id.in_(element_ids))
            .distinct()
        }
        if element_ids
        else set()
    )

    latest_by_element = latest_classifications_by_element(db, element_ids)

    quantities_by_element: dict[int, list[Quantity]] = {}
    if element_ids:
        for quantity in (
            db.query(Quantity).filter(Quantity.element_id.in_(element_ids)).all()
        ):
            quantities_by_element.setdefault(quantity.element_id, []).append(quantity)

    rows = []
    for element in elements:
        classification = latest_by_element.get(element.id)
        primary = primary_quantity(quantities_by_element.get(element.id, []))
        rows.append(
            ElementRow(
                id=element.id,
                global_id=element.global_id,
                name=element.name,
                ifc_class=element.ifc_class,
                storey=element.storey,
                material=_material_summary(element.materials),
                quantity=primary[0] if primary else None,
                unit=primary[1] if primary else None,
                family=guess_family(element.ifc_class, element.predefined_type),
                group_hash=element.group_hash,
                suggested_ibis_code=(
                    classification.ibis_code if classification else None
                ),
                internal_element=(
                    classification.internal_element if classification else None
                ),
                confidence=classification.confidence if classification else None,
                status=classification.status if classification else None,
                is_split_parent=element.id in split_parent_ids,
            )
        )
    return rows
