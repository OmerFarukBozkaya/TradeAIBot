"""Panel ayarları: şifreleme ve şema doğrulaması."""

from app import runtime_settings
from app.settings_schema import BY_KEY, GROUPS, SETTINGS


def test_all_settings_have_group_and_unique_key():
    keys = [s.key for s in SETTINGS]
    assert len(keys) == len(set(keys))
    group_ids = {g[0] for g in GROUPS}
    assert all(s.group in group_ids for s in SETTINGS)


def test_secret_roundtrip_encrypts():
    text = "gizli-anahtar-123"
    token = runtime_settings.encrypt(text)
    assert token.startswith("enc:v1:")
    assert text not in token
    assert runtime_settings.decrypt(token) == text


def test_decrypt_rejects_tampered_payload():
    token = runtime_settings.encrypt("abc")
    tampered = token[:-4] + ("a" if token[-4] != "a" else "b") + token[-3:]
    assert runtime_settings.decrypt(tampered) == ""


def test_empty_secret_roundtrip():
    assert runtime_settings.encrypt("") == ""
    assert runtime_settings.decrypt("") == ""


def test_risk_and_limits_are_derived():
    from app.config import settings

    assert set(settings.DEFAULT_RISK) == {
        "dynamic_stop", "static_stop", "support_stop", "take_profit",
    }
    assert set(settings.STRATEGY_LIMITS) == {"15m", "1h", "4h", "1d"}
    assert all(isinstance(v, int) for v in settings.STRATEGY_LIMITS.values())


def test_secret_fields_marked():
    assert BY_KEY["BINANCE_API_SECRET"].secret is True
    assert BY_KEY["MAIL_PASSWORD"].secret is True
    assert BY_KEY["TELEGRAM_TOKEN"].secret is True
