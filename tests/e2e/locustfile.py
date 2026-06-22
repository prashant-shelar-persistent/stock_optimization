"""Locust load-test scenarios for the Portfolio Optimizer API.

This file defines realistic user traffic patterns for load testing the API.
Run it with:

    locust -f tests/e2e/locustfile.py --host http://localhost:8000

Or headless (CI mode):

    locust -f tests/e2e/locustfile.py \
        --host http://localhost:8000 \
        --headless \
        --users 50 \
        --spawn-rate 5 \
        --run-time 60s \
        --html tests/e2e/load_report.html

User classes
------------
HealthCheckUser
    Simulates a monitoring agent that polls /health every 5–15 seconds.
    Weight: 1 (low traffic — monitoring is infrequent).

AssetSearchUser
    Simulates a frontend user typing in the asset search box.
    Searches for a mix of known tickers and company name fragments.
    Weight: 3 (moderate traffic — search is interactive).

OptimizationUser
    Simulates a user submitting an optimization run and polling for status.
    Submits a POST /api/v1/optimize, then polls GET /api/v1/runs/{id}/status
    until the run completes or a timeout is reached.
    Weight: 2 (lower traffic — optimization is a deliberate action).

RunHistoryUser
    Simulates a user browsing the run history dashboard.
    Fetches paginated run lists and drills into individual run details.
    Weight: 2 (moderate traffic — history browsing is common).

MixedUser
    Combines all behaviours in a single user class for realistic mixed load.
    Weight: 5 (highest weight — most users do a mix of everything).

Design notes
------------
- All users use ``self.client`` (Locust's built-in HTTP session) which
  automatically records response times and failure rates.
- Requests that are expected to return non-200 status codes (e.g., 404 for
  unknown run IDs, 422 for validation errors) use ``catch_response=True``
  and ``response.success()`` to prevent Locust from counting them as failures.
- Think times (``wait_time``) are set to realistic values:
    - HealthCheckUser: 5–15 s (monitoring interval)
    - AssetSearchUser: 0.5–3 s (interactive typing)
    - OptimizationUser: 2–10 s (deliberate action)
    - RunHistoryUser: 1–5 s (browsing)
    - MixedUser: 1–8 s (mixed)
- The ``run_id`` pool is shared across tasks within a single user session
  to simulate realistic polling behaviour.
"""

import random
import uuid
from typing import Any

from locust import HttpUser, between, task


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

# Well-known tickers used in search and optimization requests
_TICKERS: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "JPM", "JNJ", "V",
    "PG", "HD", "MA", "UNH", "BAC",
    "KO", "PEP", "COST", "WMT", "ADBE",
]

# Company name fragments for search queries
_SEARCH_QUERIES: list[str] = [
    "Apple", "Microsoft", "Google", "Amazon", "NVIDIA",
    "Tesla", "JPMorgan", "Johnson", "Visa", "Procter",
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "tech", "health", "bank", "energy", "consumer",
]

# Optimization request templates (classical only — no quantum to keep tests fast)
_OPTIMIZATION_REQUESTS: list[dict[str, Any]] = [
    {
        "tickers": ["AAPL", "MSFT"],
        "budget": 50_000.0,
        "run_quantum": False,
    },
    {
        "tickers": ["AAPL", "MSFT", "GOOGL"],
        "budget": 100_000.0,
        "run_quantum": False,
    },
    {
        "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN"],
        "budget": 200_000.0,
        "run_quantum": False,
        "max_weight_per_asset": 0.4,
    },
    {
        "tickers": ["JPM", "BAC", "V", "MA"],
        "budget": 150_000.0,
        "run_quantum": False,
        "sector_constraints": [{"sector": "Financials", "max_weight": 0.8}],
    },
    {
        "tickers": ["JNJ", "UNH", "PFE", "ABBV"],
        "budget": 80_000.0,
        "run_quantum": False,
        "min_return": 0.06,
        "max_volatility": 0.20,
    },
]


# ---------------------------------------------------------------------------
# HealthCheckUser
# ---------------------------------------------------------------------------


