"""Tests for Trading212 credential loading and redaction (slice-a-foundation).

INV-5: no network anywhere here — `load_credentials` only reads an in-memory
mapping, never the real environment or the network.
"""

import base64

import pytest

from advisor.integrations.trading212.config import (
    Trading212Credentials,
    Trading212Environment,
    load_credentials,
)
from advisor.integrations.trading212.errors import Trading212AuthError


def test_missing_api_key_raises_auth_error() -> None:
    with pytest.raises(Trading212AuthError):
        load_credentials({"T212_API_SECRET": "secret"})


def test_missing_api_secret_raises_auth_error() -> None:
    with pytest.raises(Trading212AuthError):
        load_credentials({"T212_API_KEY": "key"})


def test_empty_environment_raises_auth_error() -> None:
    with pytest.raises(Trading212AuthError):
        load_credentials({})


@pytest.mark.parametrize("blank_key", ["", "   "])
def test_empty_string_credential_raises_auth_error(blank_key: str) -> None:
    with pytest.raises(Trading212AuthError):
        load_credentials({"T212_API_KEY": blank_key, "T212_API_SECRET": "secret"})


@pytest.mark.parametrize("blank_secret", ["", "   "])
def test_empty_string_secret_raises_auth_error(blank_secret: str) -> None:
    with pytest.raises(Trading212AuthError):
        load_credentials({"T212_API_KEY": "key", "T212_API_SECRET": blank_secret})


def test_repr_and_str_redact_secrets() -> None:
    credentials = load_credentials(
        {"T212_API_KEY": "topsecretkey", "T212_API_SECRET": "topsecretsecret"}
    )
    assert "topsecretkey" not in repr(credentials)
    assert "topsecretsecret" not in repr(credentials)
    assert "topsecretkey" not in str(credentials)
    assert "topsecretsecret" not in str(credentials)


def test_base_url_selects_env_default_demo() -> None:
    credentials = load_credentials({"T212_API_KEY": "key", "T212_API_SECRET": "secret"})
    assert credentials.environment == Trading212Environment.DEMO
    assert credentials.base_url() == "https://demo.trading212.com"


def test_base_url_selects_env_live_when_configured() -> None:
    credentials = load_credentials(
        {"T212_API_KEY": "key", "T212_API_SECRET": "secret", "T212_ENVIRONMENT": "live"}
    )
    assert credentials.environment == Trading212Environment.LIVE
    assert credentials.base_url() == "https://live.trading212.com"


def test_authorization_header_is_basic_b64() -> None:
    credentials = load_credentials({"T212_API_KEY": "key", "T212_API_SECRET": "secret"})
    expected = "Basic " + base64.b64encode(b"key:secret").decode("ascii")
    assert credentials.authorization_header() == expected


def test_credentials_constructed_directly_still_redact() -> None:
    credentials = Trading212Credentials(api_key="directkey", api_secret="directsecret")
    assert "directkey" not in repr(credentials)
    assert "directsecret" not in repr(credentials)
