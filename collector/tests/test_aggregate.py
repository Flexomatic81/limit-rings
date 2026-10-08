from datetime import date, datetime
from zoneinfo import ZoneInfo

from limit_rings.aggregate import add_event, daily_series, monthly_series, prune_buckets, summarize, weekly_series
from limit_rings.models import TokenEvent

BERLIN = ZoneInfo("Europe/Berlin")


def ev(iso, i=0, o=0, cr=0, cw=0):
    return TokenEvent(datetime.fromisoformat(iso), i, o, cr, cw)


def test_buckets_by_local_date_across_dst_change():
    b = {}
    # 2026-10-25: switch from CEST to CET at 01:00 UTC
    add_event(b, ev("2026-10-24T22:30:00+00:00", i=1), BERLIN)  # 00:30 CEST, Oct 25
    add_event(b, ev("2026-10-25T22:30:00+00:00", i=1), BERLIN)  # 23:30 CET, Oct 25
    add_event(b, ev("2026-10-25T23:30:00+00:00", i=1), BERLIN)  # 00:30 CET, Oct 26
    assert b["2026-10-25"]["input"] == 2
    assert b["2026-10-26"]["input"] == 1
    assert "2026-10-24" not in b


def test_summarize_today_week_month_with_totals():
    b = {}
    add_event(b, ev("2026-10-01T10:00:00+00:00", i=1), BERLIN)         # Thu, October 1
    add_event(b, ev("2026-09-30T10:00:00+00:00", o=100), BERLIN)       # September
    add_event(b, ev("2026-10-12T10:00:00+00:00", cr=10), BERLIN)       # Mon of this week
    add_event(b, ev("2026-10-14T10:00:00+00:00", i=1, o=2, cr=3, cw=4), BERLIN)  # Wed = today

    s = summarize(b, date(2026, 10, 14))
    assert s["today"] == {"input": 1, "output": 2, "cache_read": 3, "cache_write": 4, "total": 10}
    assert s["week"]["total"] == 20          # Oct 12 + Oct 14
    assert s["month"]["total"] == 21         # Oct 1 + Oct 12 + Oct 14


def test_week_starts_monday_and_sunday_belongs_to_previous_week():
    b = {}
    add_event(b, ev("2026-10-11T10:00:00+00:00", i=5), BERLIN)  # Sun
    add_event(b, ev("2026-10-12T10:00:00+00:00", i=7), BERLIN)  # Mon
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
    add_event(b, ev("2026-09-14T10:00:00+00:00", o=99), BERLIN)  # outside
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


def test_weekly_series_has_13_weeks_from_monday_oldest_first():
    b = {}
    add_event(b, ev("2026-10-12T10:00:00+00:00", i=2), BERLIN)  # Mon of this week
    add_event(b, ev("2026-10-14T10:00:00+00:00", i=3), BERLIN)  # Wed = today
    add_event(b, ev("2026-10-11T10:00:00+00:00", i=5), BERLIN)  # Sun: previous week
    add_event(b, ev("2026-07-20T10:00:00+00:00", i=7), BERLIN)  # Mon, oldest week shown
    add_event(b, ev("2026-07-19T10:00:00+00:00", i=99), BERLIN)  # Sun before: outside
    series = weekly_series(b, date(2026, 10, 14))
    assert len(series) == 13
    assert series[0] == {"date": "2026-07-20", "total": 7}
    assert series[-2] == {"date": "2026-10-05", "total": 5}
    assert series[-1] == {"date": "2026-10-12", "total": 5}


def test_monthly_series_has_12_months_across_the_year_boundary():
    b = {}
    add_event(b, ev("2026-02-28T10:00:00+00:00", o=4), BERLIN)
    add_event(b, ev("2026-02-01T10:00:00+00:00", o=1), BERLIN)
    add_event(b, ev("2025-12-31T10:00:00+00:00", o=99), BERLIN)  # outside
    add_event(b, ev("2026-01-15T10:00:00+00:00", o=6), BERLIN)
    series = monthly_series(b, date(2026, 12, 3))
    assert len(series) == 12
    assert series[0] == {"date": "2026-01-01", "total": 6}
    assert series[1] == {"date": "2026-02-01", "total": 5}
    assert series[-1] == {"date": "2026-12-01", "total": 0}
    assert monthly_series(b, date(2027, 1, 31))[0] == {"date": "2026-02-01", "total": 5}
