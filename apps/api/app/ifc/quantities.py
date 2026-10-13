"""Reads Qto_<Class>BaseQuantities sets from IFC elements and normalizes them to SI
(metres / square metres / cubic metres) — `source="qto"` quantities. Geometry-computed
fallback quantities (`source="geometry"`, for elements with no Qto data) are Phase
2.4's job.
"""

import ifcopenshell
import ifcopenshell.util.element as ue
import ifcopenshell.util.unit as uu

# IFC's Qto_<Class>BaseQuantities sets don't use consistent property names across
# element classes (walls use NetSideArea, slabs/roofs use NetArea, ...) — try each
# alias in order and take the first match. Each entry: (candidate prop names, SI unit).
_QUANTITY_PROPERTIES: dict[str, tuple[list[str], str]] = {
    "length": (["Length"], "m"),
    "area_net": (["NetSideArea", "NetArea", "NetFootprintArea"], "m2"),
    "area_gross": (["GrossSideArea", "GrossArea", "GrossFootprintArea"], "m2"),
    "volume_net": (["NetVolume"], "m3"),
    "volume_gross": (["GrossVolume"], "m3"),
    "count": (["Count"], "count"),
}

# SI unit -> the unit_type calculate_unit_scale() expects, and the power to raise the
# length scale to when area/volume aren't independently declared (calculate_unit_scale
# already handles that — AREAUNIT/VOLUMEUNIT may be declared independently of
# LENGTHUNIT, e.g. millimetre lengths with plain square-metre areas, so each is looked
# up by its own unit_type rather than assumed to be length_scale ** power).
_UNIT_TYPE_BY_SI_UNIT = {
    "m": "LENGTHUNIT",
    "m2": "AREAUNIT",
    "m3": "VOLUMEUNIT",
    "count": None,
}


def extract_quantities(ifc_file: ifcopenshell.file, element) -> list[dict]:
    """Returns quantity dicts (quantity_type, value, unit, source="qto") for one
    element, reading whichever Qto_<Class>BaseQuantities set(s) are attached to it.
    """
    scale_cache: dict[str, float] = {}

    def scale_for(si_unit: str) -> float:
        unit_type = _UNIT_TYPE_BY_SI_UNIT[si_unit]
        if unit_type is None:
            return 1.0
        if unit_type not in scale_cache:
            scale_cache[unit_type] = uu.calculate_unit_scale(ifc_file, unit_type)
        return scale_cache[unit_type]

    qtos = ue.get_psets(element, qtos_only=True)

    results = []
    seen_types: set[str] = set()
    for props in qtos.values():
        if not isinstance(props, dict):
            continue
        for quantity_type, (prop_names, si_unit) in _QUANTITY_PROPERTIES.items():
            if quantity_type in seen_types:
                continue
            for prop_name in prop_names:
                raw_value = props.get(prop_name)
                if raw_value is None:
                    continue
                results.append(
                    {
                        "quantity_type": quantity_type,
                        "value": raw_value * scale_for(si_unit),
                        "unit": si_unit,
                        "source": "qto",
                    }
                )
                seen_types.add(quantity_type)
                break
    return results
