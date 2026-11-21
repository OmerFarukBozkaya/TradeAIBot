"""Sembol çözümleme ve hazır sembol kataloğu.

Kullanıcı sembolü tek alan olarak girebilir (``XAUUSD``, ``AAPL``,
``GARAN.IS``, ``TEFAS:AFT``) veya arayüzden varlık sınıfı seçebilir.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

ASSET_CLASSES = [
    {"id": "crypto", "label": "Kripto", "provider": "binance", "live": True},
    {"id": "metal", "label": "Altın / Gümüş", "provider": "yahoo", "live": False},
    {"id": "stock", "label": "Hisse", "provider": "yahoo", "live": False},
    {"id": "fund", "label": "TEFAS Fonu", "provider": "tefas", "live": False},
]

# Kullanıcıya gösterilen altın/gümüş kısaltmaları -> Yahoo sembolü.
METALS: Dict[str, Dict[str, str]] = {
    "XAUUSD": {"native": "GC=F", "label": "Altın (vadeli, GC=F)"},
    "XAUUSDSPOT": {"native": "XAUUSD=X", "label": "Altın (spot, XAU/USD)"},
    "XAGUSD": {"native": "SI=F", "label": "Gümüş (vadeli, SI=F)"},
    "XAGUSDSPOT": {"native": "XAGUSD=X", "label": "Gümüş (spot, XAG/USD)"},
    "XPTUSD": {"native": "PL=F", "label": "Platin (vadeli)"},
    "XPDUSD": {"native": "PA=F", "label": "Paladyum (vadeli)"},
}

STOCK_EXAMPLES = [
    ("AAPL", "Apple"), ("MSFT", "Microsoft"), ("NVDA", "NVIDIA"),
    ("TSLA", "Tesla"), ("AMZN", "Amazon"), ("GOOGL", "Alphabet"),
    ("META", "Meta"), ("SPY", "S&P 500 ETF"), ("QQQ", "Nasdaq 100 ETF"),
    ("GARAN.IS", "Garanti BBVA"), ("THYAO.IS", "Türk Hava Yolları"),
    ("ASELS.IS", "Aselsan"), ("KCHOL.IS", "Koç Holding"),
    ("SISE.IS", "Şişecam"), ("EREGL.IS", "Erdemir"),
    ("AKBNK.IS", "Akbank"), ("TUPRS.IS", "Tüpraş"),
    ("BIMAS.IS", "BİM"), ("FROTO.IS", "Ford Otosan"),
]

TEFAS_EXAMPLES = [
    ("AFT", "Ak Portföy Yeni Teknolojiler"), ("MAC", "Marmara Capital"),
    ("TTE", "Türkiye Teknoloji"), ("GAF", "Garanti Portföy"),
    ("AFA", "Ak Portföy"), ("TCD", "Tacirler Portföy"),
]

# Arama kutusu boşken gösterilen popüler kripto pariteleri.
CRYPTO_POPULAR = [
    ("BTCUSDT", "Bitcoin"), ("ETHUSDT", "Ethereum"), ("BNBUSDT", "BNB"),
    ("SOLUSDT", "Solana"), ("XRPUSDT", "XRP"), ("ADAUSDT", "Cardano"),
    ("DOGEUSDT", "Dogecoin"), ("AVAXUSDT", "Avalanche"), ("LINKUSDT", "Chainlink"),
    ("DOTUSDT", "Polkadot"), ("TRXUSDT", "TRON"), ("TONUSDT", "Toncoin"),
    ("SUIUSDT", "Sui"), ("NEARUSDT", "NEAR"), ("APTUSDT", "Aptos"),
    ("ARBUSDT", "Arbitrum"), ("OPUSDT", "Optimism"), ("INJUSDT", "Injective"),
    ("PEPEUSDT", "Pepe"), ("SHIBUSDT", "Shiba Inu"), ("LTCUSDT", "Litecoin"),
    ("BCHUSDT", "Bitcoin Cash"), ("ATOMUSDT", "Cosmos"), ("FILUSDT", "Filecoin"),
    ("HBARUSDT", "Hedera"), ("ICPUSDT", "Internet Computer"), ("ETCUSDT", "Ethereum Classic"),
    ("XLMUSDT", "Stellar"), ("UNIUSDT", "Uniswap"), ("AAVEUSDT", "Aave"),
    ("BTCTRY", "Bitcoin / TL"), ("ETHTRY", "Ethereum / TL"),
]

_CRYPTO_QUOTES = (
    "USDT", "BUSD", "USDC", "FDUSD", "TUSD", "DAI", "TRY", "BTC", "ETH", "BNB",
)
_CRYPTO_RE = re.compile(r"^[A-Z0-9]{4,20}$")
_SYMBOL_RE = re.compile(r"^[A-Z0-9:._=/+-]{2,40}$")


@dataclass(frozen=True)
class SymbolInfo:
    symbol: str          # kullanıcıya gösterilen sembol
    provider: str        # binance | yahoo | tefas
    native: str          # sağlayıcıdaki gerçek sembol
    asset_class: str     # crypto | metal | stock | fund
    live_supported: bool
    label: str = ""

    def as_dict(self) -> Dict[str, str | bool]:
        return asdict(self)


def normalize_symbol(value: str) -> str:
    text = str(value or "").strip().upper().replace(" ", "")
    if not text:
        raise ValueError("Sembol boş olamaz")
    if not _SYMBOL_RE.match(text):
        raise ValueError(f"Geçersiz sembol: {value!r}")
    return text


def _looks_like_crypto(symbol: str) -> bool:
    if not _CRYPTO_RE.match(symbol):
        return False
    return any(symbol.endswith(quote) for quote in _CRYPTO_QUOTES)


def resolve_symbol(
    symbol: str,
    *,
    source: str = "auto",
    asset_class: str = "",
) -> SymbolInfo:
    """Sembolü sağlayıcı ve gerçek sembole çözer."""
    raw = normalize_symbol(symbol)
    source = str(source or "auto").strip().lower()
    asset_class = str(asset_class or "").strip().lower()

    if source == "tefas" or raw.startswith("TEFAS:") or asset_class == "fund":
        code = raw.split(":", 1)[-1]
        if not re.match(r"^[A-Z0-9]{2,10}$", code):
            raise ValueError(f"Geçersiz TEFAS fon kodu: {code}")
        return SymbolInfo(
            symbol=f"TEFAS:{code}", provider="tefas", native=code,
            asset_class="fund", live_supported=False,
            label=f"TEFAS {code}",
        )

    if source == "yahoo" or asset_class in {"metal", "stock"} or raw in METALS:
        if raw in METALS:
            info = METALS[raw]
            return SymbolInfo(
                symbol=raw, provider="yahoo", native=info["native"],
                asset_class="metal", live_supported=False, label=info["label"],
            )
        if asset_class == "metal":
            # Altın/gümüş sınıfında kısa adlar (ALTIN, GUMUS) sağlayıcıda yok.
            # Yalnızca Yahoo'nun gerçek sembol biçimlerine izin ver.
            if not (raw.endswith(("=F", "=X")) or raw.startswith("^")):
                raise ValueError(
                    "Altın/gümüş için XAUUSD, XAGUSD, XAUUSDSPOT, XAGUSDSPOT "
                    "veya GC=F, SI=F gibi bir sembol kullanın."
                )
            return SymbolInfo(
                symbol=raw, provider="yahoo", native=raw,
                asset_class="metal", live_supported=False, label=raw,
            )
        return SymbolInfo(
            symbol=raw, provider="yahoo", native=raw,
            asset_class="stock", live_supported=False, label=raw,
        )

    if source == "binance" or asset_class == "crypto":
        return SymbolInfo(
            symbol=raw, provider="binance", native=raw,
            asset_class="crypto", live_supported=True, label=raw,
        )

    # auto
    if _looks_like_crypto(raw):
        return SymbolInfo(
            symbol=raw, provider="binance", native=raw,
            asset_class="crypto", live_supported=True, label=raw,
        )
    if raw.endswith(".IS"):
        return SymbolInfo(
            symbol=raw, provider="yahoo", native=raw,
            asset_class="stock", live_supported=False, label=raw,
        )
    if raw.endswith((".US", ".DE", ".L", ".PA", ".AS", ".MI", ".MC")):
        return SymbolInfo(
            symbol=raw, provider="yahoo", native=raw,
            asset_class="stock", live_supported=False, label=raw,
        )
    if raw.isalpha() and len(raw) <= 5:
        # Hisse sembolleri genelde kısa ve harftir; yine de Binance'e düşmek
        # yerine Yahoo'ya yönlendir.
        return SymbolInfo(
            symbol=raw, provider="yahoo", native=raw,
            asset_class="stock", live_supported=False, label=raw,
        )

    # Bilinmeyen biçim: kripto kabul et (Binance hata verirse mesaj gösterilir).
    return SymbolInfo(
        symbol=raw, provider="binance", native=raw,
        asset_class="crypto", live_supported=True, label=raw,
    )


def is_live_symbol(symbol: str) -> bool:
    """Canlı işlem yalnızca Binance kripto sembolleri için desteklenir."""
    try:
        info = resolve_symbol(symbol)
    except ValueError:
        return False
    return info.provider == "binance" and bool(_CRYPTO_RE.match(info.symbol))


def catalog() -> Dict[str, List[Dict[str, str]]]:
    metals = [
        {"symbol": key, "label": value["label"], "native": value["native"]}
        for key, value in METALS.items()
    ]
    stocks = [{"symbol": sym, "label": label} for sym, label in STOCK_EXAMPLES]
    funds = [{"symbol": f"TEFAS:{code}", "label": f"{code} - {label}"} for code, label in TEFAS_EXAMPLES]
    crypto = [
        {"symbol": sym, "label": f"{label} ({sym})"}
        for sym, label in dict.fromkeys(CRYPTO_POPULAR)
    ]
    return {
        "classes": ASSET_CLASSES,
        "metals": metals,
        "stocks": stocks,
        "funds": funds,
        "crypto": crypto,
        "periods": ["1m", "5m", "15m", "30m", "45m", "1h", "2h", "4h", "6h", "12h", "1d", "3d", "1w", "1M", "1y"],
    }


# ---------------------------------------------------------------------------
# Sembol arama
# ---------------------------------------------------------------------------
_CACHE: Dict[str, Any] = {}
_CACHE_TIME: Dict[str, float] = {}


def _fold(text: str) -> str:
    """Türkçe karakterleri sadeleştirip büyük harfe çevirir (arama için)."""
    value = str(text or "")
    for source, target in (
        ("İ", "I"), ("ı", "I"), ("Ş", "S"), ("ş", "S"),
        ("Ğ", "G"), ("ğ", "G"), ("Ü", "U"), ("ü", "U"),
        ("Ö", "O"), ("ö", "O"), ("Ç", "C"), ("ç", "C"),
        ("Â", "A"), ("â", "A"),
    ):
        value = value.replace(source, target)
    return re.sub(r"\s+", " ", value).strip().upper()


def _cached(key: str, ttl: float):
    import time

    stamp = _CACHE_TIME.get(key, 0.0)
    if stamp and time.time() - stamp < ttl:
        return _CACHE.get(key)
    return None


def _store(key: str, value):
    import time

    _CACHE[key] = value
    _CACHE_TIME[key] = time.time()
    return value


def _binance_symbols() -> List[Dict[str, str]]:
    """Binance'te işlem gören SPOT pariteleri (6 saat önbellek)."""
    cached = _cached("binance", 6 * 3600)
    if cached is not None:
        return cached
    try:
        import requests

        response = requests.get(
            "https://api.binance.com/api/v3/exchangeInfo",
            params={"permissions": "SPOT"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []
    items: List[Dict[str, str]] = []
    for row in payload.get("symbols") or []:
        try:
            if str(row.get("status")) != "TRADING":
                continue
            if "SPOT" not in (row.get("permissions") or ["SPOT"]):
                continue
            symbol = str(row["symbol"])
            base = str(row.get("baseAsset") or "")
            quote = str(row.get("quoteAsset") or "")
            if quote not in {"USDT", "TRY", "BTC", "ETH", "BNB", "FDUSD", "USDC"}:
                continue
            items.append(
                {
                    "symbol": symbol,
                    "label": f"{base} / {quote}",
                    "asset_class": "crypto",
                    "provider": "binance",
                }
            )
        except (KeyError, TypeError):
            continue
    return _store("binance", items)


def _tefas_funds() -> List[Dict[str, str]]:
    """TEFAS yatırım ve borsa yatırım fonları (12 saat önbellek)."""
    cached = _cached("tefas", 12 * 3600)
    if cached is not None:
        return cached
    import requests

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.tefas.gov.tr/",
    }
    items: List[Dict[str, str]] = []
    seen = set()

    def load(kind: str) -> List[Dict[str, Any]]:
        payload = {
            "dil": "TR", "fonTipi": kind, "kurucuKodu": None, "sfonTurKod": None,
            "fonTurAciklama": None, "islem": 1, "fonTurKod": None, "fonGrubu": None,
            "donemGetiri1a": "1", "donemGetiri3a": "1", "donemGetiri6a": "1",
            "donemGetiri1y": "1", "donemGetiriyb": "1", "donemGetiri3y": "1",
            "donemGetiri5y": "1", "basTarih": None, "bitTarih": None,
            "calismaTipi": 2, "getiriOrani": "1",
        }
        try:
            response = requests.post(
                "https://www.tefas.gov.tr/api/funds/fonGetiriBazliBilgiGetir",
                json=payload, headers=headers, timeout=12,
            )
            response.raise_for_status()
            return (response.json() or {}).get("resultList") or []
        except Exception:
            return []

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=3) as pool:
        batches = list(pool.map(load, ("YAT", "BYF", "EMK")))
    for rows in batches:
        for row in rows:
            code = str(row.get("fonKodu") or "").strip().upper()
            if not code or code in seen:
                continue
            seen.add(code)
            items.append(
                {
                    "symbol": f"TEFAS:{code}",
                    "label": f"{code} - {row.get('fonUnvan') or ''}".strip(" -"),
                    "asset_class": "fund",
                    "provider": "tefas",
                }
            )
    return _store("tefas", items)


