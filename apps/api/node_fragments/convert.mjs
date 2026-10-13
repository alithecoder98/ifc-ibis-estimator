// Phase 2.6: converts an IFC file to the That Open fragments format, for the
// (not-yet-built) 3D viewer. Invoked by app/ifc/fragments.py via subprocess - not run
// directly as part of any other workflow.
//
// Usage: node convert.mjs <input.ifc> <output.frag> <idmap.json>
//
// Writes the fragments binary to <output.frag> and a JSON object mapping each
// fragment local ID to its IFC GlobalId (only entities that have one - most geometry
// sub-items don't) to <idmap.json>. Exits non-zero with a message on stderr on failure
// - never writes partial output.

import { readFile, writeFile } from "node:fs/promises";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

import { IfcImporter, SingleThreadedFragmentsModel } from "@thatopen/fragments";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

async function convert(inputPath, outputPath, idMapPath) {
  const importer = new IfcImporter();
  importer.wasm.absolute = true;
  importer.wasm.path = path.join(__dirname, "node_modules", "web-ifc") + path.sep;

  const bytes = new Uint8Array(await readFile(inputPath));
  const fragmentsBytes = await importer.process({ bytes });
  await writeFile(outputPath, fragmentsBytes);

  const model = new SingleThreadedFragmentsModel("conversion", fragmentsBytes);
  try {
    await model.ready;
    const maxLocalId = model.getMaxLocalId();
    const localIds = Array.from({ length: maxLocalId + 1 }, (_, i) => i);
    const guids = model.getGuidsByLocalIds(localIds);

    const idMap = {};
    for (let i = 0; i < localIds.length; i++) {
      if (guids[i] !== null) idMap[localIds[i]] = guids[i];
    }
    await writeFile(idMapPath, JSON.stringify(idMap));
  } finally {
    model.dispose();
  }
}

async function main() {
  const [inputPath, outputPath, idMapPath] = process.argv.slice(2);
  if (!inputPath || !outputPath || !idMapPath) {
    console.error("usage: node convert.mjs <input.ifc> <output.frag> <idmap.json>");
    process.exit(1);
  }
  await convert(inputPath, outputPath, idMapPath);
}

main().catch((err) => {
  console.error(err.stack || String(err));
  process.exit(1);
});
