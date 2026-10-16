"""Script to verify that Alembic migrations cleanly upgrade to head and downgrade to base."""

import contextlib
import os
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config


def main() -> None:
    """Verify that migrations can upgrade to head, downgrade to base, and re-upgrade."""
    backend_dir = Path(__file__).resolve().parent.parent
    alembic_ini_path = backend_dir / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "app" / "db" / "migrations"))

    db_url = os.getenv("DATABASE_URL")
    temp_path: Path | None = None

    if not db_url:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            temp_path = Path(tf.name)
        db_url = f"sqlite:///{temp_path.as_posix()}"
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        os.environ["DATABASE_URL"] = db_url

    try:
        print(f"Verifying migrations on database target: {db_url}")
        print("1. Running alembic upgrade head...")
        command.upgrade(alembic_cfg, "head")
        print("2. Running alembic downgrade base...")
        command.downgrade(alembic_cfg, "base")
        print("3. Running alembic upgrade head (idempotency check)...")
        command.upgrade(alembic_cfg, "head")
        print("Migration verification succeeded: upgrade head and downgrade base passed cleanly.")
    finally:
        if temp_path is not None:
            with contextlib.suppress(OSError):
                temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
