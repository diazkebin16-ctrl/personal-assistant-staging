"""Migration round-trip validation from an empty database."""

from scripts.validate_migrations import validate_migrations


def test_migrations_upgrade_downgrade_and_reupgrade() -> None:
    validate_migrations()
