"""Read-only Trading212 client: positions + account summary, fail-closed status mapping.

R1: `__repr__`/`__str__` render a fixed, credential-free string.
R2: error `reason` strings are static/path-only, never interpolating the raw
response body, headers, or credentials.
"""

import json
from collections.abc import Callable

from advisor.integrations.trading212.config import Trading212Credentials
from advisor.integrations.trading212.errors import (
    Trading212AuthError,
    Trading212MalformedResponse,
    Trading212Unavailable,
)
from advisor.integrations.trading212.models import AccountSummary, Position
from advisor.integrations.trading212.transport import HttpResponse, Transport, UrllibTransport

_POSITIONS_PATH = "/api/v0/equity/portfolio"
_ACCOUNT_SUMMARY_PATH = "/api/v0/equity/account/summary"


def _raise_for_status(response: HttpResponse) -> None:
    if response.status in (401, 403):
        raise Trading212AuthError("Trading212 request was not authorized")
    if response.status < 200 or response.status >= 300:
        raise Trading212Unavailable("Trading212 request failed")


def _parse_json(response: HttpResponse) -> object:
    try:
        return json.loads(response.body)
    except json.JSONDecodeError as exc:
        raise Trading212MalformedResponse("Trading212 response was not valid JSON") from exc


class Trading212Client:
    """Thin read-only wrapper over the Trading212 portfolio/account endpoints."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    @classmethod
    def from_credentials(
        cls,
        credentials: Trading212Credentials,
        transport_factory: Callable = UrllibTransport,
    ) -> "Trading212Client":
        transport = transport_factory(
            base_url=credentials.base_url(),
            authorization_header=credentials.authorization_header(),
        )
        return cls(transport)

    def positions(self) -> list[Position]:
        payload = self._get_json(_POSITIONS_PATH)
        return [Position.from_api(raw) for raw in payload]

    def account_summary(self) -> AccountSummary:
        payload = self._get_json(_ACCOUNT_SUMMARY_PATH)
        return AccountSummary.from_api(payload)

    def _get_json(self, path: str) -> object:
        response = self._transport.get(path)
        _raise_for_status(response)
        return _parse_json(response)

    def __repr__(self) -> str:
        return "Trading212Client(transport=<redacted>)"

    def __str__(self) -> str:
        return self.__repr__()
