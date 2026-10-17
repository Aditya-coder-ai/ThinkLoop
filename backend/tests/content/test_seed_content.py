"""Tests verifying the actual seed YAML content against validation rules."""

from pathlib import Path


def test_real_seed_content_passes_strict_validation() -> None:
    """The real seed YAML content must pass strict validation with zero errors and zero warnings."""
    from app.content.validator import ContentValidator

    backend_dir = Path(__file__).resolve().parent.parent.parent
    content_root = backend_dir / "content"

    assert content_root.exists(), f"Content root directory not found at {content_root}"

    validator = ContentValidator(content_root=content_root)
    result = validator.validate()

    # Must have zero errors
    if not result.is_valid:
        error_msgs = "\n".join(f"- [{e.file_path}:{e.item_id}] {e.message}" for e in result.errors)
        raise AssertionError(
            f"Real seed content failed validation with {len(result.errors)} errors:\n{error_msgs}"
        )

    # In strict mode, must also have zero warnings
    if not result.is_valid_strict:
        warning_msgs = "\n".join(
            f"- [{w.file_path}:{w.item_id}] {w.message}" for w in result.warnings
        )
        raise AssertionError(
            f"Real seed content has {len(result.warnings)} warnings in strict mode:\n{warning_msgs}"
        )
