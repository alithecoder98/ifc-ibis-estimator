"""Phase 3.3 — shortlists candidate codes and similar past examples for an element
profile, feeding 3.4's LLM prompt (profile + candidates + examples + rules summary).
Not wired into app/ai/classify.py yet - there's no LLM step to consume this output
until 3.4 exists.

Caches per group_hash in-process (a plain module-level dict, cleared with
clear_cache() - this worker process's lifetime only, not shared across workers or
persisted) since elements sharing a group need the same embedding + search results,
the same "one lookup per group" reasoning classify.py already applies to jev.
"""

from sqlalchemy.orm import Session

from app.ai.embedder import OllamaEmbedder
from app.db.models import CodeList, ExampleMemory

# ifc_class -> code_list family (see CLAUDE.md's core data model: foundation / wall /
# floor / roof / column / beam / stair / opening / finish / other). IfcSlab is
# ambiguous on its own (a floor slab and a roof slab are both IfcSlab) - resolved via
# predefined_type where available, defaulting to "floor" otherwise.
IFC_CLASS_TO_FAMILY = {
    "IfcWall": "wall",
    "IfcSlab": "floor",
    "IfcRoof": "roof",
    "IfcFooting": "foundation",
    "IfcPile": "foundation",
    "IfcColumn": "column",
    "IfcBeam": "beam",
    "IfcStair": "stair",
    "IfcRailing": "other",
    "IfcDoor": "opening",
    "IfcWindow": "opening",
    "IfcCovering": "finish",
    "IfcBuildingElementProxy": "other",
}


def guess_family(ifc_class: str, predefined_type: str | None) -> str:
    if ifc_class == "IfcSlab" and predefined_type == "ROOF":
        return "roof"
    return IFC_CLASS_TO_FAMILY.get(ifc_class, "other")


def shortlist_codes(
    db: Session,
    profile_text: str,
    embedder: OllamaEmbedder,
    family: str | None = None,
    limit: int = 15,
) -> list[CodeList]:
    [query_vector] = embedder.embed([profile_text])

    def _search(filter_family: str | None) -> list[CodeList]:
        q = db.query(CodeList)
        if filter_family is not None:
            q = q.filter(CodeList.family == filter_family)
        return (
            q.order_by(CodeList.embedding.cosine_distance(query_vector))
            .limit(limit)
            .all()
        )

    results = _search(family)
    if family is not None and len(results) < limit:
        results = _search(None)
    return results


def similar_examples(
    db: Session, profile_text: str, embedder: OllamaEmbedder, limit: int = 5
) -> list[ExampleMemory]:
    [query_vector] = embedder.embed([profile_text])
    return (
        db.query(ExampleMemory)
        .order_by(ExampleMemory.embedding.cosine_distance(query_vector))
        .limit(limit)
        .all()
    )


_cache: dict[str, tuple[list[CodeList], list[ExampleMemory]]] = {}


def shortlist_and_examples(
    db: Session,
    embedder: OllamaEmbedder,
    group_hash: str,
    profile_text: str,
    ifc_class: str,
    predefined_type: str | None,
) -> tuple[list[CodeList], list[ExampleMemory]]:
    if group_hash in _cache:
        return _cache[group_hash]

    family = guess_family(ifc_class, predefined_type)
    result = (
        shortlist_codes(db, profile_text, embedder, family=family),
        similar_examples(db, profile_text, embedder),
    )
    _cache[group_hash] = result
    return result


def clear_cache() -> None:
    _cache.clear()
