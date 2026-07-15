"""Typed error hierarchy for the Trading212 read-only adapter.

All reasons carried here are static/path-only strings (R2, see plan): callers
must never interpolate raw urllib exceptions, Request objects, or header/
secret values into a `reason`.
"""


class Trading212Error(Exception):
    """Base error for every failure this adapter can raise."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class Trading212AuthError(Trading212Error):
    """Missing/blank credentials, or the API responded 401/403."""


class Trading212Unavailable(Trading212Error):
    """Network failure, timeout, rate limit (429), or any other unmapped non-2xx."""


class Trading212MalformedResponse(Trading212Error):
    """Response body was not JSON, or was JSON missing a required field."""
