"""Thinkloop Content Management CLI.

Commands:
- validate: validate curriculum YAML content against schemas and graph constraints.
- sync: synchronize validated curriculum content into PostgreSQL database.
- stats: display curriculum statistics.
- eval-retrieval: run retrieval evaluation harness across labeled cases.
"""

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from app.config import get_settings
from app.content.embedder import Embedder, FakeEmbedder, HttpEmbedder
from app.content.loader import ContentLoader
from app.content.validator import ContentValidator
from app.db.session import create_engine, create_session_factory

cli_app = typer.Typer(
    name="thinkloop-content",
    help="Thinkloop Curriculum & Content Management CLI",
    no_args_is_help=True,
)
console = Console()


@cli_app.command("validate")
def validate_content(
    content_dir: Annotated[
        Path,
        typer.Argument(help="Path to curriculum content root directory"),
    ] = Path("content"),
    strict: Annotated[
        bool,
        typer.Option("--strict", "-s", help="Fail on warnings as well as errors"),
    ] = False,
) -> None:
    """Validate curriculum YAML files against schemas and cross-file graph rules."""
    if not content_dir.exists():
        console.print(f"[bold red]Error: Directory '{content_dir}' does not exist.[/bold red]")
        raise typer.Exit(code=1)

    console.print(f"[bold blue]Validating curriculum content in:[/] {content_dir.resolve()}")
    validator = ContentValidator(content_root=content_dir)
    result = validator.validate()

    if result.errors:
        console.print(
            f"\n[bold red]Validation failed with {len(result.errors)} error(s):[/bold red]"
        )
        table = Table("File", "Item ID", "Error Message")
        for err in result.errors:
            table.add_row(err.file_path, err.item_id or "-", err.message)
        console.print(table)

    if result.warnings:
        console.print(
            f"\n[bold yellow]Validation reported {len(result.warnings)} warning(s):[/bold yellow]"
        )
        table = Table("File", "Item ID", "Warning Message")
        for warn in result.warnings:
            table.add_row(warn.file_path, warn.item_id or "-", warn.message)
        console.print(table)

    if not result.is_valid:
        console.print("\n[bold red]FAILED:[/] Content validation errors must be resolved.")
        raise typer.Exit(code=1)

    if strict and not result.is_valid_strict:
        console.print("\n[bold red]FAILED (Strict Mode):[//] Content warnings must be resolved.")
        raise typer.Exit(code=1)

    console.print(
        f"\n[bold green]SUCCESS:[/] Content validation passed"
        f"{' strictly (zero warnings)' if strict else ''}."
    )


