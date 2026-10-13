"""Phase 3.4 manual script: runs the real LLM classifier against a project's real
elements and logs token usage + cost, per the plan's "live run on 50 elements
succeeds and logs cost."

Usage:
    uv run python scripts/run_llm_classification.py <project_id> [limit]

One LLM call per group_hash (not per element), same batching as jev/rules/retrieval -
elements sharing a group reuse that group's single result. `limit` caps the number
of *elements* processed (default 50), not groups.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.embedder import get_embedder  # noqa: E402
from app.ai.llm import (
    classify_with_llm,
    get_llm_client,
    load_estimating_rules,
)  # noqa: E402
from app.ai.retrieval import shortlist_and_examples  # noqa: E402
from app.db.models import Element, IfcFile  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402


def main() -> None:
    if len(sys.argv) not in (2, 3):
        print(f"usage: {sys.argv[0]} <project_id> [limit]")
        raise SystemExit(1)

    project_id = int(sys.argv[1])
    limit = int(sys.argv[2]) if len(sys.argv) == 3 else 50

    db = SessionLocal()
    try:
        ifc_file_ids = [
            f.id for f in db.query(IfcFile).filter(IfcFile.project_id == project_id)
        ]
        elements = (
            db.query(Element)
            .filter(Element.ifc_file_id.in_(ifc_file_ids))
            .order_by(Element.id)
            .limit(limit)
            .all()
            if ifc_file_ids
            else []
        )
        if not elements:
            print(f"no elements found for project {project_id}")
            return

        embedder = get_embedder()
        llm_client = get_llm_client()
        rules_text = load_estimating_rules()

        elements_by_group: dict[str, list[Element]] = {}
        for element in elements:
            elements_by_group.setdefault(element.group_hash, []).append(element)

        total_prompt_tokens = 0
        total_completion_tokens = 0
        for group_hash, group_elements in elements_by_group.items():
            representative = group_elements[0]
            candidates, examples = shortlist_and_examples(
                db,
                embedder,
                group_hash,
                representative.profile_text,
                representative.ifc_class,
                representative.predefined_type,
            )
            result = classify_with_llm(
                llm_client,
                representative.profile_text,
                candidates,
                examples,
                rules_text,
            )
            total_prompt_tokens += result.prompt_tokens
            total_completion_tokens += result.completion_tokens

            print(
                f"group {group_hash[:12]}... ({len(group_elements)} element(s), "
                f"e.g. {representative.ifc_class}): -> {result.ibis_code} "
                f"(score={result.self_score}, flags={result.flags})"
            )
            print(f"  reasoning: {result.reasoning}")

        print(
            f"\n{len(elements)} elements in {len(elements_by_group)} group(s). "
            f"Tokens: {total_prompt_tokens} prompt + {total_completion_tokens} "
            f"completion. Cost: $0.00 (local model, Phase 3.1 decision)."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