def _yahoo_search(query: str, limit: int = 12) -> List[Dict[str, str]]:
    key = f"yahoo:{_fold(query)}:{int(limit)}"
    cached = _cached(key, 300)
    if cached is not None:
        return cached
    try:
        import requests

        response = requests.get(
            "https://query1.finance.yahoo.com/v1/finance/search",
            params={"q": query, "quotesCount": limit, "newsCount": 0, "listsCount": 0},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
                "Accept": "application/json,text/plain,*/*",
            },
            timeout=8,
        )
        response.raise_for_status()
        rows = (response.json() or {}).get("quotes") or []
    except Exception:
        return []
    allowed = {"EQUITY", "ETF", "FUTURE", "INDEX", "CURRENCY"}
    items: List[Dict[str, str]] = []
    for row in rows:
        try:
            symbol = str(row.get("symbol") or "").strip().upper()
            kind = str(row.get("quoteType") or "").upper()
            if not symbol or kind not in allowed:
                continue
            name = row.get("shortname") or row.get("longname") or ""
            items.append(
                {
                    "symbol": symbol,
                    "label": str(name),
                    "asset_class": "stock",
                    "provider": "yahoo",
                    "kind": kind,
                }
            )
        except (KeyError, TypeError):
            continue
    return _store(key, items)


