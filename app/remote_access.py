"""Uzaktan erişim kapısı: cihaz anahtarı ve/veya istemci sertifikası.

Neden backend'de? Cloudflare Tunnel trafiği TLS'i **Cloudflare edge'de**
sonlandırır; uygulamaya HTTP olarak ulaşır. Bu yüzden uygulama, istemcinin
sertifikasını kendi başına göremez. İki gerçekçi yol vardır:

1. **Cihaz anahtarı (bu modül, Cloudflare'de ayar gerekmez)**
   Yerel ağda oturum açmış kullanıcı bir cihaz anahtarı üretir, telefona kurar.
   Dış ağdan gelen isteklerde anahtar (HttpOnly çerez veya ``X-Device-Key``)
   yoksa istek **hiçbir sayfaya ulaşmadan** "erişim yetkiniz yok" sayfası döner.

2. **Sertifika doğrulaması (Cloudflare'in iletmesi şartıyla)**
   Cloudflare'de bir *Transform Rule* ile ``cf.tls_client_auth.cert_verified``
   değeri bir başlığa yazılırsa (WAF kuralı gerekmez), uygulama bu başlığa
   bakarak sertifikasız isteği reddeder.

Kapı yalnızca ``REMOTE_ACCESS_HOST`` içindeki hostname'lerde çalışır; yerel ağ
(aynı LAN) erişimi varsayılan olarak serbesttir.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import ipaddress
import secrets
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app import db
from app.config import settings

# --- Sabitler -------------------------------------------------------------
TRUE_VALUES = {"1", "true", "yes", "on", "verified", "ok"}
KEY_PREFIX = "tk_"
KEY_BYTES = 32

# Giriş denemesi sınırı (bellek içi; süreç yeniden başlarsa sıfırlanır).
_ATTEMPT_WINDOW = 300.0
_ATTEMPT_LIMIT = 10
_attempts: Dict[str, List[float]] = {}
_last_deny_log: Dict[str, float] = {}


# --- İstek bağlamı --------------------------------------------------------
def request_host(request) -> str:
    """İsteğin hedefi: ``X-Forwarded-Host`` → ``Host``."""
    headers = getattr(request, "headers", {}) or {}
    forwarded = headers.get("x-forwarded-host") or ""
    host = forwarded.split(",")[0].strip() if forwarded else ""
    if not host:
        host = (headers.get("host") or "").strip()
    return host.split(":")[0].strip().lower()


def _ip_text(value: Any) -> str:
    try:
        return str(ipaddress.ip_address(str(value).strip()))
    except (ValueError, TypeError):
        return ""


def client_ip(request) -> str:
    """Gerçek istemci IP'si (Cloudflare/Tunnel başlıkları dahil)."""
    headers = getattr(request, "headers", {}) or {}
    # Cloudflare edge gerçek istemciyi burada verir; sahtelenemez (edge yazar).
    candidate = _ip_text(headers.get("cf-connecting-ip"))
    if candidate:
        return candidate
    forwarded = headers.get("x-forwarded-for") or ""
    if forwarded:
        for part in forwarded.split(","):
            candidate = _ip_text(part)
            if candidate:
                return candidate
    client = getattr(request, "client", None)
    return _ip_text(getattr(client, "host", "")) if client else ""


# Yerel ağ tanımı: yalnızca gerçek özel/loopback/link-local blokları.
# (Python'un `is_private` alanı 203.0.113.0/24 gibi TEST-NET bloklarını da
# "private" sayıyor; bu, dışarıdan gelen bir test IP'sini yanlışlıkla LAN
# kabul etmemize yol açardı.)
_LAN_NETWORKS = [
    ipaddress.ip_network(net)
    for net in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
]


def is_private_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(str(value))
    except ValueError:
        return False
    return any(ip in net for net in _LAN_NETWORKS if net.version == ip.version)


def via_cloudflare(request) -> bool:
    """İstek Cloudflare edge üzerinden mi geldi?

    Tunnel, isteği docker iç ağından (172.x) iletir; bu yüzden "özel IP =
    yerel ağ" varsayımı tek başına yanıltıcıdır. Cloudflare bu isteklere
    kendi başlıklarını ekler.
    """
    headers = getattr(request, "headers", {}) or {}
    return bool(
        headers.get("cf-connecting-ip")
        or headers.get("cf-ray")
        or (headers.get("cdn-loop") or "").lower().startswith("cloudflare")
    )


def is_lan_request(request) -> bool:
    """Yerel ağdan doğrudan (Cloudflare'e uğramadan) gelen istek mi?"""
    if via_cloudflare(request):
        return False
    return is_private_ip(client_ip(request))


