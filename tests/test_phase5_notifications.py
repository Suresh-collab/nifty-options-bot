"""
Phase 5 — Real-time & Notifications tests.

Covers all 4 TDD criteria from MASTER_PLAN.md:
  5.1 WebSocket: 3 clients connected → all receive tick within 500 ms
  5.2 Telegram:  trade entry alert → message delivered with required fields
  5.3 Email:     daily summary cron → email sent with P&L table
  5.4 Dedup:     same signal fired 3× in 30 s → exactly 1 alert delivered
"""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from starlette.testclient import TestClient

from main import app
from notifications.dedup import AlertDedup, should_send, reset
from notifications.telegram import send_message, send_trade_alert
from notifications.email import send_email, send_daily_summary
from api.ws import broadcast, connected_count
import api.ws as ws_module


# ===========================================================================
# 5.1 — WebSocket: 3 clients all receive tick within 500 ms
# ===========================================================================

class TestWebSocket:
    def test_ws_endpoint_accepts_connection(self):
        """/ws/live accepts a WebSocket connection (synchronous TestClient)."""
        with TestClient(app).websocket_connect("/ws/live") as ws:
            assert ws is not None

    @pytest.mark.asyncio
    async def test_broadcast_reaches_all_three_clients(self):
        """
        TDD 5.1: 3 mock clients in the registry → broadcast() delivers to all 3.
        Tests the delivery contract without needing 3 real TCP connections.
        """
        clients = [AsyncMock() for _ in range(3)]
        for c in clients:
            ws_module._clients.add(c)

        payload = {"type": "pnl_update", "daily_pnl": 1234.5}
        await broadcast(payload)

        for c in clients:
            c.send_json.assert_called_once_with(payload)

        # Cleanup
        for c in clients:
            ws_module._clients.discard(c)

    @pytest.mark.asyncio
    async def test_broadcast_within_500ms(self):
        """TDD 5.1: broadcast completes within 500 ms (timing assertion)."""
        clients = [AsyncMock() for _ in range(3)]
        for c in clients:
            ws_module._clients.add(c)

        t0 = asyncio.get_event_loop().time()
        await broadcast({"type": "tick", "val": 42})
        elapsed_ms = (asyncio.get_event_loop().time() - t0) * 1000

        assert elapsed_ms < 500, f"broadcast took {elapsed_ms:.1f} ms (> 500 ms)"

        for c in clients:
            ws_module._clients.discard(c)

    @pytest.mark.asyncio
    async def test_broadcast_ignores_dead_clients(self):
        """broadcast() silently removes clients that have disconnected."""
        dead = AsyncMock()
        dead.send_json.side_effect = Exception("connection closed")
        ws_module._clients.add(dead)

        await broadcast({"type": "test"})

        assert dead not in ws_module._clients

    def test_connected_count_increments_on_connect(self):
        """connected_count() reflects live connections via TestClient."""
        before = connected_count()
        with TestClient(app).websocket_connect("/ws/live"):
            assert connected_count() == before + 1
        assert connected_count() == before

    @pytest.mark.asyncio
    async def test_paper_enter_broadcasts_trade_event(self):
        """POST /api/paper-trade/enter fires a WebSocket broadcast (best-effort)."""
        import api.routes as routes_module
        routes_module._kill_switch_active = False

        broadcast_calls: list[dict] = []

        async def _fake_broadcast(data):
            broadcast_calls.append(data)

        payload = {
            "ticker": "NIFTY", "strike": 22000, "direction": "BUY_CE",
            "entry_price": 150.0, "lots": 1, "lot_size": 25, "signal": {},
        }
        with patch("paper_trading.simulator.get_daily_pnl", return_value=0.0), \
             patch("paper_trading.simulator.get_open_count", return_value=0), \
             patch("paper_trading.simulator.enter_trade",
                   return_value={"trade_id": 1, "status": "OPEN",
                                 "entry_time": "t", "message": "ok"}), \
             patch("api.ws.broadcast", new=_fake_broadcast):
            async with AsyncClient(transport=ASGITransport(app=app),
                                   base_url="http://test") as client:
                res = await client.post("/api/paper-trade/enter", json=payload)

        assert res.status_code == 200
        await asyncio.sleep(0.1)   # let fire-and-forget task complete
        trade_events = [c for c in broadcast_calls if c.get("type") == "trade_event"]
        assert len(trade_events) >= 1
        assert trade_events[0]["event"] == "entry"


