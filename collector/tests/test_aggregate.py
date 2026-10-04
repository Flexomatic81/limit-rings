from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from agent_stats.aggregate import add_event, daily_series, prune_buckets, summarize
from agent_stats.models import TokenEvent

BERLIN = ZoneInfo("Europe/Berlin")


def ev(iso, i=0, o=0, cr=0, cw=0):
    return TokenEvent(datetime.fromisoformat(iso), i, o, cr, cw)


def test_buckets_by_local_date_across_dst_change():
    b = {}
    # 2026-10-25: Umstellung CEST -> CET um 01:00 UTC
    add_event(b, ev("2026-10-24T22:30:00+00:00", i=1), BERLIN)  # 00:30 CEST, 25.10.
    add_event(b, ev("2026-10-25T22:30:00+00:00", i=1), BERLIN)  # 23:30 CET, 25.10.
    add_event(b, ev("2026-10-25T23:30:00+00:00", i=1), BERLIN)  # 00:30 CET, 26.10.
    assert b["2026-10-25"]["input"] == 2
    assert b["2026-10-26"]["input"] == 1
    assert "2026-10-24" not in b


def test_summarize_today_week_month_with_totals():
    b = {}
    add_event(b, ev("2026-10-01T10:00:00+00:00", i=1), BERLIN)         # Do, 1. Oktober
    add_event(b, ev("2026-09-30T10:00:00+00:00", o=100), BERLIN)       # September
    add_event(b, ev("2026-10-12T10:00:00+00:00", cr=10), BERLIN)       # Mo dieser Woche
    add_event(b, ev("2026-10-14T10:00:00+00:00", i=1, o=2, cr=3, cw=4), BERLIN)  # Mi = heute

    s = summarize(b, date(2026, 10, 14))
    assert s["today"] == {"input": 1, "output": 2, "cache_read": 3, "cache_write": 4, "total": 10}
    assert s["week"]["total"] == 20          # 12.10. + 14.10.
    assert s["month"]["total"] == 21         # 01.10. + 12.10. + 14.10.


def test_week_starts_monday_and_sunday_belongs_to_previous_week():
    b = {}
    add_event(b, ev("2026-10-11T10:00:00+00:00", i=5), BERLIN)  # So
    add_event(b, ev("2026-10-12T10:00:00+00:00", i=7), BERLIN)  # Mo
    assert summarize(b, date(2026, 10, 12))["week"]["input"] == 7


def test_new_day_without_events_shows_zero_today():
    b = {}
    add_event(b, ev("2026-10-14T10:00:00+00:00", i=5), BERLIN)
    s = summarize(b, date(2026, 10, 15))
    assert s["today"]["total"] == 0
    assert s["week"]["total"] == 5


def test_daily_series_has_30_gapless_days_oldest_first():
    b = {}
    add_event(b, ev("2026-10-14T10:00:00+00:00", o=3), BERLIN)
    add_event(b, ev("2026-09-15T10:00:00+00:00", o=1), BERLIN)
    add_event(b, ev("2026-09-14T10:00:00+00:00", o=99), BERLIN)  # außerhalb
    series = daily_series(b, date(2026, 10, 14))
    assert len(series) == 30
    assert series[0] == {"date": "2026-09-15", "total": 1}
    assert series[-1] == {"date": "2026-10-14", "total": 3}
    assert series[1]["total"] == 0


def test_prune_drops_old_buckets():
    b = {"2025-01-01": {"input": 1, "output": 0, "cache_read": 0, "cache_write": 0},
         "2026-10-01": {"input": 1, "output": 0, "cache_read": 0, "cache_write": 0}}
    prune_buckets(b, date(2026, 10, 14), keep_days=400)
    assert list(b) == ["2026-10-01"]
