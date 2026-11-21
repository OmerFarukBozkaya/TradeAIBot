from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import requests

from app.config import settings

# Telegram mesajlarının başına konan renkli işaretler.
_KIND_ICONS = {
    "buy": "🟢",   # alış
    "sell": "🔴",  # satış
    "start": "🔵",  # bot başlangıcı
}


def _infer_kind(subject: str) -> str:
    """Konu satırından bildirim türünü tahmin eder."""
    text = str(subject or "").strip().lower()
    if text.startswith("bot başlad") or text.startswith("bot baslad"):
        return "start"
    if text.startswith("al ") or text.startswith("al|") or text == "al":
        return "buy"
    if "satış" in text or "satis" in text or text.startswith("sat"):
        return "sell"
    return ""


class Notifier:
    """Mail / Telegram bildirimleri. Hatalar botu durdurmaz.

    Değerler her gönderimde `settings` üzerinden okunur; böylece panelden
    yapılan değişiklikler yeniden başlatma olmadan geçerli olur.
    """

    @property
    def mail_enabled(self) -> bool:
        return bool(settings.MAIL_ENABLED)

    @property
    def telegram_enabled(self) -> bool:
        return bool(settings.TELEGRAM_ENABLED)

    def send(self, subject: str, message: str, kind: str = "") -> None:
        """Bildirim gönderir.

        Telegram mesajları türüne göre renkli bir yuvarlakla başlar:
        alış 🟢, satış 🔴, bot başlangıcı 🔵. `kind` boşsa konu satırından
        tahmin edilir.
        """
        if self.mail_enabled:
            self._mail(subject, message)
        if self.telegram_enabled:
            icon = _KIND_ICONS.get(kind) or _KIND_ICONS.get(_infer_kind(subject))
            text = f"{icon} {subject}\n{message}" if icon else f"{subject}\n{message}"
            self._telegram(text)

    # ------------------------------------------------------------------
    # E-posta
    # ------------------------------------------------------------------
    def _mail(self, subject: str, message: str) -> Optional[str]:
        sender = settings.MAIL_FROM
        password = settings.MAIL_PASSWORD
        recipient = settings.MAIL_TO
        if not (sender and password and recipient):
            return "E-posta ayarları eksik (gönderen, şifre, alıcı)"
        try:
            msg = MIMEMultipart()
            msg["From"] = sender
            msg["To"] = recipient
            msg["Subject"] = subject
            msg.attach(MIMEText(message, "plain", "utf-8"))
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
                server.starttls()
                server.login(sender, password)
                server.sendmail(sender, recipient, msg.as_string())
            return None
        except Exception as exc:  # bildirim hatası ticaret akışını etkilemez
            return str(exc)

    # ------------------------------------------------------------------
    # Telegram
    # ------------------------------------------------------------------
    def _telegram(self, message: str) -> Optional[str]:
        token = settings.TELEGRAM_TOKEN
        chat = settings.TELEGRAM_CHAT
        if not (token and chat):
            return "Telegram ayarları eksik (token, chat ID)"
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": message[:4000]},
                timeout=10,
            )
            if response.status_code >= 400:
                return f"Telegram hatası: HTTP {response.status_code}"
            return None
        except Exception as exc:
            return str(exc)

    # ------------------------------------------------------------------
    # Panelden test
    # ------------------------------------------------------------------
    def test_mail(self) -> str:
        if not (settings.MAIL_FROM and settings.MAIL_PASSWORD and settings.MAIL_TO):
            raise ValueError("Önce gönderen e-posta, uygulama şifresi ve alıcı adresini doldurun.")
        error = self._mail(
            "TradeAIBot test",
            "Bu bir test bildirimidir. E-posta ayarlarınız çalışıyor.",
        )
        if error:
            raise ValueError(error)
        return settings.MAIL_TO

    def test_telegram(self) -> str:
        if not (settings.TELEGRAM_TOKEN and settings.TELEGRAM_CHAT):
            raise ValueError("Önce Telegram bot token ve chat ID alanlarını doldurun.")
        error = self._telegram(
            "TradeAIBot test\nBu bir test bildirimidir. Telegram ayarlarınız çalışıyor."
        )
        if error:
            raise ValueError(error)
        return settings.TELEGRAM_CHAT


notifier = Notifier()
