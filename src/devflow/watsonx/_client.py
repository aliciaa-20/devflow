"""Minimal IBM watsonx.ai client.

Standard library only -- no new runtime dependency.  Authentication follows the
documented IBM Cloud flow: an API key is exchanged for a short-lived IAM
bearer token, which authorizes the watsonx.ai text-generation endpoint.

Credentials are read from the environment and are never written to disk, never
logged, and never included in a cached response.
"""

from __future__ import annotations

import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

from devflow.config import load_dotenv
from devflow.models.prioritization import WatsonxError

logger = logging.getLogger(__name__)

IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"
DEFAULT_ENDPOINT = "https://us-south.ml.cloud.ibm.com"  # Dallas, per hackathon guide

# Granite 4 is chat-tuned: the legacy /text/generation endpoint accepts it but
# returns empty completions, so DevFlow uses /text/chat. Verified available on
# the hackathon-provisioned Dallas project.
DEFAULT_MODEL_ID = "ibm/granite-4-h-small"
CHAT_PATH = "/ml/v1/text/chat"
API_VERSION = "2024-03-14"

# Models the IBM TechXchange 2026 hackathon guide places out of scope. Using one
# "can negatively impact the judgment of your project submission", so the client
# refuses rather than silently complying with a misconfiguration.
DENIED_MODEL_FRAGMENTS = (
    "llama-3-405b-instruct",
    "mistral-medium-2505",
    "mistral-small-3-1-24b-instruct-2503",
)

# IAM tokens last 60 minutes; refresh early so a long analysis cannot straddle
# an expiry boundary.
_TOKEN_REFRESH_MARGIN_SECONDS = 300


def is_denied_model(model_id: str) -> bool:
    normalized = (model_id or "").lower()
    return any(fragment in normalized for fragment in DENIED_MODEL_FRAGMENTS)


