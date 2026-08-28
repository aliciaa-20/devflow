import devflow
from devflow.config import Config


def test_version() -> None:
    assert devflow.__version__ == "0.1.0"


def test_config_loads() -> None:
    config = Config()
    assert config.log_level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def test_pipeline_importable() -> None:
    import devflow.pipeline  # noqa: F401