# ===========================================================================
# 5.2 — Telegram alerts with required fields
# ===========================================================================

class TestTelegram:
    @pytest.mark.asyncio
    async def test_send_message_posts_to_telegram_api(self):
        """send_message() calls the Telegram Bot API with correct payload."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch("notifications.telegram.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_http

            result = await send_message(
                "Hello", bot_token="TEST_TOKEN", chat_id="12345"
            )

        assert result is True
        mock_http.post.assert_called_once()
        _, kwargs = mock_http.post.call_args
        assert kwargs["json"]["chat_id"] == "12345"
        assert "Hello" in kwargs["json"]["text"]

    @pytest.mark.asyncio
    async def test_send_trade_alert_contains_required_fields(self):
        """
        TDD 5.2: trade entry alert must include ticker, direction, strike, price.
        """
        captured: list[str] = []

        async def _fake_send(text, *, bot_token, chat_id, parse_mode="HTML",
                             dedup_key=None):
            captured.append(text)
            return True

        reset()
        with patch("notifications.telegram.send_message", new=_fake_send):
            await send_trade_alert(
                "trade_entry",
                ticker="NIFTY", direction="BUY_CE",
                strike=22000.0, price=150.75,
                bot_token="T", chat_id="C",
            )

        assert len(captured) == 1
        msg = captured[0]
        assert "NIFTY"  in msg
        assert "BUY_CE" in msg
        assert "22000"  in msg
        assert "150.75" in msg

    @pytest.mark.asyncio
    async def test_send_trade_alert_exit_includes_pnl(self):
        """Exit alert includes P&L field."""
        captured: list[str] = []

        async def _fake_send(text, **kwargs):
            captured.append(text)
            return True

        reset()
        with patch("notifications.telegram.send_message", new=_fake_send):
            await send_trade_alert(
                "trade_exit", "NIFTY", "BUY_CE", 22000, 155.0, pnl=105.0,
                bot_token="T", chat_id="C",
            )

        assert any("105" in t for t in captured)

    @pytest.mark.asyncio
    async def test_send_message_silent_when_token_missing(self):
        result = await send_message("hi", bot_token="", chat_id="123")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_returns_false_on_network_error(self):
        with patch("notifications.telegram.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(side_effect=Exception("timeout"))
            mock_cls.return_value = mock_http

            result = await send_message("hi", bot_token="T", chat_id="C")

        assert result is False


# ===========================================================================
# 5.3 — Email: daily summary contains P&L table
# ===========================================================================

class TestEmail:
    def _smtp_cfg(self):
        return dict(smtp_host="smtp.test.com", smtp_port=587,
                    smtp_user="u@test.com", smtp_password="pw",
                    to_address="dest@test.com")

    @pytest.mark.asyncio
    async def test_send_daily_summary_calls_smtp(self):
        """TDD 5.3: daily summary fires SMTP with a P&L table in the body."""
        trades = [
            {"ticker": "NIFTY",     "direction": "BUY_CE",
             "entry_price": 150.0,  "exit_price": 180.0, "pnl": 750.0},
            {"ticker": "BANKNIFTY", "direction": "BUY_PE",
             "entry_price": 200.0,  "exit_price": 170.0, "pnl": 900.0},
        ]
        mock_send = AsyncMock()
        reset()
        with patch("aiosmtplib.send", new=mock_send):
            result = await send_daily_summary(
                trades=trades, total_pnl=1650.0, **self._smtp_cfg()
            )

        assert result is True
        mock_send.assert_called_once()
        sent_msg = mock_send.call_args[0][0]
        # Decode each MIME part to check HTML content (parts may be base64-encoded)
        body_text = ""
        for part in sent_msg.walk():
            payload = part.get_payload(decode=True)
            if payload:
                body_text += payload.decode("utf-8", errors="ignore")
        assert "NIFTY" in body_text
        assert "750"   in body_text
        assert "1650"  in body_text

    @pytest.mark.asyncio
    async def test_send_email_silent_when_config_missing(self):
        result = await send_email(
            "subj", "<p>body</p>",
            smtp_host="", smtp_port=587,
            smtp_user="", smtp_password="", to_address="",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_send_email_returns_false_on_smtp_error(self):
        mock_send = AsyncMock(side_effect=Exception("SMTP refused"))
        with patch("aiosmtplib.send", new=mock_send):
            result = await send_email(
                "subj", "<p>body</p>",
                smtp_host="h", smtp_port=587,
                smtp_user="u", smtp_password="p", to_address="t@t.com",
            )
        assert result is False


# ===========================================================================
# 5.4 — Alert de-duplication: same signal 3× in 30 s → 1 delivery
# ===========================================================================

class TestDedup:
    def test_first_call_allowed(self):
        d = AlertDedup(ttl_seconds=60)
        assert d.should_send("key1") is True

    def test_second_call_within_ttl_blocked(self):
        d = AlertDedup(ttl_seconds=60)
        d.should_send("key1")
        assert d.should_send("key1") is False

    def test_three_calls_within_ttl_exactly_one_delivered(self):
        """TDD 5.4: 3 identical calls within TTL → exactly 1 True."""
        d = AlertDedup(ttl_seconds=60)
        results = [d.should_send("signal_X") for _ in range(3)]
        assert results.count(True) == 1
        assert results.count(False) == 2

    def test_call_after_ttl_allowed_again(self):
        d = AlertDedup(ttl_seconds=0.05)   # 50 ms for test speed
        assert d.should_send("key2") is True
        time.sleep(0.1)
        assert d.should_send("key2") is True

    def test_different_keys_are_independent(self):
        d = AlertDedup(ttl_seconds=60)
        assert d.should_send("alpha") is True
        assert d.should_send("beta")  is True

    def test_reset_clears_specific_key(self):
        d = AlertDedup(ttl_seconds=60)
        d.should_send("k")
        d.reset("k")
        assert d.should_send("k") is True

    def test_reset_all_clears_everything(self):
        d = AlertDedup(ttl_seconds=60)
        d.should_send("a")
        d.should_send("b")
        d.reset()
        assert d.should_send("a") is True
        assert d.should_send("b") is True

    @pytest.mark.asyncio
    async def test_telegram_dedup_suppresses_duplicates(self):
        """send_trade_alert called 3× for the same event → only 1 HTTP call."""
        http_calls = 0

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch("notifications.telegram.httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)

            async def _count(*args, **kwargs):
                nonlocal http_calls
                http_calls += 1
                return mock_resp

            mock_http.post = _count
            mock_cls.return_value = mock_http

            reset()   # clear module-level dedup store
            for _ in range(3):
                await send_trade_alert(
                    "trade_entry", "NIFTY", "BUY_CE", 22000, 150.0,
                    bot_token="T", chat_id="C",
                )

        assert http_calls == 1

    def test_time_until_next_positive_when_blocked(self):
        d = AlertDedup(ttl_seconds=60)
        d.should_send("t")
        assert 0 < d.time_until_next("t") <= 60

    def test_time_until_next_zero_when_unseen(self):
        d = AlertDedup(ttl_seconds=60)
        assert d.time_until_next("unseen") == 0.0