def _local_items() -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for key, info in METALS.items():
        items.append(
            {
                "symbol": key, "label": info["label"], "asset_class": "metal",
                "provider": "yahoo", "native": info["native"],
            }
        )
    for sym, label in STOCK_EXAMPLES:
        items.append(
            {"symbol": sym, "label": label, "asset_class": "stock", "provider": "yahoo"}
        )
    for code, label in TEFAS_EXAMPLES:
        items.append(
            {
                "symbol": f"TEFAS:{code}", "label": f"{code} - {label}",
                "asset_class": "fund", "provider": "tefas",
            }
        )
    for sym, label in CRYPTO_POPULAR:
        items.append(
            {
                "symbol": sym, "label": f"{label} ({sym})",
                "asset_class": "crypto", "provider": "binance",
            }
        )
    return items


def _decorate(item: Dict[str, str]) -> Dict[str, Any]:
    asset_class = item.get("asset_class") or "crypto"
    symbol = item.get("symbol") or ""
    return {
        "symbol": symbol,
        "label": item.get("label") or symbol,
        "asset_class": asset_class,
        "provider": item.get("provider") or {"crypto": "binance", "fund": "tefas"}.get(asset_class, "yahoo"),
        "live": asset_class == "crypto",
        "native": item.get("native") or symbol,
    }