class HealthCheckUser(HttpUser):
    """Simulates a monitoring agent polling /health.

    Represents load balancers, uptime monitors, and Kubernetes liveness probes.
    """

    weight = 1
    wait_time = between(5, 15)

    @task
    def check_health(self) -> None:
        """GET /health — verify the application is alive."""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                body = response.json()
                if "status" not in body:
                    response.failure(
                        f"Missing 'status' field in health response: {body}"
                    )
                elif body["status"] not in ("healthy", "degraded", "unhealthy"):
                    response.failure(
                        f"Unexpected status value: {body['status']!r}"
                    )
                else:
                    response.success()
            elif response.status_code == 503:
                # 503 is a valid response when all services are down
                body = response.json()
                if body.get("status") == "unhealthy":
                    response.success()
                else:
                    response.failure(
                        f"503 without status=unhealthy: {body}"
                    )
            else:
                response.failure(
                    f"Unexpected status code: {response.status_code}"
                )


# ---------------------------------------------------------------------------
# AssetSearchUser
# ---------------------------------------------------------------------------


class AssetSearchUser(HttpUser):
    """Simulates a frontend user searching for assets.

    Represents the interactive asset search box in the portfolio builder UI.
    """

    weight = 3
    wait_time = between(0.5, 3)

    @task(5)
    def search_by_ticker(self) -> None:
        """GET /api/v1/assets/search?q={ticker} — search by known ticker."""
        ticker = random.choice(_TICKERS)
        with self.client.get(
            "/api/v1/assets/search",
            params={"q": ticker},
            name="/api/v1/assets/search?q=[ticker]",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                body = response.json()
                if not isinstance(body, list):
                    response.failure(f"Expected list, got: {type(body)}")
                elif len(body) == 0:
                    # Known tickers should always return at least one result
                    response.failure(
                        f"Empty results for known ticker '{ticker}'"
                    )
                elif "ticker" not in body[0]:
                    response.failure(
                        f"Missing 'ticker' field in result: {body[0]}"
                    )
                else:
                    response.success()
            else:
                response.failure(
                    f"Unexpected status code: {response.status_code}"
                )

    @task(3)
    def search_by_company_name(self) -> None:
        """GET /api/v1/assets/search?q={name} — search by company name fragment."""
        query = random.choice(_SEARCH_QUERIES)
        with self.client.get(
            "/api/v1/assets/search",
            params={"q": query},
            name="/api/v1/assets/search?q=[name]",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                body = response.json()
                if not isinstance(body, list):
                    response.failure(f"Expected list, got: {type(body)}")
                else:
                    response.success()
            else:
                response.failure(
                    f"Unexpected status code: {response.status_code}"
                )

    @task(1)
    def search_with_limit(self) -> None:
        """GET /api/v1/assets/search?q={q}&limit=5 — verify limit is respected."""
        query = random.choice(_SEARCH_QUERIES)
        limit = random.choice([3, 5, 10])
        with self.client.get(
            "/api/v1/assets/search",
            params={"q": query, "limit": limit},
            name="/api/v1/assets/search?q=[q]&limit=[n]",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                body = response.json()
                if len(body) > limit:
                    response.failure(
                        f"Returned {len(body)} results but limit was {limit}"
                    )
                else:
                    response.success()
            else:
                response.failure(
                    f"Unexpected status code: {response.status_code}"
                )

    @task(1)
    def search_invalid_empty_query(self) -> None:
        """GET /api/v1/assets/search?q= — empty query should return 422."""
        with self.client.get(
            "/api/v1/assets/search",
            params={"q": ""},
            name="/api/v1/assets/search?q=[empty]",
            catch_response=True,
        ) as response:
            if response.status_code == 422:
                response.success()
            else:
                response.failure(
                    f"Expected 422 for empty query, got: {response.status_code}"
                )


# ---------------------------------------------------------------------------
# OptimizationUser
# ---------------------------------------------------------------------------


class OptimizationUser(HttpUser):
    """Simulates a user submitting optimization runs and polling for status.

    Represents the core workflow: build portfolio → submit → wait for result.
    """

    weight = 2
    wait_time = between(2, 10)

    def on_start(self) -> None:
        """Initialise per-user state."""
        self._submitted_run_ids: list[str] = []

    @task(3)
    def submit_optimization(self) -> None:
        """POST /api/v1/optimize — submit a new optimization run."""
        request_body = random.choice(_OPTIMIZATION_REQUESTS)
        with self.client.post(
            "/api/v1/optimize",
            json=request_body,
            name="POST /api/v1/optimize",
            catch_response=True,
        ) as response:
            if response.status_code == 202:
                body = response.json()
                if "run_id" not in body:
                    response.failure(
                        f"Missing 'run_id' in 202 response: {body}"
                    )
                else:
                    run_id = body["run_id"]
                    # Validate UUID format
                    try:
                        uuid.UUID(run_id)
                        self._submitted_run_ids.append(run_id)
                        response.success()
                    except ValueError:
                        response.failure(
                            f"run_id '{run_id}' is not a valid UUID"
                        )
            else:
                response.failure(
                    f"Expected 202, got: {response.status_code} — {response.text[:200]}"
                )

    @task(2)
    def poll_run_status(self) -> None:
        """GET /api/v1/runs/{run_id}/status — poll status of a submitted run."""
        if not self._submitted_run_ids:
            # No runs submitted yet — skip this task
            return

        run_id = random.choice(self._submitted_run_ids)
        with self.client.get(
            f"/api/v1/runs/{run_id}/status",
            name="GET /api/v1/runs/[id]/status",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                body = response.json()
                if "status" not in body:
                    response.failure(
                        f"Missing 'status' field in status response: {body}"
                    )
                elif body["status"] not in (
                    "pending", "running", "completed", "failed"
                ):
                    response.failure(
                        f"Unexpected status value: {body['status']!r}"
                    )
                else:
                    response.success()
            elif response.status_code == 404:
                # Run may have been cleaned up — this is acceptable
                response.success()
            else:
                response.failure(
                    f"Unexpected status code: {response.status_code}"
                )

    @task(1)
    def get_run_detail(self) -> None:
        """GET /api/v1/runs/{run_id} — fetch full detail of a submitted run."""
        if not self._submitted_run_ids:
            return

        run_id = random.choice(self._submitted_run_ids)
        with self.client.get(
            f"/api/v1/runs/{run_id}",
            name="GET /api/v1/runs/[id]",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                body = response.json()
                required_fields = {"run_id", "status", "tickers", "budget", "created_at"}
                missing = required_fields - set(body.keys())
                if missing:
                    response.failure(
                        f"Missing fields in run detail: {missing}"
                    )
                else:
                    response.success()
            elif response.status_code == 404:
                # Run may have been cleaned up — acceptable
                response.success()
            else:
                response.failure(
                    f"Unexpected status code: {response.status_code}"
                )

    @task(1)
    def submit_invalid_optimization(self) -> None:
        """POST /api/v1/optimize with invalid payload — expect 422."""
        invalid_payloads = [
            # Missing budget
            {"tickers": ["AAPL", "MSFT"]},
            # Single ticker
            {"tickers": ["AAPL"], "budget": 10_000.0},
            # Negative budget
            {"tickers": ["AAPL", "MSFT"], "budget": -1000.0},
            # Empty tickers
            {"tickers": [], "budget": 10_000.0},
        ]
        payload = random.choice(invalid_payloads)
        with self.client.post(
            "/api/v1/optimize",
            json=payload,
            name="POST /api/v1/optimize [invalid]",
            catch_response=True,
        ) as response:
            if response.status_code == 422:
                body = response.json()
                if "detail" not in body:
                    response.failure(
                        f"Missing 'detail' in 422 response: {body}"
                    )
                else:
                    response.success()
            else:
                response.failure(
                    f"Expected 422 for invalid payload, got: {response.status_code}"
                )

    @task(1)
    def poll_unknown_run_id(self) -> None:
        """GET /api/v1/runs/{unknown_id}/status — expect 404."""
        unknown_id = str(uuid.uuid4())
        with self.client.get(
            f"/api/v1/runs/{unknown_id}/status",
            name="GET /api/v1/runs/[unknown]/status",
            catch_response=True,
        ) as response:
            if response.status_code == 404:
                body = response.json()
                detail = body.get("detail", {})
                if isinstance(detail, dict) and detail.get("error_code") == "RUN_NOT_FOUND":
                    response.success()
                else:
                    response.failure(
                        f"Expected error_code=RUN_NOT_FOUND in 404 body: {body}"
                    )
            else:
                response.failure(
                    f"Expected 404 for unknown run_id, got: {response.status_code}"
                )


# ---------------------------------------------------------------------------
# RunHistoryUser
# ---------------------------------------------------------------------------


class RunHistoryUser(HttpUser):
    """Simulates a user browsing the run history dashboard.

    Represents users reviewing past optimization results.
    """

    weight = 2
    wait_time = between(1, 5)

    @task(5)
    def list_runs_default(self) -> None:
        """GET /api/v1/runs — fetch first page of run history."""
        with self.client.get(
            "/api/v1/runs",
            name="GET /api/v1/runs",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                body = response.json()
                required_fields = {"items", "total", "page", "page_size"}
                missing = required_fields - set(body.keys())
                if missing:
                    response.failure(
                        f"Missing fields in run list: {missing}"
                    )
                elif not isinstance(body["items"], list):
                    response.failure(
                        f"Expected items to be a list, got: {type(body['items'])}"
                    )
                else:
                    response.success()
            else:
                response.failure(
                    f"Unexpected status code: {response.status_code}"
                )

    @task(3)
    def list_runs_paginated(self) -> None:
        """GET /api/v1/runs?page=2&page_size=10 — fetch a specific page."""
        page = random.randint(1, 3)
        page_size = random.choice([5, 10, 20])
        with self.client.get(
            "/api/v1/runs",
            params={"page": page, "page_size": page_size},
            name="GET /api/v1/runs?page=[n]&page_size=[n]",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                body = response.json()
                if body["page"] != page:
                    response.failure(
                        f"Expected page={page}, got page={body['page']}"
                    )
                elif body["page_size"] != page_size:
                    response.failure(
                        f"Expected page_size={page_size}, got {body['page_size']}"
                    )
                elif len(body["items"]) > page_size:
                    response.failure(
                        f"Returned {len(body['items'])} items but page_size={page_size}"
                    )
                else:
                    response.success()
            else:
                response.failure(
                    f"Unexpected status code: {response.status_code}"
                )

    @task(2)
    def list_runs_filtered_by_status(self) -> None:
        """GET /api/v1/runs?status={status} — filter by run status."""
        status = random.choice(["pending", "running", "completed", "failed"])
        with self.client.get(
            "/api/v1/runs",
            params={"status": status},
            name="GET /api/v1/runs?status=[status]",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                body = response.json()
                # All returned items must have the requested status
                for item in body["items"]:
                    if item["status"] != status:
                        response.failure(
                            f"Item has status={item['status']!r} but "
                            f"filter was status={status!r}"
                        )
                        return
                response.success()
            else:
                response.failure(
                    f"Unexpected status code: {response.status_code}"
                )

    @task(1)
    def list_runs_invalid_status_filter(self) -> None:
        """GET /api/v1/runs?status=invalid — expect 422."""
        with self.client.get(
            "/api/v1/runs",
            params={"status": "not_a_real_status"},
            name="GET /api/v1/runs?status=[invalid]",
            catch_response=True,
        ) as response:
            if response.status_code == 422:
                response.success()
            else:
                response.failure(
                    f"Expected 422 for invalid status filter, got: {response.status_code}"
                )

    @task(2)
    def get_unknown_run_detail(self) -> None:
        """GET /api/v1/runs/{unknown_id} — expect 404 with structured error."""
        unknown_id = str(uuid.uuid4())
        with self.client.get(
            f"/api/v1/runs/{unknown_id}",
            name="GET /api/v1/runs/[unknown]",
            catch_response=True,
        ) as response:
            if response.status_code == 404:
                body = response.json()
                detail = body.get("detail", {})
                if isinstance(detail, dict) and detail.get("error_code") == "RUN_NOT_FOUND":
                    response.success()
                else:
                    response.failure(
                        f"Expected error_code=RUN_NOT_FOUND in 404 body: {body}"
                    )
            else:
                response.failure(
                    f"Expected 404 for unknown run, got: {response.status_code}"
                )


# ---------------------------------------------------------------------------
# MixedUser — realistic combined traffic
# ---------------------------------------------------------------------------


class MixedUser(HttpUser):
    """Simulates a realistic user who does a mix of all actions.

    This is the primary user class for load testing — it combines health
    checks, asset searches, optimization submits, and history browsing in
    proportions that reflect real usage patterns.
    """

    weight = 5
    wait_time = between(1, 8)

    def on_start(self) -> None:
        """Initialise per-user state."""
        self._submitted_run_ids: list[str] = []

    # ── Health (low frequency) ──────────────────────────────────────────────

    @task(1)
    def check_health(self) -> None:
        """GET /health — periodic health check."""
        with self.client.get(
            "/health",
            name="GET /health",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 503):
                body = response.json()
                if "status" in body and "services" in body:
                    response.success()
                else:
                    response.failure(
                        f"Missing required fields in health response: {body}"
                    )
            else:
                response.failure(
                    f"Unexpected status code: {response.status_code}"
                )

    # ── Asset search (high frequency — interactive) ─────────────────────────

    @task(8)
    def search_assets(self) -> None:
        """GET /api/v1/assets/search — search for assets."""
        query = random.choice(_SEARCH_QUERIES + _TICKERS)
        with self.client.get(
            "/api/v1/assets/search",
            params={"q": query},
            name="GET /api/v1/assets/search",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                body = response.json()
                if isinstance(body, list):
                    response.success()
                else:
                    response.failure(f"Expected list, got: {type(body)}")
            else:
                response.failure(
                    f"Unexpected status code: {response.status_code}"
                )

    # ── Optimization submit (medium frequency) ──────────────────────────────

    @task(3)
    def submit_optimization(self) -> None:
        """POST /api/v1/optimize — submit a new run."""
        request_body = random.choice(_OPTIMIZATION_REQUESTS)
        with self.client.post(
            "/api/v1/optimize",
            json=request_body,
            name="POST /api/v1/optimize",
            catch_response=True,
        ) as response:
            if response.status_code == 202:
                body = response.json()
                if "run_id" in body:
                    try:
                        uuid.UUID(body["run_id"])
                        self._submitted_run_ids.append(body["run_id"])
                        response.success()
                    except ValueError:
                        response.failure(
                            f"run_id '{body['run_id']}' is not a valid UUID"
                        )
                else:
                    response.failure(f"Missing run_id in 202 response: {body}")
            else:
                response.failure(
                    f"Expected 202, got: {response.status_code}"
                )

    # ── Status polling (medium frequency) ───────────────────────────────────

    @task(4)
    def poll_run_status(self) -> None:
        """GET /api/v1/runs/{run_id}/status — poll a submitted run."""
        if not self._submitted_run_ids:
            return

        run_id = random.choice(self._submitted_run_ids)
        with self.client.get(
            f"/api/v1/runs/{run_id}/status",
            name="GET /api/v1/runs/[id]/status",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 404):
                response.success()
            else:
                response.failure(
                    f"Unexpected status code: {response.status_code}"
                )

    # ── Run history browsing (medium frequency) ─────────────────────────────

    @task(5)
    def browse_run_history(self) -> None:
        """GET /api/v1/runs — browse run history."""
        page = random.randint(1, 2)
        with self.client.get(
            "/api/v1/runs",
            params={"page": page, "page_size": 10},
            name="GET /api/v1/runs",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                body = response.json()
                if "items" in body and "total" in body:
                    response.success()
                else:
                    response.failure(
                        f"Missing required fields in run list: {body}"
                    )
            else:
                response.failure(
                    f"Unexpected status code: {response.status_code}"
                )

    # ── Run detail (low-medium frequency) ───────────────────────────────────

    @task(2)
    def view_run_detail(self) -> None:
        """GET /api/v1/runs/{run_id} — view full run detail."""
        if not self._submitted_run_ids:
            return

        run_id = random.choice(self._submitted_run_ids)
        with self.client.get(
            f"/api/v1/runs/{run_id}",
            name="GET /api/v1/runs/[id]",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 404):
                response.success()
            else:
                response.failure(
                    f"Unexpected status code: {response.status_code}"
                )

    # ── Error paths (low frequency — validates error handling) ──────────────

    @task(1)
    def submit_invalid_request(self) -> None:
        """POST /api/v1/optimize with invalid payload — expect 422."""
        with self.client.post(
            "/api/v1/optimize",
            json={"tickers": ["AAPL"], "budget": -100.0},
            name="POST /api/v1/optimize [invalid]",
            catch_response=True,
        ) as response:
            if response.status_code == 422:
                response.success()
            else:
                response.failure(
                    f"Expected 422 for invalid payload, got: {response.status_code}"
                )

    @task(1)
    def fetch_unknown_run(self) -> None:
        """GET /api/v1/runs/{unknown_id} — expect 404."""
        unknown_id = str(uuid.uuid4())
        with self.client.get(
            f"/api/v1/runs/{unknown_id}",
            name="GET /api/v1/runs/[unknown]",
            catch_response=True,
        ) as response:
            if response.status_code == 404:
                response.success()
            else:
                response.failure(
                    f"Expected 404 for unknown run, got: {response.status_code}"
                )
