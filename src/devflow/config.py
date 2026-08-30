import os
from pathlib import Path


class Config:
    """
    DevFlow configuration.

    All values are read from environment variables.
    No credentials or external secrets are required in Phase 0.

    Phase 1 will introduce:
      - repository_url: supplied as CLI input, not configuration
      - github_token:   optional, read from DEVFLOW_GITHUB_TOKEN environment variable
    """

    version: str = "0.1.0"

    def __init__(self) -> None:
        self.log_level: str = os.environ.get("DEVFLOW_LOG_LEVEL", "INFO")


# ---------------------------------------------------------------------------
# .env loading
# ---------------------------------------------------------------------------

DOTENV_FILENAME = ".env"

_dotenv_loaded = False


def find_dotenv(start: Path | None = None) -> Path | None:
    """Locate a .env file in the working directory or the project root.

    Checked in order: the current working directory, then the repository root
    that contains this package.  Returns None when no file exists.
    """
    candidates = []
    if start is not None:
        candidates.append(Path(start))
    else:
        candidates.append(Path.cwd())
    # src/devflow/config.py -> repository root
    candidates.append(Path(__file__).resolve().parents[2])

    for directory in candidates:
        candidate = directory / DOTENV_FILENAME
        if candidate.is_file():
            return candidate
    return None


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines.

    Supports ``export`` prefixes, ``#`` comments, blank lines, and single or
    double quoted values.  Deliberately minimal: this reads a local secrets
    file, so it does no interpolation and executes nothing.
    """
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def load_dotenv(path: Path | None = None, *, force: bool = False) -> list[str]:
    """Load a .env file into os.environ without overriding what is already set.

    Real environment variables always win, so an operator can override the file
    for a single command.  Returns the names (never the values) that were
    loaded, so callers can log what happened without leaking a secret.

    Runs at most once per process unless ``force`` is set.
    """
    global _dotenv_loaded
    if _dotenv_loaded and not force:
        return []

    target = path or find_dotenv()
    _dotenv_loaded = True
    if target is None:
        return []

    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return []

    loaded: list[str] = []
    for key, value in parse_dotenv(text).items():
        if key in os.environ and os.environ[key] != "":
            continue
        os.environ[key] = value
        loaded.append(key)
    return loaded
