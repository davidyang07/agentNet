"""The suite never touches the dev database (PLAN 14.3 B.9): conftest pins
the app's settings to agentnet_test before the app is first imported."""

from app.config import get_settings


def test_the_app_under_test_uses_the_test_database():
    assert get_settings().postgres_db == "agentnet_test"
