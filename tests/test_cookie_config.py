"""Oturum çerezi adının örnek bazında yapılandırılabilmesini doğrular.

Regresyon: tarayıcı çerezleri **port ayrımı yapmaz**. Aynı tarayıcıda iki panel
(ör. uzak sunucu için `localhost:8089`, yerel için `localhost:8080`) açıldığında
aynı adlı `tradeai_session` çerezi ikinci girişte birincinin üzerine yazılıyor
ve iki panel birbirinin oturumunu düşürüyordu. `TRADEAI_COOKIE_NAME` ile her
örneğe farklı çerez adı verilebilir.
"""

import os
import subprocess
import sys

from app.config import BASE_DIR

_ENV_KEYS = (
    "TRADEAI_COOKIE_NAME",
    "TRADEAI_ENV_FILE",
    "TRADEAI_DATA_DIR",
    "TRADEAI_LOG_DIR",
    "TRADEAI_STATE_DIR",
)


def _cookie_name(tmp_path, **extra):
    """Temiz bir süreçte `app.security.COOKIE_NAME` değerini okur."""
    # Gerçek .env / .env.example ve üretim verisi devreye girmesin.
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in _ENV_KEYS}
    env.update(
        {
            "TRADEAI_ENV_FILE": str(env_file),
            "TRADEAI_DATA_DIR": str(tmp_path / "Data"),
            "TRADEAI_LOG_DIR": str(tmp_path / "Log"),
            "TRADEAI_STATE_DIR": str(tmp_path / "state"),
        }
    )
    env.update(extra)
    out = subprocess.run(
        [sys.executable, "-c", "from app import security; print(security.COOKIE_NAME)"],
        cwd=BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def test_cookie_name_default(tmp_path):
    assert _cookie_name(tmp_path) == "tradeai_session"


def test_cookie_name_from_env(tmp_path):
    name = _cookie_name(tmp_path, TRADEAI_COOKIE_NAME="tradeai_remote")
    assert name == "tradeai_remote"


def test_blank_cookie_name_falls_back(tmp_path):
    assert _cookie_name(tmp_path, TRADEAI_COOKIE_NAME="   ") == "tradeai_session"
