"""Admin CRUD for rules (Phase 3.2). Matching logic lives in app/ai/rules.py and
app/ai/classify.py - this router only manages the Rule rows.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.db.models import Rule, User
from app.db.session import get_db
from app.schemas import RuleCreate, RuleOut, RuleUpdate

router = APIRouter(prefix="/rules", tags=["rules"])


@router.post("", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(
    body: RuleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> Rule:
    rule = Rule(
        conditions=[c.model_dump() for c in body.conditions],
        result_ibis_code=body.result_ibis_code,
        result_internal_element=body.result_internal_element,
        priority=body.priority,
        status=body.status,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("", response_model=list[RuleOut])
def list_rules(
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator", "viewer")),
) -> list[Rule]:
    q = db.query(Rule)
    if status_filter is not None:
        q = q.filter(Rule.status == status_filter)
    return q.order_by(Rule.priority.desc()).all()


@router.get("/{rule_id}", response_model=RuleOut)
def get_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "estimator", "viewer")),
) -> Rule:
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="rule not found"
        )
    return rule


@router.patch("/{rule_id}", response_model=RuleOut)
def update_rule(
    rule_id: int,
    body: RuleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> Rule:
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="rule not found"
        )

    updates = body.model_dump(exclude_unset=True)
    if "conditions" in updates:
        updates["conditions"] = [c.model_dump() for c in body.conditions]
    for field, value in updates.items():
        setattr(rule, field, value)

    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> None:
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="rule not found"
        )
    db.delete(rule)
    db.commit()
