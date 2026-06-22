"""Custom exception hierarchy for the Portfolio Optimizer.

All domain exceptions carry structured metadata so that FastAPI exception
handlers can return consistent JSON error responses with ``error_code``,
``message``, and ``details`` fields.
"""

from typing import Any


class PortfolioOptimizerError(Exception):
    """Base class for all application-level exceptions."""

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details: dict[str, Any] = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-serialisable dict for API error responses."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


# ── Data layer ────────────────────────────────────────────────────────────────


class DataFetchError(PortfolioOptimizerError):
    """Raised when yfinance fails to return usable price data.

    Examples:
        - Empty DataFrame returned for all requested tickers
        - Network timeout after all retries exhausted
        - All columns dropped due to excessive NaN values
    """

    def __init__(
        self,
        message: str,
        tickers: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="DATA_FETCH_ERROR",
            details={**(details or {}), "tickers": tickers or []},
        )
        self.tickers = tickers or []


class CacheError(PortfolioOptimizerError):
    """Raised when Redis cache operations fail unexpectedly."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message=message, error_code="CACHE_ERROR", details=details)


# ── Optimization layer ────────────────────────────────────────────────────────


class OptimizationError(PortfolioOptimizerError):
    """Base class for optimization engine failures."""

    def __init__(
        self,
        message: str,
        error_code: str = "OPTIMIZATION_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, error_code=error_code, details=details)


class ConstraintViolationError(OptimizationError):
    """Raised when user-supplied constraints are logically invalid.

    Examples:
        - ``min_portfolio_return`` exceeds the maximum achievable return
        - ``max_weight_per_asset`` is so small that budget constraint cannot be met
        - Sector limits sum to less than 1.0 making full budget allocation impossible
    """

    def __init__(
        self,
        message: str,
        violated_constraints: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="CONSTRAINT_VIOLATION",
            details={
                **(details or {}),
                "violated_constraints": violated_constraints or [],
            },
        )
        self.violated_constraints = violated_constraints or []


class SolverInfeasibleError(OptimizationError):
    """Raised when the CVXPY solver cannot find a feasible solution.

    This typically means the constraints are over-specified or contradictory.
    The ``relaxation_suggestions`` field provides hints for the user.
    """

    def __init__(
        self,
        message: str,
        solver_status: str = "infeasible",
        relaxation_suggestions: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="SOLVER_INFEASIBLE",
            details={
                **(details or {}),
                "solver_status": solver_status,
                "relaxation_suggestions": relaxation_suggestions or [],
            },
        )
        self.solver_status = solver_status
        self.relaxation_suggestions = relaxation_suggestions or []


class QuantumTimeoutError(OptimizationError):
    """Raised when a quantum optimization job exceeds the configured timeout."""

    def __init__(
        self,
        message: str,
        timeout_seconds: int = 60,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="QUANTUM_TIMEOUT",
            details={**(details or {}), "timeout_seconds": timeout_seconds},
        )
        self.timeout_seconds = timeout_seconds


class QuantumAssetLimitError(OptimizationError):
    """Raised when the number of assets exceeds MAX_QUANTUM_ASSETS."""

    def __init__(
        self,
        num_assets: int,
        max_assets: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=(
                f"Quantum optimization supports at most {max_assets} assets, "
                f"but {num_assets} were provided. "
                "Reduce the asset list or use classical optimization."
            ),
            error_code="QUANTUM_ASSET_LIMIT_EXCEEDED",
            details={
                **(details or {}),
                "num_assets": num_assets,
                "max_assets": max_assets,
            },
        )


# ── Agent layer ───────────────────────────────────────────────────────────────


class AgentExecutionError(PortfolioOptimizerError):
    """Raised when the LangGraph agent graph encounters an unrecoverable error."""

    def __init__(
        self,
        message: str,
        node_name: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="AGENT_EXECUTION_ERROR",
            details={**(details or {}), "node_name": node_name},
        )
        self.node_name = node_name


# ── Chat layer ────────────────────────────────────────────────────────────────


class ChatSessionNotFoundError(PortfolioOptimizerError):
    """Raised when a requested chat session does not exist in the database.

    This is the canonical 404-equivalent for the chat domain.  The
    FastAPI exception handler maps it to HTTP 404 with a structured
    JSON body.

    Attributes:
        session_id: The UUID string of the session that was not found.

    Example::

        raise ChatSessionNotFoundError(session_id="abc-123")
        # → HTTP 404  {"error_code": "CHAT_SESSION_NOT_FOUND",
        #              "message": "Chat session 'abc-123' not found.",
        #              "details": {"session_id": "abc-123"}}
    """

    def __init__(
        self,
        session_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=f"Chat session '{session_id}' not found.",
            error_code="CHAT_SESSION_NOT_FOUND",
            details={**(details or {}), "session_id": session_id},
        )
        self.session_id = session_id


class ChatSessionExpiredError(PortfolioOptimizerError):
    """Raised when a message is sent to a chat session that has already expired.

    Sessions expire after a configurable TTL (default 24 hours).  Once
    expired, the session is read-only; clients must create a new session.

    Attributes:
        session_id: The UUID string of the expired session.

    Example::

        raise ChatSessionExpiredError(session_id="abc-123")
        # → HTTP 410  {"error_code": "CHAT_SESSION_EXPIRED",
        #              "message": "Chat session 'abc-123' has expired ...",
        #              "details": {"session_id": "abc-123"}}
    """

    def __init__(
        self,
        session_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=(
                f"Chat session '{session_id}' has expired and is no longer "
                "accepting new messages. Please start a new session."
            ),
            error_code="CHAT_SESSION_EXPIRED",
            details={**(details or {}), "session_id": session_id},
        )
        self.session_id = session_id


class ChatSessionAlreadyConfirmedError(PortfolioOptimizerError):
    """Raised when a confirmation is attempted on an already-confirmed session.

    Once a session has been confirmed and an optimization run has been
    dispatched, the session transitions to ``confirmed`` status and
    cannot be confirmed again.

    Attributes:
        session_id: The UUID string of the already-confirmed session.
        run_id:     The optimization run UUID that was previously dispatched.

    Example::

        raise ChatSessionAlreadyConfirmedError(
            session_id="abc-123", run_id="xyz-456"
        )
        # → HTTP 409  {"error_code": "CHAT_SESSION_ALREADY_CONFIRMED",
        #              "message": "Chat session 'abc-123' has already been ...",
        #              "details": {"session_id": "abc-123", "run_id": "xyz-456"}}
    """

    def __init__(
        self,
        session_id: str,
        run_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        run_info = f" (run_id={run_id!r})" if run_id else ""
        super().__init__(
            message=(
                f"Chat session '{session_id}' has already been confirmed"
                f"{run_info}. "
                "Each session can only be confirmed once."
            ),
            error_code="CHAT_SESSION_ALREADY_CONFIRMED",
            details={
                **(details or {}),
                "session_id": session_id,
                "run_id": run_id,
            },
        )
        self.session_id = session_id
        self.run_id = run_id


class ChatSlotExtractionError(PortfolioOptimizerError):
    """Raised when the LLM slot-filler returns an unparseable or invalid response.

    This covers two failure modes:

    1. **Parse failure** — the LLM response is not valid JSON or does not
       conform to the expected schema.
    2. **Validation failure** — the extracted JSON is structurally valid but
       fails Pydantic validation (e.g. negative budget, empty tickers list).

    The ``raw_response`` field preserves the raw LLM output for debugging.

    Attributes:
        raw_response: The raw string returned by the LLM (may be None if the
                      API call itself failed before returning a response).

    Example::

        raise ChatSlotExtractionError(
            message="LLM returned invalid JSON for slot extraction",
            raw_response='{"tickers": null}',
        )
        # → HTTP 502  {"error_code": "CHAT_SLOT_EXTRACTION_ERROR",
        #              "message": "LLM returned invalid JSON ...",
        #              "details": {"raw_response": '{"tickers": null}'}}
    """

    def __init__(
        self,
        message: str,
        raw_response: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="CHAT_SLOT_EXTRACTION_ERROR",
            details={**(details or {}), "raw_response": raw_response},
        )
        self.raw_response = raw_response


class ChatInvalidStateError(PortfolioOptimizerError):
    """Raised when an operation is attempted on a session in an incompatible state.

    For example, sending a message to a ``confirmed`` session, or calling
    confirm on a session that is still in ``collecting`` state (i.e. the
    LLM has not yet produced a complete payload preview).

    Attributes:
        session_id:     The UUID string of the session.
        current_status: The session's current status string.
        required_status: The status that was required for the operation.

    Example::

        raise ChatInvalidStateError(
            session_id="abc-123",
            current_status="confirmed",
            required_status="pending_confirmation",
        )
        # → HTTP 409  {"error_code": "CHAT_INVALID_STATE",
        #              "message": "Operation requires session status ...",
        #              "details": {...}}
    """

    def __init__(
        self,
        session_id: str,
        current_status: str,
        required_status: str | list[str],
        details: dict[str, Any] | None = None,
    ) -> None:
        if isinstance(required_status, list):
            required_str = " or ".join(f"'{s}'" for s in required_status)
        else:
            required_str = f"'{required_status}'"

        super().__init__(
            message=(
                f"Operation requires session status {required_str}, "
                f"but session '{session_id}' is currently '{current_status}'."
            ),
            error_code="CHAT_INVALID_STATE",
            details={
                **(details or {}),
                "session_id": session_id,
                "current_status": current_status,
                "required_status": required_status,
            },
        )
        self.session_id = session_id
        self.current_status = current_status
        self.required_status = required_status


class ChatTooManyMessagesError(PortfolioOptimizerError):
    """Raised when a chat session has reached the maximum allowed message count.

    Each session has a configurable upper bound on the total number of
    messages (user + assistant combined) to prevent unbounded conversation
    growth and runaway LLM token costs.  When the limit is reached, the
    client must start a new session.

    Attributes:
        session_id:    The UUID string of the session.
        message_count: The current number of messages in the session.
        max_messages:  The configured maximum allowed message count.

    Example::

        raise ChatTooManyMessagesError(
            session_id="abc-123",
            message_count=52,
            max_messages=50,
        )
        # -> HTTP 422  {"error_code": "CHAT_TOO_MANY_MESSAGES",
        #              "message": "Chat session 'abc-123' has reached ...",
        #              "details": {"session_id": "abc-123",
        #                          "message_count": 52,
        #                          "max_messages": 50}}
    """

    def __init__(
        self,
        session_id: str,
        message_count: int,
        max_messages: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=(
                f"Chat session '{session_id}' has reached the maximum allowed "
                f"message count ({max_messages}). "
                "Please start a new session to continue."
            ),
            error_code="CHAT_TOO_MANY_MESSAGES",
            details={
                **(details or {}),
                "session_id": session_id,
                "message_count": message_count,
                "max_messages": max_messages,
            },
        )
        self.session_id = session_id
        self.message_count = message_count
        self.max_messages = max_messages


class ChatSlotOverrideError(PortfolioOptimizerError):
    """Raised when the ``slot_overrides`` dict supplied to the confirm endpoint
    is invalid -- either too many keys or an unrecognised field name.

    Attributes:
        session_id:      The UUID string of the session.
        invalid_keys:    List of unrecognised key names (empty when the error
                         is a key-count violation).
        max_keys:        The configured maximum number of override keys.

    Example::

        raise ChatSlotOverrideError(
            session_id="abc-123",
            invalid_keys=["unknown_field"],
        )
        # -> HTTP 422  {"error_code": "CHAT_SLOT_OVERRIDE_ERROR",
        #              "message": "slot_overrides contains unrecognised fields ...",
        #              "details": {...}}
    """

    def __init__(
        self,
        session_id: str,
        message: str,
        invalid_keys: list[str] | None = None,
        max_keys: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="CHAT_SLOT_OVERRIDE_ERROR",
            details={
                **(details or {}),
                "session_id": session_id,
                "invalid_keys": invalid_keys or [],
                "max_keys": max_keys,
            },
        )
        self.session_id = session_id
        self.invalid_keys = invalid_keys or []
        self.max_keys = max_keys
