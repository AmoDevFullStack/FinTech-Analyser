"""Migration-graph and build-identity checks that need no database."""

from __future__ import annotations

from app.core.release import BuildInfo, expected_revisions


def test_migrations_have_exactly_one_head() -> None:
    # Two branches that each add a migration merge cleanly in git and leave Alembic with two
    # heads; `alembic upgrade head` then refuses to run during the deploy. Failing here moves
    # that discovery from the release to the pull request.
    heads = expected_revisions()
    assert len(heads) == 1, f"expected one Alembic head, found {sorted(heads)}"


def test_build_info_defaults_describe_an_unreleased_build() -> None:
    info = BuildInfo.from_config({})
    assert info.as_dict() == {"version": "dev", "commit": "unknown", "built_at": None}


def test_build_info_reads_configured_values() -> None:
    info = BuildInfo.from_config(
        {"APP_VERSION": "1.4.0", "BUILD_SHA": "abc1234", "BUILD_TIME": "2026-11-21T10:00:00Z"}
    )
    assert info.version == "1.4.0"
    assert info.commit == "abc1234"
    assert info.built_at == "2026-11-21T10:00:00Z"