# --- Yapılandırma ---------------------------------------------------------
def enabled_hosts() -> List[str]:
    raw = str(getattr(settings, "REMOTE_ACCESS_HOST", "") or "")
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def mode() -> str:
    value = str(getattr(settings, "REMOTE_ACCESS_MODE", "off") or "off").strip().lower()
    if value not in {"off", "key", "cert", "cert-or-key"}:
        return "off"
    return value


def gate_applies(request) -> bool:
    """Bu istek için kapı devrede mi? (mod açık + hostname listede)"""
    if mode() == "off":
        return False
    hosts = enabled_hosts()
    if not hosts:
        return False
    return request_host(request) in hosts


# --- Sertifika başlığı ----------------------------------------------------
def cert_verified(request) -> bool:
    """Cloudflare'in ilettiği sertifika doğrulama sonucu."""
    headers = getattr(request, "headers", {}) or {}
    header = str(getattr(settings, "REMOTE_CERT_HEADER", "cf-client-cert-verified")).lower()
    value = str(headers.get(header) or "").strip().lower()
    if value in TRUE_VALUES:
        return True
    # RFC 9440: istemci sertifikası iletildiyse bu başlık bulunur.
    if (headers.get("client-cert") or "").strip():
        return True
    if str(headers.get("x-client-verified") or "").strip().lower() in TRUE_VALUES:
        return True
    return False


# --- Cihaz anahtarları ----------------------------------------------------
def _hash(raw: str) -> str:
    return hashlib.sha256(str(raw or "").encode("utf-8")).hexdigest()


def create_key(name: str) -> Tuple[str, Dict[str, Any]]:
    """Yeni cihaz anahtarı üretir. Ham anahtar **yalnızca bir kez** döner."""
    label = (str(name or "").strip() or "Cihaz")[:60]
    raw = KEY_PREFIX + secrets.token_urlsafe(KEY_BYTES)
    key_id = f"dev_{uuid.uuid4().hex[:12]}"
    db.execute(
        "INSERT INTO device_keys(id,name,key_hash,created_at,revoked) VALUES(?,?,?,?,0)",
        (key_id, label, _hash(raw), db.utcnow()),
    )
    db.log_event(None, f"Cihaz anahtarı oluşturuldu: {label}", "warning")
    return raw, {
        "id": key_id,
        "name": label,
        "created_at": db.utcnow(),
        "prefix": raw[:10],
    }


def list_keys() -> List[Dict[str, Any]]:
    rows = db.rows(
        "SELECT id,name,created_at,last_used_at,last_ip,revoked FROM device_keys "
        "ORDER BY created_at DESC"
    )
    for row in rows:
        row["revoked"] = bool(row.get("revoked"))
    return rows


def revoke_key(key_id: str) -> bool:
    key_id = str(key_id or "").strip()
    if not key_id:
        return False
    row = db.row("SELECT name FROM device_keys WHERE id=?", (key_id,))
    if not row:
        return False
    db.execute("UPDATE device_keys SET revoked=1 WHERE id=?", (key_id,))
    db.log_event(None, f"Cihaz anahtarı iptal edildi: {row['name']}", "warning")
    return True


def verify_key(raw: str, ip: str = "") -> Optional[Dict[str, Any]]:
    """Anahtarı doğrular; geçerliyse kaydı döndürür. Sabit zamanlı karşılaştırma."""
    text = str(raw or "").strip()
    if not text.startswith(KEY_PREFIX):
        return None
    digest = _hash(text)
    row = db.row(
        "SELECT id,name,key_hash FROM device_keys WHERE revoked=0 AND key_hash=?",
        (digest,),
    )
    if not row:
        return None
    if not hmac.compare_digest(str(row["key_hash"]), digest):
        return None
    db.execute(
        "UPDATE device_keys SET last_used_at=?, last_ip=? WHERE id=?",
        (db.utcnow(), str(ip or "")[:60], row["id"]),
    )
    return {"id": row["id"], "name": row["name"]}


def key_from_request(request) -> str:
    """İstekteki cihaz anahtarı: ``X-Device-Key`` başlığı veya çerez."""
    headers = getattr(request, "headers", {}) or {}
    header = str(headers.get("x-device-key") or "").strip()
    if header:
        return header
    cookies = getattr(request, "cookies", {}) or {}
    name = str(getattr(settings, "DEVICE_COOKIE_NAME", "tradeai_device"))
    return str(cookies.get(name) or "").strip()


# --- Deneme sınırı --------------------------------------------------------
def _recent(ip: str) -> List[float]:
    now = time.time()
    stamps = [s for s in _attempts.get(ip, []) if now - s < _ATTEMPT_WINDOW]
    _attempts[ip] = stamps
    return stamps


