import subprocess

from agent_stats import notify
from agent_stats.notify import Notice, send, update_notices

NOW = 1_791_100_000.0  # 2026-10-04 07:46:40 UTC


def limit(id="five_hour", label="5 h", pct=82.0, resets_at=int(NOW) + 4380):
    return {"id": id, "label": label, "used_percent": pct, "resets_at": resets_at, "window_minutes": 300}


def test_first_crossing_of_80_sends_one_normal_notice():
    notified = {}
    notices = update_notices({"Claude": [limit()]}, notified, NOW)
    assert notices == [Notice(key="claude:five_hour", level=80, summary="Claude: 5-h-Limit bei 82 %",
                              body="Reset in 1 h 13 min", urgent=False)]
    assert notified == {"claude:five_hour": {"level": 80, "resets_at": int(NOW) + 4380}}


def test_same_window_does_not_notify_twice():
    notified = {}
    update_notices({"Claude": [limit()]}, notified, NOW)
    assert update_notices({"Claude": [limit(pct=85.0)]}, notified, NOW + 60) == []


def test_jump_straight_to_95_sends_only_the_urgent_notice():
    notices = update_notices({"Codex": [limit(id="primary", label="Woche", pct=97.0, resets_at=None)]}, {}, NOW)
    assert [(n.level, n.urgent, n.summary, n.body) for n in notices] == [
        (95, True, "Codex: Wochenlimit bei 97 %", "")]


def test_80_then_95_in_same_window_sends_both_once():
    notified = {}
    assert [n.level for n in update_notices({"Claude": [limit(pct=81.0)]}, notified, NOW)] == [80]
    assert [n.level for n in update_notices({"Claude": [limit(pct=96.0)]}, notified, NOW)] == [95]
    assert update_notices({"Claude": [limit(pct=99.0)]}, notified, NOW) == []


def test_new_window_rearms_and_reset_window_counts_as_zero():
    notified = {}
    update_notices({"Claude": [limit(pct=90.0)]}, notified, NOW)
    # Reset-Zeitpunkt vorbei, noch alte Daten: zählt als 0 % → Eintrag entfällt, nichts verschickt
    assert update_notices({"Claude": [limit(pct=90.0, resets_at=int(NOW) - 1)]}, notified, NOW) == []
    assert notified == {}
    # neues Fenster mit neuem Reset-Zeitpunkt erreicht wieder 80 %
    nxt = update_notices({"Claude": [limit(pct=80.0, resets_at=int(NOW) + 18000)]}, notified, NOW)
    assert [n.level for n in nxt] == [80]


def test_scoped_labels_and_vanished_limits_are_cleaned_up():
    notified = {"claude:alt": {"level": 80, "resets_at": None}}
    notices = update_notices({"Claude": [limit(id="weekly_scoped:fable", label="Woche Fable", pct=80.0,
                                               resets_at=None)]}, notified, NOW)
    assert notices[0].summary == "Claude: Wochenlimit Fable bei 80 %"
    assert list(notified) == ["claude:weekly_scoped:fable"]


def test_below_threshold_sends_nothing():
    assert update_notices({"Claude": [limit(pct=79.9)], "Codex": []}, {}, NOW) == []


def test_send_calls_notify_send(monkeypatch):
    calls = []
    monkeypatch.setattr(notify.subprocess, "run", lambda args, **kw: calls.append((args, kw)))
    send(Notice("k", 95, "Claude: 5-h-Limit bei 96 %", "Reset in 5 min", True))
    args, kw = calls[0]
    assert args == ["notify-send", "-a", "Agent Stats", "-i", "utilities-system-monitor", "-u", "critical",
                    "Claude: 5-h-Limit bei 96 %", "Reset in 5 min"]
    assert kw["check"] is True and kw["timeout"] == 5


def test_send_failure_is_logged_not_raised(monkeypatch, caplog):
    def boom(args, **kw):
        raise FileNotFoundError("notify-send")
    monkeypatch.setattr(notify.subprocess, "run", boom)
    assert send(Notice("k", 80, "s", "b", False)) is False
    assert "FileNotFoundError" in caplog.text

    def fails(args, **kw):
        raise subprocess.CalledProcessError(1, args)
    monkeypatch.setattr(notify.subprocess, "run", fails)
    assert send(Notice("k", 80, "s", "b", False)) is False


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
    assert notices == [Notice(key="claude:five_hour", level=0, summary="Claude: 5-h-Limit in ~25 min voll",
                              body="Jetzt 62 % · Reset in 1 h 13 min", urgent=False)]
    assert update_notices({"Claude": [soon]}, notified, NOW + 60) == []  # nur einmal
    # später 80 % im selben Fenster: die Schwellenmeldung kommt trotzdem
    assert [n.level for n in update_notices({"Claude": [with_forecast(limit(pct=80.0), int(NOW) + 600)]},
                                            notified, NOW + 120)] == [80]


def test_no_early_warning_when_far_away_or_for_weekly_limits():
    later = with_forecast(limit(pct=62.0), int(NOW) + 31 * 60)
    weekly = with_forecast(limit(id="seven_day", label="Woche", pct=62.0) | {"window_minutes": 10080},
                           int(NOW) + 10 * 60)
    assert update_notices({"Claude": [later, weekly]}, {}, NOW) == []


def test_early_warning_with_eta_already_reached():
    notices = update_notices({"Claude": [with_forecast(limit(pct=70.0), int(NOW) - 10)]}, {}, NOW)
    assert notices[0].summary == "Claude: 5-h-Limit gleich voll"
