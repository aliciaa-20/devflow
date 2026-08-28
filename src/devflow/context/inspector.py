"""
Repository structure inspector for DevFlow Phase 2.

Walks a locally cloned repository directory and classifies every file into
one of the ArtifactKind categories. No content is read in depth — paths and
file names provide sufficient deterministic signal for classification.

Classification is repository-agnostic: it uses common naming conventions
that apply across many projects and languages, rather than hard-coding
assumptions about any specific repository.
"""

from __future__ import annotations

import os
from pathlib import Path

from devflow.models.context import ArtifactKind

# ---------------------------------------------------------------------------
# Directories that are not useful source content
# ---------------------------------------------------------------------------

_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "venv",
        ".venv",
        "env",
        ".env",
        "node_modules",
        ".idea",
        ".vscode",
        "dist",
        "build",
        "target",    # Rust / Maven
        "_build",    # Sphinx
        "site",      # MkDocs
    }
)

# ---------------------------------------------------------------------------
# Test file / directory signals
# ---------------------------------------------------------------------------

_TEST_DIR_FRAGMENTS: tuple[str, ...] = (
    "test",
    "tests",
    "spec",
    "specs",
    "__tests__",
)

_TEST_FILE_PREFIXES: tuple[str, ...] = (
    "test_",
    "test-",
)

_TEST_FILE_SUFFIXES: tuple[str, ...] = (
    "_test",
    ".test",
    "_spec",
    ".spec",
)

# ---------------------------------------------------------------------------
# Documentation signals
# ---------------------------------------------------------------------------

_DOC_DIR_FRAGMENTS: tuple[str, ...] = (
    "doc",
    "docs",
    "documentation",
    "wiki",
)

_DOC_EXTENSIONS: frozenset[str] = frozenset(
    {".md", ".rst", ".txt", ".adoc", ".asciidoc", ".html", ".htm", ".pdf"}
)

_DOC_FILENAMES: frozenset[str] = frozenset(
    {
        "readme",
        "changelog",
        "changes",
        "contributing",
        "license",
        "licence",
        "authors",
        "notice",
        "history",
        "todo",
        "roadmap",
    }
)

# ---------------------------------------------------------------------------
# Dependency manifest signals
# ---------------------------------------------------------------------------

_DEPENDENCY_FILENAMES: frozenset[str] = frozenset(
    {
        "requirements.txt",
        "requirements-dev.txt",
        "requirements-test.txt",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "pipfile",
        "pipfile.lock",
        "poetry.lock",
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "cargo.toml",
        "cargo.lock",
        "gemfile",
        "gemfile.lock",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "go.mod",
        "go.sum",
        "composer.json",
        "composer.lock",
        "mix.exs",
        "mix.lock",
        "pubspec.yaml",
        "pubspec.lock",
    }
)

# ---------------------------------------------------------------------------
# Configuration file signals
# ---------------------------------------------------------------------------

_CONFIG_FILENAMES: frozenset[str] = frozenset(
    {
        ".env",
        ".env.example",
        ".env.sample",
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        ".dockerignore",
        ".gitignore",
        ".gitattributes",
        ".editorconfig",
        "makefile",
        "justfile",
        "tox.ini",
        "pytest.ini",
        ".flake8",
        ".pylintrc",
        "mypy.ini",
        ".mypy.ini",
        "ruff.toml",
        ".ruff.toml",
        "tsconfig.json",
        "jsconfig.json",
        ".babelrc",
        "webpack.config.js",
        "vite.config.js",
        "vite.config.ts",
        ".eslintrc",
        ".eslintrc.js",
        ".eslintrc.json",
        ".prettierrc",
        ".travis.yml",
        "circle.ci",
        ".github",
        "sonar-project.properties",
        "codecov.yml",
        ".codecov.yml",
    }
)

_CONFIG_EXTENSIONS: frozenset[str] = frozenset(
    {".yml", ".yaml", ".ini", ".cfg", ".toml", ".conf", ".config", ".json"}
)

# ---------------------------------------------------------------------------
# Entry point signals
# ---------------------------------------------------------------------------

_ENTRY_POINT_FILENAMES: frozenset[str] = frozenset(
    {
        "__main__.py",
        "main.py",
        "app.py",
        "server.py",
        "wsgi.py",
        "asgi.py",
        "manage.py",
        "cli.py",
        "run.py",
        "index.js",
        "index.ts",
        "main.ts",
        "main.js",
        "main.go",
        "main.rs",
        "main.rb",
        "main.java",
        "application.java",
    }
)

