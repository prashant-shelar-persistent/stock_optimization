"""HMAC token signing and verification for WebSocket authentication.

This module provides stateless, run-scoped HMAC-SHA256 tokens that allow
the frontend to authenticate WebSocket connections without a full JWT
infrastructure.

Design
------
WebSocket upgrade requests cannot carry ``Authorization`` headers in browsers
(the ``WebSocket`` constructor does not accept custom headers). The standard
approach is to pass a short-lived signed token as a query parameter:

    ws://host/ws/runs/{run_id}/progress?token=<signed_token>

Token structure (itsdangerous.TimestampSigner)
----------------------------------------------
The token is produced by ``itsdangerous.TimestampSigner`` using HMAC-SHA256.
The *value* signed is ``run_id`` — so a token issued for run A cannot be
replayed to subscribe to run B.

    signed_token = signer.sign(run_id)
    # → b"<run_id>.<timestamp>.<hmac_signature>"

Verification checks:
    1. HMAC signature is valid (tamper detection).
    2. Token has not expired (``max_age`` enforced by TimestampSigner).
    3. The ``run_id`` embedded in the token matches the path parameter.

Token lifetime
--------------
Tokens are valid for ``WS_TOKEN_MAX_AGE_SECONDS`` (default: 300 seconds /
5 minutes). This is long enough for the frontend to connect immediately
after receiving the 202 response, but short enough to limit the window for
token theft.

Usage
-----
Issue a token (in the optimize endpoint)::

    from app.core.security import create_ws_token
    token = create_ws_token(run_id=run_id, secret_key=settings.SECRET_KEY)

Verify a token (in the WebSocket handler)::

    from app.core.security import verify_ws_token, WsTokenError
    try:
        verified_run_id = verify_ws_token(
            token=token,
            expected_run_id=run_id,
            secret_key=settings.SECRET_KEY,
        )
    except WsTokenError as exc:
        await websocket.close(code=4001, reason=str(exc))
        return
"""

from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

# Default token lifetime in seconds.
# 5 minutes is generous enough for slow connections while still limiting
# the replay window if a token is intercepted.
WS_TOKEN_MAX_AGE_SECONDS: int = 300

# Salt used to namespace WebSocket tokens from any other signed values
# that might use the same SECRET_KEY in the future.
_WS_TOKEN_SALT = "ws-progress-token"


class WsTokenError(Exception):
    """Raised when WebSocket token verification fails.

    Attributes:
        reason: Human-readable description of the failure (safe to log,
                but should NOT be sent verbatim to the client to avoid
                leaking timing/signature information).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _make_signer(secret_key: str) -> TimestampSigner:
    """Construct a ``TimestampSigner`` bound to *secret_key*.

    ``TimestampSigner`` appends a timestamp and HMAC-SHA256 signature to
    the value being signed.  The timestamp allows ``verify_ws_token`` to
    reject tokens older than ``WS_TOKEN_MAX_AGE_SECONDS``.

    Args:
        secret_key: The application secret key (``Settings.SECRET_KEY``).

    Returns:
        A configured ``TimestampSigner`` instance.
    """
    import hashlib  # noqa: PLC0415

    return TimestampSigner(
        secret_key=secret_key,
        salt=_WS_TOKEN_SALT,
        # itsdangerous default digest is SHA-1; explicitly request SHA-256
        # for stronger HMAC security.  The digest_method parameter expects
        # a callable (hash constructor), not a string.
        digest_method=hashlib.sha256,
    )


def create_ws_token(run_id: str, secret_key: str) -> str:
    """Create a signed WebSocket authentication token scoped to *run_id*.

    The token embeds the ``run_id`` as the signed value so that it cannot
    be used to authenticate a WebSocket connection for a different run.

    Args:
        run_id:     UUID string of the optimization run.
        secret_key: Application secret key (``Settings.SECRET_KEY``).

    Returns:
        A URL-safe signed token string (ASCII, safe to embed in a query
        parameter without additional encoding).

    Example::

        token = create_ws_token(
            run_id="3fa85f64-5717-4562-b3fc-2c963f66afa6",
            secret_key="my-secret",
        )
        # → "3fa85f64-5717-4562-b3fc-2c963f66afa6.ZxYz12.abc123..."
    """
    signer = _make_signer(secret_key)
    # sign() returns bytes; decode to str for JSON serialisation
    return signer.sign(run_id).decode("utf-8")


def verify_ws_token(
    token: str,
    expected_run_id: str,
    secret_key: str,
    max_age: int = WS_TOKEN_MAX_AGE_SECONDS,
) -> str:
    """Verify a WebSocket authentication token and return the embedded run_id.

    Performs three checks:
    1. The HMAC signature is valid (tamper detection).
    2. The token has not expired (``max_age`` enforced).
    3. The ``run_id`` embedded in the token matches ``expected_run_id``
       (prevents token reuse across runs).

    Args:
        token:           The signed token string from the ``?token=`` query
                         parameter.
        expected_run_id: The ``run_id`` from the WebSocket URL path parameter.
                         Must match the value embedded in the token.
        secret_key:      Application secret key (``Settings.SECRET_KEY``).
        max_age:         Maximum token age in seconds (default:
                         ``WS_TOKEN_MAX_AGE_SECONDS``).

    Returns:
        The ``run_id`` embedded in the token (equal to ``expected_run_id``
        when verification succeeds).

    Raises:
        WsTokenError: If the token is invalid, expired, or does not match
                      ``expected_run_id``.  The ``reason`` attribute contains
                      a safe-to-log description of the failure.
    """
    signer = _make_signer(secret_key)

    try:
        # unsign() raises SignatureExpired or BadSignature on failure.
        # Returns the original value (run_id) as bytes.
        run_id_bytes: bytes = signer.unsign(token, max_age=max_age)
    except SignatureExpired as exc:
        raise WsTokenError(
            f"WebSocket token expired: {exc}"
        ) from exc
    except BadSignature as exc:
        raise WsTokenError(
            f"WebSocket token has invalid signature: {exc}"
        ) from exc
    except Exception as exc:
        # Catch-all for unexpected itsdangerous errors (e.g. malformed token)
        raise WsTokenError(
            f"WebSocket token verification failed: {exc}"
        ) from exc

    embedded_run_id = run_id_bytes.decode("utf-8")

    # Guard against token reuse: the run_id in the token must match the
    # run_id in the WebSocket URL path parameter.
    if embedded_run_id != expected_run_id:
        raise WsTokenError(
            f"WebSocket token run_id mismatch: token is for run "
            f"'{embedded_run_id}', but connection requested run "
            f"'{expected_run_id}'"
        )

    return embedded_run_id
