# TradeAIBot – Yeniden Yapılandırma Planı

> Durum: **Uygulandı** (Faz 0–5 tamamlandı, AI profili opsiyonel)
> Kapsam: Docker + Web arayüzü + görsel strateji oluşturucu + veri tutarlılığı

Uygulama durumu için `README.md` dosyasına bakın. Testler: `pytest tests -q` → 16 test.

---

## 0. Onaylanan Kararlar

| Konu | Karar |
|------|-------|
| Web katmanı | **FastAPI + Uvicorn** |
| İşlem modu | **Varsayılan test (paper)**, istenildiğinde kontrollü şekilde canlıya geçiş |
| AI özellikleri | **Ayrı Docker profili** (`ai`), varsayılan kurulumda yer almaz |
| Erişim güvenliği | **Kullanıcı adı + şifre ile giriş** (hash'li, oturumlu) |
| Strateji | Hazır stratejiler korunur + **web'den görsel kural oluşturucu** |
| CLI | Tüm özellikler web'e taşınır, CLI kaldırılmaz (fallback olarak kalır) |
| İlk sürüm | **Dar kapsam + çalışan dikey dilim**, sonra genişletme |

---

## 1. Mevcut Durum Özeti

- `main.py` → 26 seçenekli interaktif CLI
- `Trade.py` → periyot bazlı alım-satım döngüsü
- `Tarama.py` → periyot bazlı piyasa tarama
- `entrypoint.py` → Docker içinde periyotları subprocess ile başlatır
- `Tmux/*.sh` + systemd → süreçleri ayakta tutar
- Ayarlar `.env` içinde; botlar çalışırken `.env`'i **değiştiriyor**
- Durumlar `Trade_Durumu/*.json`, loglar `Log/*.log`

Hesaplama katmanı (`Indikator`, `Stratejiler`, `Backtest`) değerli ve **korunacak**.

---

## 2. Tespit Edilen Kritik Sorunlar

| # | Sorun | Etki |
|---|-------|------|
| 1 | `.env` yok; `glob(".env*")` ilk bulduğu dosyayı yükler | Yanlış/placeholder anahtarla çalışma |
| 2 | Botlar çalışırken `.env`'i değiştirir | Web + çoklu bot ile yarış koşulu |
| 3 | Durdurma dosyası kök dizine yazılıyor, `Trade_Durumu/` altında aranıyor | Durdurma güvenilmez |
| 4 | Durum dosyası yalnızca periyot adıyla | Aynı periyotta ikinci bot çakışır |
| 5 | `get_strategys()` → `Data/Strategy/strategys.json`, `strategy_analyze_save()` → `Data/strategys.json` | Strateji güncellemesi etkisiz kalabilir |
| 6 | `main.py` `AI.main()` çağırıyor, `import AI` kaldırılmış | AI menüsü hata veriyor |
| 7 | `exchangeInfo` her çağrıda API'ye gidiyor | Rate-limit riski |
| 8 | Aynı log dosyasına çoklu süreç yazıyor | Log bozulması |
| 9 | Gerçek emir sonucu doğrulanmıyor | Hesap ile kayıt ayrışması |
| 10 | TensorFlow/Keras/Seaborn/ydata-profiling zorunlu | Ağır imaj |
| 11 | Bazı indikatörler farklı uzunlukta çıktı döndürüyor | Kural motorunda mum kayması |

---

## 3. Hedef Mimari

```
Docker Compose
└── tradeai (tek servis)
    ├── Web UI (vanilla HTML/CSS/JS)
    ├── FastAPI REST + SSE
    ├── Auth (oturum, CSRF, kilitleme)
    ├── Supervisor (bot süreç yönetimi)
    ├── JobRunner (backtest / tarama / analiz)
    ├── Scheduler (periyodik işler)
    └── SQLite (WAL)  data/tradeai.db

Volumes: data/  logs/  state/
Opsiyonel: ai servisi (profile: ai)
```

- Tmux ve systemd kaldırılır.
- Süreç yönetimini kendi `Supervisor` sınıfımız yapar.
- Redis/Celery/Node gibi dış bağımlılık yok.

---

## 4. Dizin Yapısı

```
TradeAIBot/
├── app/
│   ├── main.py               # FastAPI uygulaması
│   ├── config.py             # .env + ayarlar (tek kaynak)
│   ├── db.py                 # SQLite, migration, WAL
│   ├── models.py             # Bot, Trade, Position, Job, Strategy
│   ├── security.py           # şifre hash, oturum, CSRF, rate limit
│   ├── supervisor.py         # bot süreç yönetimi, heartbeat, restart
│   ├── bot_runner.py         # tek bot süreci
│   ├── job_runner.py         # backtest/tarama/analiz işleri
│   ├── notifications.py      # mail / telegram sarmalayıcı
│   ├── strategies/
│   │   ├── registry.py       # indikatör kataloğu + adaptörler
│   │   ├── compiler.py       # DSL → CompiledStrategy
│   │   ├── builtin.py        # mevcut Stratejiler.py köprüsü
│   │   └── plugins/          # opsiyonel .py eklentileri
│   └── api/
│       ├── auth.py
│       ├── bots.py
│       ├── trades.py
│       ├── strategies.py
│       ├── analysis.py
│       ├── settings.py
│       └── system.py
├── core/                     # mevcut hesaplama kodu (taşınacak)
│   ├── indikator.py
│   ├── stratejiler.py
│   ├── binance_client.py
│   ├── backtest.py
│   └── tarama.py
├── web/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── data/                     # kalıcı (volume)
├── logs/
├── state/
├── tests/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt          # çekirdek (hafif)
├── requirements-ai.txt       # AI profili
└── PLAN.md
```

> Geçiş sırasında eski dosyalar silinmez; `core/` altında uyumluluk katmanı bırakılır.

---

## 5. Bot Yaşam Döngüsü

### Model

```json
{
  "id": "bot_1h_custom_01",
  "name": "1h RSI Dip + EMA",
  "type": "trade",
  "mode": "paper",
  "period": "1h",
  "strategies": [{ "id": "custom_rsi_ema", "version": 3 }],
  "coins": ["BTCUSDT", "ETHUSDT"],
  "cash": 100,
  "risk": {
    "dynamic_stop": false,
    "static_stop": true,
    "support_stop": true,
    "take_profit": true,
    "max_candles": 0
  },
  "status": "running",
  "pid": 1234,
  "started_at": "...",
  "last_heartbeat": "..."
}
```

### Akış

1. Web `POST /api/bots` → bot tanımı DB'ye yazılır.
2. `Supervisor` → `python -m app.bot_runner --bot-id ...` başlatır.
3. Bot 5 sn'de bir heartbeat yazar.
4. Web canlı durumu heartbeat + SQLite'tan okur.
5. Durdurma → `SIGTERM` → bot pozisyonu güvenli kapatır → çıkar.
6. Çökme → supervisor yeniden başlatır (bot bazında açık/kapalı).
7. Aynı bot iki kez başlatılamaz (PID + lock dosyası).

### Test → Canlı Geçiş (güvenli akış)

Canlı işlem **dört kilitle** korunur:

1. `.env` içinde `LIVE_TRADING_ENABLED=true` olmalı.
2. Web'de global **"Canlı işlem kilidi"** açılmalı (Ayarlar → Güvenlik).
3. Botu canlıya alırken şifre tekrar sorulur + onay metni yazılır.
4. Her bot ayrıca `mode: live` olarak işaretlenmeli.

Geçiş adımları:
- Çalışan test botu **önce durdurulur** (açık pozisyon yoksa).
- Binance hesabı ile yerel ledger **mutabakat** edilir.
- Uyuşmazlık yoksa bot `live` modda yeniden başlatılır.
- Test modundaki geçmiş K/Z ile canlı K/Z ayrı raporlanır.

> Çalışan botun modu havada değiştirilmez; bu, hesap tutarlılığı için bilinçli bir kısıttır.

---

## 6. Görsel Strateji Oluşturucu

### 6.1 Strateji Tanımı

```json
{
  "id": "custom_rsi_ema",
  "name": "RSI Dip + EMA Trend",
  "version": 3,
  "periods": ["15m", "1h"],
  "buy": {
    "logic": "AND",
    "conditions": [
      { "left": { "type": "indicator", "id": "RSI", "params": { "length": 14 }, "output": "value" },
        "op": "lt",
        "right": { "type": "constant", "value": 30 } },
      { "left": { "type": "price", "field": "close" },
        "op": "crosses_above",
        "right": { "type": "indicator", "id": "EMA", "params": { "length": 50 }, "output": "value" } }
    ]
  },
  "sell": {
    "logic": "OR",
    "conditions": [
      { "left": { "type": "indicator", "id": "RSI", "params": { "length": 14 }, "output": "value" },
        "op": "gt",
        "right": { "type": "constant", "value": 70 } }
    ]
  }
}
```

### 6.2 Yapı Taşları

**Operand türleri**
- `price`: close, open, high, low, hl2, hlc3, ohlc4
- `volume`: volume_coin, volume_usdt, hacim SMA
- `indicator`: indikatör + parametre + çıktı
- `constant`: sabit sayı
- `offset`: N mum önceki değer
- `math`: toplam / fark / oran / yüzde fark

**Operatörler**
- Karşılaştırma: `>`, `>=`, `<`, `<=`, `==`, `!=`
- Kesişim: `crosses_above`, `crosses_below`
- Yön: `rising`, `falling`, `rising_for_n`, `falling_for_n`
- Aralık: `between`, `outside`
- Yüzde: `pct_change_gt`, `pct_change_lt`
- Zaman: `within_last_n`

**Mantık**
- `AND`, `OR`, `NOT`, iç içe gruplar

### 6.3 İndikatör Kataloğu (ilk sürüm)

EMA, SMA, BB (upper/mid/lower/width/percent_b), RSI, MACD (macd/signal/hist), ATR (value/atr_pct), ADX (adx/+di/-di), Stochastic RSI (k/d), Ichimoku, Donchian, SuperTrend, CCI, MFI, Momentum, Parabolic SAR.

İkinci tur: FDI, VAMA, VMZI, DMO, TSO, AlphaTrend, BBTrend, Squeeze, SMC, SignalMA, PMAI, Destek/Direnç.

**Zorunlu normalize:** Tüm indikatör çıktıları giriş uzunluğunda, başları `None` olacak şekilde hizalanır. Aksi halde sinyal yanlış muma düşer.

### 6.4 Compiler

```python
class CompiledStrategy:
    id: str
    name: str
    version: int
    warmup: int

    def buy_signal(self, data) -> bool
    def sell_signal(self, data) -> bool
    def explain(self, data) -> dict
```

- Değerlendirme **kapanmış mum** üzerinde (mevcut `[-2]` mantığı korunur).
- Aynı indikatör+parametre bir kez hesaplanır (cache).
- `warmup` yetersizse bot başlamaz, backtest uyarı verir.
- Tanım + sürüm hash'i deterministik.

### 6.5 Alım / Satım Ayrımı

- `buy` → pozisyon yokken değerlendirilir
- `sell` → pozisyon açıkken değerlendirilir
- `sell` tanımlı değilse eski davranış (SELL sinyali) korunur
- Risk kuralları satıştan bağımsız: dinamik/statik/destek stop, take-profit, zaman aşımı

### 6.6 Web Ekranı

1. Genel bilgiler + şablon seçimi (boş, RSI dip, EMA kesişimi, BB breakout, MACD, SuperTrend)
2. Alım kuralları (koşul ekle, grup, AND/OR, canlı örnek değer, sürükle-bırak)
3. Satım kuralları
4. Risk ayarları
5. Doğrulama paneli (eksik parametre, warmup, çelişki, isim çakışması)
6. Önizleme: son mum koşul dökümü + geçmiş sinyal testi
7. Kaydet / sürümle / yayınla / arşivle / kopyala

Hazır stratejiler "şablon olarak kopyala" ile özelleştirilebilir.

### 6.7 Backtest – Canlı Tutarlılığı

- Aynı `CompiledStrategy` motoru ikisinde de kullanılır.
- Sinyal zamanlaması birebir eşleşir.
- Komisyon (varsayılan %0.1) + slippage (%0.05) backtest'e dahil.
- **Parity testi**: aynı veride backtest ve canlı motor sinyalleri karşılaştırılır; fark varsa test kırılır.
- Her sinyal `signal_events` tablosuna koşul dökümüyle yazılır.

### 6.8 Güvenlik Sınırı

- Kural motoru `eval` **kullanmaz**; whitelist tabanlı değerlendirici.
- Web'den serbest Python çalıştırma yok.
- Opsiyonel eklenti: `app/strategies/plugins/*.py` elle konur, web'de listelenir.
- Backtest/tarama ayrı süreçte; eşzamanlı job limiti (varsayılan 2).

---

## 7. Veri Modeli (SQLite, WAL)

```sql
users(id, username, password_hash, role, failed_attempts, locked_until, created_at)
sessions(id, user_id, token_hash, expires_at, created_at)
bots(id, name, type, mode, period, config_json, status, pid, created_at, updated_at)
bot_runs(id, bot_id, config_snapshot, started_at, stopped_at, exit_reason)
trades(id, bot_id, run_id, coin, side, quantity, price, fee, order_id, client_order_id, mode, created_at)
positions(id, bot_id, coin, quantity, entry_price, stop, target, opened_at, closed_at)
pnl_snapshots(id, bot_id, total_value, cash, pnl, created_at)
jobs(id, type, params_json, status, result_json, started_at, finished_at)
events(id, bot_id, level, message, created_at)
strategies(id, name, definition_json, version, status, created_at, updated_at)
strategy_versions(strategy_id, version, definition_json, created_at)
strategy_backtests(id, strategy_id, version, coin, period, start_date, end_date, metrics_json, created_at)
signal_events(id, bot_id, strategy_id, version, coin, period, candle_time, decision, conditions_json, values_json, created_at)
settings(key, value, updated_at)
```

- JSON durum yazımları atomik (`tempfile + os.replace`).
- Bot başına ayrı state: `state/{bot_id}.json`.
- Eski `Log/islem_gecmisi.log` kayıtları best-effort `trades` tablosuna aktarılır.

---

## 8. REST API

```
POST   /api/auth/login
POST   /api/auth/logout
GET    /api/auth/me

GET    /api/health
GET    /api/system

GET    /api/bots
POST   /api/bots
GET    /api/bots/{id}
PATCH  /api/bots/{id}
POST   /api/bots/{id}/start
POST   /api/bots/{id}/stop
POST   /api/bots/{id}/restart
POST   /api/bots/{id}/promote-live
GET    /api/bots/{id}/logs          # SSE
GET    /api/bots/{id}/trades
GET    /api/bots/{id}/signals

GET    /api/indicators
GET    /api/strategies
POST   /api/strategies
PUT    /api/strategies/{id}
POST   /api/strategies/{id}/validate
POST   /api/strategies/{id}/preview
POST   /api/strategies/{id}/backtest
GET    /api/strategies/{id}/backtests
GET    /api/strategies/{id}/versions
POST   /api/strategies/{id}/activate
POST   /api/strategies/{id}/archive
POST   /api/strategies/{id}/duplicate

GET    /api/trades
GET    /api/positions
GET    /api/pnl
POST   /api/analysis/scan
POST   /api/analysis/market
POST   /api/analysis/indicators
POST   /api/analysis/strategy-values
POST   /api/analysis/support-resistance
POST   /api/analysis/coinlist
POST   /api/analysis/coinlist-sort
POST   /api/analysis/monthly
POST   /api/analysis/buy-result

GET    /api/settings
PUT    /api/settings
POST   /api/danger/close-all
POST   /api/danger/full-cash
POST   /api/danger/close-position
```

---

## 9. Web Arayüzü

1. **Dashboard** – botlar, heartbeat, bakiye, açık pozisyon, K/Z, son olaylar
2. **Botlar** – sihirbaz, başlat/durdur/yeniden başlat, canlı log (SSE), pozisyon, geçmiş
3. **Stratejiler** – katalog, görsel oluşturucu, backtest, sürümler
4. **Tarama** – periyot seç, BUY/SELL tablosu, bildirim anahtarı
5. **Analiz** – indikatör/strateji değerleri, destek-direnç, piyasa durumu, aylık sonuç
6. **İşlem Geçmişi** – filtreli ledger, K/Z özeti, CSV/Excel indirme
7. **Ayarlar** – bildirim, risk limitleri, coin listesi, strateji limitleri, canlı kilit
8. **Sistem** – CPU/RAM/disk, sağlık, log seviyesi

### CLI → Web eşleme

| CLI | Web |
|-----|-----|
| 0 Veri seti | Analiz → Veri seti |
| 1 Backtest kaydet | Stratejiler → sonuç kaydet |
| 2 İndikatör test | Analiz → indikatör testi |
| 3 Backtest grafik | Stratejiler → backtest |
| 4 Tarama | Tarama |
| 5 Trade | Botlar |
| 6–7 Coin değerleri | Analiz |
| 8 Cihaz | Sistem |
| 9 Piyasa durumu | Analiz |
| 10 Coinlist | Ayarlar |
| 11 İşlem geçmişi | İşlem Geçmişi |
| 12 Coinlist sırala | Ayarlar |
| 13–14 Strategys | Stratejiler |
| 15 Buy verenler | Tarama |
| 16 Destek/direnç | Analiz |
| 17–18 Acil işlemler | Ayarlar → tehlikeli |
| 19 Buy result | İşlem Geçmişi |
| 20–23 Grafik/aylık/pozisyon | Dashboard / Analiz |
| 24–25 AI | AI profili (opsiyonel) |

---

## 10. Kimlik Doğrulama ve Güvenlik

- Kullanıcı adı + şifre.
- Şifre hash: **stdlib `hashlib.scrypt`** (ek bağımlılık yok).
- Oturum: HMAC ile imzalı, `HttpOnly`, `SameSite=Lax` cookie.
- CSRF: durum değiştiren isteklerde token zorunlu.
- Giriş kilidi: 5 hatalı denemede 15 dakika kilit.
- Rate limit: login ve tehlikeli endpoint'lerde.
- İlk açılışta `ADMIN_USER` / `ADMIN_PASSWORD` ile kullanıcı oluşturulur; şifre değiştirme zorunlu.
- Canlı işlem ve tehlikeli işlemler için şifre tekrar doğrulama.
- Varsayılan olarak uygulama yalnızca `localhost`/yerel ağa yayınlanır; dışarı açmak kullanıcı tercihi + HTTPS uyarısı.

---

## 11. Docker

```yaml
services:
  tradeai:
    build: .
    container_name: tradeai
    restart: unless-stopped
    ports:
      - "127.0.0.1:8080:8080"
    env_file: [.env]
    environment:
      - TZ=Europe/Istanbul
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./state:/app/state
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')"]
      interval: 30s
      timeout: 5s
      retries: 3

  ai:
    profiles: ["ai"]
    build:
      context: .
      dockerfile: Dockerfile.ai
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
```

- Çekirdek `requirements.txt`: fastapi, uvicorn, numpy, pandas, requests, python-dotenv, python-binance, openpyxl, matplotlib.
- `requirements-ai.txt`: tensorflow, keras, scikit-learn, joblib, seaborn, ydata-profiling, plotly.
- AI profili yokken AI stratejisi ve menüleri arayüzde pasif görünür.

---

## 12. Veri Tutarlılığı

1. SQLite tek doğruluk kaynağı; loglar ikincil.
2. Gerçek emirlerde `clientOrderId`; idempotency.
3. Emir sonrası gerçek miktar/fiyat Binance'ten doğrulanır.
4. Bot başlangıcında bakiye mutabakatı; uyuşmazlıkta `reconciliation_required`.
5. Test ve canlı K/Z ayrı raporlanır.
6. Strateji sürümü bot başlatmada sabitlenir; güncelleme çalışan botu etkilemez.
7. Tüm sinyaller koşul dökümüyle kaydedilir.
8. Atomik dosya yazımı + bot başına kilit.

---

## 13. Fazlar

| Faz | İçerik | Süre |
|-----|--------|------|
| 0 | Yedek, branch, `.env` düzeltmesi, `.env.example`, smoke test | 0.5 gün |
| 1 | config, db, models, supervisor, bot_runner, indicator registry, compiler iskeleti | 1–2 gün |
| 2 | FastAPI, auth, bot CRUD/start/stop, dashboard, SSE log | 1–2 gün |
| 3 | Tüm CLI özelliklerinin web'e taşınması | 2–3 gün |
| 3.5 | Görsel strateji oluşturucu + backtest paneli + entegrasyon | 2–3 gün |
| 4 | Veri tutarlılığı, mutabakat, parity testleri, sinyal kaydı | 1–2 gün |
| 5 | Docker, testler, temizlik, README | 1 gün |
| 6 | AI profili (opsiyonel) | 1–2 gün |

---

## 14. Kabul Kriterleri

1. `docker compose up -d` sonrası `http://localhost:8080` açılıyor, giriş çalışıyor.
2. Web'den farklı periyot/stratejilerle birden fazla bot başlatılabiliyor.
3. Bot durumu, PID, heartbeat, pozisyon, K/Z canlı görülebiliyor.
4. Durdurmada pozisyon güvenli kapanıyor, süreç kalıntısı kalmıyor.
5. Container yeniden başlayınca botlar ve state korunuyor.
6. CLI'deki 26 özellik web'den erişilebilir.
7. Aynı bot iki kez başlatılamıyor; aynı emir iki kez gitmiyor.
8. Gerçek bakiye ile ledger uyuşmazsa uyarı veriyor.
9. Çalışma sırasında `.env` değiştirilmiyor.
10. Tmux/systemd olmadan çalışıyor.
11. Web'den kod yazmadan strateji oluşturulabiliyor.
12. Alım ve satım kuralları ayrı tanımlanabiliyor.
13. İndikatör parametre/çıktıları arayüzden seçilebiliyor.
14. Kural doğrulama hataları anlaşılır gösteriliyor.
15. Özel strateji backtest edilebiliyor; grafik + metrikler görünüyor.
16. Özel strateji ile bot başlatılabiliyor.
17. Backtest sinyali = canlı sinyal (parity testi geçiyor).
18. Her sinyalin koşul dökümü kayıtlı.
19. Strateji yeni sürümü çalışan botu etkilemiyor.
20. Bozuk strateji botu durduruyor; açık pozisyon etkilenmiyor.
21. Test modu varsayılan; canlıya geçiş dört kilitli onayla yapılıyor.
22. AI olmadan çekirdek imaj çalışıyor.

---

## 15. Kapsam Dışı / Riskler

- Web'den serbest Python kodu çalıştırma yok (güvenlik).
- Çalışan botun modu havada değişmez.
- İlk sürümde çoklu periyotlu birleşik kural yok (ikinci tur).
- Binance API kesintilerinde bot yeniden deneme + bildirim yapar; garanti değildir.
- Geçmiş log aktarımı best-effort; kesin muhasebe yeni ledger'dan itibaren.