def search_symbols(query: str = "", asset_class: str = "", limit: int = 25) -> List[Dict[str, Any]]:
    """Sembol arar: yerel katalog + Binance + Yahoo + TEFAS.

    ``query`` boşsa seçili varlık sınıfının popüler sembollerini döndürür.
    """
    from concurrent.futures import ThreadPoolExecutor

    text = _fold(query)
    cls = str(asset_class or "").strip().lower()
    if cls == "auto":
        cls = ""
    limit = max(1, min(int(limit), 50))

    local = [
        item for item in _local_items()
        if (not cls or item["asset_class"] == cls)
    ]
    if text:
        scored = []
        for item in local:
            hay = _fold(item["symbol"]) + " " + _fold(item["label"])
            if text in hay:
                rank = 0 if _fold(item["symbol"]).startswith(text) else 1
                scored.append((rank, item))
        scored.sort(key=lambda pair: pair[0])
        local = [item for _, item in scored]
    else:
        local = local[: max(limit, 10)]

    results: List[Dict[str, Any]] = [_decorate(item) for item in local]
    if not text:
        return results[:limit]
    # Tek harfte uzak sağlayıcıları yorma; yerel eşleşmeler yeterli.
    if len(text) < 2:
        return results[:limit]

    tasks = []
    if cls in ("", "crypto"):
        tasks.append(("binance", lambda: [
            item for item in _binance_symbols()
            if text in _fold(item["symbol"])
        ][: limit]))
    if cls in ("", "stock", "metal"):
        tasks.append(("yahoo", lambda: _yahoo_search(query, max(10, limit // 2))))
    if cls in ("", "fund"):
        tasks.append(("tefas", lambda: [
            item for item in _tefas_funds()
            if text in _fold(item["symbol"]) or text in _fold(item["label"])
        ][: limit]))

    remote: List[Dict[str, str]] = []
    if tasks:
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            for future in [pool.submit(fn) for _, fn in tasks]:
                try:
                    remote.extend(future.result(timeout=15) or [])
                except Exception:
                    continue

    seen = {item["symbol"] for item in results}
    for item in remote:
        symbol = item.get("symbol")
        if not symbol or symbol in seen:
            continue
        if cls and item.get("asset_class") != cls:
            if cls == "metal" and item.get("kind") in {"FUTURE", "CURRENCY"}:
                # Vadeli altın/gümüş kontratları da bu sınıfa kabul et.
                item = {**item, "asset_class": "metal"}
            else:
                # Yahoo araması "metal" seçiliyken hisse döndürebilir; filtrele.
                continue
        seen.add(symbol)
        results.append(_decorate(item))
        if len(results) >= limit:
            break
    return results[:limit]


def _class_provider(asset_class: str) -> Optional[str]:
    for item in ASSET_CLASSES:
        if item["id"] == asset_class:
            return str(item["provider"])
    return None