class WatsonxConfig:
    """watsonx.ai connection settings resolved from the environment."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        project_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        model_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        # Credentials commonly live in a gitignored .env rather than a shell
        # profile. Loading here (never overriding a real environment variable)
        # means the same command works in an IDE terminal, a CI job, and a
        # subprocess that did not inherit an interactive shell.
        load_dotenv()
        self.api_key = api_key or os.environ.get("DEVFLOW_WATSONX_APIKEY", "")
        self.project_id = project_id or os.environ.get("DEVFLOW_WATSONX_PROJECT_ID", "")
        self.endpoint = (
            endpoint
            or os.environ.get("DEVFLOW_WATSONX_URL")
            or DEFAULT_ENDPOINT
        ).rstrip("/")
        self.model_id = (
            model_id or os.environ.get("DEVFLOW_WATSONX_MODEL") or DEFAULT_MODEL_ID
        )
        raw_timeout = os.environ.get("DEVFLOW_WATSONX_TIMEOUT", "")
        if timeout is not None:
            self.timeout = timeout
        else:
            try:
                self.timeout = float(raw_timeout) if raw_timeout else 30.0
            except ValueError:
                self.timeout = 30.0

    @property
    def disabled(self) -> bool:
        """Whether the operator explicitly turned watsonx off."""
        return os.environ.get("DEVFLOW_WATSONX_DISABLE", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.project_id)

    def describe_gap(self) -> str:
        """Explain what is missing, without revealing any secret value."""
        if self.disabled:
            return "watsonx is disabled via DEVFLOW_WATSONX_DISABLE."
        missing = []
        if not self.api_key:
            missing.append("DEVFLOW_WATSONX_APIKEY")
        if not self.project_id:
            missing.append("DEVFLOW_WATSONX_PROJECT_ID")
        if missing:
            return f"watsonx is not configured (missing {', '.join(missing)})."
        return ""


# A transport is any callable (url, data, headers, timeout) -> decoded body.
# Injecting it keeps every test off the network.
Transport = Callable[[str, Optional[bytes], dict, float], str]


def _error_detail(exc: urllib.error.HTTPError) -> str:
    """Surface the API's own error message instead of a bare status code.

    watsonx.ai explains refusals precisely (an unavailable model, an expired
    token, a project mismatch). Discarding that body turns a one-line fix into
    a debugging session, so read it -- defensively, since the body may be
    absent or already consumed.
    """
    try:
        raw = exc.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:300]
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        messages = [
            str(item.get("message") or item.get("code"))
            for item in errors
            if isinstance(item, dict)
        ]
        return "; ".join(m for m in messages if m)[:300]
    return raw[:300]


def _ssl_context() -> ssl.SSLContext:
    """A verifying TLS context that also works on a bare python.org install.

    Framework Python builds on macOS ship without a linked CA bundle, so the
    default context trusts nothing and every IBM Cloud call fails with
    CERTIFICATE_VERIFY_FAILED.  When the system store is empty we fall back to
    certifi's bundle if it is importable.

    Certificate verification is never disabled: if no trust store can be found
    the request is allowed to fail rather than proceed unverified.
    """
    context = ssl.create_default_context()
    try:
        has_roots = context.cert_store_stats().get("x509_ca", 0) > 0
    except Exception:  # noqa: BLE001
        has_roots = True
    if not has_roots:
        try:
            import certifi

            context.load_verify_locations(cafile=certifi.where())
            logger.debug("Loaded CA bundle from certifi for watsonx TLS verification.")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "No system CA bundle and certifi unavailable (%s); "
                "TLS verification will fail rather than be skipped.",
                exc,
            )
    return context


def _urllib_transport(
    url: str, data: Optional[bytes], headers: dict, timeout: float
) -> str:
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(  # noqa: S310
        request, timeout=timeout, context=_ssl_context()
    ) as response:
        return response.read().decode("utf-8")


class WatsonxClient:
    """Text generation against watsonx.ai, with IAM token caching."""

    def __init__(
        self,
        config: Optional[WatsonxConfig] = None,
        *,
        transport: Optional[Transport] = None,
    ) -> None:
        self.config = config or WatsonxConfig()
        self._transport: Transport = transport or _urllib_transport
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # -- auth ---------------------------------------------------------------

    def _access_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires_at:
            return self._token

        payload = urllib.parse.urlencode(
            {
                "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                "apikey": self.config.api_key,
            }
        ).encode("utf-8")
        try:
            body = self._transport(
                IAM_TOKEN_URL,
                payload,
                {"Content-Type": "application/x-www-form-urlencoded"},
                self.config.timeout,
            )
        except urllib.error.URLError as exc:
            raise WatsonxError(f"IAM token request failed: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise WatsonxError(f"IAM token request failed: {exc}") from exc

        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise WatsonxError("IAM token response was not valid JSON.") from exc

        token = decoded.get("access_token")
        if not token:
            raise WatsonxError("IAM token response contained no access_token.")

        expires_in = decoded.get("expires_in")
        try:
            lifetime = float(expires_in)
        except (TypeError, ValueError):
            lifetime = 3600.0
        self._token = str(token)
        self._token_expires_at = now + max(lifetime - _TOKEN_REFRESH_MARGIN_SECONDS, 60.0)
        return self._token

    # -- inference ----------------------------------------------------------

    def generate(self, prompt: str, *, max_new_tokens: int = 900) -> str:
        """Return the model's generated text for ``prompt``."""
        if self.config.disabled or not self.config.configured:
            raise WatsonxError(self.config.describe_gap() or "watsonx is unavailable.")
        if is_denied_model(self.config.model_id):
            raise WatsonxError(
                f"Model '{self.config.model_id}' is out of scope for this hackathon "
                "and will not be called."
            )

        token = self._access_token()
        url = f"{self.config.endpoint}{CHAT_PATH}?version={API_VERSION}"
        body = json.dumps(
            {
                "model_id": self.config.model_id,
                "project_id": self.config.project_id,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_new_tokens,
                "temperature": 0,  # deterministic, so a demo replays identically
            }
        ).encode("utf-8")

        try:
            raw = self._transport(
                url,
                body,
                {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                self.config.timeout,
            )
        except urllib.error.HTTPError as exc:
            raise WatsonxError(
                f"watsonx.ai request failed: HTTP {exc.code} {_error_detail(exc)}"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise WatsonxError(f"watsonx.ai request failed: {exc}") from exc

        try:
            decoded: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WatsonxError("watsonx.ai response was not valid JSON.") from exc

        choices = decoded.get("choices") or []
        if not choices:
            raise WatsonxError("watsonx.ai response contained no choices.")
        content = (choices[0].get("message") or {}).get("content")
        if not content or not str(content).strip():
            raise WatsonxError(
                f"watsonx.ai returned an empty completion for model "
                f"'{self.config.model_id}'."
            )
        return str(content)
