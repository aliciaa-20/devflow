import os


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