def attempts_left(ip: str) -> int:
    return max(0, _ATTEMPT_LIMIT - len(_recent(ip)))


def record_attempt(ip: str) -> None:
    stamps = _recent(ip)
    stamps.append(time.time())
    _attempts[ip] = stamps


def rate_limited(ip: str) -> bool:
    return len(_recent(ip)) >= _ATTEMPT_LIMIT


def reset_attempts() -> None:
    _attempts.clear()
    _last_deny_log.clear()


# --- Karar ----------------------------------------------------------------
def check(request) -> Tuple[bool, str]:
    """``(izin_var_mı, neden)`` döndürür.

    neden: ``off`` | ``other-host`` | ``lan`` | ``cert`` | ``key`` | ``denied``
    """
    if not gate_applies(request):
        return True, "off" if mode() == "off" else "other-host"
    if getattr(settings, "REMOTE_ALLOW_LAN", True) and is_lan_request(request):
        return True, "lan"
    current = mode()
    if current in {"cert", "cert-or-key"} and cert_verified(request):
        return True, "cert"
    if current in {"key", "cert-or-key"}:
        row = verify_key(key_from_request(request), client_ip(request))
        if row:
            return True, "key"
    return False, "denied"


def log_denied(request) -> None:
    """Engellenen denemeyi en fazla dakikada bir kez kaydeder (DB şişmesin)."""
    ip = client_ip(request) or "?"
    now = time.time()
    if now - float(_last_deny_log.get(ip) or 0.0) < 60:
        return
    _last_deny_log[ip] = now
    try:
        db.log_event(
            None,
            f"Uzaktan erişim engellendi: {ip} → {request_host(request)}",
            "warning",
        )
    except Exception:  # noqa: BLE001 - log yazılamazsa istek yine engellenir
        pass


