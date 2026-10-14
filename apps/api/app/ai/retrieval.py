"""Phase 3.3 — shortlists candidate codes and similar past examples for an element
profile, feeding 3.4's LLM prompt (profile + candidates + examples + rules summary).

Caches per group_hash, but the cache must be supplied by the caller
(shortlist_and_examples' `cache` argument) and live only as long as one
classify_elements() call - never a module-level dict. group_hash is purely
content-based (app/ifc/profile.py), so two separate uploads of similar-enough IFC
files produce the *same* group_hash values; a process-lifetime cache would hand a
later job CodeList/ExampleMemory instances still bound to an earlier job's already-
closed DB session, raising DetachedInstanceError. Caught live in Phase 3.6's
verification, not by any test - two uploads of the same fixture in the same worker
process is exactly the shape of bug a single-job test run can't see.
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


def shortlist_codes_with_scores(
    db: Session,
    profile_text: str,
    embedder: OllamaEmbedder,
    family: str | None = None,
    limit: int = 15,
) -> list[tuple[CodeList, float]]:
    """Same shortlist as shortlist_codes() (family-filtered, falls back to all
    families if too few), but also returns each candidate's real cosine
    similarity (1 - cosine_distance, so higher = closer) - built for Phase 4.5's
    detail panel ("candidate codes with scores"). Kept separate from
    shortlist_codes() rather than changing its return shape: classify_with_llm()
    and compute_confidence() already depend on shortlist_codes() returning plain
    CodeList objects, and this avoids touching that tested code at all.
    """
    [query_vector] = embedder.embed([profile_text])

    def _search(filter_family: str | None) -> list[tuple[CodeList, float]]:
        q = db.query(CodeList, CodeList.embedding.cosine_distance(query_vector))
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
    return [(code, 1.0 - distance) for code, distance in results]


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


def shortlist_and_examples(
    db: Session,
    embedder: OllamaEmbedder,
    group_hash: str,
    profile_text: str,
    ifc_class: str,
    predefined_type: str | None,
    cache: dict[str, tuple[list[CodeList], list[ExampleMemory]]],
) -> tuple[list[CodeList], list[ExampleMemory]]:
    """`cache` is owned by the caller and must not outlive the DB session its
    results are bound to - one classify_elements() call creates a fresh {} and
    passes it to every call it makes, never a module-level dict (see the module
    docstring for why).
    """
    if group_hash in cache:
        return cache[group_hash]

    family = guess_family(ifc_class, predefined_type)
    result = (
        shortlist_codes(db, profile_text, embedder, family=family),
        similar_examples(db, profile_text, embedder),
    )
    cache[group_hash] = result
    return result
