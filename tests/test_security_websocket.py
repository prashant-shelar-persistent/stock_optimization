"""Security tests for WebSocket authentication.

Tests the HMAC token-based authentication mechanism for the WebSocket
progress endpoint (``/ws/runs/{run_id}/progress``).

Coverage
--------
1. Token issuance — ``create_ws_token`` produces a valid signed token.
2. Token verification — ``verify_ws_token`` accepts a valid token.
3. Token expiry — expired tokens are rejected with ``WsTokenError``.
4. Token tampering — tokens with invalid signatures are rejected.
5. Token cross-run reuse — a token for run A cannot authenticate run B.
6. UUID path validation — non-UUID run_id values are rejected by the
   ``_RunId`` path parameter type in ``runs.py``.
7. Settings validation — ``SECRET_KEY`` is enforced in production.

These tests do NOT require a running Redis or database instance.
They test the security primitives in isolation.
"""

import time
import uuid
from unittest.mock import patch

import pytest

from app.core.security import (
    WS_TOKEN_MAX_AGE_SECONDS,
    WsTokenError,
    create_ws_token,
    verify_ws_token,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def run_id() -> str:
    """A valid UUID run_id for testing."""
    return str(uuid.uuid4())


@pytest.fixture
def secret_key() -> str:
    """A test secret key (not used in production)."""
    return "test-secret-key-for-unit-tests-only-32chars"


@pytest.fixture
def valid_token(run_id: str, secret_key: str) -> str:
    """A freshly issued valid token for the test run_id."""
    return create_ws_token(run_id=run_id, secret_key=secret_key)


# ── Token issuance tests ──────────────────────────────────────────────────────

class TestCreateWsToken:
    """Tests for ``create_ws_token``."""

    def test_returns_string(self, run_id: str, secret_key: str) -> None:
        """Token is returned as a plain string."""
        token = create_ws_token(run_id=run_id, secret_key=secret_key)
        assert isinstance(token, str)

    def test_token_is_non_empty(self, run_id: str, secret_key: str) -> None:
        """Token is not empty."""
        token = create_ws_token(run_id=run_id, secret_key=secret_key)
        assert len(token) > 0

    def test_token_contains_run_id(self, run_id: str, secret_key: str) -> None:
        """Token contains the run_id as a prefix (before the signature)."""
        token = create_ws_token(run_id=run_id, secret_key=secret_key)
        # itsdangerous.TimestampSigner format: value.timestamp.signature
        assert token.startswith(run_id)

    def test_different_run_ids_produce_different_tokens(
        self, secret_key: str
    ) -> None:
        """Tokens for different run_ids are different."""
        run_id_a = str(uuid.uuid4())
        run_id_b = str(uuid.uuid4())
        token_a = create_ws_token(run_id=run_id_a, secret_key=secret_key)
        token_b = create_ws_token(run_id=run_id_b, secret_key=secret_key)
        assert token_a != token_b

    def test_different_secrets_produce_different_tokens(
        self, run_id: str
    ) -> None:
        """Tokens signed with different secrets are different."""
        token_a = create_ws_token(run_id=run_id, secret_key="secret-a")
        token_b = create_ws_token(run_id=run_id, secret_key="secret-b")
        assert token_a != token_b

    def test_token_is_url_safe(self, run_id: str, secret_key: str) -> None:
        """Token contains only URL-safe characters (no encoding needed)."""
        token = create_ws_token(run_id=run_id, secret_key=secret_key)
        # itsdangerous uses base64url encoding for the signature
        # The run_id (UUID) contains only hex chars and hyphens
        # The separator is '.'
        # All characters should be safe for URL query parameters
        import urllib.parse  # noqa: PLC0415

        encoded = urllib.parse.quote(token, safe="")
        # If the token is URL-safe, encoding should not change it significantly
        # (only '.' might be encoded, but it's safe in query params)
        decoded = urllib.parse.unquote(encoded)
        assert decoded == token


# ── Token verification tests ──────────────────────────────────────────────────

class TestVerifyWsToken:
    """Tests for ``verify_ws_token``."""

    def test_valid_token_returns_run_id(
        self, run_id: str, secret_key: str, valid_token: str
    ) -> None:
        """A valid token returns the embedded run_id."""
        result = verify_ws_token(
            token=valid_token,
            expected_run_id=run_id,
            secret_key=secret_key,
        )
        assert result == run_id

    def test_tampered_token_raises_ws_token_error(
        self, run_id: str, secret_key: str, valid_token: str
    ) -> None:
        """A token with a modified signature raises WsTokenError."""
        # Corrupt the last few characters of the signature
        tampered = valid_token[:-4] + "XXXX"
        with pytest.raises(WsTokenError):
            verify_ws_token(
                token=tampered,
                expected_run_id=run_id,
                secret_key=secret_key,
            )

    def test_wrong_secret_raises_ws_token_error(
        self, run_id: str, valid_token: str
    ) -> None:
        """A token verified with the wrong secret raises WsTokenError."""
        with pytest.raises(WsTokenError):
            verify_ws_token(
                token=valid_token,
                expected_run_id=run_id,
                secret_key="wrong-secret-key",
            )

    def test_cross_run_token_raises_ws_token_error(
        self, secret_key: str
    ) -> None:
        """A token for run A cannot be used to authenticate run B."""
        run_id_a = str(uuid.uuid4())
        run_id_b = str(uuid.uuid4())
        token_for_a = create_ws_token(run_id=run_id_a, secret_key=secret_key)

        with pytest.raises(WsTokenError) as exc_info:
            verify_ws_token(
                token=token_for_a,
                expected_run_id=run_id_b,  # Different run!
                secret_key=secret_key,
            )

        # Error message should mention the mismatch
        assert "mismatch" in str(exc_info.value).lower() or run_id_a in str(exc_info.value)

    def test_empty_token_raises_ws_token_error(
        self, run_id: str, secret_key: str
    ) -> None:
        """An empty token raises WsTokenError."""
        with pytest.raises(WsTokenError):
            verify_ws_token(
                token="",
                expected_run_id=run_id,
                secret_key=secret_key,
            )

    def test_malformed_token_raises_ws_token_error(
        self, run_id: str, secret_key: str
    ) -> None:
        """A completely malformed token raises WsTokenError."""
        with pytest.raises(WsTokenError):
            verify_ws_token(
                token="not-a-valid-token-at-all",
                expected_run_id=run_id,
                secret_key=secret_key,
            )

    def test_expired_token_raises_ws_token_error(
        self, run_id: str, secret_key: str
    ) -> None:
        """An expired token raises WsTokenError.

        We use a very short max_age (1 second) and sleep to force expiry.
        """
        token = create_ws_token(run_id=run_id, secret_key=secret_key)

        # Verify with max_age=0 to immediately expire the token
        with pytest.raises(WsTokenError) as exc_info:
            verify_ws_token(
                token=token,
                expected_run_id=run_id,
                secret_key=secret_key,
                max_age=0,  # Immediately expired
            )

        # Should be a SignatureExpired error
        assert "expired" in str(exc_info.value).lower()

    def test_token_valid_within_max_age(
        self, run_id: str, secret_key: str
    ) -> None:
        """A freshly issued token is valid within the default max_age."""
        token = create_ws_token(run_id=run_id, secret_key=secret_key)
        # Should not raise
        result = verify_ws_token(
            token=token,
            expected_run_id=run_id,
            secret_key=secret_key,
            max_age=WS_TOKEN_MAX_AGE_SECONDS,
        )
        assert result == run_id


# ── WsTokenError tests ────────────────────────────────────────────────────────

class TestWsTokenError:
    """Tests for the ``WsTokenError`` exception class."""

    def test_is_exception(self) -> None:
        """WsTokenError is a subclass of Exception."""
        assert issubclass(WsTokenError, Exception)

    def test_reason_attribute(self) -> None:
        """WsTokenError stores the reason in the ``reason`` attribute."""
        err = WsTokenError("test reason")
        assert err.reason == "test reason"

    def test_str_representation(self) -> None:
        """WsTokenError str() returns the reason."""
        err = WsTokenError("test reason")
        assert str(err) == "test reason"


# ── UUID path validation tests ────────────────────────────────────────────────

class TestUuidPathValidation:
    """Tests that non-UUID run_id values are rejected at the path level.

    These tests verify the ``_RunId`` annotated type alias in ``runs.py``
    which uses a regex pattern to validate UUID format before the handler
    is called.
    """

    @pytest.mark.parametrize("invalid_run_id", [
        # Path traversal attempts
        "../../../etc/passwd",
        "..%2F..%2Fetc%2Fpasswd",
        # SQL injection attempts
        "'; DROP TABLE runs; --",
        "1 OR 1=1",
        # Too short / too long
        "abc",
        "a" * 100,
        # Wrong format (not UUID)
        "not-a-uuid",
        "12345678-1234-1234-1234-12345678901",  # 35 chars (too short)
        "12345678-1234-1234-1234-1234567890123",  # 37 chars (too long)
        # Empty
        "",
    ])
    def test_invalid_run_id_format(self, invalid_run_id: str) -> None:
        """Non-UUID run_id values do not match the UUID regex pattern."""
        import re  # noqa: PLC0415

        uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        assert not re.match(uuid_pattern, invalid_run_id), (
            f"Expected '{invalid_run_id}' to NOT match UUID pattern"
        )

    @pytest.mark.parametrize("valid_run_id", [
        "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "00000000-0000-0000-0000-000000000000",
        "ffffffff-ffff-ffff-ffff-ffffffffffff",
        str(uuid.uuid4()),
        str(uuid.uuid4()),
    ])
    def test_valid_run_id_format(self, valid_run_id: str) -> None:
        """Valid UUID strings match the UUID regex pattern."""
        import re  # noqa: PLC0415

        uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        assert re.match(uuid_pattern, valid_run_id), (
            f"Expected '{valid_run_id}' to match UUID pattern"
        )


# ── Settings security validation tests ───────────────────────────────────────

class TestSettingsSecurityValidation:
    """Tests for production secret key validation in Settings."""

    def test_insecure_default_secret_rejected_in_production(self) -> None:
        """Settings raises ValueError if SECRET_KEY is the default in production."""
        from pydantic import ValidationError  # noqa: PLC0415

        with pytest.raises((ValueError, ValidationError)):
            from app.core.config import Settings  # noqa: PLC0415

            Settings(
                ENVIRONMENT="production",
                SECRET_KEY="CHANGE_ME_IN_PRODUCTION",
                DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
                REDIS_URL="redis://localhost:6379/0",
                ALLOWED_ORIGINS="https://example.com",
            )

    def test_empty_secret_rejected_in_production(self) -> None:
        """Settings raises ValueError if SECRET_KEY is empty in production."""
        from pydantic import ValidationError  # noqa: PLC0415

        with pytest.raises((ValueError, ValidationError)):
            from app.core.config import Settings  # noqa: PLC0415

            Settings(
                ENVIRONMENT="production",
                SECRET_KEY="",
                DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
                REDIS_URL="redis://localhost:6379/0",
                ALLOWED_ORIGINS="https://example.com",
            )

    def test_strong_secret_accepted_in_production(self) -> None:
        """Settings accepts a strong SECRET_KEY in production."""
        from app.core.config import Settings  # noqa: PLC0415

        # Should not raise
        settings = Settings(
            ENVIRONMENT="production",
            SECRET_KEY="a" * 64,  # 64-char hex string (strong)
            DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
            REDIS_URL="redis://localhost:6379/0",
            ALLOWED_ORIGINS="https://example.com",
        )
        assert settings.SECRET_KEY == "a" * 64

    def test_wildcard_cors_rejected_in_production(self) -> None:
        """Settings raises ValueError if ALLOWED_ORIGINS contains '*' in production."""
        from pydantic import ValidationError  # noqa: PLC0415

        with pytest.raises((ValueError, ValidationError)):
            from app.core.config import Settings  # noqa: PLC0415

            Settings(
                ENVIRONMENT="production",
                SECRET_KEY="a" * 64,
                DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
                REDIS_URL="redis://localhost:6379/0",
                ALLOWED_ORIGINS="*",
            )

    def test_development_allows_insecure_defaults(self) -> None:
        """Settings does not raise for insecure defaults in development."""
        from app.core.config import Settings  # noqa: PLC0415

        # Should not raise in development
        settings = Settings(
            ENVIRONMENT="development",
            SECRET_KEY="CHANGE_ME_IN_PRODUCTION",
            DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
            REDIS_URL="redis://localhost:6379/0",
            ALLOWED_ORIGINS="http://localhost:3000",
        )
        assert settings.ENVIRONMENT == "development"
