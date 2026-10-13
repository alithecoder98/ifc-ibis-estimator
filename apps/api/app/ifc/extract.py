"""Extracts building elements from an opened IFC file into plain dicts ready for the
`elements` table.

No geometry is touched here — fast and memory-light regardless of file size. Computed
(geometry-based) quantities are Phase 2.4's job; Qto-based quantities are 2.3's;
profile_text/group_hash are 2.5's.
"""

import ifcopenshell
import ifcopenshell.util.element as ue

SUPPORTED_CLASSES = [
    "IfcWall",
    "IfcSlab",
    "IfcRoof",
    "IfcFooting",
    "IfcColumn",
    "IfcBeam",
    "IfcStair",
    "IfcRailing",
    "IfcDoor",
    "IfcWindow",
    "IfcCovering",
    "IfcPile",
    "IfcBuildingElementProxy",
]


def _get_storey_name(element) -> str | None:
    container = ue.get_container(element)
    if container is not None and container.is_a("IfcBuildingStorey"):
        return container.Name
    return None


def _get_materials(element) -> list[dict] | None:
    material = ue.get_material(element)
    if material is None:
        return None

    if material.is_a("IfcMaterialLayerSetUsage"):
        layer_set = material.ForLayerSet
    elif material.is_a("IfcMaterialLayerSet"):
        layer_set = material
    else:
        layer_set = None

    if layer_set is not None:
        return [
            {
                "material": layer.Material.Name if layer.Material else None,
                "thickness_mm": layer.LayerThickness,
            }
            for layer in layer_set.MaterialLayers
        ]

    if material.is_a("IfcMaterial"):
        return [{"material": material.Name, "thickness_mm": None}]

    return None


def _get_is_external_load_bearing(psets: dict) -> tuple[bool | None, bool | None]:
    # IsExternal/LoadBearing are standardized property *names* across several
    # differently-named Common psets (Pset_WallCommon, Pset_SlabCommon, ...) — scan
    # whichever psets are actually present rather than hardcoding per-class names.
    is_external = None
    load_bearing = None
    for props in psets.values():
        if not isinstance(props, dict):
            continue
        if is_external is None and "IsExternal" in props:
            is_external = props["IsExternal"]
        if load_bearing is None and "LoadBearing" in props:
            load_bearing = props["LoadBearing"]
    return is_external, load_bearing


def iter_supported_elements(ifc_file: ifcopenshell.file):
    """Yields raw entities for every supported class, deduplicated by entity id
    (by_type() already includes subtypes, e.g. IfcWallStandardCase comes back from
    "IfcWall"). Shared by extract_elements() below and app/ifc/quantities.py's caller
    (the worker) so both walk the file once instead of twice.
    """
    seen_ids: set[int] = set()

    for ifc_class in SUPPORTED_CLASSES:
        for element in ifc_file.by_type(ifc_class):
            if element.id() in seen_ids:
                continue
            seen_ids.add(element.id())
            yield element


def build_element_data(element) -> dict:
    """Builds the elements-table dict for one raw entity."""
    psets = ue.get_psets(element)
    is_external, load_bearing = _get_is_external_load_bearing(psets)

    return {
        "global_id": element.GlobalId,
        "ifc_class": element.is_a(),
        "predefined_type": getattr(element, "PredefinedType", None),
        "name": element.Name,
        "object_type": getattr(element, "ObjectType", None),
        "storey": _get_storey_name(element),
        "is_external": is_external,
        "load_bearing": load_bearing,
        "materials": _get_materials(element),
        "psets": psets or None,
    }


def extract_elements(ifc_file: ifcopenshell.file):
    """Yields one dict per supported element — see build_element_data()/
    iter_supported_elements() for the pieces, kept separate so the worker can reuse
    the raw entity (e.g. to also look up its quantities) without re-walking the file.
    """
    for element in iter_supported_elements(ifc_file):
        yield build_element_data(element)
