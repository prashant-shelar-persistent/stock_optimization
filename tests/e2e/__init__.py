"""End-to-end (E2E) test package for the Portfolio Optimizer API.

This package contains two complementary test suites:

smoke_test.py
    Pytest-based smoke tests that exercise every public API endpoint using
    real HTTP requests.  In CI the tests run against the FastAPI app via
    ASGI transport (no real network socket required).  Against a live
    deployment they can be pointed at any base URL via the
    ``E2E_BASE_URL`` environment variable.

locustfile.py
    Locust load-test scenarios that simulate realistic user traffic patterns
    (health checks, asset searches, optimization submits, run-history polls).
    Run with ``locust -f tests/e2e/locustfile.py`` after starting the server.

Environment variables
---------------------
E2E_BASE_URL
    Base URL of the server under test.
    Default: ``http://localhost:8000`` (used by locustfile.py).
    The pytest smoke tests use ASGI transport by default and ignore this
    variable unless ``E2E_USE_REAL_SERVER=1`` is set.

E2E_USE_REAL_SERVER
    Set to ``1`` to make the pytest smoke tests send real HTTP requests to
    ``E2E_BASE_URL`` instead of using ASGI transport.  Requires the server
    to be running before the test suite is invoked.
"""
