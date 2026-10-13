"""Phase 3.8 — the full evaluation harness the plan's week-6 gate reads: overall
accuracy, auto-accept rate, precision of auto-accepted items, unflagged errors,
accuracy per family, and token/cost totals. Supersedes P.4's app/ai/accuracy.py for
reporting purposes (that module's compare_accuracy() was explicitly scoped down from
this harness for the 1-2 day PoC) - reuses its load_ground_truth() rather than a
second copy of the same 2-column CSV format.

Self-tested only (tests/test_evaluate.py) - njderidder's manually-verified reference
calculations still haven't arrived, same blocker as P.4/2.7/3.6's calibration script.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.ai.retrieval import guess_family
from app.db.models import Classification, Element, IfcFile


@dataclass
class EvaluationRow:
    global_id: str
    family: str
    expected_ibis_code: str
    actual_ibis_code: str | None
    is_correct: bool
    status: str
    source: str
    prompt_tokens: int | None
    completion_tokens: int | None


def gather_evaluation_rows(
    db: Session, project_id: int, ground_truth: dict[str, str]
) -> list[EvaluationRow]:
    """One row per element that has both a ground truth entry and at least one
    stored classification - compared against that element's *latest* classification
    (by created_at), same "latest wins" convention as app/ai/calibrate.py.
    """
    ifc_file_ids = [
        f.id for f in db.query(IfcFile).filter(IfcFile.project_id == project_id)
    ]
    elements = (
        db.query(Element).filter(Element.ifc_file_id.in_(ifc_file_ids)).all()
        if ifc_file_ids
        else []
    )

    rows = []
    for element in elements:
        if element.global_id not in ground_truth:
            continue
        classification = (
            db.query(Classification)
            .filter(Classification.element_id == element.id)
            .order_by(Classification.created_at.desc())
            .first()
        )
        if classification is None:
            continue

        expected = ground_truth[element.global_id]
        rows.append(
            EvaluationRow(
                global_id=element.global_id,
                family=guess_family(element.ifc_class, element.predefined_type),
                expected_ibis_code=expected,
                actual_ibis_code=classification.ibis_code,
                is_correct=classification.ibis_code == expected,
                status=classification.status,
                source=classification.source,
                prompt_tokens=classification.prompt_tokens,
                completion_tokens=classification.completion_tokens,
            )
        )
    return rows


def total_tokens_for_project(db: Session, project_id: int) -> tuple[int, int]:
    """Summed across *every* source="llm" classification row for this project's
    elements, not just the latest-per-element subset gather_evaluation_rows()
    compares - a re-run's earlier, superseded rows still cost real tokens and
    real wall-clock time, and "cost per model" should reflect what was actually
    spent, not just what's currently showing.
    """
    ifc_file_ids = [
        f.id for f in db.query(IfcFile).filter(IfcFile.project_id == project_id)
    ]
    element_ids = [
        e.id
        for e in (
            db.query(Element).filter(Element.ifc_file_id.in_(ifc_file_ids)).all()
            if ifc_file_ids
            else []
        )
    ]
    if not element_ids:
        return 0, 0

    rows = (
        db.query(Classification)
        .filter(
            Classification.element_id.in_(element_ids),
            Classification.source == "llm",
        )
        .all()
    )
    return (
        sum(r.prompt_tokens or 0 for r in rows),
        sum(r.completion_tokens or 0 for r in rows),
    )


@dataclass
class EvaluationReport:
    n_compared: int
    overall_accuracy: float
    auto_accept_rate: float
    auto_accept_precision: float | None  # None if nothing was auto-accepted
    unflagged_error_rate: float
    accuracy_by_family: dict[str, float] = field(default_factory=dict)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    cost_usd: float = 0.0  # local model (Phase 3.1 decision) - real, not a placeholder


def evaluate(
    rows: list[EvaluationRow], total_prompt_tokens: int, total_completion_tokens: int
) -> EvaluationReport:
    n = len(rows)
    if n == 0:
        return EvaluationReport(
            n_compared=0,
            overall_accuracy=0.0,
            auto_accept_rate=0.0,
            auto_accept_precision=None,
            unflagged_error_rate=0.0,
            total_prompt_tokens=total_prompt_tokens,
            total_completion_tokens=total_completion_tokens,
        )

    correct = [r for r in rows if r.is_correct]
    auto_accepted = [r for r in rows if r.status == "auto_accepted"]
    auto_accepted_correct = [r for r in auto_accepted if r.is_correct]
    # A wrong auto_accepted row is the dangerous case: nothing flagged it for
    # review, so it would silently reach the Excel export. A wrong needs_review
    # row was already caught by the pipeline itself, however imperfectly, so it
    # doesn't count as "unflagged".
    unflagged_errors = [r for r in auto_accepted if not r.is_correct]

    families = sorted({r.family for r in rows})
    accuracy_by_family = {
        family: (
            sum(1 for r in rows if r.family == family and r.is_correct)
            / sum(1 for r in rows if r.family == family)
        )
        for family in families
    }

    return EvaluationReport(
        n_compared=n,
        overall_accuracy=len(correct) / n,
        auto_accept_rate=len(auto_accepted) / n,
        auto_accept_precision=(
            len(auto_accepted_correct) / len(auto_accepted) if auto_accepted else None
        ),
        unflagged_error_rate=len(unflagged_errors) / n,
        accuracy_by_family=accuracy_by_family,
        total_prompt_tokens=total_prompt_tokens,
        total_completion_tokens=total_completion_tokens,
    )


def render_markdown(
    report: EvaluationReport, project_id: int, generated_at: str
) -> str:
    lines = [
        f"# Evaluation report — project {project_id}",
        "",
        f"Generated: {generated_at}",
        "",
        f"- Elements compared against ground truth: **{report.n_compared}**",
        f"- Overall accuracy: **{report.overall_accuracy:.1%}**",
        f"- Auto-accept rate: **{report.auto_accept_rate:.1%}**",
        (
            f"- Auto-accept precision: **{report.auto_accept_precision:.1%}**"
            if report.auto_accept_precision is not None
            else "- Auto-accept precision: **n/a (nothing was auto-accepted)**"
        ),
        f"- Unflagged error rate: **{report.unflagged_error_rate:.1%}**",
        (
            f"- Tokens: {report.total_prompt_tokens} prompt + "
            f"{report.total_completion_tokens} completion"
        ),
        f"- Cost: **${report.cost_usd:.2f}** (local model, Phase 3.1 decision)",
        "",
        "## Accuracy by family",
        "",
        "| Family | Accuracy |",
        "|---|---|",
    ]
    for family, accuracy in sorted(report.accuracy_by_family.items()):
        lines.append(f"| {family} | {accuracy:.1%} |")
    lines.append("")
    return "\n".join(lines)
