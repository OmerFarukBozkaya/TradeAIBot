"""Panelden düzenlenebilen ayarların tanımı.

Her ayar bir anahtar (config.py'deki `settings.<KEY>`), bir tür ve doğrulama
aralığı taşır. `.env` yalnızca ilk varsayılan / altyapı içindir; panelden
yapılan değişiklikler SQLite'ta tutulur ve çalışma anında geçerli olur.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

# group id -> (başlık, açıklama)
GROUPS: Tuple[Tuple[str, str, str], ...] = (
    ("trading", "İşlem", "Varsayılan mod, bakiye ve test maliyetleri"),
    ("risk", "Risk", "Yeni botların varsayılan koruma kuralları"),
    ("limits", "Strateji limitleri", "Periyot başına en fazla strateji sayısı"),
    ("binance", "Binance", "Borsa API anahtarları ve parite"),
    ("notifications", "Bildirimler", "E-posta ve Telegram bildirimleri"),
    ("system", "Sistem", "Bot izleme, iş kuyruğu ve yapay zekâ"),
)


@dataclass(frozen=True)
class SettingDef:
    key: str
    label: str
    group: str
    kind: str  # bool | int | float | str | secret | select
    help: str = ""
    min: float | None = None
    max: float | None = None
    options: Tuple[Tuple[str, str], ...] = ()
    secret: bool = False
    placeholder: str = ""


SETTINGS: Tuple[SettingDef, ...] = (
    # ---------------- İşlem ----------------
    SettingDef(
        "LIVE_ENABLED", "Canlı işlem sunucu izni", "trading", "bool",
        "Kapatıldığında panelden canlı işlem açılamaz. Normal kullanımda üst çubuktaki anahtarı kullan.",
    ),
    SettingDef(
        "DEFAULT_MODE", "Yeni bot varsayılan modu", "trading", "select",
        "Yeni botlar bu modda oluşturulur.",
        options=(("paper", "Test (paper)"), ("live", "Canlı")),
    ),
    SettingDef(
        "DEFAULT_CASH", "Varsayılan başlangıç nakdi (USDT)", "trading", "float",
        "Yeni bot formunda önerilen bakiye.", min=1, max=10_000_000,
    ),
    SettingDef(
        "PAPER_FEE", "Test komisyon oranı", "trading", "float",
        "0.001 = %0.1. Yalnızca test modunda uygulanır.", min=0, max=0.1,
    ),
    SettingDef(
        "PAPER_SLIPPAGE", "Test kayma oranı", "trading", "float",
        "0.0005 = %0.05. Test fiyatına eklenen kayma.", min=0, max=0.1,
    ),
    SettingDef(
        "EXCHANGE_PROTECTIVE_STOP", "Borsada koruyucu stop bırak", "trading", "bool",
        "Canlı pozisyon açılınca stop seviyesine borsada STOP_LOSS_LIMIT emri bırakılır. "
        "Bot süreci çökse bile pozisyon korunur. Gap riski için limit fiyatı stopun biraz altındadır.",
    ),
    SettingDef(
        "SHARED_ACCOUNT", "Binance hesabı birden fazla botla paylaşılıyor", "trading", "bool",
        "Açıksa nakit mutabakatı hesap toplamı yerine botun kendi kaydıyla yapılır. "
        "Kapalıyken hesapta başka bot varsa uyarı verilir.",
    ),
    SettingDef(
        "ADOPT_EXTERNAL_BUY", "Harici alımları benimse", "trading", "bool",
        "Borsada elle alınan miktar botun pozisyonuna eklenir. Kapalıyken yalnızca uyarı verilir "
        "(bot kullanıcının cüzdanından gelen coini istemeden satmaz).",
    ),

    # ---------------- Risk ----------------
    SettingDef(
        "DYNAMIC_STOP_LOSE", "Dinamik stop varsayılanı", "risk", "bool",
        "Fiyat yükseldikçe stop seviyesini yukarı taşır.",
    ),
    SettingDef(
        "STATIC_STOP_LOSE", "Sabit stop varsayılanı", "risk", "bool",
        "Giriş fiyatının belirli yüzdesi altında çıkar.",
    ),
    SettingDef(
        "SUPPORT_STOP_LOSE", "Destek stop varsayılanı", "risk", "bool",
        "Destek seviyesi kırılırsa pozisyonu kapatır.",
    ),
    SettingDef(
        "TAKE_PROFIT", "Kâr al varsayılanı", "risk", "bool",
        "Hedef kâra ulaşınca satar.",
    ),

    # ---------------- Strateji limitleri ----------------
    SettingDef("STRATEGY_LIMIT_15M", "15m limiti", "limits", "int", "", min=0, max=200),
    SettingDef("STRATEGY_LIMIT_1H", "1h limiti", "limits", "int", "", min=0, max=200),
    SettingDef("STRATEGY_LIMIT_4H", "4h limiti", "limits", "int", "", min=0, max=200),
    SettingDef("STRATEGY_LIMIT_1D", "1d limiti", "limits", "int", "", min=0, max=200),

    # ---------------- Binance ----------------
    SettingDef(
        "BINANCE_API_KEY", "API anahtarı", "binance", "secret",
        "Salt okunur anahtar önerilir; işlem için gerekli izinleri ver.",
        secret=True, placeholder="••••••••",
    ),
    SettingDef(
        "BINANCE_API_SECRET", "API gizli anahtarı", "binance", "secret",
        "Panelde şifreli saklanır. Boş bırakılırsa mevcut değer korunur.",
        secret=True, placeholder="••••••••",
    ),
    SettingDef(
        "QUOTE_ASSET", "Ana parite", "binance", "str",
        "Bakiye ve parite hesaplarında kullanılır.", placeholder="USDT",
    ),

    # ---------------- Bildirimler ----------------
    SettingDef("MAIL_ENABLED", "E-posta bildirimi", "notifications", "bool", "İşlem ve hata bildirimlerini e-posta ile gönder."),
    SettingDef("TELEGRAM_ENABLED", "Telegram bildirimi", "notifications", "bool", "İşlem ve hata bildirimlerini Telegram ile gönder."),
    SettingDef("MAIL_FROM", "Gönderen e-posta", "notifications", "str", "", placeholder="ornek@gmail.com"),
    SettingDef("MAIL_PASSWORD", "E-posta uygulama şifresi", "notifications", "secret", "Gmail uygulama şifresi. Panelde şifreli saklanır.", secret=True),
    SettingDef("MAIL_TO", "Alıcı e-posta", "notifications", "str", "", placeholder="alici@ornek.com"),
    SettingDef("TELEGRAM_TOKEN", "Telegram bot token", "notifications", "secret", "BotFather'dan alınan token. Panelde şifreli saklanır.", secret=True),
    SettingDef("TELEGRAM_CHAT", "Telegram chat ID", "notifications", "str", "", placeholder="123456789"),

    # ---------------- Sistem ----------------
    SettingDef("AUTO_RESTART", "Çökmede otomatik yeniden başlat", "system", "bool", "Beklenmedik kapanan botu supervisor ayağa kaldırır."),
    SettingDef("HEARTBEAT_SECONDS", "Heartbeat aralığı (sn)", "system", "int", "Supervisor kontrol sıklığı.", min=2, max=300),
    SettingDef("MAX_JOBS", "Eşzamanlı iş limiti", "system", "int", "Backtest/tarama gibi ağır işlerin paralel sayısı.", min=1, max=16),
    SettingDef("AI_ENABLED", "Yapay zekâ özellikleri", "system", "bool", "AI Eğitimi sekmesini ve model eğitimini açar."),
    SettingDef(
        "EXIT_RETRY_SECONDS", "Başarısız satış tekrar aralığı (sn)", "system", "int",
        "Satış emri reddedilirse kaç saniye sonra tekrar deneneceği. Karar kalıcıdır; mum beklenmez.",
        min=2, max=300,
    ),
    SettingDef(
        "RECONCILE_SECONDS", "Periyodik mutabakat aralığı (sn)", "system", "int",
        "Canlı bot çalışırken borsa bakiyesiyle karşılaştırma sıklığı. 0 = kapalı.",
        min=0, max=3600,
    ),
    SettingDef(
        "RECONCILE_TOLERANCE_PCT", "Mutabakat toleransı (%)", "system", "float",
        "Nakit/miktar farkı bu yüzdeyi aşarsa uyarı verilir.", min=0.1, max=50,
    ),
    SettingDef(
        "RECONCILE_STOP_ON_MISMATCH", "Mutabakat farkında botu durdur", "system", "bool",
        "Tolerans aşılırsa bot işlem yapmayı bırakır (reconciliation_required).",
    ),
    SettingDef(
        "LIVE_LOCK_STALE_SECONDS", "Hesap kilidi bayatlama süresi (sn)", "system", "int",
        "Canlı emir kilidi bu süreden eskiyse (süreç çöktüyse) kırılır.", min=30, max=3600,
    ),
)

BY_KEY: Dict[str, SettingDef] = {item.key: item for item in SETTINGS}

# config.Settings içinde özel olarak hesaplanan anahtarlar
COMPUTED_KEYS = frozenset({"DEFAULT_RISK", "STRATEGY_LIMITS"})

# Sadece okunur / panelden düzenlenmeyen anahtarlar
READONLY_KEYS = frozenset(
    {
        "APP_NAME",
        "HOST",
        "PORT",
        "SECRET_KEY",
        "SESSION_HOURS",
        "COOKIE_SECURE",
        "ADMIN_USER",
        "ADMIN_PASSWORD",
        "SUPPORTED_PERIODS",
        "HEARTBEAT_TIMEOUT_SECONDS",
    }
)
