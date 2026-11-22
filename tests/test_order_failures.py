"""Emir dayanıklılığı: reddedilen satış/alış, tekrar deneme, adet hesabı.

Kapsanan senaryolar:
- Satış emri reddedilirse pozisyon ve nakit **bozulmaz**, karar kalıcı kalır.
- Bekleyen çıkış mum kapanışı beklemeden tekrar denenir.
- Panelden gelen manuel satış isteği başarısızlıkta silinmez.
- DB yazımı başarısızsa paper modda çift satış oluşmaz.
- Adet `stepSize`'a göre yuvarlanır, `minNotional` ve `maxQty` kontrol edilir.
- Canlı alım `quoteOrderQty` ile yapılır; bakiye aşılmaz.
- Zaman aşımında emir kimliğiyle durum sorgulanır, çift emir gönderilmez.
"""

from __future__ import annotations

import sqlite3

import pytest

from app import account_lock, bot_state, db, exchange
from app.paths import paths


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "db", tmp_path / "test.db")
    db.init_db()
    yield


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("app.engine.time.sleep", lambda *a, **k: None)
    monkeypatch.setattr("app.engine.notifier.send", lambda *a, **k: None)


class FakeClient:
    def __init__(self, balances=None):
        self._balances = balances or []
        self.orders = {}

    def get_account(self):
        return {"balances": self._balances}

    def get_order(self, symbol=None, orderId=None):
        return self.orders.get(int(orderId))


class FakeBinance:
    """Emirleri taklit eden sahte borsa; hatalar testten ayarlanır."""

    def __init__(self, balances=None, buy_error=None, sell_error=None):
        self.client = FakeClient(balances)
        self.buy_error = buy_error
        self.sell_error = sell_error
        self.buy_calls = []
        self.sell_calls = []
        self.buy_quote_calls = []
        self.cancelled = 0
        self.protective = []
        self.status_lookup = {}
        self.filters = {
            "symbol": "BTCUSDT",
            "status": "TRADING",
            "step_size": 0.00001,
            "min_qty": 0.00001,
            "max_qty": 9000.0,
            "market_max_qty": None,
            "min_notional": 5.0,
            "tick_size": 0.01,
            "found": True,
        }

    # --- veri / bakiye -------------------------------------------------
    def get_coin_filters(self, coin):
        return dict(self.filters)

    def get_coin_minQTY(self, coin):
        return float(self.filters["min_qty"])

    def mevcut_adedim(self, coin):
        from app.exchange import asset_of

        asset = asset_of(coin)
        for item in self.client.get_account()["balances"]:
            if str(item["asset"]).upper() == asset:
                return float(item["free"])
        return 0.0

    # --- emirler -------------------------------------------------------
    def market_buy(self, coin, adet, client_order_id=None):
        self.buy_calls.append((coin, adet, client_order_id))
        if self.buy_error:
            raise self.buy_error
        return {
            "orderId": 1,
            "executedQty": str(adet),
            "cummulativeQuoteQty": str(float(adet) * 100.0),
            "status": "FILLED",
        }

    def market_buy_quote(self, coin, quote_qty, client_order_id=None):
        self.buy_quote_calls.append((coin, quote_qty, client_order_id))
        if self.buy_error:
            raise self.buy_error
        executed = float(quote_qty) / 100.0
        return {
            "orderId": 2,
            "executedQty": str(executed),
            "cummulativeQuoteQty": str(float(quote_qty)),
            "status": "FILLED",
        }

    def market_sell(self, coin, adet, client_order_id=None):
        self.sell_calls.append((coin, adet, client_order_id))
        if self.sell_error:
            raise self.sell_error
        return {
            "orderId": 3,
            "executedQty": str(adet),
            "cummulativeQuoteQty": str(float(adet) * 100.0),
            "status": "FILLED",
        }

    def order_status(self, coin, client_order_id):
        if client_order_id in self.status_lookup:
            return self.status_lookup[client_order_id]
        raise RuntimeError("order not found")

    def open_orders(self, coin):
        return []

    def cancel_open_orders(self, coin):
        self.cancelled += 1
        return []

    def place_protective_stop(self, coin, quantity, stop_price, tick_size=0.0):
        self.protective.append((coin, quantity, stop_price))
        return {"orderId": 9}

    def place_protective_oco(self, coin, quantity, stop_price, target_price, tick_size=0.0):
        self.protective.append((coin, quantity, stop_price, target_price))
        return {
            "orderListId": 11,
            "orders": [
                {"orderId": 12, "type": "STOP_LOSS_LIMIT"},
                {"orderId": 13, "type": "LIMIT_MAKER"},
            ],
        }

    def cancel_order_list(self, coin, order_list_id):
        self.cancelled += 1
        return []