# --- HTML sayfaları -------------------------------------------------------
def _page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{html.escape(title)}</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
    background:#080d17; color:#e6edf7;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif; padding:22px; }}
  .card {{ width:100%; max-width:520px; background:#0d1524; border:1px solid #1e2b42;
    border-radius:16px; padding:28px 26px; box-shadow:0 18px 50px rgba(0,0,0,.45); }}
  .badge {{ display:inline-flex; align-items:center; gap:8px; font-size:12px; letter-spacing:.4px;
    text-transform:uppercase; color:#fca5a5; background:rgba(248,113,113,.12);
    border:1px solid rgba(248,113,113,.35); padding:5px 10px; border-radius:999px; }}
  h1 {{ font-size:20px; margin:16px 0 8px; line-height:1.3; }}
  p {{ color:#9fb0c8; font-size:14px; line-height:1.6; margin:8px 0; }}
  code {{ background:#111c2e; border:1px solid #1e2b42; border-radius:6px;
    padding:2px 6px; font-size:12.5px; color:#cbd5e1; word-break:break-all; }}
  .muted {{ color:#64748b; font-size:12.5px; }}
  label {{ display:block; font-size:13px; color:#9fb0c8; margin:16px 0 6px; }}
  input {{ width:100%; padding:11px 12px; border-radius:10px; border:1px solid #24334d;
    background:#0a1120; color:#e6edf7; font-size:14px; }}
  input:focus {{ outline:none; border-color:#3b82f6; }}
  button {{ width:100%; margin-top:14px; padding:11px 14px; border-radius:10px; border:0;
    background:#2563eb; color:#fff; font-size:14.5px; font-weight:600; cursor:pointer; }}
  button:hover {{ background:#1d4ed8; }}
  .ok {{ color:#6ee7b7; }}
  .err {{ color:#fca5a5; margin-top:12px; font-size:13.5px; }}
  .keybox {{ margin-top:14px; padding:12px; border-radius:10px; background:#07101d;
    border:1px dashed #2b3f5e; font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
    font-size:12.5px; word-break:break-all; color:#a7f3d0; }}
  ul {{ padding-left:18px; margin:10px 0; }}
  li {{ color:#9fb0c8; font-size:13.5px; line-height:1.7; }}
  a {{ color:#60a5fa; }}
</style></head>
<body><div class="card">{body}</div></body></html>"""


def denied_page(host: str = "", lan_hint: str = "") -> str:
    local = (
        f'<p class="muted">Aynı ağdaysan panel normal adresinden açılır: '
        f"<code>{html.escape(lan_hint)}</code></p>"
        if lan_hint
        else ""
    )
    return _page(
        "Erişim yetkiniz yok",
        f"""
        <span class="badge">Yetkisiz cihaz</span>
        <h1>Buraya erişim yetkiniz yok</h1>
        <p><b>{html.escape(host or 'Bu panel')}</b> adresine yalnızca yetkili
        cihazlardan erişilebilir. Bu cihazda geçerli bir erişim anahtarı ya da
        istemci sertifikası bulunamadı.</p>
        <p>Erişim gerekiyorsa: evdeki ağa bağlanıp panelde
        <code>Ayarlar → Uzaktan erişim</code> bölümünden yeni bir cihaz anahtarı
        oluşturun, sonra telefonda aşağıdaki bağlantıya girip anahtarı yazın.</p>
        <p><a href="/device-login">Cihaz anahtarı ile giriş yap</a></p>
        {local}
        <p class="muted">Bu sayfa her isteği engeller; adres çubuğunu değiştirmek
        sonucu değiştirmez.</p>
        """,
    )


def device_login_page(error: str = "", next_url: str = "/") -> str:
    err = f'<div class="err">{html.escape(error)}</div>' if error else ""
    return _page(
        "Cihaz girişi",
        f"""
        <span class="badge" style="color:#93c5fd;background:rgba(59,130,246,.12);
          border-color:rgba(59,130,246,.35)">Cihaz anahtarı</span>
        <h1>Cihaz anahtarı ile giriş</h1>
        <p>Telefonunuza kurduğunuz erişim anahtarını yazın. Anahtar bu cihazda
        bir yıl boyunca hatırlanır; her seferinde yazmanız gerekmez.</p>
        <form method="post" action="/api/device/login">
          <input type="hidden" name="next" value="{html.escape(next_url)}">
          <label for="key">Erişim anahtarı</label>
          <input id="key" name="key" autocomplete="off" spellcheck="false"
                 autocapitalize="off" placeholder="tk_..." required>
          <button type="submit">Giriş yap</button>
        </form>
        {err}
        <p class="muted">Anahtar yalnızca yerel ağda, panelde oturum açmışken
        oluşturulabilir.</p>
        """,
    )


def setup_page(
    keys: List[Dict[str, Any]],
    new_key: str = "",
    error: str = "",
    csrf: str = "",
) -> str:
    csrf_field = (
        f'<input type="hidden" name="csrf" value="{html.escape(csrf)}">' if csrf else ""
    )
    rows = ""
    for item in keys:
        state = (
            '<span class="badge" style="color:#fca5a5;background:rgba(248,113,113,.12);'
            'border-color:rgba(248,113,113,.35)">iptal</span>'
            if item.get("revoked")
            else '<span class="ok">aktif</span>'
        )
        used = html.escape(str(item.get("last_used_at") or "—"))
        revoke = (
            ""
            if item.get("revoked")
            else f"""<form method="post" action="/setup/device/revoke" style="margin:6px 0 0">
                <input type="hidden" name="id" value="{html.escape(str(item['id']))}">
                {csrf_field}
                <button type="submit" style="background:#7f1d1d;padding:7px 10px;font-size:12.5px">
                  İptal et</button></form>"""
        )
        rows += (
            f"<li><b>{html.escape(str(item.get('name')))}</b> · {state}<br>"
            f'<span class="muted">oluşturuldu {html.escape(str(item.get("created_at") or ""))}'
            f" · son kullanım {used}</span>{revoke}</li>"
        )
    if not rows:
        rows = '<li class="muted">Henüz cihaz anahtarı yok.</li>'
    new_block = (
        '<p class="ok"><b>Yeni anahtar (yalnızca şimdi gösterilir):</b></p>'
        f'<div class="keybox">{html.escape(new_key)}</div>'
        '<p class="muted">Telefonda <code>/device-login</code> adresini açıp bu '
        "anahtarı yazın. Sayfayı yenilerseniz anahtar bir daha görünmez; "
        "gerekirse yenisini oluşturun.</p>"
        if new_key
        else ""
    )
    err = f'<div class="err">{html.escape(error)}</div>' if error else ""
    return _page(
        "Uzaktan erişim",
        f"""
        <span class="badge" style="color:#6ee7b7;background:rgba(52,211,153,.12);
          border-color:rgba(52,211,153,.35)">Yerel ağ</span>
        <h1>Uzaktan erişim anahtarları</h1>
        <p>Bu sayfa yalnızca yerel ağdan açılabilir. Dış ağdan gelen istekler
        geçerli bir anahtar olmadan hiçbir sayfaya ulaşamaz.</p>
        {new_block}
        <form method="post" action="/setup/device">
          {csrf_field}
          <label for="name">Cihaz adı</label>
          <input id="name" name="name" placeholder="Telefon" maxlength="60" required>
          <button type="submit">Yeni anahtar oluştur</button>
        </form>
        {err}
        <p style="margin-top:22px"><b>Mevcut anahtarlar</b></p>
        <ul>{rows}</ul>
        """,
    )
