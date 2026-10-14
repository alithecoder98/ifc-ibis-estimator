"""Phase 4.5 — full detail for one element: properties, material layers,
quantities with source, the latest classification's AI reasoning, candidate
codes with real cosine-similarity scores, similar past examples, and review
history/comments.

Candidates/similar examples are recomputed fresh against the element's *current*
profile_text and the *current* code_list/example_memory - not a historical record
of what classify.py actually showed the LLM at classification time (nothing
persists that). A known simplification, not a bug: this project hasn't
retrofitted historical snapshots anywhere else either. This needs a real Ollama
embedding call every time it's requested, regardless of the project's
classification_engine setting - unlike classify.py, which only calls the embedder
when the engine uses the LLM, this feature's whole point is showing candidates
for *any* element, so there's no "jev-only, stay offline" path here. Tests inject
FakeEmbedder (same pattern as test_classify.py's monkeypatching) so CI doesn't
need live Ollama.

"corrected"/review history is always empty today, honestly - no review/
correction endpoint exists yet (Phase 6.1), same situation as 4.3's "corrected"
count.
"""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.ai.embedder import OllamaEmbedder
from app.ai.retrieval import guess_family, shortlist_codes_with_scores, similar_examples
from app.ai.summary import latest_classifications_by_element
from app.db.models import Classification, Element, ExampleMemory, Quantity, Review, User


@dataclass
class CandidateDetail:
    ibis_code: str
    internal_element: str
    description: str | None
    score: float


@dataclass
class ReviewDetail:
    action: str
    comment: str | None
    created_at: datetime
    user_email: str


@dataclass
class ElementDetail:
    element: Element
    quantities: list[Quantity]
    classification: Classification | None
    candidates: list[CandidateDetail] = field(default_factory=list)
    similar_examples: list[ExampleMemory] = field(default_factory=list)
    reviews: list[ReviewDetail] = field(default_factory=list)


def get_element_detail(
    db: Session, element_id: int, embedder: OllamaEmbedder
) -> ElementDetail | None:
    element = db.get(Element, element_id)
    if element is None:
        return None

    quantities = db.query(Quantity).filter(Quantity.element_id == element_id).all()

    latest_by_element = latest_classifications_by_element(db, [element_id])
    classification = latest_by_element.get(element_id)

    candidates: list[CandidateDetail] = []
    examples: list[ExampleMemory] = []
    if element.profile_text:
        family = guess_family(element.ifc_class, element.predefined_type)
        scored = shortlist_codes_with_scores(
            db, element.profile_text, embedder, family=family
        )
        candidates = [
            CandidateDetail(
                ibis_code=code.ibis_code,
                internal_element=code.internal_element,
                description=code.description,
                score=round(score, 4),
            )
            for code, score in scored
        ]
        examples = similar_examples(db, element.profile_text, embedder)

    all_classification_ids = [
        c.id
        for c in db.query(Classification).filter(
            Classification.element_id == element_id
        )
    ]
    reviews: list[ReviewDetail] = []
    if all_classification_ids:
        review_rows = (
            db.query(Review, User.email)
            .join(User, User.id == Review.user_id)
            .filter(Review.classification_id.in_(all_classification_ids))
            .order_by(Review.created_at)
            .all()
        )
        reviews = [
            ReviewDetail(
                action=review.action,
                comment=review.comment,
                created_at=review.created_at,
                user_email=email,
            )
            for review, email in review_rows
        ]

    return ElementDetail(
        element=element,
        quantities=quantities,
        classification=classification,
        candidates=candidates,
        similar_examples=examples,
        reviews=reviews,
    )
