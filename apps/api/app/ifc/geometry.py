"""Computes quantities from 3D geometry when an element has no Qto data at all
(`source="geometry"`). Only used as a fallback — see app/workers/extraction.py — never
overrides real Qto data.

Scope, deliberately bounded:
- volume_net / volume_gross: accurate. ifcopenshell automatically performs the boolean
  subtraction for any IfcOpeningElement voiding the element (default settings); passing
  `disable-opening-subtractions` gives the un-voided gross shape instead. Verified
  against a wall with a known opening: gross/net volumes matched the expected values
  exactly (see sub-phase 2.4 commit).
- area_gross: total mesh surface area (all faces, gross shape). This is **not** the
  same concept as Qto's side-area properties (e.g. a wall's NetSideArea is one face;
  this is every face including ends, top and bottom) — isolating just the "side" faces
  would need face-normal classification this module doesn't attempt. Stored as its own
  honest quantity_type, not pretended to match Qto's area semantics.
- length: the longest horizontal (X or Y) extent of the gross shape's bounding box.
  Exact for simple axis-aligned box-like elements (as verified against the wall/footing
  test fixtures); an approximation for anything else (curved walls, non-rectangular
  footprints, ...).
- No per-layer (composite) quantities — the `quantities` table has no concept of a
  material layer. Deferred to Phase 6.2 (composite split review), which is where the
  plan actually uses this; see CLAUDE.md decision log for why this wasn't added here.
"""

import ifcopenshell.geom as geom

_settings_net = geom.settings()
_settings_gross = geom.settings()
_settings_gross.set("disable-opening-subtractions", True)


def _mesh_volume(shape) -> float:
    verts = shape.geometry.verts
    faces = shape.geometry.faces
    points = [verts[i : i + 3] for i in range(0, len(verts), 3)]
    total = 0.0
    for i in range(0, len(faces), 3):
        ax, ay, az = points[faces[i]]
        bx, by, bz = points[faces[i + 1]]
        cx, cy, cz = points[faces[i + 2]]
        total += (
            ax * (by * cz - bz * cy)
            - ay * (bx * cz - bz * cx)
            + az * (bx * cy - by * cx)
        )
    return abs(total) / 6.0


def _mesh_surface_area(shape) -> float:
    verts = shape.geometry.verts
    faces = shape.geometry.faces
    points = [verts[i : i + 3] for i in range(0, len(verts), 3)]
    total = 0.0
    for i in range(0, len(faces), 3):
        ax, ay, az = points[faces[i]]
        bx, by, bz = points[faces[i + 1]]
        cx, cy, cz = points[faces[i + 2]]
        ux, uy, uz = bx - ax, by - ay, bz - az
        vx, vy, vz = cx - ax, cy - ay, cz - az
        cx_, cy_, cz_ = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        total += 0.5 * (cx_**2 + cy_**2 + cz_**2) ** 0.5
    return total


def _horizontal_extent(shape) -> float:
    verts = shape.geometry.verts
    xs = verts[0::3]
    ys = verts[1::3]
    return max(max(xs) - min(xs), max(ys) - min(ys))


def compute_geometry_quantities(element) -> list[dict]:
    """Returns quantity dicts (quantity_type, value, unit, source="geometry") for one
    element, or [] if it has no usable geometric representation.
    """
    try:
        net_shape = geom.create_shape(_settings_net, element)
        gross_shape = geom.create_shape(_settings_gross, element)
    except Exception:
        return []

    return [
        {
            "quantity_type": "volume_net",
            "value": _mesh_volume(net_shape),
            "unit": "m3",
            "source": "geometry",
        },
        {
            "quantity_type": "volume_gross",
            "value": _mesh_volume(gross_shape),
            "unit": "m3",
            "source": "geometry",
        },
        {
            "quantity_type": "area_gross",
            "value": _mesh_surface_area(gross_shape),
            "unit": "m2",
            "source": "geometry",
        },
        {
            "quantity_type": "length",
            "value": _horizontal_extent(gross_shape),
            "unit": "m",
            "source": "geometry",
        },
    ]