def _definition():
    return {
        "name": "Emir testi",
        "risk": {},
        "buy": {
            "logic": "AND",
            "conditions": [
                {
                    "left": {"type": "price", "field": "close"},
                    "op": "gt",
                    "right": {"type": "constant", "value": 0},
                }
            ],
        },
        "sell": {
            "logic": "OR",
            "conditions": [
                {
                    "left": {"type": "price", "field": "close"},
                    "op": "lt",
                    "right": {"type": "constant", "value": 0},
                }
            ],
        },
    }


def make_engine(monkeypatch, mode="live", binance=None, position=None, cash=100.0, risk=None):
    from app.engine import TradingEngine
    from app.strategies.service import create_custom

    definition = _definition()
    definition["risk"] = risk or {}
    item = create_custom(definition)
    engine = TradingEngine(
        "bot_order",
        {
            "period": "1h",
            "strategies": [{"type": "custom", "id": item["id"]}],
            "cash": cash,
            "risk": risk or {},
        },
        mode,
    )
    engine.binance = binance or FakeBinance()
    engine.protective_enabled = True
    engine.state = {
        "bot_id": "bot_order",
        "mode": mode,
        "cash": cash,
        "initial_cash": 100.0,
        "position": position,
        "total_realized_pnl": 0.0,
        "trade_count": 1,
        "candle_seq": 3,
        "pending_exit": None,
        "exit_reasons": {},
    }
    monkeypatch.setattr(engine, "_save_state", lambda: None)
    monkeypatch.setattr(engine, "_log", lambda *a, **k: None)
    return engine


def _position(**kwargs):
    base = {
        "coin": "BTCUSDT",
        "quantity": 0.5,
        "entry_price": 100.0,
        "highest_price": 100.0,
        "atr": 2.0,
        "candles": 1,
        "stop_price": 95.0,
    }
    base.update(kwargs)
    return base


# ----------------------------------------------------------------------
# Satış hataları
# ----------------------------------------------------------------------
def test_sell_failure_keeps_position_and_records_pending(temp_db, monkeypatch):
    binance = FakeBinance(
        balances=[{"asset": "BTC", "free": "0.5", "locked": "0"},
                  {"asset": "USDT", "free": "0", "locked": "0"}],
        sell_error=RuntimeError("-2010 Insufficient balance"),
    )
    engine = make_engine(monkeypatch, binance=binance, position=_position(), cash=0.0)

    ok = engine._close_position(95.0, "stop")

    assert ok is False
    assert engine.state["position"] is not None
    assert engine.state["cash"] == 0.0
    assert engine.state["pending_exit"]["reason"] == "stop"
    assert engine.state["last_error"]
    assert not db.rows("SELECT * FROM trades WHERE bot_id='bot_order'")


def test_pending_exit_retries_until_success(temp_db, monkeypatch):
    binance = FakeBinance(
        balances=[{"asset": "BTC", "free": "0.5", "locked": "0"},
                  {"asset": "USDT", "free": "0", "locked": "0"}],
        sell_error=RuntimeError("500 Server Error"),
    )
    engine = make_engine(monkeypatch, binance=binance, position=_position(), cash=0.0)

    engine._request_exit("takipli-stop", 96.0)
    assert engine._process_pending_exit() is True          # ilk deneme: başarısız
    assert engine.state["pending_exit"]["attempts"] == 1
    assert engine.state["position"] is not None

    # Bekleme süresini atla ve borsa bu kez başarılı olsun.
    binance.sell_error = None
    engine.state["pending_exit"]["last_attempt"] = 0.0
    assert engine._process_pending_exit() is True

    assert engine.state["position"] is None
    assert engine.state["pending_exit"] is None
    trades = db.rows("SELECT side, reason, price FROM trades WHERE bot_id='bot_order'")
    assert trades and trades[-1]["side"] == "SELL"
    assert trades[-1]["reason"] == "takipli-stop"


def test_manual_sell_request_survives_failure(temp_db, monkeypatch):
    binance = FakeBinance(
        balances=[{"asset": "BTC", "free": "0.5", "locked": "0"},
                  {"asset": "USDT", "free": "0", "locked": "0"}],
        sell_error=RuntimeError("-2010 rejected"),
    )
    engine = make_engine(monkeypatch, binance=binance, position=_position(), cash=0.0)
    bot_state.request_sell("bot_order", price=100.0)

    engine._handle_sell_request()

    assert bot_state.sell_requested("bot_order") is not None   # istek korunur
    assert engine.state["position"] is not None
    assert engine.state["pending_exit"]["reason"] == "manuel"

    # Borsa düzelince istek temizlenir.
    binance.sell_error = None
    engine.state["pending_exit"]["last_attempt"] = 0.0
    engine._handle_sell_request()

    assert bot_state.sell_requested("bot_order") is None
    assert engine.state["position"] is None
    assert engine.state["pending_exit"] is None


