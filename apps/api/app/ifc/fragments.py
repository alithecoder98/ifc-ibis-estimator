"""Converts an IFC file to the That Open fragments format for the (not-yet-built) 3D
viewer (Phase 2.6). The actual conversion is JS-only — @thatopen/fragments has no
Python equivalent — so this shells out to node_fragments/convert.mjs, the same way
app/ifc/geometry.py only invokes ifcopenshell.geom when Qto data is missing: a real
subprocess call, not a guess at an API nobody has run.
"""

import json
import subprocess
import tempfile
from pathlib import Path

NODE_FRAGMENTS_DIR = Path(__file__).resolve().parent.parent.parent / "node_fragments"


def convert_to_fragments(ifc_path: Path) -> tuple[bytes, dict[str, int]]:
    """Returns (fragments_bytes, global_id_to_local_id). Raises RuntimeError with the
    Node script's stderr on failure - never returns partial output.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "output.frag"
        idmap_path = Path(tmp_dir) / "idmap.json"

        result = subprocess.run(
            ["node", "convert.mjs", str(ifc_path), str(output_path), str(idmap_path)],
            cwd=NODE_FRAGMENTS_DIR,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"fragments conversion failed (exit {result.returncode}): "
                f"{result.stderr.strip()}"
            )

        fragments_bytes = output_path.read_bytes()
        local_id_by_global_id = {
            global_id: int(local_id)
            for local_id, global_id in json.loads(idmap_path.read_text()).items()
        }
        return fragments_bytes, local_id_by_global_id
