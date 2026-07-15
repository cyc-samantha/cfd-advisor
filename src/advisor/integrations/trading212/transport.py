"""HTTP transport seam for the Trading212 adapter (stdlib urllib only).

R2: error messages here are static/path-only — the raw urllib exception,
Request object, and Authorization header are never interpolated into a
`Trading212Unavailable` reason, since that header carries the caller's
credentials.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from advisor.integrations.trading212.errors import Trading212Unavailable


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: str


class Transport(Protocol):
    """Structural protocol: anything with a matching `get` satisfies this seam."""

    def get(self, path: str) -> HttpResponse: ...  # pragma: no cover - protocol stub


def _default_opener(request: Request, timeout: float):
    return urlopen(request, timeout=timeout)  # noqa: S310 - fixed https base_url only


class UrllibTransport:
    """Read-only GET transport authenticated via a pre-built Basic auth header."""

    def __init__(
        self,
        base_url: str,
        authorization_header: str,
        timeout: float = 10.0,
        opener: Callable[[Request, float], object] | None = None,
    ) -> None:
        self._base_url = base_url
        self._authorization_header = authorization_header
        self._timeout = timeout
        self._opener = opener or _default_opener

    def get(self, path: str) -> HttpResponse:
        request = self._build_request(path)
        try:
            return self._send(request)
        except HTTPError as exc:
            return HttpResponse(status=exc.code, body=exc.read().decode("utf-8"))
        except (URLError, TimeoutError) as exc:
            raise Trading212Unavailable("network request to Trading212 failed") from exc

    def _build_request(self, path: str) -> Request:
        request = Request(self._base_url + path)  # noqa: S310 - fixed https base_url only
        request.add_unredirected_header("Authorization", self._authorization_header)
        return request

    def _send(self, request: Request) -> HttpResponse:
        with self._opener(request, self._timeout) as handle:
            status = getattr(handle, "status", 200)
            return HttpResponse(status=status, body=handle.read().decode("utf-8"))

    def __repr__(self) -> str:
        return "UrllibTransport(base_url=<redacted>)"

    def __str__(self) -> str:
        return self.__repr__()
