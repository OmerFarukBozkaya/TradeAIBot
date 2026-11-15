"""Merkezi yapılandırma.

Öncelik: panelden kaydedilen ayarlar (SQLite) > `.env` > kod varsayılanı.
`.env` yalnızca ilk varsayılanlar ve altyapı (port, secret key) içindir;
çalışma anında değiştirilmez. Tüm işlem/bildirim ayarları panelden yönetilir.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Mevcut modüller 'Data' ve 'Log' (büyük harf) bekliyor.
DATA_DIR = Path(os.getenv("TRADEAI_DATA_DIR", BASE_DIR / "Data"))
LOG_DIR = Path(os.getenv("TRADEAI_LOG_DIR", BASE_DIR / "Log"))
STATE_DIR = Path(os.getenv("TRADEAI_STATE_DIR", BASE_DIR / "state"))
TRADE_STATE_DIR = BASE_DIR / "Trade_Durumu"
TRADE_STATE_AI_DIR = BASE_DIR / "Trade_Durumu_AI"

for _dir in (DATA_DIR, LOG_DIR, STATE_DIR, TRADE_STATE_DIR, TRADE_STATE_AI_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# .env dosyasını bilinçli olarak tek isimle yükle. glob(".env*") yanlış dosya seçiyordu.
_ENV_FILE = Path(os.getenv("TRADEAI_ENV_FILE", BASE_DIR / ".env"))
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=False)
else:
    # Geliştirme kolaylığı: .env yoksa .env.example değerleri kullanılmaz,
    # sadece uyarı verilir. Üretimde .env zorunludur.
    load_dotenv(BASE_DIR / ".env.example", override=False)


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class _SettingsMeta(type):
    """`settings.<KEY>` erişimini panelden kaydedilen değerlere yönlendirir.

    Öncelik: SQLite (panel) > `.env` / varsayılan. Böylece tüm mevcut kod
    değişmeden panel ayarlarını görür.
    """

    def __getattribute__(cls, name: str):
        if name == "DEFAULT_RISK":
            return {
                "dynamic_stop": bool(_settings_value("DYNAMIC_STOP_LOSE", False)),
                "static_stop": bool(_settings_value("STATIC_STOP_LOSE", False)),
                "support_stop": bool(_settings_value("SUPPORT_STOP_LOSE", True)),
                "take_profit": bool(_settings_value("TAKE_PROFIT", True)),
            }
        if name == "STRATEGY_LIMITS":
            return {
                "15m": int(_settings_value("STRATEGY_LIMIT_15M", 3) or 0),
                "1h": int(_settings_value("STRATEGY_LIMIT_1H", 3) or 0),
                "4h": int(_settings_value("STRATEGY_LIMIT_4H", 3) or 0),
                "1d": int(_settings_value("STRATEGY_LIMIT_1D", 3) or 0),
            }
        if name in _RUNTIME_KEYS:
            default = type.__getattribute__(cls, name)
            return _settings_value(name, default)
        return type.__getattribute__(cls, name)


def _settings_value(name: str, default):
    try:
        from app import runtime_settings

        if name in runtime_settings.BY_KEY:
            raw = runtime_settings.value(name, default)
            if runtime_settings.BY_KEY[name].secret and isinstance(raw, str):
                return runtime_settings.decrypt(raw)
            return raw
    except Exception:
        return default
    return default


_RUNTIME_KEYS = frozenset(
    {
        "LIVE_ENABLED", "DEFAULT_MODE", "DEFAULT_CASH", "PAPER_FEE", "PAPER_SLIPPAGE",
        "AUTO_RESTART", "HEARTBEAT_SECONDS", "MAX_JOBS", "AI_ENABLED",
        "BINANCE_API_KEY", "BINANCE_API_SECRET", "QUOTE_ASSET",
        "MAIL_ENABLED", "TELEGRAM_ENABLED",
        "MAIL_FROM", "MAIL_PASSWORD", "MAIL_TO", "TELEGRAM_TOKEN", "TELEGRAM_CHAT",
        "DYNAMIC_STOP_LOSE", "STATIC_STOP_LOSE", "SUPPORT_STOP_LOSE", "TAKE_PROFIT",
        "STRATEGY_LIMIT_15M", "STRATEGY_LIMIT_1H", "STRATEGY_LIMIT_4H", "STRATEGY_LIMIT_1D",
    }
)


class Settings(metaclass=_SettingsMeta):
    def __getattribute__(self, name: str):
        if name == "DEFAULT_RISK":
            return {
                "dynamic_stop": bool(_settings_value("DYNAMIC_STOP_LOSE", False)),
                "static_stop": bool(_settings_value("STATIC_STOP_LOSE", False)),
                "support_stop": bool(_settings_value("SUPPORT_STOP_LOSE", True)),
                "take_profit": bool(_settings_value("TAKE_PROFIT", True)),
            }
        if name == "STRATEGY_LIMITS":
            return {
                "15m": int(_settings_value("STRATEGY_LIMIT_15M", 3) or 0),
                "1h": int(_settings_value("STRATEGY_LIMIT_1H", 3) or 0),
                "4h": int(_settings_value("STRATEGY_LIMIT_4H", 3) or 0),
                "1d": int(_settings_value("STRATEGY_LIMIT_1D", 3) or 0),
            }
        if name in _RUNTIME_KEYS:
            default = object.__getattribute__(self, name)
            return _settings_value(name, default)
        return object.__getattribute__(self, name)

    # Uygulama
    APP_NAME = "TradeAIBot"
    HOST = os.getenv("TRADEAI_HOST", "0.0.0.0")
    PORT = _int("TRADEAI_PORT", 8080)
    SECRET_KEY = os.getenv("TRADEAI_SECRET_KEY", "")
    SESSION_HOURS = _int("TRADEAI_SESSION_HOURS", 12)
    COOKIE_SECURE = _bool("TRADEAI_COOKIE_SECURE", False)

    # İlk kurulum
    ADMIN_USER = os.getenv("ADMIN_USER", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

    # İşlem güvenliği
    LIVE_ENABLED = _bool("LIVE_TRADING_ENABLED", True)
    DEFAULT_MODE = os.getenv("DEFAULT_TRADE_MODE", "paper").strip().lower()
    PAPER_FEE = _float("PAPER_FEE", 0.001)
    PAPER_SLIPPAGE = _float("PAPER_SLIPPAGE", 0.0005)
    DEFAULT_CASH = _float("DEFAULT_CASH", 100.0)

    # Botlar
    HEARTBEAT_SECONDS = _int("BOT_HEARTBEAT_SECONDS", 5)
    HEARTBEAT_TIMEOUT_SECONDS = _int("BOT_HEARTBEAT_TIMEOUT_SECONDS", 90)
    AUTO_RESTART = _bool("BOT_AUTO_RESTART", True)
    MAX_JOBS = _int("MAX_JOBS", 4)

    # Binance
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
    QUOTE_ASSET = os.getenv("QUOTE_ASSET", "USDT")

    # Bildirim
    MAIL_ENABLED = _bool("MAIL_GONDER", False)
    TELEGRAM_ENABLED = _bool("TELEGRAM_MESAJ_GONDER", False)
    MAIL_FROM = os.getenv("MAIL_FROM") or os.getenv("GONDERICI_EMAIL", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD") or os.getenv("GONDERICI_EMAIL_SIFRE", "")
    MAIL_TO = os.getenv("MAIL_TO") or os.getenv("ALICI_EMAIL", "")
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_API_TOKEN", "")
    TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT") or os.getenv("TELEGRAM_CHAT_ID", "")

    # Risk varsayılanları
    DEFAULT_RISK = {
        "dynamic_stop": _bool("DINAMIK_STOP_LOSE", False),
        "static_stop": _bool("STATIC_STOP_LOSE", False),
        "support_stop": _bool("DESTEK_STOP_LOSE", True),
        "take_profit": _bool("TAKE_PROFIT", True),
    }

    # Strateji limitleri
    STRATEGY_LIMITS = {
        "15m": _int("STRATEGY_LIMIT_15M", 3),
        "1h": _int("STRATEGY_LIMIT_1H", 3),
        "4h": _int("STRATEGY_LIMIT_4H", 3),
        "1d": _int("STRATEGY_LIMIT_1D", 3),
    }

    SUPPORTED_PERIODS: List[str] = ["1m", "5m", "15m", "1h", "4h", "1d"]

    # AI ayrı profil
    AI_ENABLED = _bool("AI_ENABLED", False)


settings = Settings()

# Secret key yoksa kalıcı bir anahtar üret (Data/ altında sakla, volume ile korunur).
_SECRET_FILE = DATA_DIR / ".secret_key"
if not settings.SECRET_KEY:
    if _SECRET_FILE.exists():
        settings.SECRET_KEY = _SECRET_FILE.read_text(encoding="utf-8").strip()
    else:
        import secrets

        settings.SECRET_KEY = secrets.token_urlsafe(48)
        _SECRET_FILE.write_text(settings.SECRET_KEY, encoding="utf-8")
