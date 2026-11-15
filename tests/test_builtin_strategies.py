"""Hazır stratejilerin panelden yönetimi (kopya / arşiv / yeniden adlandırma)."""

from app.strategies import service
from app.strategies.builtin import builtin_names


def test_builtin_listing_contains_metadata():
    items = service.list_builtin(include_archived=True)
    assert items
    first = items[0]
    for key in ("id", "name", "label", "archived", "kind"):
        assert key in first
    assert first["kind"] == "builtin"


def test_builtin_wrapper_validates():
    from app.strategies.compiler import validate_definition

    name = builtin_names()[0]
    assert validate_definition({"name": "Kopya", "builtin": name}) == []
    assert validate_definition({"name": "Kopya", "builtin": "YOK_BOYLE"})