# ---------------------------------------------------------------------------
# Source file extensions
# ---------------------------------------------------------------------------

_SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".java",
        ".kt",
        ".scala",
        ".go",
        ".rs",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".cs",
        ".rb",
        ".php",
        ".swift",
        ".m",
        ".ex",
        ".exs",
        ".erl",
        ".hs",
        ".ml",
        ".clj",
        ".cljs",
        ".dart",
        ".lua",
        ".r",
        ".jl",
        ".nim",
        ".zig",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
    }
)


# ---------------------------------------------------------------------------
# Main classifier
# ---------------------------------------------------------------------------


def classify_file(rel_path: str) -> ArtifactKind:
    """
    Classify a file path (relative to the repository root) into an ArtifactKind.

    Classification priority (highest first):
    1. Dependency manifest
    2. Test file / directory
    3. Documentation
    4. Configuration
    5. Source code
    6. Other

    Args:
        rel_path: Forward-slash separated path relative to repo root.

    Returns:
        An ArtifactKind enum value.
    """
    path = Path(rel_path)
    filename_lower = path.name.lower()
    stem_lower = path.stem.lower()
    ext = path.suffix.lower()
    parts_lower = [p.lower() for p in path.parts]

    # 1 — Dependency manifest (check before config as some overlap, e.g. pyproject.toml)
    if filename_lower in _DEPENDENCY_FILENAMES:
        return ArtifactKind.DEPENDENCY

    # 2 — Test files
    # a) Any part of the directory path is a known test dir
    if any(
        part in _TEST_DIR_FRAGMENTS
        for part in parts_lower[:-1]  # only directory parts
    ):
        return ArtifactKind.TEST
    # b) Filename has test prefix / suffix
    if stem_lower.startswith(_TEST_FILE_PREFIXES) or stem_lower.endswith(
        _TEST_FILE_SUFFIXES
    ):
        return ArtifactKind.TEST

    # 3 — Documentation
    if any(frag in parts_lower[:-1] for frag in _DOC_DIR_FRAGMENTS):
        return ArtifactKind.DOCUMENTATION
    if ext in _DOC_EXTENSIONS:
        return ArtifactKind.DOCUMENTATION
    if stem_lower in _DOC_FILENAMES:
        return ArtifactKind.DOCUMENTATION

    # 4 — Configuration (only if ext matches; raw filenames like Dockerfile below)
    if filename_lower in _CONFIG_FILENAMES:
        return ArtifactKind.CONFIGURATION
    if ext in _CONFIG_EXTENSIONS:
        return ArtifactKind.CONFIGURATION

    # 5 — Source code
    if ext in _SOURCE_EXTENSIONS:
        return ArtifactKind.SOURCE

    return ArtifactKind.OTHER


def is_entry_point(rel_path: str) -> bool:
    """Return True if the file is a likely application entry point."""
    return Path(rel_path).name.lower() in _ENTRY_POINT_FILENAMES


# ---------------------------------------------------------------------------
# Repository walker
# ---------------------------------------------------------------------------


def walk_repository(root: Path) -> tuple[list[str], list[str]]:
    """
    Walk a local repository root and return all inspectable file paths.

    Args:
        root: Absolute path to the repository root.

    Returns:
        A (all_files, entry_points) tuple where:
        - all_files is a sorted list of paths relative to root (forward slashes).
        - entry_points is the subset identified as application entry points.

    Skips known non-source directories (.git, node_modules, __pycache__, etc.).
    """
    all_files: list[str] = []
    entry_points: list[str] = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skipped directories in-place (affects os.walk recursion).
        dirnames[:] = [
            d for d in dirnames if d.lower() not in _SKIP_DIRS and not d.startswith(".")
        ]

        rel_dir = Path(dirpath).relative_to(root)

        for filename in sorted(filenames):
            rel_path = str(rel_dir / filename) if str(rel_dir) != "." else filename
            # Normalise to forward slashes.
            rel_path = rel_path.replace(os.sep, "/")
            all_files.append(rel_path)
            if is_entry_point(rel_path):
                entry_points.append(rel_path)

    all_files.sort()
    entry_points.sort()
    return all_files, entry_points
