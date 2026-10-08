from datetime import datetime
from zoneinfo import ZoneInfo

from limit_rings.changes import GONE_AFTER, KEEP_EVENTS, RECENT, recent, update
from limit_rings.limits import make_limit

BERLIN = ZoneInfo("Europe/Berlin")
T0 = 1_791_100_000
FIVE_RESET = T0 + 4 * 3600
WEEK_RESET = T0 + 3 * 86400


def five(pct=10.0, resets_at=FIVE_RESET, minutes=300, id="five_hour"):
    return make_limit(id, pct, resets_at, minutes)


def week(pct=20.0, resets_at=WEEK_RESET):
    return make_limit("seven_day", pct, resets_at, 10080)


def opus(pct=5.0):
    return make_limit("seven_day_opus", pct, WEEK_RESET, 10080, "Opus")


def rec(limits, at):
    return {"limits": limits, "updated_at": at}


def run(structure, limits, at, source="oauth"):
    return update(structure, rec(limits, at), source, at)


def kinds(structure):
    return [(e["kind"], e["id"]) for e in structure["events"]]


def test_first_run_records_a_baseline_without_events():
    s = run(None, [five(), week()], T0)
    assert s["events"] == []
    assert set(s["windows"]) == {"five_hour", "seven_day"}


def test_unchanged_windows_give_no_event():
    s = run(None, [five(), week()], T0)
    s = run(s, [five(30.0), week(25.0)], T0 + 300)
    assert s["events"] == []


def test_a_new_window_is_noted():
    s = run(None, [five(), week()], T0)
    s = run(s, [five(), week(), opus()], T0 + 300)
    assert kinds(s) == [("new", "seven_day_opus")]
    event = s["events"][0]
    assert (event["minutes"], event["model"], event["at"]) == (10080, "Opus", T0 + 300)


def test_a_window_missing_briefly_is_no_change():
    s = run(None, [five(), week()], T0)
    s = run(s, [week()], T0 + 300)
    s = run(s, [five(), week()], T0 + 600)
    assert s["events"] == []


def test_a_window_missing_for_an_hour_is_gone_since_its_first_absence():
    s = run(None, [five(), week()], T0)
    s = run(s, [week()], T0 + 300)
    s = run(s, [week()], T0 + 300 + GONE_AFTER - 1)
    assert s["events"] == []
    s = run(s, [week()], T0 + 300 + GONE_AFTER)
    assert kinds(s) == [("gone", "five_hour")]
    assert s["events"][0]["at"] == T0 + 300


def test_a_gone_window_that_returns_is_back():
    s = run(None, [five(), week()], T0)
    s = run(s, [week()], T0 + 300)
    s = run(s, [week()], T0 + 300 + GONE_AFTER)
    s = run(s, [five(), week()], T0 + 2 * GONE_AFTER)
    assert kinds(s) == [("gone", "five_hour"), ("back", "five_hour")]


def test_a_changed_window_length_is_noted_with_the_previous_length():
    s = run(None, [five(), week()], T0)
    s = run(s, [five(minutes=180), week()], T0 + 300)
    assert kinds(s) == [("length", "five_hour")]
    assert (s["events"][0]["minutes"], s["events"][0]["previous_minutes"]) == (180, 300)


def test_an_early_reset_is_noted():
    s = run(None, [five(), week(60.0)], T0)
    s = run(s, [five(), week(0.0, resets_at=T0 + 7 * 86400)], T0 + 300)
    assert kinds(s) == [("early_reset", "seven_day")]


def test_a_reset_on_time_is_no_change():
    s = run(None, [five(80.0)], FIVE_RESET - 300)
    s = run(s, [five(0.0, resets_at=FIVE_RESET + 5 * 3600)], FIVE_RESET + 60)
    assert s["events"] == []


def test_a_slightly_moved_reset_is_no_change():
    s = run(None, [week(60.0)], T0)
    s = run(s, [week(61.0, resets_at=WEEK_RESET + 120)], T0 + 300)
    assert s["events"] == []


def test_a_moved_reset_without_a_drop_is_no_early_reset():
    s = run(None, [week(60.0)], T0)
    s = run(s, [week(62.0, resets_at=WEEK_RESET + 86400)], T0 + 300)
    assert s["events"] == []


def test_a_change_of_source_starts_a_new_baseline():
    s = run(None, [five(), week(), opus()], T0)
    s = run(s, [five(), week()], T0 + 300, source="statusline")
    s = run(s, [five(), week()], T0 + 300 + GONE_AFTER, source="statusline")
    assert s["events"] == []
    assert s["source"] == "statusline"


def test_events_survive_a_change_of_source():
    s = run(None, [five(), week()], T0)
    s = run(s, [five(), week(), opus()], T0 + 300)
    s = run(s, [five(), week()], T0 + 600, source="statusline")
    assert kinds(s) == [("new", "seven_day_opus")]


def test_no_new_data_changes_nothing():
    s = run(None, [five(), week()], T0)
    again = update(s, rec([week()], T0), "oauth", T0 + 2 * GONE_AFTER)
    assert again["events"] == [] and "five_hour" in again["windows"]


def test_without_limits_the_structure_is_kept():
    s = run(None, [five()], T0)
    assert update(s, None, None, T0 + 300) is s
    assert update(None, None, None, T0) is None


def test_old_events_are_dropped_and_the_list_stays_small():
    s = run(None, [week()], T0)
    extra = []
    for i in range(30):
        extra.append(make_limit(f"x{i}", 1.0, None, 60))
        s = run(s, [week(), *extra], T0 + 300 * (i + 1))
    assert len(s["events"]) == 20
    assert s["events"][-1]["id"] == "x29"
    late = T0 + KEEP_EVENTS + 86400
    s = update(s, rec([week(), *extra], late), "oauth", late)
    assert s["events"] == []


def test_recent_returns_the_last_days_for_stats():
    s = run(None, [five(), week()], T0)
    s = run(s, [five(minutes=180), week(), opus()], T0 + 300)
    out = recent(s, T0 + 600, BERLIN)
    assert out == [
        {"kind": "length", "limit": {"id": "five_hour", "window_minutes": 180}, "previous_minutes": 300,
         "at": datetime.fromtimestamp(T0 + 300, BERLIN).isoformat(timespec="seconds")},
        {"kind": "new", "limit": {"id": "seven_day_opus", "window_minutes": 10080, "model": "Opus"},
         "at": datetime.fromtimestamp(T0 + 300, BERLIN).isoformat(timespec="seconds")},
    ]
    assert recent(s, T0 + 300 + RECENT + 1, BERLIN) == []
    assert recent(None, T0, BERLIN) == []


def test_events_remember_their_source_and_local_only_skips_endpoint_ones():
    s = run(None, [five(), week()], T0)
    s = run(s, [five(), week(), opus()], T0 + 300)
    assert s["events"][0]["source"] == "oauth"
    assert recent(s, T0 + 600, BERLIN, local_only=True) == []
    s = run(s, [five()], T0 + 900, source="statusline")
    s = run(s, [five(), week()], T0 + 1200, source="statusline")
    assert [e["kind"] for e in recent(s, T0 + 1500, BERLIN, local_only=True)] == ["new"]


def test_events_without_a_source_count_as_endpoint_data():
    s = run(None, [five()], T0, source="statusline")
    s = run(s, [five(), week()], T0 + 300, source="statusline")
    del s["events"][0]["source"]        # written by a collector before events remembered their source
    assert recent(s, T0 + 600, BERLIN, local_only=True) == []
    assert [e["kind"] for e in recent(s, T0 + 600, BERLIN)] == ["new"]
