import json
import runpy
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from limit_rings import status

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 10, 8, 13, 20, tzinfo=BERLIN)
T = NOW.timestamp()
RUN_PY = Path(__file__).resolve().parents[1] / "run.py"


@pytest.fixture(autouse=True)
def berlin(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Berlin")   # times come out in the local zone, as in stats.json


def iso(seconds_from_now):
    return (NOW + timedelta(seconds=seconds_from_now)).isoformat(timespec="seconds")


def stats(**overrides):
    claude = {"limits": [
        {"id": "five_hour", "used_percent": 64.0, "resets_at": int(T + 6600), "window_minutes": 300,
         "forecast": {"status": "full", "eta": int(T + 2400)}},
        {"id": "seven_day_opus", "used_percent": 27.0, "resets_at": int(T + 277200), "window_minutes": 10080,
         "model": "Opus", "forecast": {"status": "enough"}}],
        "limits_source": "oauth", "limits_updated_at": iso(-30), "plan": "max", "login": True,
        "tokens": {}, "daily": [], "errors": []}
    codex = {"limits": [{"id": "primary", "used_percent": 18.0, "resets_at": int(T - 60), "window_minutes": 300}],
             "limits_source": "session_log", "limits_updated_at": iso(-600), "plan": "plus", "login": False}
    work = {**claude, "limits": [{"id": "five_hour", "used_percent": 92.0, "resets_at": None, "window_minutes": 300}],
            "plan": "pro", "provider": "claude", "name": "Work", "dir": "~/.claude-work"}
    out = {"schema": 2, "generated_at": iso(-40), "providers": {"claude": claude, "codex": codex},
           "accounts": {"k7f3a2": work}}
    out.update(overrides)
    return out


def test_status_json_is_lean_and_versioned():
    out = status.build(stats(), T)
    assert out["status_version"] == 1
    assert out["generated_at"] == iso(-40) and out["stale"] is False
    assert [p["id"] for p in out["providers"]] == ["claude", "codex", "k7f3a2"]
    claude, codex, work = out["providers"]
    assert {k: claude[k] for k in ("provider", "name", "account", "plan", "login", "limits_source")} == \
        {"provider": "claude", "name": "Claude", "account": None, "plan": "max", "login": True,
         "limits_source": "oauth"}
    five, opus = claude["limits"]
    assert five == {"id": "five_hour", "window_minutes": 300, "model": None, "used_percent": 64.0,
                    "remaining_percent": 36.0, "resets_at": iso(6600), "reset": False,
                    "forecast": {"status": "full", "eta": iso(2400)}}
    assert opus["model"] == "Opus" and opus["forecast"] == {"status": "enough"}
    # a window whose reset has passed counts as 0 % used, like in the widget
    assert codex["limits"][0]["reset"] is True and codex["limits"][0]["used_percent"] == 0.0
    assert codex["limits"][0]["remaining_percent"] == 100.0 and codex["limits"][0]["forecast"] is None
    assert work["name"] == "Claude (Work)" and work["account"] == {"name": "Work", "dir": "~/.claude-work"}
    assert work["limits"][0]["resets_at"] is None
    assert "tokens" not in claude and "daily" not in claude


def test_old_or_missing_stats_are_marked():
    assert status.build(stats(generated_at=iso(-301)), T)["stale"] is True
    empty = status.build(None, T)
    assert empty == {"status_version": 1, "generated_at": None, "stale": True, "providers": []}
    assert status.build({"schema": 99}, T)["providers"] == []


def test_waybar_output():
    bar = status.waybar(status.build(stats(), T), T)
    assert bar["text"] == "C 64% · X 0% · W 92%"
    assert bar["percentage"] == 92
    assert bar["class"] == ["critical"]
    lines = bar["tooltip"].split("\n")
    assert lines[0] == "Claude · 5-hour limit: 64 % · Reset in 1 h 50 min · full in ~40 min"
    assert lines[1] == "Claude · weekly Opus limit: 27 % · Reset in 3 d 5 h · lasts until reset"
    assert lines[2] == "Codex · 5-hour limit: reset"


def test_waybar_classes_follow_usage_forecast_and_age():
    s = stats(accounts={})
    s["providers"]["claude"]["limits"][0]["used_percent"] = 50.0
    assert status.waybar(status.build(s, T), T)["class"] == ["warning"]       # forecast: full before the reset
    s["providers"]["claude"]["limits"][0]["forecast"] = {"status": "enough"}
    assert status.waybar(status.build(s, T), T)["class"] == ["normal"]
    s["providers"]["claude"]["limits"][0]["used_percent"] = 75.0
    assert status.waybar(status.build(s, T), T)["class"] == ["warning"]
    s["generated_at"] = iso(-900)
    assert status.waybar(status.build(s, T), T)["class"] == ["warning", "stale"]


def test_waybar_without_data():
    bar = status.waybar(status.build(None, T), T)
    assert bar == {"text": "–", "tooltip": "No data – is the Limit Rings widget running?", "class": ["stale"],
                   "percentage": 0}


def test_main_reads_only_the_stats_file(tmp_path, capsys):
    cache = tmp_path / ".cache" / "limit-rings"
    cache.mkdir(parents=True)
    (cache / "stats.json").write_text(json.dumps(stats()))
    before = sorted(p.name for p in cache.iterdir())
    assert status.main(["--status"], home=tmp_path, now=T) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status_version"] == 1 and len(out["providers"]) == 3
    assert status.main(["--status", "--waybar"], home=tmp_path, now=T) == 0
    assert json.loads(capsys.readouterr().out)["text"] == "C 64% · X 0% · W 92%"
    assert sorted(p.name for p in cache.iterdir()) == before     # no log, no lock, no state written


def test_main_without_cache_creates_nothing(tmp_path, capsys):
    assert status.main(["--status"], home=tmp_path, now=T) == 0
    assert json.loads(capsys.readouterr().out)["providers"] == []
    assert not (tmp_path / ".cache").exists()


def test_run_py_dispatches_status_without_collecting(tmp_path, monkeypatch, capsys):
    import limit_rings.widget as widget_mod
    monkeypatch.setattr(widget_mod, "main", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not collect")))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "argv", [str(RUN_PY), "--status"])
    try:
        runpy.run_path(str(RUN_PY), run_name="__main__")
    except SystemExit as e:
        assert e.code == 0
    assert json.loads(capsys.readouterr().out)["status_version"] == 1
