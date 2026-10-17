"""Unit tests for content CLI commands."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from app.content.cli import cli_app
from app.content.loader import SyncReport

runner = CliRunner()


def test_cli_validate_success() -> None:
    backend_dir = Path(__file__).resolve().parent.parent.parent
    content_dir = backend_dir / "content"

    result = runner.invoke(cli_app, ["validate", str(content_dir), "--strict"])
    assert result.exit_code == 0
    assert "SUCCESS" in result.stdout


def test_cli_validate_nonexistent_dir() -> None:
    result = runner.invoke(cli_app, ["validate", "nonexistent/dir/path"])
    assert result.exit_code == 1
    assert "does not exist" in result.stdout


def test_cli_validate_with_errors(tmp_path: Path) -> None:
    # Create invalid YAML
    t_dir = tmp_path / "physics" / "mechanics"
    t_dir.mkdir(parents=True)
    (t_dir / "topic.yaml").write_text("invalid_key: 123\n")

    result = runner.invoke(cli_app, ["validate", str(tmp_path)])
    assert result.exit_code == 1
    assert "Validation failed" in result.stdout


def test_cli_stats_success() -> None:
    backend_dir = Path(__file__).resolve().parent.parent.parent
    content_dir = backend_dir / "content"

    result = runner.invoke(cli_app, ["stats", str(content_dir)])
    assert result.exit_code == 0
    assert "Curriculum Content Overview" in result.stdout
    assert "Concepts" in result.stdout
    assert "15" in result.stdout


def test_cli_stats_nonexistent_dir() -> None:
    result = runner.invoke(cli_app, ["stats", "nonexistent/dir/path"])
    assert result.exit_code == 1
    assert "does not exist" in result.stdout


def test_cli_sync_nonexistent_dir() -> None:
    result = runner.invoke(cli_app, ["sync", "nonexistent/dir/path"])
    assert result.exit_code == 1
    assert "does not exist" in result.stdout


def test_cli_sync_validation_failure_aborts(tmp_path: Path) -> None:
    t_dir = tmp_path / "physics" / "mechanics"
    t_dir.mkdir(parents=True)
    (t_dir / "topic.yaml").write_text("bad: yaml\n")

    result = runner.invoke(cli_app, ["sync", str(tmp_path)])
    assert result.exit_code == 1
    assert "Sync aborted" in result.stdout


def test_cli_sync_dry_run_success() -> None:
    backend_dir = Path(__file__).resolve().parent.parent.parent
    content_dir = backend_dir / "content"

    mock_report = SyncReport(
        created_concepts=15,
        created_edges=16,
        created_misconceptions=15,
        created_problems=18,
        embeddings_computed=30,
        is_dry_run=True,
    )

    with patch("app.content.loader.ContentLoader.sync", new_callable=AsyncMock) as mock_sync:
        mock_sync.return_value = mock_report
        result = runner.invoke(cli_app, ["sync", str(content_dir), "--dry-run", "--fake-embedder"])
        assert result.exit_code == 0
        assert "Synchronization Report" in result.stdout
        assert "Dry Run Mode" in result.stdout
        mock_sync.assert_called_once_with(dry_run=True)


def test_cli_sync_failure_handling() -> None:
    backend_dir = Path(__file__).resolve().parent.parent.parent
    content_dir = backend_dir / "content"

    with patch("app.content.loader.ContentLoader.sync", new_callable=AsyncMock) as mock_sync:
        mock_sync.side_effect = RuntimeError("Database connection timed out")
        result = runner.invoke(cli_app, ["sync", str(content_dir), "--fake-embedder"])
        assert result.exit_code == 1
        assert "Sync failed with error" in result.stdout


def test_cli_eval_retrieval_fake_mode() -> None:
    with patch("evals.run_retrieval_eval.run_evaluation", new_callable=AsyncMock) as mock_eval:
        mock_eval.return_value = {"recall_at_5": 0.9}
        result = runner.invoke(cli_app, ["eval-retrieval", "--embedder", "fake"])
        assert result.exit_code == 0
        mock_eval.assert_called_once()
