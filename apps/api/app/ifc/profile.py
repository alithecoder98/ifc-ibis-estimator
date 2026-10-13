"""Builds a deterministic, compact text summary per element (the classification
pipeline's input and embedding source — Phase 3) and a group hash so elements of the
same construction type are classified once instead of individually.

Both are pure functions over data already extracted in 2.2-2.4 — no new IFC parsing.
"""

import hashlib
import json


def build_profile_text(element_data: dict, quantities: list[dict]) -> str:
    """A human/LLM-readable summary: class+type, materials, storey, external/
    load-bearing, quantities, and notable properties from any `*Common` pset. Fields
    are sorted wherever order isn't already meaningful, so the same element always
    produces the exact same text (see test_profile.py's snapshot tests).
    """
    lines = []

    class_line = element_data["ifc_class"]
    if element_data.get("predefined_type"):
        class_line += f" ({element_data['predefined_type']})"
    lines.append(f"Class: {class_line}")

    if element_data.get("name"):
        lines.append(f"Name: {element_data['name']}")

    materials = element_data.get("materials")
    if materials:
        parts = []
        for m in materials:
            name = m.get("material") or "Unknown material"
            thickness = m.get("thickness_mm")
            parts.append(f"{name} ({thickness:g}mm)" if thickness is not None else name)
        lines.append("Materials: " + ", ".join(parts))

    if element_data.get("storey"):
        lines.append(f"Storey: {element_data['storey']}")

    flags = []
    if element_data.get("is_external") is not None:
        flags.append(f"External={element_data['is_external']}")
    if element_data.get("load_bearing") is not None:
        flags.append(f"LoadBearing={element_data['load_bearing']}")
    if flags:
        lines.append(" | ".join(flags))

    if quantities:
        q_parts = [
            f"{q['quantity_type']}={q['value']:.2f}{q['unit']}"
            for q in sorted(quantities, key=lambda q: q["quantity_type"])
        ]
        lines.append("Quantities: " + ", ".join(q_parts))

    # "Top relevant" properties: anything in a *Common pset, excluding IsExternal/
    # LoadBearing (already shown above) and "id" (ifcopenshell.util.element.get_psets()
    # always injects this - it's the pset entity's own STEP id for traceability, not
    # an IFC property), sorted for determinism.
    psets = element_data.get("psets") or {}
    skip_keys = {"IsExternal", "LoadBearing", "id"}
    common_props: dict = {}
    for pset_name in sorted(psets):
        props = psets[pset_name]
        if not pset_name.endswith("Common") or not isinstance(props, dict):
            continue
        for key in sorted(props):
            if key in skip_keys or props[key] is None:
                continue
            common_props[key] = props[key]
    if common_props:
        lines.append(
            "Properties: " + ", ".join(f"{k}={v}" for k, v in common_props.items())
        )

    return "\n".join(lines)


def compute_group_hash(element_data: dict) -> str:
    """SHA256 over only the fields that define a *construction type* - deliberately
    excludes global_id, name, storey and quantities, so two elements that are the
    "same kind of thing" (same class/predefined_type/materials/external/load-bearing)
    share a hash even when they differ in location or individual size. That's the
    point: Phase 3 classifies one representative per group, not every element.
    """
    canonical = {
        "ifc_class": element_data["ifc_class"],
        "predefined_type": element_data.get("predefined_type"),
        "materials": element_data.get("materials"),
        "is_external": element_data.get("is_external"),
        "load_bearing": element_data.get("load_bearing"),
    }
    blob = json.dumps(canonical, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