def test_paper_record_failure_prevents_double_sell(temp_db, monkeypatch):
    engine = make_engine(monkeypatch, mode="paper", position=_position(), cash=0.0)
    original = engine._record_trade
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return original(*a, **k)

    monkeypatch.setattr(engine, "_record_trade", flaky)
    ok = engine._close_position(100.0, "sinyal")

    assert ok is False
    assert engine.state["position"] is not None
    assert engine.state["cash"] == 0.0

    # Kilit açıldığında tek satış gerçekleşir (çift satış yok).
    engine.state["pending_exit"] = None
    assert engine._close_position(100.0, "sinyal") is True
    trades = db.rows("SELECT side FROM trades WHERE bot_id='bot_order'")
    assert len([t for t in trades if t["side"] == "SELL"]) == 1
    assert engine.state["position"] is None


# ----------------------------------------------------------------------
# Alım hataları
# ----------------------------------------------------------------------
def test_rejected_buy_does_not_open_position(temp_db, monkeypatch):
    binance = FakeBinance(
        balances=[{"asset": "USDT", "free": "100", "locked": "0"}],
        buy_error=RuntimeError("-2010 Insufficient balance"),
    )
    engine = make_engine(monkeypatch, binance=binance, position=None, cash=100.0)
    from app.strategies.service import build_evaluator

    ok = engine._open_live(
        "BTCUSDT", 100.0, engine.evaluators[0], {"buy_detail": None}, 2.0, budget=100.0
    )

    assert ok is False
    assert engine.state["position"] is None
    assert engine.state["cash"] == 100.0


def test_timeout_order_is_verified_instead_of_resent(temp_db, monkeypatch):
    binance = FakeBinance(
        balances=[{"asset": "USDT", "free": "100", "locked": "0"}],
        buy_error=TimeoutError("timed out"),
    )
    engine = make_engine(monkeypatch, binance=binance, position=None, cash=100.0)
    from app.exchange import new_client_id  # noqa: F401 - kimlik biçimi kontrolü

    def fake_buy(coin, adet, client_order_id=None):
        binance.buy_calls.append((coin, adet, client_order_id))
        # Emir borsada gerçekleşti ama yanıt gelmedi.
        binance.status_lookup[client_order_id] = {
            "orderId": 7,
            "status": "FILLED",
            "executedQty": str(adet),
            "cummulativeQuoteQty": str(float(adet) * 100.0),
        }
        raise TimeoutError("timed out")

    binance.market_buy = fake_buy
    order = engine._submit_order("BUY", "BTCUSDT", qty=0.5)

    assert order["status"] == "FILLED"
    assert len(binance.buy_calls) == 1


def test_open_live_uses_quote_order_qty_and_local_cash(temp_db, monkeypatch):
    binance = FakeBinance(balances=[{"asset": "USDT", "free": "1000", "locked": "0"}])
    engine = make_engine(monkeypatch, binance=binance, position=None, cash=20.0)

    ok = engine._open_live(
        "BTCUSDT", 100.0, engine.evaluators[0], {"buy_detail": None}, 2.0, budget=20.0
    )

    assert ok is True
    # Emir USDT tutarıyla verildi ve botun kendi 20 USDT'si aşılmadı.
    assert binance.buy_quote_calls
    _coin, quote_qty, client_id = binance.buy_quote_calls[0]
    assert quote_qty <= 20.0
    assert client_id
    position = engine.state["position"]
    assert position["quantity"] == pytest.approx(quote_qty / 100.0)
    fee = quote_qty * engine.fee
    assert engine.state["cash"] == pytest.approx(max(0.0, 20.0 - quote_qty - fee))


def test_open_live_falls_back_when_quote_not_supported(temp_db, monkeypatch):
    binance = FakeBinance(balances=[{"asset": "USDT", "free": "100", "locked": "0"}])

    def quote_unsupported(coin, quote_qty, client_order_id=None):
        raise RuntimeError("-1102 Mandatory parameter 'quantity' was not sent")

    binance.market_buy_quote = quote_unsupported
    engine = make_engine(monkeypatch, binance=binance, position=None, cash=100.0)

    ok = engine._open_live(
        "BTCUSDT", 100.0, engine.evaluators[0], {"buy_detail": None}, 2.0, budget=100.0
    )

    assert ok is True
    assert binance.buy_calls  # adet bazlı yedeğe düştü
    assert engine.state["position"] is not None


