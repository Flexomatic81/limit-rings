from limit_rings import notify
from limit_rings.notify import Notice, update_notices

NOW = 1_791_100_000.0  # 2026-10-04 07:46:40 UTC


def limit(id="five_hour", pct=82.0, resets_at=int(NOW) + 4380, window_minutes=300, model=None):
    out = {"id": id, "used_percent": pct, "resets_at": resets_at, "window_minutes": window_minutes}
    return out | {"model": model} if model else out


def test_first_crossing_of_80_sends_one_normal_notice():
    notified = {}
    notices = update_notices({"Claude": [limit()]}, notified, NOW)
    assert notices == [Notice(key="claude:five_hour", level=80, summary="Claude: 5-hour limit at 82 %",
                              body="Reset in 1 h 13 min", urgent=False)]
    assert notified == {"claude:five_hour": {"level": 80, "resets_at": int(NOW) + 4380, "minutes": 300}}


def test_same_window_does_not_notify_twice():
    notified = {}
    update_notices({"Claude": [limit()]}, notified, NOW)
    assert update_notices({"Claude": [limit(pct=85.0)]}, notified, NOW + 60) == []


def test_jump_straight_to_95_sends_only_the_urgent_notice():
    notices = update_notices({"Codex": [limit(id="primary", window_minutes=10080, pct=97.0, resets_at=None)]}, {}, NOW)
    assert [(n.level, n.urgent, n.summary, n.body) for n in notices] == [
        (95, True, "Codex: weekly limit at 97 %", "")]


def test_80_then_95_in_same_window_sends_both_once():
    notified = {}
    assert [n.level for n in update_notices({"Claude": [limit(pct=81.0)]}, notified, NOW)] == [80]
    assert [n.level for n in update_notices({"Claude": [limit(pct=96.0)]}, notified, NOW)] == [95]
    assert update_notices({"Claude": [limit(pct=99.0)]}, notified, NOW) == []


def test_new_window_rearms_and_reset_window_counts_as_zero():
    notified = {}
    update_notices({"Claude": [limit(pct=90.0)]}, notified, NOW)
    # reset time passed, data still old: counts as 0 % → entry dropped, nothing sent
    assert update_notices({"Claude": [limit(pct=90.0, resets_at=int(NOW) - 1)]}, notified, NOW) == []
    assert notified == {}
    # new window with a new reset time reaches 80 % again
    nxt = update_notices({"Claude": [limit(pct=80.0, resets_at=int(NOW) + 18000)]}, notified, NOW)
    assert [n.level for n in nxt] == [80]


def test_scoped_labels_and_vanished_limits_are_cleaned_up():
    notified = {"claude:old": {"level": 80, "resets_at": None}}
    notices = update_notices({"Claude": [limit(id="weekly_scoped:fable", window_minutes=10080, model="Fable",
                                               pct=80.0, resets_at=None)]}, notified, NOW)
    assert notices[0].summary == "Claude: weekly Fable limit at 80 %"
    assert list(notified) == ["claude:weekly_scoped:fable"]


def test_below_threshold_sends_nothing():
    assert update_notices({"Claude": [limit(pct=79.9)], "Codex": []}, {}, NOW) == []


def test_notice_as_json_for_the_widget():
    n = Notice("claude:five_hour", 95, "Claude: 5-hour limit at 96 %", "Reset in 5 min", True)
    assert n.to_json() == {"key": "claude:five_hour", "summary": "Claude: 5-hour limit at 96 %",
                           "body": "Reset in 5 min", "urgent": True}


def test_notify_send_is_gone():
    assert not hasattr(notify, "send")


def test_reset_jitter_does_not_notify_again():
    notified = {}
    update_notices({"Claude": [limit(pct=85.0, resets_at=int(NOW) + 4380)]}, notified, NOW)
    assert update_notices({"Claude": [limit(pct=86.0, resets_at=int(NOW) + 4379)]}, notified, NOW + 60) == []


def with_forecast(lim, eta):
    return {**lim, "forecast": {"status": "full", "eta": eta}}


def test_early_warning_when_five_hour_limit_is_full_within_30_minutes():
    notified = {}
    soon = with_forecast(limit(pct=62.0), int(NOW) + 25 * 60)
    notices = update_notices({"Claude": [soon]}, notified, NOW)
    assert notices == [Notice(key="claude:five_hour", level=0, summary="Claude: 5-hour limit full in ~25 min",
                              body="Now 62 % · Reset in 1 h 13 min", urgent=False)]
    assert update_notices({"Claude": [soon]}, notified, NOW + 60) == []  # only once
    # later 80 % in the same window: the threshold notice still comes
    assert [n.level for n in update_notices({"Claude": [with_forecast(limit(pct=80.0), int(NOW) + 600)]},
                                            notified, NOW + 120)] == [80]


def test_no_early_warning_when_far_away():
    later = with_forecast(limit(pct=62.0), int(NOW) + 31 * 60)
    weekly = with_forecast(limit(id="seven_day", pct=62.0, window_minutes=10080, resets_at=int(NOW) + 5 * 86400),
                           int(NOW) + 25 * 3600)
    assert update_notices({"Claude": [later, weekly]}, {}, NOW) == []


