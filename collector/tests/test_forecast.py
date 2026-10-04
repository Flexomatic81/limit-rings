from limit_rings.forecast import forecast, update_history

T0 = 1_791_100_000  # arbitrary start time (epoch seconds)
RESET = T0 + 4 * 3600


def five_h(pct, resets_at=RESET, id="five_hour"):
    return {"id": id, "label": "5 h", "used_percent": pct, "resets_at": resets_at, "window_minutes": 300}


def week(pct):
    return {"id": "seven_day", "label": "Week", "used_percent": pct, "resets_at": RESET, "window_minutes": 10080}


def feed(history, samples, name="Claude", limit_factory=five_h):
    """samples: list of (seconds from T0, percent); one collector run with fresh data per sample."""
    for offset, pct in samples:
        update_history(history, {name: ([limit_factory(pct)], T0 + offset)})


def test_steady_rise_predicts_when_full():
    h = {}
    feed(h, [(0, 10.0), (600, 15.0), (1200, 20.0)])  # 0.5 %/min
    # 80 % to go at 0.5 %/min → 160 min after the last data point
    assert forecast(h["claude:five_hour"], RESET, T0 + 1200) == {"status": "full", "eta": T0 + 1200 + 160 * 60}


def test_rise_that_ends_after_reset_is_enough():
    h = {}
    feed(h, [(0, 10.0), (1200, 11.0)])  # 0.05 %/min → long after the reset
    assert forecast(h["claude:five_hour"], RESET, T0 + 1200) == {"status": "enough"}


def test_no_rise_is_enough():
    h = {}
    feed(h, [(0, 30.0), (900, 30.0)])
    assert forecast(h["claude:five_hour"], RESET, T0 + 900) == {"status": "enough"}


def test_too_short_span_gives_no_forecast():
    h = {}
    feed(h, [(0, 10.0), (540, 20.0)])  # only 9 minutes
    assert forecast(h["claude:five_hour"], RESET, T0 + 540) is None


def test_rate_uses_only_the_last_30_minutes():
    h = {}
    # quiet for an hour first, then from 10 to 30 % in 20 minutes
    feed(h, [(0, 10.0), (1800, 10.0), (3600, 10.0), (4800, 30.0)])
    result = forecast(h["claude:five_hour"], RESET + 3600, T0 + 4800)
    assert result["status"] == "full"
    # reference is the point at 3600 s (last one within 30 min): 20 % in 20 min → 1 %/min → 70 min
    assert result["eta"] == T0 + 4800 + 70 * 60


def test_stale_data_gives_no_forecast():
    h = {}
    feed(h, [(0, 10.0), (1200, 20.0)])
    assert forecast(h["claude:five_hour"], RESET, T0 + 1200 + 31 * 60) is None


def test_duplicate_samples_from_unchanged_data_are_ignored():
    h = {}
    update_history(h, {"Claude": ([five_h(10.0)], T0)})
    update_history(h, {"Claude": ([five_h(10.0)], T0)})  # same updated_at → no new point
    assert h["claude:five_hour"]["points"] == [[T0, 10.0]]


def test_new_window_restarts_history_and_old_points_are_dropped():
    h = {}
    feed(h, [(0, 50.0), (600, 60.0)])
    update_history(h, {"Claude": ([five_h(1.0, resets_at=RESET + 5 * 3600)], T0 + 700)})
    assert h["claude:five_hour"] == {"resets_at": RESET + 5 * 3600, "points": [[T0 + 700, 1.0]]}
    feed(h, [(700 + 3700, 2.0)], limit_factory=lambda p: five_h(p, resets_at=RESET + 5 * 3600))
    assert [p[0] for p in h["claude:five_hour"]["points"]] == [T0 + 4400]  # older than 60 min is dropped


def test_five_hour_and_week_windows_are_tracked_and_vanished_ones_removed():
    other = {"id": "x", "label": "2 d", "used_percent": 1.0, "resets_at": RESET, "window_minutes": 2880}
    h = {"codex:old": {"resets_at": None, "points": []}}
    update_history(h, {"Claude": ([five_h(5.0), week(30.0), other], T0), "Codex": ([], None)})
    assert sorted(h) == ["claude:five_hour", "claude:seven_day"]


def test_missing_updated_at_adds_no_point():
    h = {}
    update_history(h, {"Claude": ([five_h(5.0)], None)})
    assert h == {"claude:five_hour": {"resets_at": RESET, "points": []}}
    assert forecast(h["claude:five_hour"], RESET, T0) is None


def test_reset_jitter_of_a_second_keeps_the_window():
    h = {}
    update_history(h, {"Claude": ([five_h(10.0, resets_at=RESET)], T0)})
    update_history(h, {"Claude": ([five_h(15.0, resets_at=RESET - 1)], T0 + 600)})  # API rounding
    assert [p[1] for p in h["claude:five_hour"]["points"]] == [10.0, 15.0]


WEEK_RESET = T0 + 5 * 86400


def week_at(pct):
    return {"id": "seven_day", "label": "Week", "used_percent": pct, "resets_at": WEEK_RESET,
            "window_minutes": 10080}


def test_week_forecast_uses_last_24_hours():
    h = {}
    # at 0 % 30 h ago, then from 20 to 44 % over the last 24 h → 1 %/h
    feed(h, [(0, 0.0), (6 * 3600, 20.0), (30 * 3600, 44.0)], limit_factory=week_at)
    now = T0 + 30 * 3600
    # point at 0 h is older than 24 h and is dropped; 56 % to go at 1 %/h → 56 h
    assert forecast(h["claude:seven_day"], WEEK_RESET + 86400, now, 10080) == {
        "status": "full", "eta": now + 56 * 3600}
    # it would be full 86 h after T0; a reset after just 80 h comes first
    assert forecast(h["claude:seven_day"], T0 + 80 * 3600, now, 10080) == {"status": "enough"}


def test_week_needs_two_hours_and_fresh_data():
    h = {}
    feed(h, [(0, 10.0), (3600, 10.0)], limit_factory=week_at)  # only 1 h apart
    assert forecast(h["claude:seven_day"], WEEK_RESET, T0 + 3600, 10080) is None
    feed(h, [(3 * 3600, 10.0)], limit_factory=week_at)  # no rise → enough
    assert forecast(h["claude:seven_day"], WEEK_RESET, T0 + 3 * 3600, 10080)["status"] == "enough"
    assert forecast(h["claude:seven_day"], WEEK_RESET, T0 + 3 * 3600 + 6 * 3600 + 1, 10080) is None  # stale


def test_week_points_are_thinned_to_ten_minutes():
    h = {}
    feed(h, [(0, 10.0), (300, 10.0), (599, 10.0), (600, 11.0)], limit_factory=week_at)
    assert [p[0] - T0 for p in h["claude:seven_day"]["points"]] == [0, 600]