# ----------------------------------------------------------------------
# Adet / filtre hesabı
# ----------------------------------------------------------------------
def test_round_step_uses_step_size():
    assert exchange.round_step(1.23456789, 0.001) == pytest.approx(1.234)
    assert exchange.round_step(1.23456789, 0.001, "up") == pytest.approx(1.235)
    assert exchange.round_step(0.000019, 0.00001) == pytest.approx(0.00001)
    assert exchange.round_step(5, 1) == 5
    assert exchange.round_step(0.5, 0) == 0.5


def test_symbol_filters_looks_up_by_type_not_position():
    info = {
        "symbols": [
            {
                "symbol": "XUSDT",
                "status": "TRADING",
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.0001"},
                    {"filterType": "NOTIONAL", "minNotional": "1.0"},
                    {"filterType": "ICEBERG_PARTS", "limit": "10"},
                    {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001", "maxQty": "5000"},
                ],
            }
        ]
    }
    flt = exchange.symbol_filters(info, "XUSDT")
    assert flt["found"] is True
    assert flt["step_size"] == 0.001
    assert flt["min_qty"] == 0.001
    assert flt["max_qty"] == 5000
    assert flt["min_notional"] == 1.0
    assert flt["tick_size"] == 0.0001


def test_unknown_symbol_gets_safe_defaults():
    flt = exchange.symbol_filters({"symbols": []}, "NOPEUSDT")
    assert flt["found"] is False
    assert flt["min_notional"] == exchange.DEFAULT_MIN_NOTIONAL


def test_error_classification():
    assert exchange.is_permanent(RuntimeError("APIError(code=-2010): insufficient balance"))
    assert exchange.is_permanent(RuntimeError("Invalid API-key"))
    assert exchange.is_transient(RuntimeError("500 Server Error"))
    assert exchange.is_transient(TimeoutError("timed out"))
    assert not exchange.is_transient(RuntimeError("-1013 Filter failure: LOT_SIZE"))
    assert exchange.retry_delay(TimeoutError("timed out"), 0) >= 2


# ----------------------------------------------------------------------
# Koruyucu stop / hesap kilidi / mutabakat
# ----------------------------------------------------------------------
def test_protective_stop_placed_and_cancelled(temp_db, monkeypatch):
    binance = FakeBinance(balances=[{"asset": "BTC", "free": "0.5", "locked": "0"}])
    engine = make_engine(monkeypatch, binance=binance, position=_position(), cash=0.0)

    engine._sync_protective("BTCUSDT", 0.5, 95.0)
    assert binance.protective and binance.protective[0][2] == 95.0
    assert engine.state["position"]["protective_stop"] == 95.0

    engine._cancel_protective("BTCUSDT")
    assert binance.cancelled >= 1
    assert engine.state["position"]["protective_stop"] is None


def test_sell_failure_rearms_protective_stop(temp_db, monkeypatch):
    binance = FakeBinance(
        balances=[{"asset": "BTC", "free": "0.5", "locked": "0"}],
        sell_error=RuntimeError("-2010 rejected"),
    )
    engine = make_engine(monkeypatch, binance=binance, position=_position(highest_price=110.0), cash=0.0)
    engine.state["position"]["protective_stop"] = None

    engine._close_position(95.0, "stop")

    assert engine.state["position"] is not None
    assert binance.protective  # satış başarısız olunca koruma geri kuruldu


def test_protective_fill_is_recorded_as_stop(temp_db, monkeypatch):
    binance = FakeBinance(
        balances=[{"asset": "BTC", "free": "0", "locked": "0"},
                  {"asset": "USDT", "free": "95.0", "locked": "0"}]
    )
    binance.client.orders[9] = {
        "orderId": 9,
        "status": "FILLED",
        "executedQty": "0.5",
        "cummulativeQuoteQty": "47.5",
    }
    position = _position(highest_price=110.0)
    position["protective_stop"] = 95.0
    position["protective_order_id"] = "9"
    position["last_price"] = 95.0
    engine = make_engine(monkeypatch, binance=binance, position=position, cash=0.0)

    engine._sync_live_position()

    assert engine.state["position"] is None
    trades = db.rows("SELECT reason, price FROM trades WHERE bot_id='bot_order'")
    assert trades[-1]["reason"] == "stop"
    assert trades[-1]["price"] == pytest.approx(95.0)


