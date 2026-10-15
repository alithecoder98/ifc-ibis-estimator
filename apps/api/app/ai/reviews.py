"""Phase 6.1 — approve/correct/undo. Every action writes a fresh Classification
row (never mutates an existing one - same "latest classification wins,
append-only" convention used everywhere else in this project, e.g.
app/ai/classify.py's re-run behavior) plus a Review row logging what happened.

No new Classification.status value was added for "approved" vs "corrected" -
both land on status="auto_accepted" (the review resolved it, so it's no longer
in the review queue), source="review". The distinction between "AI
auto-accepted" / "human-approved" / "human-corrected" stays derivable by
cross-referencing the reviews table, exactly how app/ai/summary.py's
"corrected" stat already works - not a new enum value to keep in sync
everywhere else that reads status.

Undo doesn't delete anything either: it writes another fresh Classification
row restoring the target review's `before` snapshot, plus a new Review row
(action="undo") logging the undo itself. The full history stays intact.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import Classification, CodeList, Element, Review, User


class ReviewError(Exception):
    """Raised for request-level problems (bad code, nothing to approve, etc.) -
    routers translate this to a 400, not a 500.
    """


def _classification_snapshot(classification: Classification | None) -> dict:
    if classification is None:
        return {
            "ibis_code": None,
            "internal_element": None,
            "status": None,
            "source": None,
            "confidence": None,
        }
    return {
        "ibis_code": classification.ibis_code,
        "internal_element": classification.internal_element,
        "status": classification.status,
        "source": classification.source,
        "confidence": classification.confidence,
    }


def _write_resolved_classification(
    db: Session,
    element: Element,
    ibis_code: str,
    internal_element: str,
) -> Classification:
    classification = Classification(
        element_id=element.id,
        ibis_code=ibis_code,
        internal_element=internal_element,
        reasoning=None,
        self_score=None,
        confidence=1.0,
        flags=None,
        status="auto_accepted",
        source="review",
    )
    db.add(classification)
    db.flush()
    return classification


@dataclass
class ReviewResult:
    classification: Classification
    review: Review


def approve_element(
    db: Session,
    element: Element,
    current: Classification | None,
    user: User,
    comment: str | None,
) -> ReviewResult:
    if current is None or current.ibis_code is None:
        raise ReviewError("nothing to approve - this element has no suggested code yet")

    new_classification = _write_resolved_classification(
        db, element, current.ibis_code, current.internal_element or ""
    )
    review = Review(
        classification_id=new_classification.id,
        user_id=user.id,
        action="approve",
        before=_classification_snapshot(current),
        after=_classification_snapshot(new_classification),
        comment=comment,
    )
    db.add(review)
    db.flush()
    return ReviewResult(classification=new_classification, review=review)


def correct_element(
    db: Session,
    element: Element,
    current: Classification | None,
    ibis_code: str,
    user: User,
    comment: str | None,
) -> ReviewResult:
    code = (
        db.query(CodeList)
        .filter(CodeList.ibis_code == ibis_code)
        .order_by(CodeList.version.desc())
        .first()
    )
    if code is None:
        raise ReviewError(f"unknown ibis_code '{ibis_code}'")

    new_classification = _write_resolved_classification(
        db, element, code.ibis_code, code.internal_element
    )
    review = Review(
        classification_id=new_classification.id,
        user_id=user.id,
        action="correct",
        before=_classification_snapshot(current),
        after=_classification_snapshot(new_classification),
        comment=comment,
    )
    db.add(review)
    db.flush()
    return ReviewResult(classification=new_classification, review=review)


def undo_review(
    db: Session, review: Review, element: Element, user: User
) -> ReviewResult:
    before = review.before or {}
    # Unlike approve/correct, this restores the *exact* prior snapshot rather
    # than always landing on status="auto_accepted" - the element's state
    # before the review being undone may honestly have had no code at all
    # (e.g. jev's stub) and still needs_review, which is a legitimate thing to
    # undo back to, not an error case.
    restored = Classification(
        element_id=element.id,
        ibis_code=before.get("ibis_code"),
        internal_element=before.get("internal_element"),
        reasoning=None,
        self_score=None,
        confidence=before.get("confidence"),
        flags=None,
        status=before.get("status") or "needs_review",
        source="review",
    )
    db.add(restored)
    db.flush()
    undo_review_row = Review(
        classification_id=restored.id,
        user_id=user.id,
        action="undo",
        before=_classification_snapshot(
            db.get(Classification, review.classification_id)
        ),
        after=_classification_snapshot(restored),
        comment=f"undo of review #{review.id}",
    )
    db.add(undo_review_row)
    db.flush()
    return ReviewResult(classification=restored, review=undo_review_row)
