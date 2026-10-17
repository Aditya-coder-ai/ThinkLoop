"""Live integration test suite for Neon PostgreSQL.

Activated ONLY when TEST_DATABASE_URL is explicitly set.
Safely rolls back any test transactions and NEVER deletes or modifies production data.
"""

import os
import uuid

import pytest
from sqlalchemy import inspect, select

from app.db.models import Profile
from app.db.session import create_engine, create_session_factory, ping_database


@pytest.mark.asyncio
async def test_live_neon_connectivity_and_schema() -> None:
    """Validate live connectivity and schema integrity against Neon PostgreSQL.

    Safety Guarantee:
    - Skips automatically if TEST_DATABASE_URL is not set.
    - Uses rollbacks for any write verification.
    - Zero data deletion.
    """
    test_db_url = os.getenv("TEST_DATABASE_URL")
    if not test_db_url:
        pytest.skip("TEST_DATABASE_URL not set; skipping live Neon database test.")

    engine = create_engine(test_db_url)

    # 1. Connectivity test
    connected = await ping_database(engine)
    assert connected is True, "Live Neon database failed connectivity ping."

    # 2. Verify schema tables and expected columns
    async with engine.connect() as conn:
        # Check required tables
        def _inspect_tables(connection):
            insp = inspect(connection)
            return set(insp.get_table_names())

        table_names = await conn.run_sync(_inspect_tables)

        # Expected tables
        assert "profiles" in table_names, "Table 'public.profiles' missing in Neon database."
        assert "concepts" in table_names, "Table 'public.concepts' missing in Neon database."
        assert "learner_mastery" in table_names, (
            "Table 'public.learner_mastery' missing in Neon database."
        )

        # Verify columns on profiles
        def _inspect_profiles_cols(connection):
            insp = inspect(connection)
            return {c["name"] for c in insp.get_columns("profiles")}

        profile_cols = await conn.run_sync(_inspect_profiles_cols)
        expected_profile_cols = {
            "user_id",
            "display_name",
            "learning_level",
            "exam_target",
            "created_at",
            "updated_at",
        }
        missing_p_cols = expected_profile_cols - profile_cols
        assert not missing_p_cols, f"Missing columns in profiles: {missing_p_cols}"

        # Verify columns on learner_mastery
        def _inspect_mastery_cols(connection):
            insp = inspect(connection)
            return {c["name"] for c in insp.get_columns("learner_mastery")}

        mastery_cols = await conn.run_sync(_inspect_mastery_cols)
        expected_mastery_cols = {
            "id",
            "user_id",
            "concept_id",
            "mastery_score",
            "attempts",
            "last_practiced_at",
            "next_review_at",
            "updated_at",
        }
        missing_m_cols = expected_mastery_cols - mastery_cols
        assert not missing_m_cols, f"Missing columns in learner_mastery: {missing_m_cols}"

    # 3. Non-destructive write & rollback test
    session_factory = create_session_factory(engine)
    test_user_id = f"test_neon_ephemeral_{uuid.uuid4().hex[:8]}"

    async with session_factory() as session:
        try:
            # Test profile insert inside transaction
            profile = Profile(
                user_id=test_user_id,
                display_name="Ephemeral Test Learner",
                learning_level="Test Level",
            )
            session.add(profile)
            await session.flush()

            # Verify it was visible in this transaction
            stmt = select(Profile).where(Profile.user_id == test_user_id)
            res = await session.execute(stmt)
            fetched = res.scalar_one_or_none()
            assert fetched is not None
        finally:
            # Explicit rollback ensures zero test data persists into production database
            await session.rollback()

    await engine.dispose()
