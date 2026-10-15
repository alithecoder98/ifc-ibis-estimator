"""Phase 6.2 — splits a composite element (e.g. a multi-layer wall) into one real
Element row per material layer, so each layer gets its own quantity, its own
classification, and its own review lifecycle, per the charter's step 4
("splits composite elements... into separate lines").

Each split-out layer points back at the original row via `parent_element_id`
(app/db/models/ifc.py). The original row is left in place, not deleted - but
every place that sums quantities (app/ai/summary.py, the CSV export) excludes
any element that has since become a split parent, so its quantity isn't
counted twice against its own children's.

New child rows are left unclassified (no Classification row) - re-running
classification (the existing POST .../classify endpoint) picks them up like
any other element, since it queries the ifc_file's elements fresh each call.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import Element, Quantity
from app.ifc.profile import build_profile_text, compute_group_hash


class AlreadySplitError(Exception):
    """Raised when an element has already been split into layers."""


class NotCompositeError(Exception):
    """Raised when an element has fewer than 2 material layers to split."""


@dataclass
class SplitLayer:
    material: str
    thickness_mm: float | None
    quantity_value: float | None
    quantity_unit: str | None


def _quantity_for_split(
    quantities: list[Quantity],
) -> tuple[str, float, str] | None:
    """Same precedence as app/ai/summary.py's primary_quantity(), but also
    returns which quantity_type matched - summary.py's version intentionally
    doesn't, since nothing there needs to reconstruct a new Quantity row.
    """
    precedence = (
        "area_net",
        "area_gross",
        "volume_net",
        "volume_gross",
        "length",
        "count",
    )
    by_type = {q.quantity_type: q for q in quantities}
    for quantity_type in precedence:
        quantity = by_type.get(quantity_type)
        if quantity is not None:
            return quantity_type, float(quantity.value), quantity.unit
    return None


def split_element(db: Session, element_id: int) -> list[Element]:
    """Creates one child Element per material layer and returns them, newest
    first matching the layer order in `element.materials`. Caller commits.
    """
    element = db.get(Element, element_id)
    if element is None:
        raise ValueError("element not found")

    materials = element.materials or []
    if len(materials) < 2:
        raise NotCompositeError(
            "element has fewer than 2 material layers - nothing to split"
        )

    already_split = (
        db.query(Element).filter(Element.parent_element_id == element_id).first()
        is not None
    )
    if already_split:
        raise AlreadySplitError("element has already been split")

    quantities = db.query(Quantity).filter(Quantity.element_id == element_id).all()
    primary = _quantity_for_split(quantities)

    thicknesses = [m.get("thickness_mm") for m in materials]
    if all(isinstance(t, (int, float)) and t > 0 for t in thicknesses):
        total_thickness = sum(thicknesses)
        proportions = [t / total_thickness for t in thicknesses]
    else:
        # No thickness data to split proportionally by - split evenly rather
        # than guess, and say so isn't needed here since an even split is
        # the obviously-labeled fallback once a reviewer sees N equal values.
        proportions = [1 / len(materials) for _ in materials]

    children: list[Element] = []
    for index, (material, proportion) in enumerate(
        zip(materials, proportions, strict=True)
    ):
        material_name = material.get("material") or f"Layer {index + 1}"
        base_name = element.name or element.global_id
        element_data = {
            "ifc_class": element.ifc_class,
            "predefined_type": element.predefined_type,
            "name": f"{base_name} - {material_name}",
            "object_type": element.object_type,
            "storey": element.storey,
            "is_external": element.is_external,
            "load_bearing": element.load_bearing,
            "materials": [material],
            "psets": element.psets,
        }

        child_quantity_data: dict | None = None
        if primary is not None:
            quantity_type, value, unit = primary
            child_quantity_data = {
                "quantity_type": quantity_type,
                "value": value * proportion,
                "unit": unit,
                "source": "split",
            }

        profile_text = build_profile_text(
            element_data, [child_quantity_data] if child_quantity_data else []
        )
        group_hash = compute_group_hash(element_data)

        child = Element(
            ifc_file_id=element.ifc_file_id,
            parent_element_id=element.id,
            global_id=element.global_id,
            profile_text=profile_text,
            group_hash=group_hash,
            **element_data,
        )
        db.add(child)
        db.flush()  # assigns child.id, needed for the Quantity row below

        if child_quantity_data is not None:
            db.add(Quantity(element_id=child.id, **child_quantity_data))

        children.append(child)

    return children
