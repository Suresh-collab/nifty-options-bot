"""0.5 — structured JSON logging + request-id propagation tests."""
import logging
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture(autouse=True)
def _reset_logging():
    """Avoid log handler bleed between tests."""
    yield
    for handler in logging.getLogger().handlers[:]:
        logging.getLogger().removeHandler(handler)


@pytest.mark.asyncio
async def test_request_id_in_response_header():
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert "x-request-id" in response.headers
    rid = response.headers["x-request-id"]
    assert len(rid) == 36  # UUID4 format


@pytest.mark.asyncio
async def test_three_requests_each_get_unique_ids():
    from main import app
    rids = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(3):
            r = await client.get("/health")
            rids.append(r.headers["x-request-id"])
    assert len(set(rids)) == 3, "Each request must have a unique request_id"


@pytest.mark.asyncio
async def test_log_lines_carry_request_id():
    """Log records emitted during a request must carry that request's ID."""
    from main import app
    from middleware.logging import request_id_var

    captured: list[logging.LogRecord] = []

    class _Cap(logging.Handler):
        def emit(self, record):
            captured.append(record)

    cap = _Cap()
    logging.getLogger().addHandler(cap)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health")

    rid = r.headers["x-request-id"]
    records_with_rid = [rec for rec in captured if getattr(rec, "request_id", None) == rid]
    assert len(records_with_rid) >= 2, "At least request_start and request_end should carry request_id"