def test_protective_oco_places_stop_and_target(temp_db, monkeypatch):
    binance = FakeBinance(balances=[{"asset": "BTC", "free": "0.5", "locked": "0"}])
    engine = make_engine(monkeypatch, binance=binance, position=_position(), cash=0.0)

    engine._sync_protective("BTCUSDT", 0.5, 95.0, 110.0)

    assert binance.protective[-1] == ("BTCUSDT", 0.5, 95.0, 110.0)
    position = engine.state["position"]
    assert position["protective_list_id"] == "11"
    assert position["protective_order_id"] == "12"
    assert position["protective_tp_order_id"] == "13"
    assert position["protective_tp"] == 110.0


def test_oco_failure_falls_back_to_stop_only(temp_db, monkeypatch):
    binance = FakeBinance(balances=[{"asset": "BTC", "free": "0.5", "locked": "0"}])

    def broken(*a, **k):
        raise RuntimeError("-2010 OCO not supported")

    binance.place_protective_oco = broken
    engine = make_engine(monkeypatch, binance=binance, position=_position(), cash=0.0)

    engine._sync_protective("BTCUSDT", 0.5, 95.0, 110.0)

    assert binance.protective[-1] == ("BTCUSDT", 0.5, 95.0)
    assert engine.state["position"]["protective_stop"] == 95.0
    assert engine.state["position"]["protective_list_id"] is None


def test_protective_target_fill_recorded_as_take_profit(temp_db, monkeypatch):
    binance = FakeBinance(
        balances=[{"asset": "BTC", "free": "0", "locked": "0"},
                  {"asset": "USDT", "free": "55.0", "locked": "0"}]
    )
    binance.client.orders[12] = {"orderId": 12, "status": "CANCELED"}
    binance.client.orders[13] = {
        "orderId": 13,
        "status": "FILLED",
        "executedQty": "0.5",
        "cummulativeQuoteQty": "55.0",
    }
    position = _position(highest_price=110.0)
    position.update({
        "protective_stop": 95.0,
        "protective_order_id": "12",
        "protective_tp": 110.0,
        "protective_tp_order_id": "13",
        "protective_list_id": "11",
    })
    engine = make_engine(monkeypatch, binance=binance, position=position, cash=0.0)

    engine._sync_live_position()

    assert engine.state["position"] is None
    trades = db.rows("SELECT reason, price FROM trades WHERE bot_id='bot_order'")
    assert trades[-1]["reason"] == "take-profit"
    assert trades[-1]["price"] == pytest.approx(110.0)
    assert engine.state["exit_reasons"]["take-profit"] == 1


def test_pending_exit_keeps_attempts_on_same_reason(temp_db, monkeypatch):
    binance = FakeBinance(balances=[{"asset": "BTC", "free": "0.5", "locked": "0"}])
    engine = make_engine(monkeypatch, binance=binance, position=_position(), cash=0.0)

    engine._request_exit("stop", 95.0)
    engine.state["pending_exit"]["attempts"] = 4
    engine._request_exit("stop", 94.0)   # aynı neden: sayaç korunmalı

    assert engine.state["pending_exit"]["attempts"] == 4
    assert engine.state["pending_exit"]["price"] == 94.0

    engine._request_exit("manuel", 93.0)  # neden değişti: yeni karar
    assert engine.state["pending_exit"]["attempts"] == 0
    assert engine.state["pending_exit"]["reason"] == "manuel"


def test_account_lock_serializes_processes():
    account_lock.release()
    assert account_lock.acquire(timeout=1) is True
    try:
        assert account_lock.acquire(timeout=0.1, stale=60) is False
    finally:
        account_lock.release()
    assert account_lock.acquire(timeout=1) is True
    account_lock.release()


def test_reconcile_skips_cash_when_account_shared(temp_db, monkeypatch):
    binance = FakeBinance(
        balances=[{"asset": "BTC", "free": "0.5", "locked": "0"},
                  {"asset": "USDT", "free": "999", "locked": "0"}]
    )
    engine = make_engine(monkeypatch, binance=binance, position=_position(), cash=50.0)
    engine.binance.sahip_olduklarim = lambda: {"BTCUSDT": 0.5}

    monkeypatch.setattr("app.engine.settings.SHARED_ACCOUNT", True, raising=False)
    issues = engine._reconcile_live(notify=False)
    assert issues == []

    monkeypatch.setattr("app.engine.settings.SHARED_ACCOUNT", False, raising=False)
    issues = engine._reconcile_live(notify=False)
    assert any("USDT" in issue for issue in issues)
