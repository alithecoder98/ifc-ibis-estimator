"""Phase 3.2 — deterministic rule-based classification, evaluated before AI
(rules -> embeddings/LLM/jev). A matching active rule gets confidence=1.0,
source="rule" - no model call needed for anything a rule already covers.

Rule.conditions is a list of {field, operator, value} dicts (the shape already used
in tests/test_models.py since Phase 1.3) - every condition in a rule must match (AND).
Evaluated per element, not per group_hash like jev (app/ai/classify.py): group_hash
excludes storey, so two elements in the same jev group can still differ on a
storey_keyword rule.
"""

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import Element, Rule

CONDITION_FIELDS = (
    "ifc_class",
    "predefined_type",
    "material_keyword",
    "thickness_mm",
    "is_external",
    "load_bearing",
    "storey_keyword",
)
CONDITION_OPERATORS = ("==", "contains", "between")


class RuleCondition(BaseModel):
    field: Literal[*CONDITION_FIELDS]
    operator: Literal[*CONDITION_OPERATORS]
    value: Any


class RuleRow(BaseModel):
    """One entry in an initial-rules JSON file (see load_rules_from_json)."""

    conditions: list[RuleCondition]
    result_ibis_code: str
    result_internal_element: str
    priority: int = 0
    status: Literal["suggested", "active"] = "active"


def load_rules_from_json(db: Session, path: Path) -> list[Rule]:
    rows = [RuleRow(**row) for row in json.loads(path.read_text(encoding="utf-8"))]
    rules = [
        Rule(
            conditions=[c.model_dump() for c in row.conditions],
            result_ibis_code=row.result_ibis_code,
            result_internal_element=row.result_internal_element,
            priority=row.priority,
            status=row.status,
        )
        for row in rows
    ]
    db.add_all(rules)
    db.flush()
    return rules


def _field_values(element: Element, field: str) -> list:
    """Returns the element's value(s) for a condition field, always as a list so
    material-layer fields (which can have several values) use the same matching
    code as scalar fields.
    """
    if field == "ifc_class":
        return [element.ifc_class]
    if field == "predefined_type":
        return [element.predefined_type]
    if field == "is_external":
        return [element.is_external]
    if field == "load_bearing":
        return [element.load_bearing]
    if field == "storey_keyword":
        return [element.storey]
    if field == "material_keyword":
        return [m.get("material") for m in (element.materials or [])]
    if field == "thickness_mm":
        return [m.get("thickness_mm") for m in (element.materials or [])]
    raise ValueError(f"unknown rule condition field: {field!r}")


def _condition_matches(value, operator: str, target) -> bool:
    if value is None:
        return False
    if operator == "==":
        return value == target
    if operator == "contains":
        return isinstance(value, str) and target.lower() in value.lower()
    if operator == "between":
        low, high = target
        return isinstance(value, (int, float)) and low <= value <= high
    raise ValueError(f"unknown rule condition operator: {operator!r}")


def rule_matches(element: Element, rule: Rule) -> bool:
    for condition in rule.conditions:
        values = _field_values(element, condition["field"])
        if not any(
            _condition_matches(v, condition["operator"], condition["value"])
            for v in values
        ):
            return False
    return True


def match_rule(element: Element, active_rules: list[Rule]) -> Rule | None:
    """`active_rules` should already be filtered to status == "active" - this
    function doesn't check status, so a suggested rule passed in by mistake would
    still be applied. Highest `priority` first; returns the first match or None.
    """
    for rule in sorted(active_rules, key=lambda r: -r.priority):
        if rule_matches(element, rule):
            return rule
    return None