@cli_app.command("sync")
def sync_content(
    content_dir: Annotated[
        Path,
        typer.Argument(help="Path to curriculum content root directory"),
    ] = Path("content"),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Simulate synchronization without committing to DB"),
    ] = False,
    force_fake_embedder: Annotated[
        bool,
        typer.Option("--fake-embedder", help="Force FakeEmbedder even if HTTP credentials exist"),
    ] = False,
) -> None:
    """Synchronize validated curriculum content into PostgreSQL database."""
    if not content_dir.exists():
        console.print(f"[bold red]Error: Directory '{content_dir}' does not exist.[/bold red]")
        raise typer.Exit(code=1)

    # 1. Validation gate: abort immediately before touching DB if invalid
    console.print(f"[bold blue]Step 1: Validating curriculum content in:[/] {content_dir}")
    validator = ContentValidator(content_root=content_dir)
    val_res = validator.validate()
    if not val_res.is_valid:
        console.print(
            f"\n[bold red]Validation failed with {len(val_res.errors)} error(s). "
            "Sync aborted.[/bold red]"
        )
        for err in val_res.errors:
            console.print(f"  - [{err.file_path}:{err.item_id or '-'}] {err.message}")
        raise typer.Exit(code=1)

    # 2. Database & Embedder configuration
    settings = get_settings()
    console.print(f"[bold blue]Step 2: Connecting to database:[/] {settings.database_url}")
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    embedder: Embedder
    if not force_fake_embedder and settings.embedding_endpoint_url:
        console.print(f"Using HttpEmbedder: {settings.embedding_endpoint_url}")
        embedder = HttpEmbedder(
            endpoint_url=str(settings.embedding_endpoint_url),
            api_key=settings.embedding_api_key or "",
            model=settings.embedding_model,
            dimension=settings.embedding_dim,
        )
    else:
        console.print(f"Using FakeEmbedder (dimension={settings.embedding_dim})")
        embedder = FakeEmbedder(dimension=settings.embedding_dim)

    # 3. Synchronize
    loader = ContentLoader(
        session_factory=session_factory,
        embedder=embedder,
        content_root=content_dir,
    )

    async def _do_sync() -> None:
        try:
            report = await loader.sync(dry_run=dry_run)
            console.print("\n[bold green]Synchronization Report:[/bold green]")
            table = Table("Entity", "Created", "Updated", "Deactivated")
            table.add_row(
                "Concepts",
                str(report.created_concepts),
                str(report.updated_concepts),
                str(report.deactivated_concepts),
            )
            table.add_row(
                "Concept Edges", str(report.created_edges), "-", str(report.removed_edges)
            )
            table.add_row(
                "Misconceptions",
                str(report.created_misconceptions),
                str(report.updated_misconceptions),
                str(report.deactivated_misconceptions),
            )
            table.add_row(
                "Problems",
                str(report.created_problems),
                str(report.updated_problems),
                str(report.deactivated_problems),
            )
            console.print(table)
            console.print(f"Embeddings Computed : {report.embeddings_computed}")
            console.print(f"Dry Run Mode        : {report.is_dry_run}")
        finally:
            await engine.dispose()

    try:
        asyncio.run(_do_sync())
    except Exception as exc:
        console.print(f"\n[bold red]Sync failed with error:[/] {exc}")
        raise typer.Exit(code=1) from exc


@cli_app.command("stats")
def content_stats(
    content_dir: Annotated[
        Path,
        typer.Argument(help="Path to curriculum content root directory"),
    ] = Path("content"),
) -> None:
    """Display curriculum overview statistics from YAML source files."""
    if not content_dir.exists():
        console.print(f"[bold red]Error: Directory '{content_dir}' does not exist.[/bold red]")
        raise typer.Exit(code=1)

    validator = ContentValidator(content_root=content_dir)
    data = validator.load_all()

    topics = data.get("topics", [])
    concepts = data.get("concepts", [])
    misconceptions = data.get("misconceptions", [])
    problems = data.get("problems", [])

    total_edges = sum(len(c.prerequisites) for c in concepts)

    table = Table(title="Curriculum Content Overview")
    table.add_column("Resource Type", style="cyan")
    table.add_column("Count", style="green")

    table.add_row("Topics", str(len(topics)))
    table.add_row("Concepts", str(len(concepts)))
    table.add_row("Prerequisite Edges", str(total_edges))
    table.add_row("Misconceptions", str(len(misconceptions)))
    table.add_row("Problems", str(len(problems)))

    console.print(table)


@cli_app.command("eval-retrieval")
def eval_retrieval_cmd(
    embedder: Annotated[
        str,
        typer.Option("--embedder", "-e", help="Embedder mode ('fake' or 'http')"),
    ] = "fake",
    cases: Annotated[
        Path | None,
        typer.Option("--cases", "-c", help="Path to retrieval_cases.yaml"),
    ] = None,
    content: Annotated[
        Path | None,
        typer.Option("--content", help="Path to content directory"),
    ] = None,
) -> None:
    """Run vector retrieval evaluation harness."""
    from evals.run_retrieval_eval import run_evaluation

    asyncio.run(
        run_evaluation(
            embedder_mode=embedder,
            cases_file=cases,
            content_dir=content,
        )
    )


if __name__ == "__main__":
    cli_app()
