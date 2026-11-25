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

from app import db, bot_state, account_lock, exchange
from app import live_prices
from app.config import settings
from app.notifications import notifier
from app.strategies.service import build_evaluator, normalize_specs

INTERVAL_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "45m": 2700,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "3d": 259200,
    "1w": 604800,
    "1M": 2592000,
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
        self.asset_class = str(config.get("asset_class") or "")
        self.max_position_pct = float(config.get("max_position_pct", 100)) / 100.0
        self.adopt_external_buy = bool(settings.ADOPT_EXTERNAL_BUY)
        self.protective_enabled = bool(settings.EXCHANGE_PROTECTIVE_STOP)
        self.stop_event = False
        self.run_id: Optional[int] = None
        self.binance = None
        self.araclar = None
        self._last_reconcile = 0.0
        self._reconcile_signature = ""
        self._protective_error = ""
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
            "pending_exit": None,
        }

    def _load_state(self) -> Dict[str, Any]:
        existing = bot_state.load_state(self.bot_id)
        if existing:
            existing["mode"] = self.mode
            existing["period"] = self.period
            existing.setdefault("pending_exit", None)
            existing.setdefault("exit_reasons", {})
            return existing
        return self._default_state()

    def _save_state(self) -> None:
        # Kuruş yuvarlaması nakdi eksiye düşürebiliyordu; anlamlı bir borç
        # değilse sıfıra sabitle (kartta eksi nakit görünmesin).
        try:
            cash = float(self.state.get("cash") or 0)
        except (TypeError, ValueError):
            cash = 0.0
        if -1.0 < cash < 0.0:
            self.state["cash"] = 0.0
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
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{stamp}] {level.upper():7s} {message}", flush=True)

    # ------------------------------------------------------------------
    # Başlangıç
    # ------------------------------------------------------------------
    def _is_binance_symbol(self, coin: str) -> bool:
        try:
            from app.market_data import resolve_symbol

            return resolve_symbol(coin).provider == "binance"
        except Exception:  # noqa: BLE001 - çözülemeyen sembol Binance'e bırakılır
            return True

    def _needs_binance(self) -> bool:
        if self.mode == "live":
            return True
        if not self.coins:
            # Evren boşsa varsayılan Binance coin listesi taranır.
            return True
        return any(self._is_binance_symbol(coin) for coin in self.coins)

    def _init_clients(self) -> None:
        if self.binance is None and self._needs_binance():
            from core import Binance

            while True:
                try:
                    self.binance = Binance()
                    break
                except Exception as exc:
                    if self.stop_event or bot_state.stop_requested(self.bot_id):
                        raise
                    # Kalıcı hata (geçersiz anahtar, yetki yok) sonsuz denenmez:
                    # bot "çalışıyor" görünüp saatlerce boş dönmesin.
                    if exchange.is_permanent(exc):
                        text = (
                            f"Binance bağlantısı kurulamadı (kalıcı hata): {exc}. "
                            "API anahtarlarını ve işlem izinlerini kontrol edin."
                        )
                        self._log(self.bot_id, text, "error")
                        try:
                            notifier.send(f"Bot Başlatılamadı | {self.bot_name}", text)
                        except Exception:  # noqa: BLE001
                            pass
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

    def _reconcile_live(self, notify: bool = True) -> List[str]:
        """Canlı modda yerel state ile Binance bakiyesini karşılaştırır.

        Ham hesap bakiyeleri kullanılır (``sahip_olduklarim`` her varlık için
        ayrı fiyat çektiğinden periyodik kontrolde rate limit'e takılırdı).
        """
        issues: List[str] = []
        balances = None
        # Geçici ağ hatasında botu durdurmak yerine birkaç kez denenir.
        for attempt in range(3):
            balances = self._account_balances()
            if balances is not None:
                break
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
        if balances is None:
            message = "Mutabakat yapılamadı: borsa bakiyesi okunamadı (3 deneme)"
            self._log(self.bot_id, message, "warning")
            if notify:
                try:
                    notifier.send(f"Mutabakat Uyarısı | {self.bot_name}", message)
                except Exception:  # noqa: BLE001
                    pass
            return []
        usdt = float((balances.get("USDT") or {}).get("free", 0.0))

        tolerance = max(0.1, float(settings.RECONCILE_TOLERANCE_PCT)) / 100.0
        position = self.state.get("position")
        if position:
            asset = exchange.asset_of(position["coin"])
            entry = balances.get(asset) or {"free": 0.0, "locked": 0.0}
            actual = float(entry.get("free", 0.0)) + float(entry.get("locked", 0.0))
            local = float(position["quantity"])
            if local > 0 and abs(actual - local) / local > tolerance:
                issues.append(
                    f"{position['coin']} miktar uyuşmazlığı: yerel={local}, borsa={actual}"
                )
        # Hesap paylaşılıyorsa (birden fazla bot) toplam USDT botun kendi
        # nakdiyle eşleşmez; nakit karşılaştırması yapılmaz.
        if not settings.SHARED_ACCOUNT:
            if self.state.get("cash") and abs(usdt - float(self.state["cash"])) / max(usdt, 1) > tolerance:
                issues.append(
                    f"USDT uyuşmazlığı: yerel={self.state['cash']:.2f}, borsa={usdt:.2f}"
                )
        if issues:
            signature = "|".join(sorted(issues))
            if notify and signature != self._reconcile_signature:
                self._reconcile_signature = signature
                for issue in issues:
                    self._log(self.bot_id, f"Mutabakat uyarısı: {issue}", "warning")
                try:
                    notifier.send(
                        f"Mutabakat Uyarısı | {self.bot_name}", "\n".join(issues)
                    )
                except Exception:  # noqa: BLE001
                    pass
        else:
            self._reconcile_signature = ""
        return issues

    def _warn_shared_account(self) -> None:
        """Aynı Binance hesabını kullanan başka canlı bot varsa uyar."""
        try:
            rows = db.rows(
                "SELECT id, name FROM bots WHERE id<>? AND mode='live' "
                "AND status IN ('running','stopping')",
                (self.bot_id,),
            )
        except Exception:  # noqa: BLE001 - DB okunamazsa işlem engellenmez
            return
        if not rows:
            return
        names = ", ".join(str(r.get("name") or r.get("id")) for r in rows[:6])
        text = (
            f"Aynı Binance hesabında {len(rows)} canlı bot daha çalışıyor: {names}. "
            "Emirler sırayla gönderilir ve her bot kendi nakit kaydını kullanır; "
            "yine de bakiye paylaşımını Ayarlar > İşlem'den işaretleyin."
        )
        self._log(self.bot_id, text, "warning")
        try:
            notifier.send(f"Hesap Paylaşımı | {self.bot_name}", text)
        except Exception:  # noqa: BLE001
            pass

    def _reconcile_periodic(self) -> None:
        """Çalışırken borsayla periyodik karşılaştırma (nakit kayması birikmesin)."""
        if self.mode != "live":
            return
        interval = int(settings.RECONCILE_SECONDS or 0)
        if interval <= 0:
            return
        now = time.time()
        if now - self._last_reconcile < interval:
            return
        self._last_reconcile = now
        issues = self._reconcile_live(notify=True)
        if issues and settings.RECONCILE_STOP_ON_MISMATCH:
            self.state["reconciliation_required"] = True
            self._safe_save_state()
            self._log(
                self.bot_id,
                "Mutabakat farkı toleransı aştı; bot durduruluyor (reconciliation_required).",
                "error",
            )
            bot_state.request_stop(self.bot_id)
            try:
                notifier.send(
                    f"Bot Durduruldu | {self.bot_name}",
                    "Borsa ile yerel kayıt uyuşmuyor:\n" + "\n".join(issues),
                )
            except Exception:  # noqa: BLE001
                pass

    def run(self) -> None:
        # Önce durumu yaz: web arayüzü bot daha Binance'e bağlanmadan durum görsün.
        # Yeni bir çalıştırma başladığında önceki çöküntünün hatası temizlenir.
        self.state["last_error"] = None
        self.state["reconciliation_required"] = False
        self._save_state()
        self.heartbeat()
        try:
            self._init_clients()
        except Exception as exc:
            self.state["last_error"] = traceback.format_exc()
            self._safe_save_state()
            raise
        self._start_run()
        if self.mode == "live":
            self._warn_shared_account()
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
            kind="start",
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
        # Panelden gelen manuel satış isteği her şeyden önce uygulanır.
        if self._handle_sell_request():
            return
        # Önceki turda başarısız olan çıkış kararı varsa tekrar denenir
        # (mum kapanışı beklenmez; karar kalıcıdır).
        if self._process_pending_exit():
            return
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
                    transient = exchange.is_transient(exc)
                    if not transient:
                        break
                    self._log(
                        self.bot_id,
                        f"Geçici hata (deneme {attempt + 1}/3), kısa bekleyip tekrar deniyorum: {text[:120]}",
                        "warning",
                    )
                    time.sleep(5 * (attempt + 1))
            if last is not None:
                trace = traceback.format_exc()
                self.state["last_error"] = trace
                try:
                    self._save_state()
                except Exception:  # noqa: BLE001
                    pass
                self._log(self.bot_id, f"Döngü hatası: {last}", "error")
                # Aynı hata her mumda tekrarlarsa bildirim spam'i olmasın.
                signature = f"{type(last).__name__}|{str(last)[:160]}"
                previous = self.state.get("loop_error") or {}
                if (
                    previous.get("signature") != signature
                    or time.time() - float(previous.get("at") or 0) > 1800
                ):
                    self.state["loop_error"] = {"signature": signature, "at": time.time()}
                    try:
                        notifier.send(f"Bot Hatası | {self.bot_name}", str(last))
                    except Exception:  # noqa: BLE001
                        pass
                time.sleep(5)
            else:
                self.state["last_error"] = None
                self.state["loop_error"] = None
            self._wait_for_candle()

    def _last_price(self, coin: str) -> float:
        """Son bilinen fiyat: canlı fiyat → mum kapanışı → pozisyon fiyatı."""
        try:
            live = live_prices.prices([coin]).get(coin)
            if live:
                return float(live)
        except Exception:  # noqa: BLE001 - fiyat servisi geçici olarak kapalı olabilir
            pass
        position = self.state.get("position") or {}
        try:
            data = self._data(coin)
            return float(data["close"][-1])
        except Exception:  # noqa: BLE001
            return float(position.get("last_price") or position.get("entry_price") or 0)

    def _handle_sell_request(self) -> bool:
        """Panelden istenen manuel satışı uygular.

        İstek dosyası **yalnızca satış başarılı olunca** silinir. Emir reddedilirse
        ``pending_exit`` kalır ve birkaç saniye içinde yeniden denenir; böylece
        kullanıcı tekrar "sat" demek zorunda kalmaz.

        Döndürür: istek işlendi mi (döngüde pozisyon yönetimini atlamak için).
        """
        request = bot_state.sell_requested(self.bot_id)
        if request is None:
            return False
        position = self.state.get("position")
        if not position:
            self._log(
                self.bot_id,
                "Manuel satış isteği alındı ama açık pozisyon yok",
                "warning",
            )
            bot_state.clear_sell(self.bot_id)
            return False
        if not self.state.get("pending_exit"):
            coin = str(position.get("coin") or "")
            price = float(request.get("price") or 0)
            if price <= 0:
                price = self._last_price(coin)
            self._log(
                self.bot_id,
                f"Manuel satış isteği alındı: {coin} @ {price:.8f}",
                "info",
            )
            self._request_exit("manuel", price)
        else:
            # Kullanıcı açıkça satış istedi: bekleyen çıkışın nedeni "manuel" olur.
            pending = self.state["pending_exit"]
            if isinstance(pending, dict) and pending.get("reason") != "manuel":
                pending["reason"] = "manuel"
                self._safe_save_state()
        handled = self._process_pending_exit()
        if not self.state.get("pending_exit"):
            bot_state.clear_sell(self.bot_id)
        return handled

    # ------------------------------------------------------------------
    # Kalıcı çıkış (satılamadıysa tekrar dene)
    # ------------------------------------------------------------------
    def _request_exit(self, reason: str, price: Optional[float] = None) -> None:
        """Çıkış kararını **emirden önce** diske yazar.

        Bot süreci çökse veya emir reddedilse bile karar kaybolmaz; ``_wait_for_candle``
        döngüsü ve sonraki turlar bunu tekrar dener. Aynı nedenle gelen tekrar
        çağrılar deneme sayacını sıfırlamaz (bildirim tekrarı olmasın).
        """
        reason = reason or "signal"
        existing = self.state.get("pending_exit")
        if isinstance(existing, dict) and existing.get("reason") == reason:
            # Fiyat bilgisi tazelenir; sayaç ve bildirim durumu korunur.
            if price:
                existing["price"] = float(price)
            self._safe_save_state()
            return
        self.state["pending_exit"] = {
            "reason": reason,
            "price": float(price) if price else None,
            "created_at": utcnow(),
            "attempts": 0,
            "last_attempt": 0.0,
            "notified": False,
        }
        self._safe_save_state()

    def _clear_pending_exit(self) -> None:
        if self.state.get("pending_exit") is not None:
            self.state["pending_exit"] = None
            self._safe_save_state()

    def _process_pending_exit(self) -> bool:
        """Bekleyen çıkışı (varsa) dener.

        Döndürür: bekleyen çıkış var mı (başarılı, bekliyor veya başarısız).
        """
        pending = self.state.get("pending_exit")
        if not pending:
            return False
        position = self.state.get("position")
        if not position:
            self._clear_pending_exit()
            return False
        if not isinstance(pending, dict):
            self._clear_pending_exit()
            return False

        now = time.time()
        attempts = int(pending.get("attempts") or 0)
        retry_after = max(2, int(settings.EXIT_RETRY_SECONDS or 5))
        last_attempt = float(pending.get("last_attempt") or 0.0)
        if attempts > 0 and now - last_attempt < retry_after:
            return True

        coin = str(position.get("coin") or "")
        price = float(pending.get("price") or 0)
        if price <= 0:
            price = self._last_price(coin)
        elif attempts > 0 and self.mode != "live":
            # Paper modda tekrar deneme dakikalar sonra olabilir; eski seviye
            # fiyatıyla satmak sonucu bozar. Güncel fiyat kullanılır.
            fresh = float(self._last_price(coin) or 0.0)
            if fresh > 0:
                price = fresh
        pending["attempts"] = attempts + 1
        pending["last_attempt"] = now
        pending["price"] = float(price)
        self.state["pending_exit"] = pending
        self._safe_save_state()

        ok = self._close_position(price, str(pending.get("reason") or "signal"))
        if ok:
            self._clear_pending_exit()
            bot_state.clear_sell(self.bot_id)
            return True

        pending = self.state.get("pending_exit") or pending
        attempts = int(pending.get("attempts") or 0)
        # 3. denemeden sonra kullanıcıya haber ver; her 20 denemede bir hatırlat.
        if attempts >= 3 and (not pending.get("notified") or attempts % 20 == 0):
            pending["notified"] = True
            self.state["pending_exit"] = pending
            self._safe_save_state()
            try:
                notifier.send(
                    f"Satış Yapılamadı | {self.bot_name}",
                    f"Bot: {self.bot_name}\n{coin} satılamadı ({pending.get('reason')}).\n"
                    f"Deneme: {attempts}\nSon hata: {self.state.get('last_error') or 'emir reddedildi'}\n"
                    "Karar kaydedildi; bot birkaç saniyede bir yeniden deniyor.",
                    kind="sell",
                )
            except Exception:  # noqa: BLE001
                pass
        return True

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
            # Mum bekleme sırasında da panelden gelen manuel satışı uygula.
            try:
                if not self._handle_sell_request():
                    self._process_pending_exit()
            except Exception as exc:  # noqa: BLE001
                self._log(self.bot_id, f"Satış tekrar denemesi hatası: {exc}", "error")
            # Mum bekleme sırasında da elle satışı yakala (yaklaşık 30 saniyede bir).
            if self.mode == "live" and self.state.get("position"):
                if time.time() - last_sync >= 30:
                    last_sync = time.time()
                    try:
                        self._sync_live_position()
                    except Exception as exc:  # noqa: BLE001
                        self._log(self.bot_id, f"Manuel satış kontrolü hatası: {exc}", "warning")
            try:
                self._reconcile_periodic()
            except Exception as exc:  # noqa: BLE001
                self._log(self.bot_id, f"Periyodik mutabakat hatası: {exc}", "warning")
            time.sleep(min(5, max(1, next_close - time.time())))

    # ------------------------------------------------------------------
    # Veri
    # ------------------------------------------------------------------
    def _data(self, coin: str) -> Dict[str, List[float]]:
        """Mum verisi. Borsa geçici hata verirse (5xx / bağlantı / 429) kısa
        bekleyip yeniden dener; kalıcı hatada (geçersiz sembol) hemen çıkar.

        Kripto dışı semboller (hisse, altın/gümüş, döviz, TEFAS) ortak
        ``app.market_data`` katmanından okunur; paper botlar için Binance
        bağlantısı gerekmez.
        """
        if not self._is_binance_symbol(coin):
            from app.market_data import load_history

            data, _meta = load_history(
                coin, self.period, 1000, asset_class=self.asset_class
            )
            return data
        last: Optional[Exception] = None
        for attempt in range(4):
            if self.stop_event or bot_state.stop_requested(self.bot_id):
                break
            try:
                return self.binance.get_coin_data(coin, self.period, 1000)
            except Exception as exc:  # noqa: BLE001 - borsa/ağ hatası
                last = exc
                text = str(exc)
                if not exchange.is_transient(exc):
                    break
                self._log(
                    self.bot_id,
                    f"{coin} veri alınamadı (deneme {attempt + 1}/4): {text[:120]}",
                    "warning",
                )
                time.sleep(min(15, exchange.retry_delay(exc, attempt)))
        if last:
            raise last
        raise RuntimeError("Veri alınamadı")

    def _coinlist(self) -> List[str]:
        if self.coins:
            return list(self.coins)
        if self.binance is None:
            return []
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

    def _protective_fill(self, coin: str) -> Optional[tuple]:
        """Borsadaki koruyucu emir gerçekleştiyse ``(fiyat, neden)`` döndürür.

        OCO kullanılıyorsa iki bacak da kontrol edilir: stop bacağı ``stop``,
        kâr al bacağı ``take-profit`` olarak kaydedilir.
        """
        position = self.state.get("position") or {}
        legs = (
            (position.get("protective_order_id"), "stop"),
            (position.get("protective_tp_order_id"), "take-profit"),
        )
        for order_id, reason in legs:
            if not order_id:
                continue
            try:
                order = self.binance.client.get_order(symbol=coin, orderId=int(order_id))
            except Exception:
                continue
            status = str((order or {}).get("status") or "").upper()
            if status not in {"FILLED", "PARTIALLY_FILLED"}:
                continue
            executed = exchange.order_quantity(order)
            quote = exchange.order_quote(order)
            if executed > 0 and quote > 0:
                return (quote / executed, reason)
        return None

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
            # Koruyucu emir tetiklendiyse kapanış nedeni ona göre kaydedilir;
            # aksi halde kullanıcı elle satmış sayılır.
            fill = self._protective_fill(coin)
            if fill:
                price, reason = fill
                self._close_manually(usdt, coin, local, reason=reason, price_override=price)
                label = "kâr al" if reason == "take-profit" else "stop"
                return [f"{coin}: borsadaki koruyucu {label} emri gerçekleşti, pozisyon kapatıldı"]
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
            # Borsadaki koruyucu emir eski miktarı kilitliyor; kalan miktarla
            # yeniden kurulur.
            if position.get("protective_stop"):
                try:
                    self._sync_protective(
                        coin, actual, float(position["protective_stop"]),
                        position.get("protective_tp"),
                    )
                except Exception as exc:  # noqa: BLE001
                    self._log(
                        self.bot_id,
                        f"Kısmi manuel satış sonrası koruyucu emir güncellenemedi {coin}: {exc}",
                        "warning",
                    )
            notifier.send(
                f"Kısmi manuel satış | {self.bot_name}",
                f"Bot: {self.bot_name}\n{coin}\nSatılan: {sold:g}\nKalan: {actual:g}\nFiyat: {price:.8f}",
                kind="sell",
            )
            return changes
        if actual > local * 1.02:
            added = actual - local
            if not self.adopt_external_buy:
                message = (
                    f"{coin}: harici alım algılandı (+{added:g}). "
                    "Pozisyon değiştirilmedi (Ayarlar > İşlem > Harici alımları benimse kapalı)."
                )
                self._log(self.bot_id, message, "warning")
                if not self.state.get("external_buy_warned"):
                    self.state["external_buy_warned"] = True
                    self._safe_save_state()
                    try:
                        notifier.send(f"Harici Alım | {self.bot_name}", message)
                    except Exception:  # noqa: BLE001
                        pass
                return changes
            position["quantity"] = actual
            self.state["external_buy_warned"] = False
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

    def _close_manually(
        self,
        usdt: float,
        coin: str,
        local_qty: float,
        reason: str = "manuel",
        price_override: Optional[float] = None,
    ) -> None:
        """Borsada elle satılmış (veya koruyucu stop tetiklenmiş) pozisyonu kapatır."""
        position = self.state["position"]
        self._cancel_protective(coin)
        entry_price = float(position.get("entry_price") or 0)
        price = float(price_override or 0) or self._external_exit_price(usdt, local_qty, local_qty)
        labels = {
            "stop": "STOP (borsa)",
            "take-profit": "KÂR AL (borsa)",
            "takipli-stop": "TAKİPLİ STOP (borsa)",
            "breakeven": "BREAKEVEN (borsa)",
        }
        label = labels.get(reason, "MANUEL SATIŞ")
        pnl_pct = (price / entry_price - 1) * 100 if entry_price else 0.0
        fee_amount = local_qty * price * self.fee
        self.state["cash"] = round(usdt, 8)
        self.state["total_realized_pnl"] = round(
            float(self.state.get("total_realized_pnl", 0)) + (price - entry_price) * local_qty, 8
        )
        self._record_trade(coin, "SELL", local_qty, price, fee_amount, None, reason, pnl_pct)
        db.execute(
            "UPDATE positions SET closed_at=?, close_price=?, pnl_pct=?, status='closed' "
            "WHERE bot_id=? AND coin=? AND status='open'",
            (utcnow(), price, pnl_pct, self.bot_id, coin),
        )
        self.state["position"] = None
        self.state["pending_exit"] = None
        # Çıkış nedeni dağılımı (panelde gösterilir).
        counters = self.state.setdefault("exit_reasons", {})
        counters[reason or "manuel"] = int(counters.get(reason or "manuel", 0)) + 1
        self._apply_cooldown(pnl_pct)
        self._save_state()
        self._log(
            self.bot_id,
            f"{label} algılandı: {coin} borsada kalmamış · {local_qty:g} @ {price:.8f} · "
            f"K/Z {pnl_pct:+.2f}% · nakit {usdt:.2f} olarak güncellendi",
            "warning",
        )
        notifier.send(
            f"{label.title()} | {self.bot_name}",
            f"Bot: {self.bot_name}\n{coin} borsada kapatılmış.\nAdet: {local_qty:g}\n"
            f"Fiyat: {price:.8f}\nK/Z: {pnl_pct:+.2f}%\n"
            f"Pozisyon kapatıldı, nakit {usdt:.2f} USDT.",
            kind="sell",
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
                    return        self._log(self.bot_id, f"Tarama bitti: {len(candidates)} coin, alım sinyali yok", "debug")

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
    # Emir yardımcıları
    # ------------------------------------------------------------------
    def _filters(self, coin: str) -> Dict[str, Any]:
        """Parite filtreleri; borsa okunamazsa güvenli varsayılan."""
        min_qty = 0.0
        if self.binance is not None:
            try:
                filters = self.binance.get_coin_filters(coin)
                if isinstance(filters, dict) and filters:
                    return filters
            except Exception:
                pass
            try:
                min_qty = float(self.binance.get_coin_minQTY(coin) or 0.0)
            except Exception:
                pass
        return {
            "symbol": str(coin or "").upper(),
            "step_size": min_qty,
            "min_qty": min_qty,
            "max_qty": None,
            "market_max_qty": None,
            "min_notional": exchange.DEFAULT_MIN_NOTIONAL,
            "tick_size": 0.0,
            "found": False,
        }

    def _find_order(self, coin: str, client_id: str) -> Optional[Dict[str, Any]]:
        """Zaman aşımı sonrası: emir gerçekleşti mi?"""
        try:
            order = self.binance.order_status(coin, client_id)
            return order if isinstance(order, dict) else None
        except Exception:
            return None

    def _submit_order(
        self,
        side: str,
        coin: str,
        qty: Optional[float] = None,
        quote_qty: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Piyasa emrini dayanıklı gönderir.

        - Aynı ``clientOrderId`` ile en fazla 3 deneme. Zaman aşımından sonra
          tekrar gönderim çift emir oluşturmaz (Binance ikinci kimliği reddeder).
        - Hata alınsa bile emir gerçekleşmiş olabilir; kimlikle durumu sorgulanır.
        - 429/418 ve 5xx'te artan bekleme uygulanır.
        """
        client_id = exchange.new_client_id(self.bot_id, side)
        last: Optional[Exception] = None
        for attempt in range(3):
            try:
                if side == "BUY" and quote_qty is not None:
                    return self.binance.market_buy_quote(coin, quote_qty, client_id)
                if side == "BUY":
                    return self.binance.market_buy(coin, qty, client_id)
                return self.binance.market_sell(coin, qty, client_id)
            except Exception as exc:  # noqa: BLE001
                last = exc
                found = self._find_order(coin, client_id)
                status = str((found or {}).get("status") or "").upper()
                if found and status in {"FILLED", "PARTIALLY_FILLED"}:
                    self._log(
                        self.bot_id,
                        f"{coin} emri hata yanıtına rağmen gerçekleşmiş ({status}); "
                        "çift emir gönderilmedi.",
                        "warning",
                    )
                    return found
                if not exchange.is_transient(exc) or attempt >= 2:
                    raise
                delay = exchange.retry_delay(exc, attempt)
                self._log(
                    self.bot_id,
                    f"{coin} {side} emri geçici hata (deneme {attempt + 1}/3), "
                    f"{delay:.1f} sn sonra tekrar: {str(exc)[:120]}",
                    "warning",
                )
                time.sleep(delay)
        raise last or RuntimeError("Emir gönderilemedi")

    def _fatal_auth_error(self, exc: BaseException) -> bool:
        """API anahtarı/izin hatası: düzeltilene kadar işlem yapılamaz."""
        code = exchange.error_code(exc)
        if code in {-2014, -2015, -1022}:
            return True
        text = str(exc).lower()
        return "invalid api-key" in text or "invalid api key" in text

    def _stop_for_auth_error(self, exc: BaseException) -> None:
        message = (
            f"Binance API anahtarı geçersiz veya işlem izni yok: {exc}. "
            "Bot durduruluyor; Ayarlar > Binance bölümünden anahtarları kontrol edin."
        )
        self._log(self.bot_id, message, "error")
        self.state["last_error"] = message
        self._safe_save_state()
        bot_state.request_stop(self.bot_id)
        try:
            notifier.send(f"Bot Durduruldu | {self.bot_name}", message)
        except Exception:  # noqa: BLE001
            pass

    def _order_failure(self, action: str, coin: str, exc: BaseException, notify: bool = True) -> None:
        """Emir hatasını logla, state'e yaz ve (varsa) Telegram'a gönder.

        Aynı hata saniyeler içinde tekrar ederse bildirim spam'i olmaması için
        yalnızca hata değiştiğinde veya 10 dakika geçtiğinde haber verilir.
        """
        text = f"{action} emri başarısız {coin}: {exc}"
        self._log(self.bot_id, text, "error")
        self.state["last_error"] = text
        now = time.time()
        previous = self.state.get("order_error") or {}
        signature = f"{action}|{coin}|{type(exc).__name__}|{str(exc)[:160]}"
        last_at = float(previous.get("at") or 0)
        should_notify = (
            notify
            and (
                previous.get("signature") != signature
                or now - last_at > 600
            )
        )
        self.state["order_error"] = {"signature": signature, "at": now}
        try:
            self._safe_save_state()
        except Exception:  # noqa: BLE001
            pass
        if should_notify:
            try:
                notifier.send(f"Emir Hatası | {self.bot_name}", text)
            except Exception:  # noqa: BLE001
                pass

    def _cancel_protective(self, coin: str) -> None:
        """Borsadaki koruyucu emirleri iptal eder."""
        position = self.state.get("position")
        if position is None:
            return
        if position.get("protective_stop") and self.mode == "live":
            try:
                order_list = position.get("protective_list_id")
                if order_list:
                    self.binance.cancel_order_list(coin, order_list)
                else:
                    self.binance.cancel_open_orders(coin)
            except Exception as exc:  # noqa: BLE001
                # OCO iptali başarısızsa açık emirler yine de temizlenmeye çalışılır.
                try:
                    self.binance.cancel_open_orders(coin)
                except Exception:
                    pass
                self._log(
                    self.bot_id, f"Koruyucu emir iptal edilemedi {coin}: {exc}", "warning"
                )
        position["protective_stop"] = None
        position["protective_order_id"] = None
        position["protective_tp_order_id"] = None
        position["protective_list_id"] = None
        position["protective_at"] = 0.0

    def _sync_protective(
        self,
        coin: str,
        qty: float,
        stop_price: Optional[float],
        target_price: Optional[float] = None,
    ) -> None:
        """Canlı pozisyonda borsada koruyucu stop bırakır/günceller."""
        if self.mode != "live" or not self.protective_enabled:
            return
        position = self.state.get("position")
        if not position:
            return
        if stop_price is None or float(stop_price) <= 0 or qty <= 0:
            if position.get("protective_stop"):
                self._cancel_protective(coin)
                self._safe_save_state()
            return
        current = position.get("protective_stop")
        target = float(target_price) if target_price and float(target_price) > 0 else None
        current_target = position.get("protective_tp")
        if (
            current
            and abs(float(current) - float(stop_price)) / float(stop_price) < 0.001
            and (target is None) == (current_target is None)
            and (
                target is None
                or abs(float(current_target) - target) / target < 0.001
            )
        ):
            return
        # Borsaya emir göndermek rate limit yer; koruyucu emir yalnızca yedek
        # olduğundan en fazla 30 saniyede bir taşınır (büyük sıçramalar hariç).
        last_at = float(position.get("protective_at") or 0.0)
        big_move = (
            not current
            or abs(float(current) - float(stop_price)) / float(stop_price) >= 0.01
        )
        if current and not big_move and time.time() - last_at < 30:
            return
        try:
            filters = self._filters(coin)
            qty_r = exchange.round_step(qty, filters.get("step_size") or 0)
            caps = [float(v) for v in (filters.get("max_qty"), filters.get("market_max_qty")) if v]
            if caps:
                qty_r = min(qty_r, min(caps))
            if qty_r <= 0:
                return
            tick = filters.get("tick_size") or 0.0
            # OCO'da kâr al bacağı fiyatın üstünde olmalı; değilse yalnız stop.
            last = float(position.get("last_price") or 0.0)
            if target is not None and last > 0 and target <= last * 1.002:
                target = None
            # Emirler dinamik olarak taşınacağı için açık emirler her zaman
            # temizlenir (OCO listesi varsa onunla birlikte).
            self._cancel_protective(coin)
            order: Dict[str, Any] = {}
            if target is not None:
                try:
                    order = self.binance.place_protective_oco(
                        coin, qty_r, float(stop_price), target, tick
                    )
                    position["protective_list_id"] = (
                        str(order.get("orderListId"))
                        if order.get("orderListId") is not None else None
                    )
                    position["protective_tp"] = target
                    # OCO iki bacak döndürür: stop ve limit (kâr al) emirleri.
                    for leg in order.get("orders") or []:
                        leg_type = str(leg.get("type") or "").upper()
                        if leg_type.startswith("STOP"):
                            position["protective_order_id"] = str(leg.get("orderId"))
                        elif leg_type in {"LIMIT", "LIMIT_MAKER"}:
                            position["protective_tp_order_id"] = str(leg.get("orderId"))
                except Exception as exc:  # noqa: BLE001 - OCO desteklenmeyebilir
                    self._log(
                        self.bot_id,
                        f"OCO kurulamadı {coin}, yalnızca stop bırakılıyor: {exc}",
                        "warning",
                    )
                    target = None
            if target is None:
                order = self.binance.place_protective_stop(
                    coin, qty_r, float(stop_price), tick
                )
                position["protective_order_id"] = (
                    str(order.get("orderId")) if isinstance(order, dict) else None
                )
                position["protective_tp"] = None
                position["protective_tp_order_id"] = None
                position["protective_list_id"] = None
            position["protective_stop"] = float(stop_price)
            position["protective_at"] = time.time()
            self._safe_save_state()
            self._protective_error = ""
            self._log(
                self.bot_id,
                f"Koruyucu emir bırakıldı {coin}: {qty_r:g} · stop {float(stop_price):.8f}"
                + (f" · hedef {target:.8f}" if target else ""),
                "info",
            )
        except Exception as exc:  # noqa: BLE001 - koruma botu durdurmamalı
            message = f"Koruyucu stop bırakılamadı {coin}: {exc}"
            if message != self._protective_error:
                self._protective_error = message
                self._log(self.bot_id, message, "warning")

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
        # Pozisyon boyutu: `risk_per_trade_pct` verilmişse stop mesafesine göre
        # hesaplanır (her işlemde kaybedilecek tutar sabit); yoksa eskisi gibi
        # nakit × max_position_pct.
        from app import risk as risk_rules

        cash_now = float(self.state.get("cash") or 0)
        stop_hint, _kind = risk_rules.effective_stop(
            price, atr_value, price, self.risk
        )
        budget = risk_rules.position_budget(
            cash_now, price, stop_hint, self.risk, self.max_position_pct
        )
        budget = math.floor(budget * 100) / 100
        budget = max(0.0, min(budget, cash_now))
        if self.mode == "live":
            self._open_live(coin, price, evaluator, result, atr_value, budget)
        else:
            self._open_paper(coin, price, budget, evaluator, result, atr_value)

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

    def _open_paper(self, coin, price, cash_available, evaluator, result, atr_value=0.0) -> bool:
        exec_price = price * (1 + self.slippage)
        filters = self._filters(coin)
        # Harcanabilir tutar mevcut nakdi asla aşmamalı (komisyon payı dahil).
        cash_now = float(self.state.get("cash") or 0)
        budget = min(float(cash_available or 0), cash_now)
        if budget <= 0:
            return False
        qty = exchange.round_step(
            budget / (exec_price * (1 + self.fee)), filters.get("step_size") or 0.0
        )
        min_notional = float(filters.get("min_notional") or exchange.DEFAULT_MIN_NOTIONAL)
        if qty <= 0 or qty * exec_price < min_notional:
            self._log(
                self.bot_id,
                f"Alım atlandı {coin}: bütçe minimum işlem tutarının altında "
                f"({budget:.2f} < {min_notional:g} USDT)",
                "debug",
            )
            return False
        fee_amount = qty * exec_price * self.fee
        cash_after = cash_now - (qty * exec_price) - fee_amount
        if cash_after < 0:
            # Kayan nokta/min-adet yuvarlaması: kalanı sıfıra sabitle.
            cash_after = 0.0
        try:
            self._record_trade(coin, "BUY", qty, exec_price, fee_amount, None, "sinyal")
        except Exception as exc:  # noqa: BLE001 - kayıt yazılamazsa pozisyon açılmasın
            self._order_failure("Alım kaydı", coin, exc, notify=False)
            return False
        self.state["cash"] = round(cash_after, 8)
        self._set_position(coin, qty, exec_price, evaluator, result, atr=atr_value)
        notifier.send(
            f"AL | {self.bot_name}",
            f"Bot: {self.bot_name}\n{coin} alındı\nAdet: {qty}\nFiyat: {exec_price:.8f}\nMod: paper",
            kind="buy",
        )
        return True

    def _open_live(self, coin, price, evaluator, result, atr_value=0.0, budget=None) -> bool:
        usdt = 0.0
        try:
            for item in self.binance.client.get_account()["balances"]:
                if item["asset"] == "USDT":
                    usdt = float(item["free"])
                    break
        except Exception as exc:
            self._order_failure("Bakiye okuma", coin, exc)
            return False
        has_local_cash = self.state.get("cash") is not None
        local_cash = float(self.state.get("cash") or 0.0)
        available = usdt * self.max_position_pct
        # Bot yalnızca kendi kaydındaki nakdi harcar. Aynı hesabı kullanan
        # başka bot varsa bakiye iki kez kullanılmaz.
        if has_local_cash:
            available = min(available, max(0.0, local_cash))
        if budget is not None:
            available = min(available, float(budget))
        filters = self._filters(coin)
        min_notional = float(filters.get("min_notional") or exchange.DEFAULT_MIN_NOTIONAL)
        if available < max(10.0, min_notional):
            self._log(
                self.bot_id,
                f"Yetersiz nakit: {available:.2f} USDT (min {min_notional:g})",
                "warning",
            )
            return False
        if not filters.get("found"):
            self._log(
                self.bot_id,
                f"{coin} filtreleri okunamadı; varsayılan değerlerle deneniyor",
                "warning",
            )
        # Komisyon ve fiyat kayması payı: bakiyenin tamamı harcanmaz.
        spend_limit = min(available, usdt) * 0.999
        quote_qty = math.floor(spend_limit * 100) / 100
        if quote_qty < min_notional:
            return False
        order: Optional[Dict[str, Any]] = None
        try:
            with account_lock.live_account_lock() as locked:
                if not locked:
                    self._log(
                        self.bot_id,
                        "Hesap kilidi alınamadı; emir yine de gönderiliyor (gecikme olabilir)",
                        "warning",
                    )
                try:
                    order = self._submit_order("BUY", coin, quote_qty=quote_qty)
                except Exception as exc:
                    # Bazı pariteler quoteOrderQty kabul etmez: adet bazlı dene.
                    if exchange.error_code(exc) not in (-1102, -1106, -1013):
                        raise
                    qty_try = exchange.round_step(
                        spend_limit / price, filters.get("step_size") or 0.0
                    )
                    if filters.get("max_qty"):
                        qty_try = min(qty_try, float(filters["max_qty"]))
                    if qty_try <= 0 or qty_try * price < min_notional:
                        raise
                    order = self._submit_order("BUY", coin, qty=qty_try)
        except Exception as exc:  # noqa: BLE001
            self._order_failure("Alım", coin, exc)
            if self._fatal_auth_error(exc):
                self._stop_for_auth_error(exc)
            return False
        if not isinstance(order, dict):
            self._order_failure("Alım", coin, RuntimeError("borsa yanıtı okunamadı"))
            return False
        executed = exchange.order_quantity(order, 0.0)
        quote = exchange.order_quote(order, executed * price)
        if executed <= 0:
            self._order_failure("Alım", coin, RuntimeError("emir gerçekleşmedi (executedQty=0)"))
            return False
        avg = quote / executed if executed else price
        fee_amount = quote * self.fee
        base_cash = local_cash if has_local_cash else usdt
        self.state["cash"] = round(max(0.0, base_cash - quote - fee_amount), 8)
        self._set_position(
            coin, executed, avg, evaluator, result,
            order_id=str(order.get("orderId")), atr=atr_value,
        )
        try:
            self._record_trade(
                coin, "BUY", executed, avg, fee_amount, str(order.get("orderId")), "sinyal"
            )
        except Exception as exc:  # noqa: BLE001 - emir gerçekleşti; kayıt eksik kalmasın diye logla
            self._log(self.bot_id, f"Alım işlem kaydı yazılamadı {coin}: {exc}", "error")
        # Pozisyon açılır açılmaz borsada koruyucu stop bırakılır: bot süreci
        # anında çökse bile pozisyon korumasız kalmaz.
        try:
            from app import risk as risk_rules

            stop, _kind = risk_rules.effective_stop(avg, atr_value, avg, self.risk)
            target = risk_rules.target_price(avg, atr_value, self.risk)
            self._sync_protective(coin, executed, stop, target)
        except Exception as exc:  # noqa: BLE001 - koruma botu durdurmamalı
            self._log(self.bot_id, f"Koruyucu stop kurulamadı {coin}: {exc}", "warning")
        notifier.send(
            f"AL | {self.bot_name}",
            f"Bot: {self.bot_name}\n{coin} alındı\nAdet: {executed}\nFiyat: {avg:.8f}\nMod: LIVE",
            kind="buy",
        )
        return True

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
            "order_id": str(order_id) if order_id else None,
            "protective_stop": None,
            "protective_order_id": None,
            "protective_tp": None,
            "protective_tp_order_id": None,
            "protective_list_id": None,
            "protective_at": 0.0,
            "strategy_id": evaluator.id,
            "strategy_version": evaluator.version,
            "entry_signal": result.get("buy_detail"),
        }
        self.state["trade_count"] = int(self.state.get("trade_count", 0)) + 1
        self._save_state()
        try:
            db.execute(
                "INSERT INTO positions(bot_id,coin,quantity,entry_price,highest_price,opened_at,status) "
                "VALUES(?,?,?,?,?,?, 'open')",
                (self.bot_id, coin, qty, price, price, utcnow()),
            )
        except Exception as exc:  # noqa: BLE001 - emir gerçekleşti; kayıt hatası botu durdurmasın
            self._log(self.bot_id, f"Pozisyon kaydı yazılamadı {coin}: {exc}", "error")

    def _record_trade(self, coin, side, qty, price, fee, order_id, reason, pnl_pct=None) -> None:
        db.execute(
            "INSERT INTO trades(bot_id,run_id,coin,side,quantity,price,fee,order_id,mode,reason,pnl_pct,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.bot_id, self.run_id, coin, side, qty, price, fee, order_id, self.mode, reason, pnl_pct, utcnow()),
        )

    def _close_position(self, price, reason, fee_override=None) -> bool:
        """Pozisyonu kapatır.

        Döndürür: kapandı mı. Emir reddedilirse pozisyon ve nakit **değişmez**;
        karar ``pending_exit`` olarak kalır, ``_process_pending_exit`` tekrar dener.
        """
        position = self.state.get("position")
        if not position:
            self.state["pending_exit"] = None
            return True
        coin = position["coin"]
        entry = float(position["entry_price"])
        qty_local = float(position.get("quantity") or 0)
        if qty_local <= 0:
            self.state["position"] = None
            self.state["pending_exit"] = None
            self._save_state()
            return True

        # Karar emirden ÖNCE kalıcı yazılır: süreç çökse bile kaybolmaz.
        if not self.state.get("pending_exit"):
            self._request_exit(reason, price)

        # Satış için borsadaki koruyucu emir iptal edilir; satış başarısız olursa
        # pozisyon korumasız kalmasın diye tekrar kurulur.
        rearm_stop = position.get("stop_price")
        rearm_target = position.get("protective_tp")
        rearm_qty = qty_local

        if self.mode == "live":
            try:
                self._cancel_protective(coin)
                filters = self._filters(coin)
                free = self.binance.mevcut_adedim(coin)
                if free is not None and float(free) <= 0:
                    # Borsada bakiye yok: emir göndermek anlamsız. Harici satış
                    # olarak yerel kayda işlenir (gerçek nakit kullanılır).
                    self._log(
                        self.bot_id,
                        f"{coin} için borsada satılabilir bakiye yok; harici satış varsayılıyor",
                        "warning",
                    )
                    self._sync_live_position()
                    if self.state.get("position") is None:
                        self._clear_pending_exit()
                        return True
                    raise RuntimeError("borsada satılabilir bakiye yok")
                qty = min(float(free), qty_local) if free is not None else qty_local
                qty = exchange.round_step(qty, filters.get("step_size") or 0.0)
                min_qty = float(filters.get("min_qty") or 0.0)
                if qty <= 0 or (min_qty > 0 and qty < min_qty):
                    raise RuntimeError(
                        f"satılabilir miktar filtre altında (adet={qty:g}, min={min_qty:g})"
                    )
                if filters.get("max_qty"):
                    qty = min(qty, float(filters["max_qty"]))
                with account_lock.live_account_lock() as locked:
                    if not locked:
                        self._log(
                            self.bot_id,
                            "Hesap kilidi alınamadı; satış yine de gönderiliyor",
                            "warning",
                        )
                    order = self._submit_order("SELL", coin, qty=qty)
            except Exception as exc:  # noqa: BLE001
                self._order_failure("Satış", coin, exc)
                if self._fatal_auth_error(exc):
                    self._stop_for_auth_error(exc)
                # Emir gönderilemedi: pozisyon açık, koruyucu stop geri konur.
                if rearm_stop:
                    self._sync_protective(coin, rearm_qty, rearm_stop, rearm_target)
                return False
            if not isinstance(order, dict):
                self._order_failure("Satış", coin, RuntimeError("borsa yanıtı okunamadı"))
                if rearm_stop:
                    self._sync_protective(coin, rearm_qty, rearm_stop, rearm_target)
                return False
            executed = exchange.order_quantity(order, qty)
            quote = exchange.order_quote(order, executed * price)
            if executed <= 0:
                self._order_failure("Satış", coin, RuntimeError("emir gerçekleşmedi (executedQty=0)"))
                if rearm_stop:
                    self._sync_protective(coin, rearm_qty, rearm_stop, rearm_target)
                return False
            avg = quote / executed if executed else price
            fee_amount = quote * self.fee
            try:
                self._record_trade(
                    coin, "SELL", executed, avg, fee_amount, str(order.get("orderId")),
                    reason, (avg / entry - 1) * 100,
                )
            except Exception as exc:  # noqa: BLE001 - emir gerçekleşti, akış sürmeli
                self._log(
                    self.bot_id,
                    f"Satış işlem kaydı yazılamadı {coin} (emir gerçekleşti): {exc}",
                    "error",
                )
            self.state["cash"] = round(
                float(self.state.get("cash") or 0) + quote - fee_amount, 8
            )
            qty, price = executed, avg
        else:
            exec_price = price * (1 - self.slippage)
            fee_amount = qty_local * exec_price * self.fee
            try:
                self._record_trade(
                    coin, "SELL", qty_local, exec_price, fee_amount, None, reason,
                    (exec_price / entry - 1) * 100,
                )
            except Exception as exc:  # noqa: BLE001
                # Kayıt yazılamadı: nakit ve pozisyon değişmedi. Karar kalıcı,
                # sonraki turda tekrar denenir; çift satış oluşmaz.
                self._order_failure("Satış kaydı", coin, exc, notify=False)
                return False
            self.state["cash"] = round(
                float(self.state.get("cash") or 0) + (qty_local * exec_price) - fee_amount, 8
            )
            qty, price = qty_local, exec_price

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
        try:
            db.execute(
                "UPDATE positions SET closed_at=?, close_price=?, pnl_pct=?, status='closed' "
                "WHERE bot_id=? AND coin=? AND status='open'",
                (utcnow(), price, pnl_pct, self.bot_id, coin),
            )
        except Exception as exc:  # noqa: BLE001 - kayıt hatası kapanışı engellemesin
            self._log(self.bot_id, f"Pozisyon kaydı kapatılamadı {coin}: {exc}", "error")
        self.state["position"] = None
        self.state["pending_exit"] = None
        self.state["last_error"] = None
        # Çıkış nedeni dağılımı (panelde gösterilir).
        counters = self.state.setdefault("exit_reasons", {})
        counters[reason or "signal"] = int(counters.get(reason or "signal", 0)) + 1
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
            kind="sell",
        )
        return True

    def _partial_close(self, price, reason, fraction) -> bool:
        """Pozisyonun bir kısmını satar; kalan kısım takibe devam eder.

        Kısmi satıştan sonra stop en az giriş fiyatına çekilir (``stop_floor``),
        yani kalan pozisyon kâr garantili devam eder. Emir reddedilirse
        pozisyon olduğu gibi kalır (bir sonraki mumda tekrar denenir).
        """
        position = self.state.get("position")
        if not position:
            return False
        fraction = max(0.0, min(float(fraction or 0.0), 1.0))
        if fraction <= 0:
            return False
        coin = position["coin"]
        entry = float(position["entry_price"])
        qty_total = float(position.get("quantity") or 0)
        if qty_total <= 0:
            return False
        filters = self._filters(coin)
        min_notional = float(filters.get("min_notional") or exchange.DEFAULT_MIN_NOTIONAL)
        sold = exchange.round_step(qty_total * fraction, filters.get("step_size") or 0.0)
        remaining = qty_total - sold
        # Kalan kısım minimum işlem tutarının altındaysa tamamen kapat.
        if sold <= 0 or remaining * price < min_notional:
            return self._close_position(price, reason)
        if self.mode == "live":
            # Koruyucu OCO/stop miktarı kilitler; kısmi satıştan önce iptal edilir.
            had_protective = bool(position.get("protective_stop"))
            rearm_stop = position.get("stop_price")
            rearm_target = position.get("protective_tp")
            if had_protective:
                self._cancel_protective(coin)
            try:
                free = self.binance.mevcut_adedim(coin)
                if free is not None and float(free) <= 0:
                    # Borsada miktar kalmamış (elle satış / koruyucu stop):
                    # pozisyon senkronu kapatır, kısmi satış denemesi sürmez.
                    self._sync_live_position()
                    done = self.state.get("position") is None
                    if not done and rearm_stop:
                        self._sync_protective(coin, qty_total, rearm_stop, rearm_target)
                    return done
                if free is not None:
                    sold = min(sold, float(free))
                    sold = exchange.round_step(sold, filters.get("step_size") or 0.0)
                if sold <= 0:
                    raise RuntimeError("satılabilir miktar yok")
                with account_lock.live_account_lock() as locked:
                    if not locked:
                        self._log(
                            self.bot_id,
                            "Hesap kilidi alınamadı; kısmi satış yine de gönderiliyor",
                            "warning",
                        )
                    order = self._submit_order("SELL", coin, qty=sold)
            except Exception as exc:  # noqa: BLE001
                self._order_failure("Kısmi satış", coin, exc)
                if self._fatal_auth_error(exc):
                    self._stop_for_auth_error(exc)
                if rearm_stop:
                    self._sync_protective(coin, qty_total, rearm_stop, rearm_target)
                return False
            if not isinstance(order, dict):
                self._order_failure("Kısmi satış", coin, RuntimeError("borsa yanıtı okunamadı"))
                if rearm_stop:
                    self._sync_protective(coin, qty_total, rearm_stop, rearm_target)
                return False
            executed = exchange.order_quantity(order, sold)
            quote = exchange.order_quote(order, executed * price)
            if executed <= 0:
                self._order_failure("Kısmi satış", coin, RuntimeError("emir gerçekleşmedi"))
                return False
            avg = quote / executed if executed else price
            fee_amount = quote * self.fee
            try:
                self._record_trade(
                    coin, "SELL", executed, avg, fee_amount, str(order.get("orderId")),
                    reason, (avg / entry - 1) * 100,
                )
            except Exception as exc:  # noqa: BLE001 - emir gerçekleşti
                self._log(
                    self.bot_id,
                    f"Kısmi satış kaydı yazılamadı {coin} (emir gerçekleşti): {exc}",
                    "error",
                )
            self.state["cash"] = round(
                float(self.state.get("cash") or 0) + quote - fee_amount, 8
            )
            sold, price = executed, avg
        else:
            exec_price = price * (1 - self.slippage)
            fee_amount = sold * exec_price * self.fee
            try:
                self._record_trade(
                    coin, "SELL", sold, exec_price, fee_amount, None, reason,
                    (exec_price / entry - 1) * 100,
                )
            except Exception as exc:  # noqa: BLE001 - kayıt yoksa nakit değişmesin
                self._order_failure("Kısmi satış kaydı", coin, exc, notify=False)
                return False
            self.state["cash"] = round(
                float(self.state.get("cash") or 0) + (sold * exec_price) - fee_amount, 8
            )
            price = exec_price

        position["quantity"] = round(float(position.get("quantity") or 0) - sold, 10)
        position["partial_taken"] = True
        position["stop_floor"] = entry
        position["stop_price"] = round(entry, 8)
        # Kalan pozisyonun borsadaki koruyucu stopu da girişe çekilir.
        try:
            self._sync_protective(coin, position["quantity"], entry)
        except Exception as exc:  # noqa: BLE001
            self._log(self.bot_id, f"Kısmi sonrası stop güncellenemedi {coin}: {exc}", "warning")
        self.state["total_realized_pnl"] = round(
            float(self.state.get("total_realized_pnl", 0)) + (price - entry) * sold, 8
        )
        try:
            db.execute(
                "UPDATE positions SET quantity=? WHERE bot_id=? AND coin=? AND status='open'",
                (position["quantity"], self.bot_id, coin),
            )
        except Exception as exc:  # noqa: BLE001
            self._log(self.bot_id, f"Kısmi satış kaydı güncellenemedi {coin}: {exc}", "error")
        self._save_state()
        self._log(
            self.bot_id,
            f"KISMİ SATIŞ {coin} | {reason} | {sold:g} @ {price:.8f} | "
            f"kalan {position['quantity']:g}",
            "info",
        )
        notifier.send(
            f"Kısmi satış | {self.bot_name}",
            f"Bot: {self.bot_name}\n{coin}\nSatılan: {sold:g}\nKalan: {position['quantity']:g}\n"
            f"Fiyat: {price:.8f}\nNeden: {reason}",
            kind="sell",
        )
        return True

    # ------------------------------------------------------------------
    # Pozisyon yönetimi
    # ------------------------------------------------------------------
    def _manage_position(self) -> None:
        from app import risk as risk_rules

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

        entry = float(position["entry_price"])
        highest = float(position.get("highest_price") or entry)
        atr_base = float(position.get("atr") or 0.0)
        if atr_base <= 0:
            atr_base = self._atr_value(data)
            position["atr"] = atr_base

        # --- Stop / takipli stop / breakeven / kâr al (backtest ile ortak) ---
        stop_price, stop_kind = risk_rules.effective_stop(
            entry, atr_base, highest, self.risk, floor=position.get("stop_floor")
        )
        target = risk_rules.target_price(entry, atr_base, self.risk)
        partial_target = risk_rules.partial_target_price(entry, atr_base, self.risk)

        exit_reason: Optional[str] = None
        exit_price: Optional[float] = None
        partial_price: Optional[float] = None

        candle_open = float(data["open"][-1]) if data.get("open") else None

        def _stop_fill(level: float) -> float:
            """Gap'te açılıştan, aksi halde stop seviyesinden çık (kötümser)."""
            if candle_open is not None and candle_open <= level:
                return candle_open
            return level

        if stop_price is not None and float(low[-1]) <= stop_price:
            exit_reason = stop_kind
            exit_price = _stop_fill(stop_price)
        elif target is not None and float(high[-1]) >= target:
            exit_reason = "take-profit"
            exit_price = target
        elif result.get("sell"):
            exit_reason = "sinyal"
        else:
            # Kâr koruma: kârdayken kısa vadeli yapı kırılırsa çık (hızlı çıkış).
            profit_don = int(self.risk.get("profit_exit_donchian") or 0)
            if profit_don > 0 and price > entry and len(close) >= profit_don + 3:
                try:
                    from app.strategies.registry import IndicatorCache

                    lower = IndicatorCache(data).compute(
                        "DONCHIAN", {"length": profit_don}, "lower"
                    )
                    if (
                        lower[-2] is not None and lower[-3] is not None
                        and float(close[-1]) < float(lower[-2])
                        and float(close[-2]) >= float(lower[-3])
                    ):
                        exit_reason = "profit-exit"
                except Exception as exc:
                    self._log(self.bot_id, f"Kâr koruma hatası: {exc}", "warning")

        # --- Eski (panelde seçilebilen) destek / dinamik / sabit stop ---
        if exit_reason is None and self.risk.get("support_stop"):
            try:
                refresh = risk_rules.support_refresh(self.risk)
                age = int(position.get("candles", 0)) - int(position.get("destek_at", -refresh))
                if position.get("destek") is None or age >= refresh:
                    destek, direnc, stop = risk_rules.support_stop(
                        entry, position.get("destek"), position.get("direnc"),
                        close, low, self.risk,
                    )
                    position["destek_at"] = int(position.get("candles", 0))
                    if stop == "STOP-LOSE":
                        exit_reason = "destek-stop"
                    else:
                        position["destek"] = destek
                        position["direnc"] = direnc
                elif risk_rules.support_break(price, position.get("destek"), self.risk):
                    # Aramalar arasında saklanan seviye her mumda kontrol edilir.
                    exit_reason = "destek-stop"
            except Exception as exc:
                self._log(self.bot_id, f"Destek stop hatası: {exc}", "warning")

        if exit_reason is None and self.risk.get("dynamic_stop"):
            try:
                from app.strategies.registry import IndicatorCache

                adx_values = IndicatorCache(data).compute("ADX", {"length": 14}, "adx")
                level = risk_rules.dynamic_stop_level(
                    highest, atr_base, adx_values[-1], self.risk
                )
                if risk_rules.dynamic_stop_hit(price, level, self.risk):
                    exit_reason = "dinamik-stop"
            except Exception as exc:
                self._log(self.bot_id, f"Dinamik stop hatası: {exc}", "warning")

        if exit_reason is None and self.risk.get("static_stop"):
            level = risk_rules.static_stop_price(entry, self.risk)
            if level is not None and float(low[-1]) <= level:
                exit_reason = "statik-stop"
                exit_price = _stop_fill(level)

        # --- Kısmi kâr al: pozisyonun bir kısmını sat, kalanı takibe bırak ---
        if (
            exit_reason is None
            and partial_target is not None
            and not position.get("partial_taken")
            and float(high[-1]) >= partial_target
        ):
            partial_price = partial_target

        position["candles"] = int(position.get("candles", 0)) + 1
        # Anlık durum: son fiyat, gerçekleşmemiş K/Z ve aktif seviyeler.
        qty_now = float(position.get("quantity") or 0)
        position["last_price"] = price
        position["last_price_at"] = utcnow()
        position["unrealized_pnl"] = round((price - entry) * qty_now, 4)
        position["unrealized_pnl_pct"] = round((price / entry - 1) * 100, 2) if entry else 0.0
        if stop_price is not None:
            position["stop_price"] = round(float(stop_price), 8)
        position["take_profit_price"] = round(float(target), 8) if target is not None else None
        # Zaman limiti kaldırıldı: pozisyon yalnızca sinyal veya stop ile kapanır.
        self._save_state()

        # Canlı modda stop seviyesi borsaya da bırakılır: bot süreci çökse bile
        # pozisyon korumasız kalmaz (Ayarlar > İşlem).
        try:
            takeprofit = target if not position.get("partial_taken") else None
            self._sync_protective(coin, qty_now, stop_price, takeprofit)
        except Exception as exc:  # noqa: BLE001 - koruma botu durdurmamalı
            self._log(self.bot_id, f"Koruyucu stop güncellenemedi {coin}: {exc}", "warning")

        if exit_reason:
            self._request_exit(exit_reason, exit_price if exit_price is not None else price)
            self._process_pending_exit()
        elif partial_price is not None:
            self._partial_close(
                partial_price, "take-profit-partial", risk_rules.partial_fraction(self.risk)
            )
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
