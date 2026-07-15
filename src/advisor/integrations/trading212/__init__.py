"""Read-only Trading212 Invest/ISA adapter (isolated port, not a MarketDataProvider).

Wraps two endpoints only: GET /api/v0/equity/portfolio and
GET /api/v0/equity/account/summary. See the pipeline plan
(t212-invest-readonly-adapter) for verified API contracts and rationale.
"""

from advisor.integrations.trading212.client import Trading212Client
from advisor.integrations.trading212.config import (
    Trading212Credentials,
    Trading212Environment,
    load_credentials,
)
from advisor.integrations.trading212.errors import (
    Trading212AuthError,
    Trading212Error,
    Trading212MalformedResponse,
    Trading212Unavailable,
)
from advisor.integrations.trading212.models import AccountSummary, Position

__all__ = [
    "AccountSummary",
    "Position",
    "Trading212AuthError",
    "Trading212Client",
    "Trading212Credentials",
    "Trading212Environment",
    "Trading212Error",
    "Trading212MalformedResponse",
    "Trading212Unavailable",
    "load_credentials",
]
