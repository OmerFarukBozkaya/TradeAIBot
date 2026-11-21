"""Telegram bildirimlerinin başındaki renkli yuvarlaklar."""

from __future__ import annotations

import pytest

from app import notifications


class _Response:
    status_code = 200


@pytest.fixture()
def sent(monkeypatch):
    messages = []

    def fake_post(url, json=None, timeout=None):  # noqa: A002
        messages.append(json or {})
        return _Response()

    monkeypatch.setattr(notifications.settings, "TELEGRAM_ENABLED", True)
    monkeypatch.setattr(notifications.settings, "TELEGRAM_TOKEN", "token")
    monkeypatch.setattr(notifications.settings, "TELEGRAM_CHAT", "123")
    monkeypatch.setattr(notifications.settings, "MAIL_ENABLED", False)
    monkeypatch.setattr(notifications.requests, "post", fake_post)
    return messages


def test_buy_gets_green_circle(sent):
    notifications.notifier.send("AL | Bot", "BTCUSDT alındı", kind="buy")
    assert sent[-1]["text"].startswith("🟢 AL | Bot")


def test_sell_gets_red_circle(sent):
    notifications.notifier.send("SAT | Bot", "BTCUSDT satıldı", kind="sell")
    assert sent[-1]["text"].startswith("🔴 SAT | Bot")


def test_start_gets_blue_circle(sent):
    notifications.notifier.send("Bot Başladı | Bot", "Mod: paper", kind="start")
    assert sent[-1]["text"].startswith("🔵 Bot Başladı | Bot")


def test_kind_is_inferred_from_subject(sent):
    notifications.notifier.send("AL | Bot", "alındı")
    notifications.notifier.send("SAT | Bot", "satıldı")
    notifications.notifier.send("Manuel satış | Bot", "elle satıldı")
    notifications.notifier.send("Bot Başladı | Bot", "başladı")

    assert sent[0]["text"].startswith("🟢 AL | Bot")
    assert sent[1]["text"].startswith("🔴 SAT | Bot")
    assert sent[2]["text"].startswith("🔴 Manuel satış | Bot")
    assert sent[3]["text"].startswith("🔵 Bot Başladı | Bot")


def test_other_notifications_stay_plain(sent):
    notifications.notifier.send("Bot Hatası | Bot", "hata")
    assert sent[-1]["text"].startswith("Bot Hatası | Bot")
