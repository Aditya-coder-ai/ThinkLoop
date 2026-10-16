"""Integration test for Alembic migration upgrade and downgrade cycles."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


def test_alembic_upgrade_head_and_downgrade_base(tmp_path: Path) -> None:
    """Alembic migrations upgrade to head and downgrade to base cleanly."""
    db_file = tmp_path / "migration_test.db"
    # Use sync sqlite driver for alembic CLI runner
    sync_url = f"sqlite:///{db_file}"

    # Path to alembic.ini inside backend
    backend_dir = Path(__file__).resolve().parent.parent.parent
    alembic_ini_path = backend_dir / "alembic.ini"

    if not alembic_ini_path.exists():
        pytest.skip("alembic.ini not yet generated in step 4")

    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", sync_url)
    alembic_cfg.set_main_option("script_location", str(backend_dir / "app" / "db" / "migrations"))

    # Test upgrade head
    command.upgrade(alembic_cfg, "head")

    # Test downgrade base
    command.downgrade(alembic_cfg, "base")

    # Re-upgrade to ensure idempotency
    command.upgrade(alembic_cfg, "head")
