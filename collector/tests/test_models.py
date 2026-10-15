import pytest

from limit_rings.models import parse_ts


def test_parse_ts_accepts_z_and_offsets():
    assert parse_ts("2026-10-03T10:00:00Z") == parse_ts("2026-10-03T12:00:00+02:00")


@pytest.mark.parametrize(
    ("value", "message"), [(None, "missing"), (17, "missing"), ("2026-10-03T10:00:00", "time zone")]
)
def test_parse_ts_rejects_missing_or_zoneless_timestamps(value, message):
    with pytest.raises(ValueError, match=message):
        parse_ts(value)