def test_early_warning_for_the_weekly_limit_within_a_day():
    notified = {}
    weekly = with_forecast(limit(id="seven_day", pct=62.0, window_minutes=10080, resets_at=int(NOW) + 2 * 86400),
                           int(NOW) + 18 * 3600)
    notices = update_notices({"Claude": [weekly]}, notified, NOW)
    assert notices == [Notice(key="claude:seven_day", level=0, summary="Claude: weekly limit full in ~18 h 0 min",
                              body="Now 62 % · Reset in 2 d 0 h", urgent=False)]
    assert update_notices({"Claude": [weekly]}, notified, NOW + 600) == []


def test_custom_thresholds_and_urgency_at_the_second_one():
    notified = {}
    at = lambda pct: update_notices({"Claude": [limit(pct=pct)]}, notified, NOW, thresholds=(50, 75))
    assert [(n.level, n.urgent) for n in at(55.0)] == [(50, False)]
    assert at(60.0) == []
    assert [(n.level, n.urgent) for n in at(76.0)] == [(75, True)]


def test_reset_notice_only_after_a_warning_and_only_when_wanted():
    def run(notified, pct, resets_at, now, wanted=True):
        return update_notices({"Claude": [limit(pct=pct, resets_at=resets_at)]}, notified, now, reset_notice=wanted)
    # warned window whose reset time passes
    notified = {}
    run(notified, 85.0, int(NOW) + 600, NOW)
    notices = run(notified, 85.0, int(NOW) + 600, NOW + 700)
    assert [(n.key, n.level, n.summary, n.body, n.urgent) for n in notices] == [
        ("claude:five_hour", -1, "Claude: 5-hour limit reset", "", False)]
    assert run(notified, 0.0, int(NOW) + 18600, NOW + 800) == []          # the new window says nothing more
    # warned window replaced by a new one before its reset time was seen to pass
    notified = {}
    run(notified, 85.0, int(NOW) + 600, NOW)
    assert [n.level for n in run(notified, 3.0, int(NOW) + 18600, NOW + 60)] == [-1]
    # never warned: no reset notice; switched off: none either
    notified = {}
    run(notified, 20.0, int(NOW) + 600, NOW)
    assert run(notified, 20.0, int(NOW) + 600, NOW + 700) == []
    notified = {}
    run(notified, 85.0, int(NOW) + 600, NOW, wanted=False)
    assert run(notified, 85.0, int(NOW) + 600, NOW + 700, wanted=False) == []


def test_early_warning_with_eta_already_reached():
    notices = update_notices({"Claude": [with_forecast(limit(pct=70.0), int(NOW) - 10)]}, {}, NOW)
    assert notices[0].summary == "Claude: 5-hour limit almost full"


def test_limit_names_for_other_windows_and_missing_window():
    two_days = limit(id="x", pct=81.0, resets_at=None, window_minutes=2880)
    assert update_notices({"Codex": [two_days]}, {}, NOW)[0].summary == "Codex: 2 d limit at 81 %"
    no_window = limit(id="primary", pct=81.0, resets_at=None, window_minutes=None)
    assert update_notices({"Codex": [no_window]}, {}, NOW)[0].summary == "Codex: primary limit at 81 %"


def test_legacy_label_without_model_still_names_the_model():
    old = {"id": "seven_day_opus", "label": "Woche Opus", "used_percent": 96.0, "resets_at": None,
           "window_minutes": 10080}
    assert update_notices({"Claude": [old]}, {}, NOW)[0].summary == "Claude: weekly Opus limit at 96 %"


def test_texts_go_through_the_translation(monkeypatch):
    import gettext
    from limit_rings import i18n

    class Marked(gettext.NullTranslations):
        def gettext(self, message):
            return "»" + message

    monkeypatch.setattr(i18n, "_translation", Marked())
    notice = update_notices({"Claude": [limit()]}, {}, NOW)[0]
    assert (notice.summary, notice.body) == ("»Claude: »5-hour limit at 82 %", "»Reset in 1 h 13 min")


def test_model_is_named_for_other_windows_too():
    scoped = limit(id="x", pct=81.0, resets_at=None, window_minutes=2880, model="Opus")
    assert update_notices({"Claude": [scoped]}, {}, NOW)[0].summary == "Claude: 2 d Opus limit at 81 %"


def test_window_length_change_without_reset_times_notifies_again():
    notified = {}
    update_notices({"Codex": [limit(id="primary", resets_at=None)]}, notified, NOW)
    notices = update_notices({"Codex": [limit(id="primary", resets_at=None, window_minutes=10080)]}, notified, NOW + 60)
    assert [n.level for n in notices] == [80]


def test_entries_from_before_window_lengths_were_recorded_still_count():
    notified = {"claude:five_hour": {"level": 80, "resets_at": int(NOW) + 4380}}
    assert update_notices({"Claude": [limit(pct=85.0)]}, notified, NOW) == []
