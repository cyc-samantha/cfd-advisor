"""Trading212 credentials: env loading, redaction, and Basic-auth header building."""

import base64
from collections.abc import Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, SecretStr

from advisor.integrations.trading212.errors import Trading212AuthError

_BASE_URLS = {
    "demo": "https://demo.trading212.com",
    "live": "https://live.trading212.com",
}


class Trading212Environment(StrEnum):
    DEMO = "demo"
    LIVE = "live"


class Trading212Credentials(BaseModel):
    """Basic-auth credentials for the Trading212 REST API.

    `repr`/`str` are overridden (redacted) rather than relying on pydantic's
    default field-dumping repr, which would render the raw secret values.
    """

    model_config = ConfigDict(frozen=True)

    api_key: SecretStr
    api_secret: SecretStr
    environment: Trading212Environment = Trading212Environment.DEMO

    def base_url(self) -> str:
        return _BASE_URLS[self.environment.value]

    def authorization_header(self) -> str:
        raw = f"{self.api_key.get_secret_value()}:{self.api_secret.get_secret_value()}"
        return "Basic " + base64.b64encode(raw.encode("utf-8")).decode("ascii")

    def __repr__(self) -> str:
        return f"Trading212Credentials(env={self.environment.value})"

    def __str__(self) -> str:
        return self.__repr__()


def _require_non_blank(value: str) -> None:
    if not value.strip():
        raise Trading212AuthError("missing or empty Trading212 API credentials")


def _parse_environment(raw: str) -> Trading212Environment:
    try:
        return Trading212Environment(raw)
    except ValueError as exc:
        raise Trading212AuthError("invalid T212_ENVIRONMENT value") from exc


def _read_required_credentials(source: Mapping[str, str]) -> tuple[str, str]:
    api_key = source.get("T212_API_KEY", "")
    api_secret = source.get("T212_API_SECRET", "")
    _require_non_blank(api_key)
    _require_non_blank(api_secret)
    return api_key, api_secret


def load_credentials(env: Mapping[str, str] | None = None) -> Trading212Credentials:
    """Build credentials from an env-like mapping; fails closed (Trading212AuthError) on blanks."""
    source = env or {}
    pair = _read_required_credentials(source)
    api_key = pair[0]
    api_secret = pair[1]
    environment_raw = source.get("T212_ENVIRONMENT", Trading212Environment.DEMO.value)
    environment = _parse_environment(environment_raw)
    return Trading212Credentials(api_key=api_key, api_secret=api_secret, environment=environment)
