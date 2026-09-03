"""Build a deterministic source artifact while preserving the safe env template."""

from __future__ import annotations

import argparse
import stat
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

EXCLUDED_DIRECTORIES = {
    ".git",
    ".gradle",
    ".idea",
    ".kotlin",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".vscode",
    ".vite",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "playwright-report",
    "test-results",
}
EXCLUDED_SUFFIXES = {
    ".aab",
    ".apk",
    ".db",
    ".dm",
    ".jks",
    ".keystore",
    ".log",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
    ".webm",
}
EXCLUDED_FILENAMES = {".coverage", ".DS_Store", "local.properties"}
SAFE_ENV_EXAMPLE_PATHS = {
    ".env.example",
    "apps/web/.env.local.example",
    "apps/web/.env.production.example",
}
SENSITIVE_TEMPLATE_KEYS = {
    "DATABASE_URL",
    "SENTRY_DSN",
    "SUPABASE_ANON_KEY",
    "SUPABASE_JWKS_URL",
    "SUPABASE_JWT_ISSUER",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_URL",
}


def should_include(relative_path: Path) -> bool:
    """Return whether a source path is safe and necessary in the release ZIP."""
    if any(
        part in EXCLUDED_DIRECTORIES or part.endswith(".egg-info") for part in relative_path.parts
    ):
        return False
    if relative_path.as_posix() in SAFE_ENV_EXAMPLE_PATHS:
        return True
    if relative_path.name == ".env" or relative_path.name.startswith(".env."):
        return False
    if relative_path.name in EXCLUDED_FILENAMES:
        return False
    return relative_path.suffix.lower() not in EXCLUDED_SUFFIXES


def validate_env_template(template: Path) -> None:
    """Reject missing templates and non-placeholder sensitive configuration."""
    if not template.is_file():
        raise ValueError(".env.example must be present in every release artifact")
    for raw_line in template.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise ValueError(f"Malformed .env.example entry: {key}")
        if key in SENSITIVE_TEMPLATE_KEYS and value.strip():
            raise ValueError(f"Sensitive template value must be empty: {key}")


def build_archive(source_root: Path, output: Path) -> int:
    """Create a stable source ZIP and return its file count."""
    source_root = source_root.resolve()
    output = output.resolve()
    validate_env_template(source_root / ".env.example")
    for relative_path in SAFE_ENV_EXAMPLE_PATHS - {".env.example"}:
        template = source_root / relative_path
        if template.exists():
            validate_env_template(template)
    files = sorted(
        path
        for path in source_root.rglob("*")
        if path.is_file()
        and should_include(path.relative_to(source_root))
        and path.resolve() != output
    )
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = PurePosixPath(source_root.name) / PurePosixPath(
                path.relative_to(source_root).as_posix()
            )
            info = ZipInfo(str(relative), date_time=(1980, 1, 1, 0, 0, 0))
            mode = stat.S_IMODE(path.stat().st_mode)
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, path.read_bytes(), compresslevel=9)
    return len(files)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--source", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()
    count = build_archive(args.source, args.output)
    print(f"Created {args.output} with {count} files")


if __name__ == "__main__":
    main()
