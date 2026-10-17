"""Thinkloop Retrieval Evaluation Harness.

Computes Recall@3, Recall@5, MRR (Mean Reciprocal Rank), and False Positive Rate
for negative controls across labeled misconception retrieval cases.

Modes:
- fake: Wiring test using deterministic FakeEmbedder (CI / make verify default).
- http: Quality gate using HttpEmbedder against semantic embeddings provider.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

# Ensure backend root is on sys.path for direct script execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.content.embedder import Embedder, FakeEmbedder, HttpEmbedder
from app.content.loader import ContentLoader
from app.content.retrieval import RetrievalService
from app.db.base import Base


async def setup_eval_db(embedder: Embedder, content_dir: Path) -> async_sessionmaker[AsyncSession]:
    """Initialize an isolated in-memory/temp database and sync content."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    loader = ContentLoader(
        session_factory=session_factory,
        embedder=embedder,
        content_root=content_dir,
    )
    await loader.sync()
    return session_factory


async def run_evaluation(
    embedder_mode: str = "fake",
    cases_file: Path | None = None,
    content_dir: Path | None = None,
    min_score_threshold: float = 0.65,
    target_recall_at_5: float = 0.85,
    target_mrr: float = 0.60,
    target_max_fp_rate: float = 0.20,
) -> dict[str, float]:
    """Run full evaluation suite and return metrics dict."""
    root_dir = Path(__file__).resolve().parent.parent
    if cases_file is None:
        cases_file = root_dir / "evals" / "retrieval_cases.yaml"
    if content_dir is None:
        content_dir = root_dir / "content"

    with open(cases_file, encoding="utf-8") as f:
        cases: list[dict[str, Any]] = yaml.safe_load(f)

    # Initialize embedder
    embedder: Embedder
    settings = get_settings()
    if embedder_mode == "http":
        if not settings.embedding_endpoint_url:
            print("ERROR: EMBEDDING_ENDPOINT_URL is required for http mode.")
            sys.exit(1)
        embedder = HttpEmbedder(
            endpoint_url=str(settings.embedding_endpoint_url),
            api_key=settings.embedding_api_key or "",
            model=settings.embedding_model,
            dim=settings.embedding_dim,
        )
    else:
        embedder = FakeEmbedder(dim=settings.embedding_dim)

    session_factory = await setup_eval_db(embedder, content_dir)

    positive_cases = [c for c in cases if c.get("expected_misconception_id") is not None]
    negative_cases = [c for c in cases if c.get("expected_misconception_id") is None]

    hits_at_3 = 0
    hits_at_5 = 0
    reciprocal_ranks: list[float] = []
    false_positives = 0

    async with session_factory() as session:
        retrieval = await RetrievalService.from_db(session=session, embedder=embedder)

        # Evaluate positive cases
        for case in positive_cases:
            text = case["text"]
            expected_id = case["expected_misconception_id"]
            concept_id = case.get("concept_id")

            results = retrieval.find_misconceptions(
                text=text,
                concept_id=concept_id,
                k=10,
                include_prereqs=True,
            )

            matched_rank: int | None = None
            for idx, item in enumerate(results):
                if item.misconception_id == expected_id:
                    matched_rank = idx + 1
                    break

            if matched_rank is not None:
                if matched_rank <= 3:
                    hits_at_3 += 1
                if matched_rank <= 5:
                    hits_at_5 += 1
                reciprocal_ranks.append(1.0 / matched_rank)
            else:
                reciprocal_ranks.append(0.0)

        # Evaluate negative cases
        for case in negative_cases:
            text = case["text"]
            concept_id = case.get("concept_id")

            results = retrieval.find_misconceptions(
                text=text,
                concept_id=concept_id,
                k=5,
                include_prereqs=True,
            )

            # Check if any top result exceeds min_score threshold
            if results and results[0].score >= min_score_threshold:
                false_positives += 1

    total_pos = len(positive_cases)
    total_neg = len(negative_cases)

    recall_at_3 = (hits_at_3 / total_pos) if total_pos > 0 else 0.0
    recall_at_5 = (hits_at_5 / total_pos) if total_pos > 0 else 0.0
    mrr = (sum(reciprocal_ranks) / total_pos) if total_pos > 0 else 0.0
    fp_rate = (false_positives / total_neg) if total_neg > 0 else 0.0

    print("\n" + "=" * 60)
    print(f"RETRIEVAL EVALUATION REPORT (Mode: {embedder_mode})")
    print("=" * 60)
    print(f"Total Test Cases     : {len(cases)}")
    print(f"  - Positive Cases   : {total_pos}")
    print(f"  - Negative Controls: {total_neg}")
    print("-" * 60)
    print("Metric               Score      Target     Status")
    print("-" * 60)

    # Format status strings
    status_r5 = "PASS" if recall_at_5 >= target_recall_at_5 else "FAIL"
    status_mrr = "PASS" if mrr >= target_mrr else "FAIL"
    status_fp = "PASS" if fp_rate <= target_max_fp_rate else "FAIL"

    if embedder_mode == "fake":
        status_r5 = "INFO (fake)"
        status_mrr = "INFO (fake)"
        status_fp = "INFO (fake)"

    print(f"Recall@3             {recall_at_3:6.3f}     N/A        INFO")
    print(f"Recall@5             {recall_at_5:6.3f}     >={target_recall_at_5:.2f}     {status_r5}")
    print(f"MRR                  {mrr:6.3f}     >={target_mrr:.2f}     {status_mrr}")
    print(f"False Positive Rate  {fp_rate:6.3f}     <={target_max_fp_rate:.2f}     {status_fp}")
    print("=" * 60)

    metrics = {
        "recall_at_3": recall_at_3,
        "recall_at_5": recall_at_5,
        "mrr": mrr,
        "fp_rate": fp_rate,
        "positive_cases": total_pos,
        "negative_cases": total_neg,
    }

    if embedder_mode == "http":
        passed = (
            recall_at_5 >= target_recall_at_5
            and mrr >= target_mrr
            and fp_rate <= target_max_fp_rate
        )
        if not passed:
            print("\nEvaluation failed to meet required thresholds in HTTP mode.")
            sys.exit(1)
        else:
            print("\nAll retrieval evaluation criteria passed successfully!")
    else:
        print("\nWiring verification successful: FakeEmbedder evaluated mechanically.")

    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Thinkloop Retrieval Evaluation Harness")
    parser.add_argument(
        "--embedder",
        choices=["fake", "http"],
        default="fake",
        help="Embedder implementation ('fake' for wiring test, 'http' for quality gate)",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=None,
        help="Path to retrieval_cases.yaml",
    )
    parser.add_argument(
        "--content",
        type=Path,
        default=None,
        help="Path to curriculum content root directory",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.65,
        help="Minimum similarity score threshold for negative FP check",
    )
    args = parser.parse_args()

    asyncio.run(
        run_evaluation(
            embedder_mode=args.embedder,
            cases_file=args.cases,
            content_dir=args.content,
            min_score_threshold=args.min_score,
        )
    )


if __name__ == "__main__":
    main()
