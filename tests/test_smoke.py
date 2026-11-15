"""Uygulamanın temel import ve şema bütünlüğü testleri."""


def test_import_app():
    import app.main  # noqa: F401


def test_schema_defines_core_tables():
    from app import db

    for table in ("bots", "trades", "positions", "strategies", "signal_events", "jobs", "users", "coin_lists"):
        assert table in db.SCHEMA


def test_job_handlers_registered():
    from app.job_runner import HANDLERS

    for name in ("backtest", "scan", "indicator_values", "market", "ai_train"):
        assert name in HANDLERS
