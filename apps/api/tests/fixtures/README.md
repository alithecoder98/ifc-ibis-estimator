# Test fixtures

- **`sample.ifc`** — synthetic, generated via `ifcopenshell`'s own API (see the
  generator script referenced in the 2.1/2.2 commit history). Covers wall, slab, roof,
  footing, column, beam, stair, railing, door, window, covering, and proxy — one of
  each, with a material layer + `Pset_WallCommon` on the layered ones and
  `Qto_WallBaseQuantities` on the wall. Deliberately clean/minimal: good for asserting
  exact extraction behavior, not for catching real-world messiness.

- **`real_sample.ifc`** — `Building-Architecture.ifc` from buildingSMART's
  [Sample-Test-Files](https://github.com/buildingSMART/Sample-Test-Files) repo
  (`IFC 2.3.0.1 (IFC 2x3 TC1)/Simple-Scene/`), licensed
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) by buildingSMART
  International Ltd. A real SketchUp export with walls, slabs, a roof, and proxies,
  real `Qto_*BaseQuantities` sets and material names — has the inconsistencies a real
  authoring tool produces (not every element has every Pset filled in), which the
  synthetic fixture above doesn't exercise. Does not cover columns, beams, stairs,
  railings, doors, or windows — `sample.ifc` fills those gaps.

- **`corrupt.ifc`** — garbage bytes with a `.ifc` extension, for the upload
  rejection-path test (sub-phase 2.1).
