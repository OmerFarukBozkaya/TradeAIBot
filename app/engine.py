"""Bot yürütme motoru.

Mevcut `Trade.py` davranışını bot konfigürasyonuna uyarlar:
- tek pozisyon, kapanmış mum sinyali ([-2])
- destek/dinamik/statik stop, take-profit
- paper (varsayılan) ve live mod
- SQLite ledger + atomik state
"""

from __future__ import annotations

import math
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app import db, bot_state
from app.config import settings
from app.notifications import notifier
from app.strategies.service import build_evaluator, normalize_specs

INTERVAL_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _floor_step(quantity: float, min_qty: float) -> float:
    if min_qty and min_qty > 0:
        precision = int(round(-math.log10(min_qty), 0))
        return math.floor(quantity * (10 ** precision)) / (10 ** precision)
    return quantity


class TradingEngine:
    def __init__(self, bot_id: str, config: Dict[str, Any], mode: str):
        self.bot_id = bot_id
        self.config = config
        self.mode = mode
        try:
            row = db.row("SELECT name FROM bots WHERE id=?", (bot_id,))
            self.bot_name = (row or {}).get("name") or bot_id
        except Exception:
            self.bot_name = bot_id
        self.period = config["period"]
        self.cash_start = float(config.get("cash", settings.DEFAULT_CASH))
        self.risk = {
            **settings.DEFAULT_RISK,
            **self._inherited_risk(config),
            # Panelde açıkça verilen değerler (0 ve false dahil) devralınanı ezer.
            **{k: v for k, v in (config.get("risk") or {}).items() if v is not None and v != ""},
        }
        self.filters = config.get("filters") or {}
        self.poll_seconds = int(config.get("poll_seconds", 10))
        self.fee = float(config.get("fee", settings.PAPER_FEE))
        self.slippage = float(config.get("slippage", settings.PAPER_SLIPPAGE))
        self.strategy_specs = normalize_specs(config.get("strategies"))
        if not self.strategy_specs:
            raise ValueError("Bot için en az bir strateji gerekli")
        self.evaluators = [build_evaluator(spec) for spec in self.strategy_specs]
        self.strategy_labels = self._strategy_labels()
        self.coins = list(config.get("coins") or [])
        self.max_position_pct = float(config.get("max_position_pct", 100)) / 100.0
        self.stop_event = False
        self.run_id: Optional[int] = None
        self.binance = None
        self.araclar = None
        self.state = self._load_state()

    # ------------------------------------------------------------------
    # Durum
    # ------------------------------------------------------------------
    @staticmethod
    def _inherited_risk(config: Dict[str, Any]) -> Dict[str, Any]:
        """Strateji tanımındaki risk bloğu (ATR stop, kâr koruma...).

        Eski bot kayıtlarında config.risk yalnızca 4 boolean taşıyordu; burada
        stratejiden devralınır ki canlı motor backtest ile aynı kuralları uygulasın.
        """
        from app.strategies.service import get_custom, normalize_specs

        for spec in normalize_specs(config.get("strategies")):
            if (spec.get("type") or spec.get("kind")) != "custom":
                continue
            item = get_custom(spec.get("id") or "")
            definition = (item or {}).get("definition") or {}
            inherited = definition.get("risk") if isinstance(definition, dict) else None
            if isinstance(inherited, dict) and inherited:
                return dict(inherited)
        return {}

    def _default_state(self) -> Dict[str, Any]:
        return {
            "bot_id": self.bot_id,
            "mode": self.mode,
            "period": self.period,
            "cash": self.cash_start,
            "initial_cash": self.cash_start,
            "position": None,
            "total_realized_pnl": 0.0,
            "trade_count": 0,
            "started_at": utcnow(),
            "last_update": utcnow(),
            "last_error": None,
            "reconciliation_required": False,
        }

    def _load_state(self) -> Dict[str, Any]:
        existing = bot_state.load_state(self.bot_id)
        if existing:
            existing["mode"] = self.mode
            existing["period"] = self.period
            return existing
        return self._default_state()

    def _save_state(self) -> None:
        self.state["last_update"] = utcnow()
        bot_state.save_state(self.bot_id, self.state)

    def heartbeat(self) -> None:
        """Durumu ve pid'i yazar. Geçici DB kesintisi botu durdurmamalı."""
        try:
            self._save_state()
        except Exception as exc:  # noqa: BLE001
            print(f"[heartbeat] state yazılamadı: {exc}", flush=True)
        try:
            db.execute(
                "UPDATE bots SET updated_at=?, pid=? WHERE id=?",
                (utcnow(), __import__("os").getpid(), self.bot_id),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[heartbeat] pid yazılamadı: {exc}", flush=True)

    def _strategy_labels(self) -> Dict[str, str]:
        """Strateji kimliği -> okunur ad eşlemesi (loglarda custom_xxx yerine ad)."""
        from app.strategies.service import get_custom, list_builtin

        builtin_labels = {i["name"]: (i.get("label") or i["name"]) for i in list_builtin(include_archived=True)}
        labels: Dict[str, str] = {}
        for spec in self.strategy_specs:
            kind = spec.get("type") or spec.get("kind")
            if kind == "custom":
                sid = str(spec.get("id") or "")
                name = spec.get("name")
                if not name:
                    item = get_custom(sid)
                    name = item["name"] if item else sid
                labels[sid] = name or sid
            else:
                motor = str(spec.get("name") or "")
                if (spec.get("type") or spec.get("kind")) == "ai":
                    labels[str(spec.get("model_id") or motor)] = spec.get("name") or motor
                else:
                    labels[motor] = spec.get("label") or builtin_labels.get(motor, motor)
        return labels

    def _evaluator_name(self, evaluator) -> str:
        eid = str(getattr(evaluator, "id", "") or "")
        return self.strategy_labels.get(eid, eid or "strateji")

    def _log(self, bot_id: str, message: str, level: str = "info") -> None:
        """Olayı hem veritabanına hem botun log dosyasına yazar.

        DB yazımı başarısız olsa bile (geçici kilit/kesinti) süreç logu yazılır
        ve bot çalışmaya devam eder.
        """
        try:
            db.log_event(bot_id, message, level)
        except Exception as exc:  # noqa: BLE001
            print(f"[log] olay yazılamadı: {exc}", flush=True)
        stamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{stamp}] {level.upper():7s} {message}", flush=True)

    # ------------------------------------------------------------------
    # Başlangıç
    # ------------------------------------------------------------------
    def _init_clients(self) -> None:
        if self.binance is None:
            from core import Binance

            while True:
                try:
                    self.binance = Binance()
                    break
                except Exception as exc:
                    if self.stop_event or bot_state.stop_requested(self.bot_id):
                        raise
                    self._log(
                        self.bot_id,
                        f"Binance bağlantısı kurulamadı, yeniden denenecek: {exc}",
                        "warning",
                    )
                    self.heartbeat()
                    time.sleep(10)
        if self.araclar is None:
            from core import Araclar

            self.araclar = Araclar()

    def _start_run(self) -> None:
        try:
            self.run_id = db.execute(
                "INSERT INTO bot_runs(bot_id,config_snapshot,mode,started_at,pid) VALUES(?,?,?,?,?)",
                (self.bot_id, db.json.dumps(self.config, ensure_ascii=False), self.mode, utcnow(), __import__("os").getpid()),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[start_run] çalıştırma kaydı yazılamadı: {exc}", flush=True)
        names = ", ".join(self._evaluator_name(ev) for ev in self.evaluators)
        self._log(self.bot_id, f"Bot başladı ({self.mode}, {self.period}) · strateji: {names}", "info")

    def _finish_run(self, reason: str) -> None:
        if self.run_id:
            try:
                db.execute(
                    "UPDATE bot_runs SET stopped_at=?, exit_reason=? WHERE id=?",
                    (utcnow(), reason, self.run_id),
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[finish_run] kayıt güncellenemedi: {exc}", flush=True)
        self._log(self.bot_id, f"Bot durdu: {reason}", "info")

    def _reconcile_live(self) -> List[str]:
        """Canlı modda yerel state ile Binance bakiyesini karşılaştırır."""
        issues: List[str] = []
        try:
            balances = self.binance.sahip_olduklarim()
        except Exception as exc:
            return [f"Bakiye okunamadı: {exc}"]
        usdt = 0.0
        try:
            for item in self.binance.client.get_account()["balances"]:
                if item["asset"] == "USDT":
                    usdt = float(item["free"])
                    break
        except Exception as exc:
            return [f"USDT bakiyesi okunamadı: {exc}"]

        position = self.state.get("position")
        if position:
            actual = balances.get(position["coin"], 0.0)
            local = float(position["quantity"])
            if local > 0 and abs(actual - local) / local > 0.02:
                issues.append(
                    f"{position['coin']} miktar uyuşmazlığı: yerel={local}, borsa={actual}"
                )
        # Nakit farkı %2'den fazlaysa uyar
        if self.state.get("cash") and abs(usdt - float(self.state["cash"])) / max(usdt, 1) > 0.02:
            issues.append(
                f"USDT uyuşmazlığı: yerel={self.state['cash']:.2f}, borsa={usdt:.2f}"
            )
        if issues:
            for issue in issues:
                self._log(self.bot_id, f"Mutabakat uyarısı: {issue}", "warning")
            notifier.send(f"Mutabakat Uyarısı | {self.bot_name}", "\n".join(issues))
        return issues

    def run(self) -> None:
        # Önce durumu yaz: web arayüzü bot daha Binance'e bağlanmadan durum görsün.
        # Yeni bir çalıştırma başladığında önceki çöküntünün hatası temizlenir.
        self.state["last_error"] = None
        self.state["reconciliation_required"] = False
        self._save_state()
        self.heartbeat()
        self._init_clients()
        self._start_run()
        if self.mode == "live":
            issues = self._reconcile_live()
            if issues:
                self.state["reconciliation_required"] = True
                self._save_state()
                db.execute("UPDATE bots SET status='reconciliation_required' WHERE id=?", (self.bot_id,))
                self._finish_run("reconciliation_required")
                return
        notifier.send(
            f"Bot Başladı | {self.bot_name}",
            f"Bot: {self.bot_name}\nMod: {self.mode}\nPeriyot: {self.period}\nNakit: {self.state['cash']:.2f}\n"
            f"Strateji: {', '.join(self._evaluator_name(ev) for ev in self.evaluators)}",
        )
        try:
            self._loop()
        except Exception as exc:
            self.state["last_error"] = traceback.format_exc()
            self._safe_save_state()
            self._log(self.bot_id, f"Kritik hata: {exc}", "error")
            try:
                notifier.send(f"Bot Hatası | {self.bot_name}", str(exc))
            except Exception:  # noqa: BLE001
                pass
            raise
        finally:
            self._safe_save_state()
            self._finish_run("normal" if not self.state.get("last_error") else "error")

    def _safe_save_state(self) -> None:
        """Durumu yaz; disk/DB geçici olarak erişilemezse çökme."""
        try:
            self._save_state()
        except Exception as exc:  # noqa: BLE001
            print(f"[save_state] durum yazılamadı: {exc}", flush=True)

    def _run_cycle(self) -> None:
        # Canlı modda borsa gerçeği yerel kayda göre önceliklidir:
        # kullanıcı elle satış yaptıysa pozisyon burada kapatılır.
        if self.mode == "live" and self.state.get("position"):
            self._sync_live_position()
        if self.state.get("position"):
            self._manage_position()
        else:
            self._scan_for_entry()

    def _loop(self) -> None:
        self._wait_for_candle(first=True)
        while not self.stop_event and not bot_state.stop_requested(self.bot_id):
            self.heartbeat()
            last: Optional[Exception] = None
            # Geçici borsa/ağ hatasında mumu atlamak yerine kısa bekleyip tekrar dene.
            for attempt in range(3):
                try:
                    self._run_cycle()
                    last = None
                    break
                except Exception as exc:  # noqa: BLE001
                    last = exc
                    text = str(exc)
                    transient = any(
                        token in text
                        for token in ("500", "502", "503", "504", "429", "timed out",
                                      "Connection", "Timeout", "Temporary",
                                      "unable to open database file", "database is locked")
                    )
                    if not transient:
                        break
                    self._log(
                        self.bot_id,
                        f"Geçici hata (deneme {attempt + 1}/3), kısa bekleyip tekrar deniyorum: {text[:120]}",
                        "warning",
                    )
                    time.sleep(5 * (attempt + 1))
            if last is not None:
                self.state["last_error"] = traceback.format_exc()
                try:
                    self._save_state()
                except Exception:  # noqa: BLE001
                    pass
                self._log(self.bot_id, f"Döngü hatası: {last}", "error")
                notifier.send(f"Bot Hatası | {self.bot_name}", str(last))
                time.sleep(5)
            else:
                self.state["last_error"] = None
            self._wait_for_candle()

    # ------------------------------------------------------------------
    # Zamanlama
    # ------------------------------------------------------------------
    def _wait_for_candle(self, first: bool = False) -> None:
        interval = INTERVAL_SECONDS.get(self.period, 3600)
        if first:
            # İlk açılışta mevcut mumun kapanmasını bekle (küçük tampon).
            now = time.time()
            next_close = (math.floor(now / interval) + 1) * interval + 2
        else:
            now = time.time()
            next_close = (math.floor(now / interval) + 1) * interval + 2
        last_sync = 0.0
        while time.time() < next_close:
            if self.stop_event or bot_state.stop_requested(self.bot_id):
                return
            self.heartbeat()
            # Mum bekleme sırasında da elle satışı yakala (yaklaşık 30 saniyede bir).
            if self.mode == "live" and self.state.get("position"):
                if time.time() - last_sync >= 30:
                    last_sync = time.time()
                    try:
                        self._sync_live_position()
                    except Exception as exc:  # noqa: BLE001
                        self._log(self.bot_id, f"Manuel satış kontrolü hatası: {exc}", "warning")
            time.sleep(min(5, max(1, next_close - time.time())))

    # ------------------------------------------------------------------
    # Veri
    # ------------------------------------------------------------------
    def _data(self, coin: str) -> Dict[str, List[float]]:
        """Mum verisi. Borsa geçici hata verirse (5xx / bağlantı) kısa bekleyip
        yeniden dener; tüm denemeler başarısızsa hata yükselir (döngü atlar)."""
        last: Optional[Exception] = None
        for attempt in range(4):
            if self.stop_event or bot_state.stop_requested(self.bot_id):
                break
            try:
                return self.binance.get_coin_data(coin, self.period, 1000)
            except Exception as exc:  # noqa: BLE001 - borsa/ağ hatası
                last = exc
                text = str(exc)
                transient = any(
                    token in text
                    for token in ("500", "502", "503", "504", "429", "timed out",
                                  "Connection", "Timeout", "Temporary")
                )
                if not transient and attempt >= 1:
                    break
                self._log(
                    self.bot_id,
                    f"{coin} veri alınamadı (deneme {attempt + 1}/4): {text[:120]}",
                    "warning",
                )
                time.sleep(min(15, 2 * (attempt + 1)))
        if last:
            raise last
        raise RuntimeError("Veri alınamadı")

    def _coinlist(self) -> List[str]:
        if self.coins:
            return list(self.coins)
        try:
            return self.binance.coin_list()
        except Exception:
            return []

    def _owned_coins(self) -> Dict[str, float]:
        if self.mode != "live":
            return {}
        try:
            return self.binance.sahip_olduklarim()
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Harici (manuel) işlem takibi — yalnızca canlı mod
    # ------------------------------------------------------------------
    @staticmethod
    def _asset_of(coin: str) -> str:
        text = str(coin or "").upper()
        for quote in ("USDT", "BUSD", "FDUSD", "USDC", "TRY", "BTC", "ETH", "BNB"):
            if text.endswith(quote) and len(text) > len(quote):
                return text[: -len(quote)]
        return text

    def _account_balances(self) -> Optional[Dict[str, Dict[str, float]]]:
        """Borsadaki free+locked bakiyeler (ham). Okunamazsa None."""
        try:
            payload = self.binance.client.get_account()["balances"]
        except Exception as exc:
            self._log(self.bot_id, f"Bakiye okunamadı (manuel takip): {exc}", "warning")
            return None
        result: Dict[str, Dict[str, float]] = {}
        for item in payload:
            try:
                result[str(item["asset"]).upper()] = {
                    "free": float(item["free"]),
                    "locked": float(item["locked"]),
                }
            except (KeyError, TypeError, ValueError):
                continue
        return result

    def _sync_live_position(self) -> List[str]:
        """Borsadaki gerçek miktarla yerel pozisyonu senkronlar.

        - Coin tamamen satılmışsa (elle satış) pozisyon kapatılır, gerçek nakit
          yazılır ve işlem geçmişine "manuel" nedenli SAT olarak eklenir.
        - Kısmi satışta kalan miktar yerel kayda işlenir.
        - Harici alım yapılmışsa (yerelde olmayan miktar) yerel miktar güncellenir.
        Döndürür: yapılan düzeltmelerin okunur listesi.
        """
        if self.mode != "live":
            return []
        position = self.state.get("position")
        if not position:
            return []
        balances = self._account_balances()
        if balances is None:
            return []
        coin = str(position.get("coin") or "")
        asset = self._asset_of(coin)
        entry = balances.get(asset) or {"free": 0.0, "locked": 0.0}
        actual = float(entry.get("free", 0.0)) + float(entry.get("locked", 0.0))
        local = float(position.get("quantity") or 0)
        if local <= 0:
            return []
        usdt = float((balances.get("USDT") or {}).get("free", self.state.get("cash") or 0.0))
        changes: List[str] = []

        if actual <= local * 0.01:
            self._close_manually(usdt, coin, local)
            return [f"{coin}: manuel satış algılandı, pozisyon kapatıldı"]
        if actual < local * 0.98:
            sold = local - actual
            price = self._external_exit_price(usdt, local, sold)
            entry_price = float(position.get("entry_price") or 0)
            fee_amount = sold * price * self.fee
            self.state["cash"] = round(usdt, 8)
            self.state["total_realized_pnl"] = round(
                float(self.state.get("total_realized_pnl", 0)) + (price - entry_price) * sold, 8
            )
            self._record_trade(
                coin, "SELL", sold, price, fee_amount, None, "manuel",
                (price / entry_price - 1) * 100 if entry_price else None,
            )
            position["quantity"] = actual
            self._save_state()
            changes.append(f"{coin}: kısmi manuel satış ({sold:g}) yerel kayda işlendi")
            self._log(self.bot_id, changes[-1], "warning")
            notifier.send(
                f"Kısmi manuel satış | {self.bot_name}",
                f"Bot: {self.bot_name}\n{coin}\nSatılan: {sold:g}\nKalan: {actual:g}\nFiyat: {price:.8f}",
            )
            return changes
        if actual > local * 1.02:
            added = actual - local
            position["quantity"] = actual
            self._save_state()
            changes.append(f"{coin}: harici alım algılandı (+{added:g}), pozisyon miktarı güncellendi")
            self._log(self.bot_id, changes[-1], "warning")
        return changes

    def _external_exit_price(self, usdt: float, local_qty: float, sold_qty: float) -> float:
        """Manuel satışta gerçekleşen fiyatı tahmin eder.

        Nakit artışı (borsadaki USDT − yerel nakit) satılan miktara bölünür;
        bu makul değilse canlı/mum fiyatına düşülür.
        """
        position = self.state.get("position") or {}
        local_cash = float(self.state.get("cash") or 0.0)
        proceeds = usdt - local_cash
        reference = float(position.get("last_price") or position.get("entry_price") or 0.0)
        if sold_qty > 0 and proceeds > 0:
            price = proceeds / sold_qty
            # Nakit değişimi (başka coin alımı, komisyon, transfer) fiyatı bozabilir:
            # referans fiyattan çok sapıyorsa gerçekleşen fiyat olarak kullanma.
            if price > 0 and (reference <= 0 or 0.5 <= price / reference <= 2.0):
                return price
        if reference > 0:
            return reference
        try:
            return float(self._data(str(position.get("coin") or ""))["close"][-1])
        except Exception:
            return 0.0

    def _apply_cooldown(self, pnl_pct: float) -> None:
        """Kapanış sonrası bekleme uygular.

        `cooldown_min_loss_pct` > 0 ise bekleme yalnızca zarar bu yüzdeye
        ulaştığında devreye girer; küçük/kârlı çıkışlarda bot hemen devam eder.
        """
        cooldown = int(self.risk.get("cooldown") or 0)
        if cooldown <= 0:
            return
        min_loss = float(self.risk.get("cooldown_min_loss_pct") or 0)
        if min_loss > 0 and pnl_pct > -min_loss:
            self._log(
                self.bot_id,
                f"Cooldown atlandı: K/Z {pnl_pct:+.2f}% (eşik -%{min_loss:g})",
                "debug",
            )
            return
        self.state["cooldown_until"] = int(self.state.get("candle_seq", 0)) + cooldown
        self._log(
            self.bot_id,
            f"Cooldown başladı: {cooldown} mum (K/Z {pnl_pct:+.2f}%)",
            "info",
        )

    def _close_manually(self, usdt: float, coin: str, local_qty: float) -> None:
        """Borsada elle satılmış pozisyonu yerel olarak kapatır (emir göndermez)."""
        position = self.state["position"]
        entry_price = float(position.get("entry_price") or 0)
        price = self._external_exit_price(usdt, local_qty, local_qty)
        pnl_pct = (price / entry_price - 1) * 100 if entry_price else 0.0
        fee_amount = local_qty * price * self.fee
        self.state["cash"] = round(usdt, 8)
        self.state["total_realized_pnl"] = round(
            float(self.state.get("total_realized_pnl", 0)) + (price - entry_price) * local_qty, 8
        )
        self._record_trade(coin, "SELL", local_qty, price, fee_amount, None, "manuel", pnl_pct)
        db.execute(
            "UPDATE positions SET closed_at=?, close_price=?, pnl_pct=?, status='closed' "
            "WHERE bot_id=? AND coin=? AND status='open'",
            (utcnow(), price, pnl_pct, self.bot_id, coin),
        )
        self.state["position"] = None
        self._apply_cooldown(pnl_pct)
        self._save_state()
        self._log(
            self.bot_id,
            f"MANUEL SATIŞ algılandı: {coin} borsada kalmamış · {local_qty:g} @ {price:.8f} · "
            f"K/Z {pnl_pct:+.2f}% · nakit {usdt:.2f} olarak güncellendi",
            "warning",
        )
        notifier.send(
            f"Manuel satış | {self.bot_name}",
            f"Bot: {self.bot_name}\n{coin} borsada elle satılmış.\nAdet: {local_qty:g}\nTahmini fiyat: {price:.8f}\n"
            f"K/Z: {pnl_pct:+.2f}%\nPozisyon kapatıldı, nakit {usdt:.2f} USDT.",
        )

    # ------------------------------------------------------------------
    # Giriş
    # ------------------------------------------------------------------
    def _scan_for_entry(self) -> None:
        # Mum sayacı: cooldown hesabı için her taramada artar.
        self.state["candle_seq"] = int(self.state.get("candle_seq", 0)) + 1
        if int(self.state.get("candle_seq", 0)) <= int(self.state.get("cooldown_until", -1)):
            self._log(self.bot_id, "Bekleme süresi (cooldown) aktif, giriş yok", "debug")
            return
        coinlist = self._coinlist()
        if not coinlist:
            return
        owned = self._owned_coins()
        candidates = [c for c in coinlist if c not in owned]
        if not candidates:
            return
        with ThreadPoolExecutor(max_workers=min(10, len(candidates))) as executor:
            futures = {executor.submit(self._check_coin, coin): coin for coin in candidates}
            for future in as_completed(futures):
                if self.stop_event or bot_state.stop_requested(self.bot_id):
                    return
                coin = futures[future]
                try:
                    hit = future.result()
                except Exception as exc:
                    self._log(self.bot_id, f"{coin} kontrol hatası: {exc}", "warning")
                    continue
                if hit:
                    self._open_position(coin, hit["data"], hit["evaluator"], hit["result"])
                    return
        self._log(self.bot_id, f"Tarama bitti: {len(candidates)} coin, alım sinyali yok", "debug")

    def _check_coin(self, coin: str) -> Optional[Dict[str, Any]]:
        data = self._data(coin)
        close = data.get("close") or []
        if len(close) < 60:
            return None
        try:
            if self.araclar and self.araclar.mum_sagligi(open=data["open"][-50:], close=close[-50:]) > 5:
                return None
        except Exception:
            pass
        for evaluator in self.evaluators:
            result = evaluator.evaluate(data)
            if not result.get("warmup_ok"):
                continue
            if result["buy"]:
                if not self._passes_filters(data):
                    continue
                self._record_signal(coin, evaluator, result, "BUY")
                return {"data": data, "evaluator": evaluator, "result": result}
            if result.get("buy_detail"):
                # Sadece açıklama için; DB'yi şişirmemek adına kaydetmiyoruz.
                pass
        return None

    def _passes_filters(self, data: Dict[str, List[float]]) -> bool:
        from core import Indikator

        close = data["close"]
        if self.filters.get("buy_ma_control"):
            ema = Indikator.EMA(close, 50)
            if ema[-1] is None or close[-1] <= ema[-1]:
                return False
        if self.filters.get("buy_bb_control"):
            _, mid, _ = Indikator.BB(close)
            if mid[-1] is None or close[-1] >= mid[-1]:
                return False
        return True

    # ------------------------------------------------------------------
    # Alım / Satım
    # ------------------------------------------------------------------
    def _open_position(self, coin: str, data, evaluator, result) -> None:
        close = data["close"]
        price = float(close[-1])
        atr_value = self._atr_value(data)
        # İşlemlerden öğrenme için giriş anındaki özellik fotoğrafı. AI stratejisi
        # zaten kendi detayında gönderir; diğer stratejiler için burada üretilir.
        try:
            detail = result.get("buy_detail")
            if isinstance(detail, dict) and not detail.get("features"):
                from app.ai.features import build_features

                feature = build_features(data)
                idx = max(0, len(feature["close"]) - 2)
                row = feature["frame"].iloc[idx]
                detail["features"] = {
                    str(k): (None if row[k] != row[k] else float(row[k]))
                    for k in feature["feature_names"]
                }
                detail["feature_index"] = idx
        except Exception as exc:  # noqa: BLE001 - öğrenme kaydı girişi engellemesin
            self._log(self.bot_id, f"AI giriş özellikleri alınamadı: {exc}", "debug")
        self._log(
            self.bot_id,
            f"ALIM sinyali: {coin} @ {price:.8f} ({self._evaluator_name(evaluator)})",
            "info",
        )
        size_pct = math.ceil(self.state["cash"] * self.max_position_pct * 100) / 100
        if self.mode == "live":
            self._open_live(coin, price, evaluator, result, atr_value)
        else:
            self._open_paper(coin, price, size_pct, evaluator, result, atr_value)

    def _atr_value(self, data) -> float:
        """Girişteki ATR(14): stop ve takipli stop seviyeleri buna göre ölçülür."""
        try:
            from app.strategies.registry import IndicatorCache

            vals = IndicatorCache(data).compute("ATR", {"length": 14}, "value")
            for v in reversed(vals):
                if v is not None and v == v and float(v) > 0:
                    return float(v)
        except Exception:
            pass
        return 0.0

    def _open_paper(self, coin, price, cash_available, evaluator, result, atr_value=0.0) -> None:
        exec_price = price * (1 + self.slippage)
        min_qty = 0.0
        try:
            min_qty = self.binance.get_coin_minQTY(coin) or 0.0
        except Exception:
            pass
        qty = _floor_step(cash_available / (exec_price * (1 + self.fee)), min_qty)
        if qty <= 0 or qty * exec_price < 5:
            return
        fee_amount = qty * exec_price * self.fee
        self.state["cash"] = round(self.state["cash"] - (qty * exec_price) - fee_amount, 8)
        self._set_position(coin, qty, exec_price, evaluator, result, atr=atr_value)
        self._record_trade(coin, "BUY", qty, exec_price, fee_amount, None, "sinyal")
        notifier.send(
            f"AL | {self.bot_name}",
            f"Bot: {self.bot_name}\n{coin} alındı\nAdet: {qty}\nFiyat: {exec_price:.8f}\nMod: paper",
        )

    def _open_live(self, coin, price, evaluator, result, atr_value=0.0) -> None:
        usdt = 0.0
        try:
            for item in self.binance.client.get_account()["balances"]:
                if item["asset"] == "USDT":
                    usdt = float(item["free"])
                    break
        except Exception as exc:
            self._log(self.bot_id, f"USDT bakiyesi okunamadı: {exc}", "error")
            return
        available = usdt * self.max_position_pct
        if available < 10:
            self._log(self.bot_id, "Yetersiz nakit", "warning")
            return
        min_qty = 0.0
        try:
            min_qty = self.binance.get_coin_minQTY(coin) or 0.0
        except Exception:
            pass
        qty = _floor_step(available / price, min_qty)
        if qty <= 0:
            return
        try:
            order = self.binance.market_buy(coin, qty)
        except Exception as exc:
            self._log(self.bot_id, f"Alım emri hatası {coin}: {exc}", "error")
            return
        executed = float(order.get("executedQty") or qty)
        quote = float(order.get("cummulativeQuoteQty") or (executed * price))
        avg = quote / executed if executed else price
        fee_amount = quote * self.fee
        self.state["cash"] = round(usdt - quote - fee_amount, 8)
        self._set_position(coin, executed, avg, evaluator, result, order_id=str(order.get("orderId")), atr=atr_value)
        self._record_trade(coin, "BUY", executed, avg, fee_amount, str(order.get("orderId")), "sinyal")
        notifier.send(
            f"AL | {self.bot_name}",
            f"Bot: {self.bot_name}\n{coin} alındı\nAdet: {executed}\nFiyat: {avg:.8f}\nMod: LIVE",
        )

    def _set_position(self, coin, qty, price, evaluator, result, order_id=None, atr=0.0) -> None:
        self.state["position"] = {
            "coin": coin,
            "quantity": qty,
            "entry_price": price,
            "highest_price": price,
            "last_price": price,
            "last_price_at": utcnow(),
            "unrealized_pnl": 0.0,
            "unrealized_pnl_pct": 0.0,
            "stop_price": None,
            "atr": float(atr or 0.0),
            "destek": None,
            "direnc": None,
            "opened_at": utcnow(),
            "candles": 0,
            "durum_list": [],
            "strategy_id": evaluator.id,
            "strategy_version": evaluator.version,
            "entry_signal": result.get("buy_detail"),
        }
        self.state["trade_count"] = int(self.state.get("trade_count", 0)) + 1
        self._save_state()
        db.execute(
            "INSERT INTO positions(bot_id,coin,quantity,entry_price,highest_price,opened_at,status) "
            "VALUES(?,?,?,?,?,?, 'open')",
            (self.bot_id, coin, qty, price, price, utcnow()),
        )

    def _record_trade(self, coin, side, qty, price, fee, order_id, reason, pnl_pct=None) -> None:
        db.execute(
            "INSERT INTO trades(bot_id,run_id,coin,side,quantity,price,fee,order_id,mode,reason,pnl_pct,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.bot_id, self.run_id, coin, side, qty, price, fee, order_id, self.mode, reason, pnl_pct, utcnow()),
        )

    def _close_position(self, price, reason, fee_override=None) -> None:
        position = self.state.get("position")
        if not position:
            return
        coin = position["coin"]
        qty = float(position["quantity"])
        entry = float(position["entry_price"])
        if self.mode == "live":
            try:
                free = self.binance.mevcut_adedim(coin) or qty
                min_qty = 0.0
                try:
                    min_qty = self.binance.get_coin_minQTY(coin) or 0.0
                except Exception:
                    pass
                qty = _floor_step(min(free, qty) if free else qty, min_qty)
                order = self.binance.market_sell(coin, qty)
                executed = float(order.get("executedQty") or qty)
                quote = float(order.get("cummulativeQuoteQty") or (executed * price))
                avg = quote / executed if executed else price
                fee_amount = quote * self.fee
                self.state["cash"] = round(float(self.state["cash"]) + quote - fee_amount, 8)
                self._record_trade(coin, "SELL", executed, avg, fee_amount, str(order.get("orderId")), reason, (avg / entry - 1) * 100)
                qty, price = executed, avg
            except Exception as exc:
                self._log(self.bot_id, f"Satış emri hatası {coin}: {exc}", "error")
                return
        else:
            exec_price = price * (1 - self.slippage)
            fee_amount = qty * exec_price * self.fee
            self.state["cash"] = round(float(self.state["cash"]) + (qty * exec_price) - fee_amount, 8)
            self._record_trade(coin, "SELL", qty, exec_price, fee_amount, None, reason, (exec_price / entry - 1) * 100)
            price = exec_price

        pnl_pct = (price / entry - 1) * 100
        # Kapanan her bot işlemi "deneyim" olarak saklanır (özellik fotoğrafıyla).
        # AI eğitimi bu kayıtları sınırlı ağırlıkla kullanabilir.
        try:
            entry_signal = position.get("entry_signal") or {}
            if isinstance(entry_signal, dict) and entry_signal.get("features"):
                from app.ai.artifacts import record_experience

                record_experience(
                    {
                        "model_id": entry_signal.get("model_id") or position.get("strategy_id"),
                        "bot_id": self.bot_id,
                        "coin": coin,
                        "period": self.period,
                        "side": "BUY",
                        "features": entry_signal.get("features") or {},
                        "entry_price": entry,
                        "exit_price": price,
                        "pnl_pct": pnl_pct,
                        "candles": int(position.get("candles") or 0),
                        "reason": reason,
                        "mode": self.mode,
                    }
                )
        except Exception as exc:  # noqa: BLE001 - öğrenme kaydı botu durdurmamalı
            self._log(self.bot_id, f"AI deneyim kaydı yazılamadı: {exc}", "debug")
        self.state["total_realized_pnl"] = round(
            float(self.state.get("total_realized_pnl", 0)) + (price - entry) * qty, 8
        )
        db.execute(
            "UPDATE positions SET closed_at=?, close_price=?, pnl_pct=?, status='closed' "
            "WHERE bot_id=? AND coin=? AND status='open'",
            (utcnow(), price, pnl_pct, self.bot_id, coin),
        )
        self.state["position"] = None
        # Stop/kâr sonrası hemen yeniden girişi engelle (komisyon erozyonu).
        self._apply_cooldown(pnl_pct)
        self._save_state()
        self._log(
            self.bot_id,
            f"SAT {coin} | {reason} | {qty} @ {price:.8f} | K/Z {pnl_pct:.2f}%",
            "info",
        )
        notifier.send(
            f"SAT | {self.bot_name}",
            f"Bot: {self.bot_name}\n{coin} satıldı\nAdet: {qty}\nFiyat: {price:.8f}\nK/Z: {pnl_pct:.2f}%\nNeden: {reason}",
        )

    # ------------------------------------------------------------------
    # Pozisyon yönetimi
    # ------------------------------------------------------------------
    def _manage_position(self) -> None:
        from core import Stratejiler

        position = self.state["position"]
        coin = position["coin"]
        data = self._data(coin)
        close = data["close"]
        high = data["high"]
        low = data["low"]
        price = float(close[-1])

        # Takipli stop pozisyonun mum zirvesinden ölçülür (backtest ile aynı: high).
        peak = max(price, float(high[-1]))
        if peak > float(position.get("highest_price") or 0):
            position["highest_price"] = peak

        evaluator = self._evaluator_for(position)
        result = evaluator.evaluate(data)
        self._record_signal(coin, evaluator, result, "SELL" if result.get("sell") else "HOLD", price)

        sells: List[str] = []

        # --- ATR stop / takipli stop (backtest ile aynı kurallar) ---
        entry = float(position["entry_price"])
        highest = float(position.get("highest_price") or entry)
        atr_base = float(position.get("atr") or 0.0)
        stop_price = None
        if atr_base <= 0:
            atr_base = self._atr_value(data)
            position["atr"] = atr_base
        if atr_base > 0:
            stop_atr = float(self.risk.get("stop_atr") or 0)
            trail_atr = float(self.risk.get("trail_atr") or 0)
            trail_after = float(self.risk.get("trail_after_pct") or 0)
            stop_price = entry - stop_atr * atr_base if stop_atr > 0 else None
            # Üst sınır: stop, girişten en fazla `max_stop_pct` kadar aşağıda olabilir
            # (yüksek volatiliteli coinlerde 35×ATR işlevsiz kalıyor).
            max_stop_pct = float(self.risk.get("max_stop_pct") or 0)
            if stop_price is not None and max_stop_pct > 0:
                stop_price = max(stop_price, entry * (1 - max_stop_pct / 100))
            armed = True
            if trail_atr > 0 and trail_after > 0:
                armed = highest >= entry * (1 + trail_after / 100)
            if trail_atr > 0 and armed:
                trail = highest - trail_atr * atr_base
                stop_price = trail if stop_price is None else max(stop_price, trail)
            if stop_price is not None and float(low[-1]) <= stop_price:
                sells.append("takipli-stop" if (trail_atr > 0 and armed and
                                                 (stop_atr <= 0 or trail >= entry - stop_atr * atr_base))
                             else "stop")

        if result.get("sell"):
            sells.append("sinyal")

        # Kâr koruma: kârdayken kısa vadeli yapı kırılırsa çık (hızlı çıkış).
        profit_don = int(self.risk.get("profit_exit_donchian") or 0)
        if profit_don > 0 and price > entry and len(close) >= profit_don + 3:
            try:
                from app.strategies.registry import IndicatorCache

                lower = IndicatorCache(data).compute("DONCHIAN", {"length": profit_don}, "lower")
                if (
                    lower[-2] is not None and lower[-3] is not None
                    and float(close[-1]) < float(lower[-2])
                    and float(close[-2]) >= float(lower[-3])
                ):
                    sells.append("kâr-koruma")
            except Exception as exc:
                self._log(self.bot_id, f"Kâr koruma hatası: {exc}", "warning")

        if self.risk.get("support_stop"):
            try:
                destek, direnc, stop = Stratejiler.destek_stop_lose(
                    position["entry_price"], position.get("destek"), position.get("direnc"), close, low
                )
                if stop == "STOP-LOSE":
                    sells.append("destek-stop")
                else:
                    position["destek"] = destek
                    position["direnc"] = direnc
            except Exception as exc:
                self._log(self.bot_id, f"Destek stop hatası: {exc}", "warning")

        if self.risk.get("dynamic_stop"):
            try:
                check, highest, stop_level = Stratejiler.dinamik_stop_lose(
                    high, low, close, position.get("highest_price")
                )
                position["highest_price"] = highest or position.get("highest_price")
                if check == "STOP-LOSE":
                    sells.append("dinamik-stop")
            except Exception as exc:
                self._log(self.bot_id, f"Dinamik stop hatası: {exc}", "warning")

        if self.risk.get("static_stop"):
            try:
                if Stratejiler.static_stop_lose(close, position["entry_price"]) == "STOP-LOSE":
                    sells.append("statik-stop")
            except Exception as exc:
                self._log(self.bot_id, f"Statik stop hatası: {exc}", "warning")

        if self.risk.get("take_profit"):
            try:
                pnl = (price / position["entry_price"] - 1) * 100
                if pnl > 5:
                    position.setdefault("durum_list", []).append(pnl)
                ort, signal = Stratejiler.take_profit(position.get("durum_list") or [])
                if signal == "TAKE-PROFIT":
                    sells.append("take-profit")
            except Exception as exc:
                self._log(self.bot_id, f"Take profit hatası: {exc}", "warning")

        position["candles"] = int(position.get("candles", 0)) + 1
        # Anlık durum: son fiyat, gerçekleşmemiş K/Z ve aktif stop seviyesi.
        qty_now = float(position.get("quantity") or 0)
        position["last_price"] = price
        position["last_price_at"] = utcnow()
        position["unrealized_pnl"] = round((price - entry) * qty_now, 4)
        position["unrealized_pnl_pct"] = round((price / entry - 1) * 100, 2) if entry else 0.0
        if stop_price is not None:
            position["stop_price"] = round(float(stop_price), 8)
        # Zaman limiti kaldırıldı: pozisyon yalnızca sinyal veya stop ile kapanır.
        self._save_state()

        if sells:
            self._close_position(price, sells[0])
        else:
            pnl = (price / float(position["entry_price"]) - 1) * 100
            self._log(
                self.bot_id,
                f"{coin} izleniyor | {price:.8f} | K/Z {pnl:+.2f}% | mum {position['candles']}",
                "debug",
            )

    def _evaluator_for(self, position) -> Any:
        for evaluator in self.evaluators:
            if evaluator.id == position.get("strategy_id"):
                return evaluator
        return self.evaluators[0]

    def _record_signal(self, coin, evaluator, result, decision, price=None) -> None:
        db.execute(
            "INSERT INTO signal_events(bot_id,strategy_id,version,coin,period,candle_time,decision,conditions_json,values_json,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                self.bot_id,
                evaluator.id,
                evaluator.version,
                coin,
                self.period,
                str(result.get("candle_time")),
                decision,
                db.json.dumps(result.get("buy_detail") or result.get("sell_detail"), ensure_ascii=False, default=str),
                db.json.dumps(
                    {
                        "buy": result.get("buy"),
                        "sell": result.get("sell"),
                        "warmup_ok": result.get("warmup_ok"),
                    },
                    ensure_ascii=False,
                ),
                utcnow(),
            ),
        )
        # pnl snapshot (yaklaşık her sinyalde)
        try:
            position = self.state.get("position")
            if position and position.get("coin") == coin:
                mark = float(price or position["entry_price"])
                total = float(self.state["cash"]) + float(position["quantity"]) * mark
            else:
                total = float(self.state["cash"])
            db.execute(
                "INSERT INTO pnl_snapshots(bot_id,total_value,cash,pnl,created_at) VALUES(?,?,?,?,?)",
                (
                    self.bot_id,
                    total,
                    float(self.state["cash"]),
                    total - float(self.state.get("initial_cash", total)),
                    utcnow(),
                ),
            )
        except Exception:
            pass
