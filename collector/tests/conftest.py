import pytest

from agent_stats import i18n


@pytest.fixture(autouse=True)
def english():
    """Tests expect the English source texts, whatever the language of the test run."""
    i18n.install(["en"])
    yield
    i18n.install(["en"])
