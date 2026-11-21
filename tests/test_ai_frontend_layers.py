"""Paneldeki mimari metninin tip güvenliği (regresyon koruması).

Transformer eski kayıtlarında ``metrics.model.layers`` bir **sayı** (blok
sayısı) idi; panel bunu gizli katman listesi sanıp ``(layers || []).join``
çağırınca "join is not a function" hatası veriyordu.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.ai.trainer import _layers_metric

APP_JS = Path(__file__).resolve().parents[1] / "web" / "app.js"


def _source() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_layers_never_joined_directly_without_helper():
    """``layers``/``hidden_layers`` doğrudan join edilmemeli; layersText kullanılmalı."""
    src = _source()
    bad_patterns = [
        r"\(layers \|\| \[\]\)\.join",
        r"\(mdl\.layers \|\| \[\]\)\.join",
        r"spec\.hidden_layers\.join",
        r"s\.hidden_layers\.join",
        r"res\.spec\.hidden_layers\.join",
        r"\(spec\.hidden_layers \|\| \[\]\)\.join\(\)",
    ]
    for pattern in bad_patterns:
        assert not re.search(pattern, src), f"güvensiz join kullanımı: {pattern}"


def test_layers_helper_exists_and_is_used():
    src = _source()
    assert "function layersText(" in src
    assert "function archSummaryText(" in src
    # Model kartı ve mimari özeti yardımcıyı kullanmalı.
    assert src.count("layersText(") >= 3
    assert src.count("archSummaryText(") >= 2


def test_arch_summary_handles_scalar_layers_in_js_source():
    """Sayısal layers değeri için koruma kodu bulunmalı."""
    src = _source()
    start = src.index("function layersText(")
    end = src.index("async function showBotAnalysis", start)
    block = src[start:end]
    assert "Array.isArray(" in block
    assert "String(value)" in block


def test_layers_metric_scalar_inputs():
    assert _layers_metric(1) is None
    assert _layers_metric(2) is None
    assert _layers_metric([64, 32]) == [64, 32]
