"""Release packaging must preserve templates without leaking real environment files."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.package_release import build_archive, should_include, validate_env_template


def test_env_example_is_explicitly_included() -> None:
    assert should_include(Path(".env.example"))


@pytest.mark.parametrize(
    "name",
    ["apps/web/.env.local.example", "apps/web/.env.production.example"],
)
def test_safe_web_env_examples_are_explicitly_included(name: str) -> None:
    assert should_include(Path(name))


def test_unapproved_env_example_is_excluded() -> None:
    assert not should_include(Path("apps/web/.env.preview.example"))


@pytest.mark.parametrize("name", [".env", ".env.local", ".env.staging", ".env.production"])
def test_real_environment_files_are_excluded(name: str) -> None:
    assert not should_include(Path(name))


@pytest.mark.parametrize(
    "name",
    [
        "apps/web/node_modules/pkg/index.js",
        "apps/web/dist/assets/app.js",
        "apps/web/.vite/cache.json",
        "apps/web/coverage/index.html",
        "apps/web/playwright-report/index.html",
        "apps/web/test-results/failure.webm",
    ],
)
def test_web_tooling_outputs_are_excluded(name: str) -> None:
    assert not should_include(Path(name))


def test_build_archive_preserves_template_and_excludes_secret_env(tmp_path: Path) -> None:
    source = tmp_path / "project"
    source.mkdir()
    (source / ".env.example").write_text("APP_VERSION=0.11.0\nSUPABASE_ANON_KEY=\n")
    (source / ".env").write_text("SUPABASE_ANON_KEY=real-secret\n")
    (source / "source.txt").write_text("source\n")
    output = tmp_path / "artifact.zip"

    assert build_archive(source, output) == 2
    with ZipFile(output) as archive:
        assert archive.namelist() == ["project/.env.example", "project/source.txt"]


def test_sensitive_template_value_is_rejected(tmp_path: Path) -> None:
    template = tmp_path / ".env.example"
    template.write_text("SUPABASE_SERVICE_ROLE_KEY=not-a-placeholder\n")
    with pytest.raises(ValueError, match="must be empty"):
        validate_env_template(template)


def test_missing_template_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be present"):
        validate_env_template(tmp_path / ".env.example")
