"""IBM watsonx.ai integration for DevFlow.

Exactly one product responsibility: acting as the evidence-backed priority
judge over findings the deterministic pipeline already produced.  watsonx never
establishes a repository fact, and every failure path falls back to DevFlow's
own deterministic ordering.
"""

from devflow.watsonx._client import (  # noqa: F401
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL_ID,
    DENIED_MODEL_FRAGMENTS,
    WatsonxClient,
    WatsonxConfig,
    is_denied_model,
)
from devflow.watsonx._judge import (  # noqa: F401
    deterministic_order,
    prioritize_findings,
)

__all__ = [
    "DEFAULT_ENDPOINT",
    "DEFAULT_MODEL_ID",
    "DENIED_MODEL_FRAGMENTS",
    "WatsonxClient",
    "WatsonxConfig",
    "deterministic_order",
    "is_denied_model",
    "prioritize_findings",
]
