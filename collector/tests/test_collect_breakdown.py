import json
from datetime import timedelta

from collect_helpers import BERLIN, NOW, codex_line, make_paths, ok_fetch

from limit_rings.collect import run


def week_fetch(token, timeout=10.0):
    return {
        "five_hour": {"utilization": 5.0, "resets_at": None},
        "seven_day": {"utilization": 30.0, "resets_at": "2026-10-06T04:00:00+00:00"},
    }


def project_line(msg_id, ts, cwd, out=10, model="claude-opus-5"):
    return json.dumps(
        {
            "timestamp": ts,
            "requestId": "r",
            "cwd": cwd,
            "message": {"id": msg_id, "model": model, "usage": {"input_tokens": 1, "output_tokens": out}},
        }
    )


def breakdown_setup(tmp_path):
    p = make_paths(tmp_path)
    repo = tmp_path / "work" / "website"
    (repo / ".git").mkdir(parents=True)
    (repo / "frontend").mkdir()
    (p.claude_root / "proj").mkdir()
    (p.claude_root / "proj" / "s.jsonl").write_text(
        "\n".join(
            [
                project_line("m1", "2026-10-03T10:00:00Z", str(repo / "frontend")),
                project_line("m2", "2026-09-28T10:00:00Z", str(repo)),  # before the weekly window
                project_line("m3", "2026-10-02T10:00:00Z", str(tmp_path / "scratch"), model="claude-sonnet-5"),
            ]
        )
        + "\n"
    )
    return p


def test_breakdown_covers_the_claude_week_window(tmp_path):
    p = breakdown_setup(tmp_path)
    b = run(p, NOW, BERLIN, fetch=week_fetch, notifier=lambda n: True)["providers"]["claude"]["breakdown"]
    assert b == {
        "since": "2026-09-29T06:00:00+02:00",
        "basis": "window",
        "total": 22,
        "projects": [{"name": "scratch", "total": 11}, {"name": "website", "total": 11}],
        "models": [{"name": "Opus 5", "total": 11}, {"name": "Sonnet 5", "total": 11}],
    }


def test_breakdown_falls_back_to_last_seven_days(tmp_path):
    p = breakdown_setup(tmp_path)
    b = run(p, NOW, BERLIN, fetch=ok_fetch, notifier=lambda n: True)["providers"]["claude"]["breakdown"]
    assert b["basis"] == "7d" and b["since"] == "2026-09-26T19:42:00+02:00"
    assert b["total"] == 33


def test_backfill_for_existing_state_counts_once(tmp_path):
    p = breakdown_setup(tmp_path)
    run(p, NOW, BERLIN, fetch=week_fetch, notifier=lambda n: True)
    state = json.loads(p.state_file.read_text())
    del state["claude"]["hourly"], state["claude"]["hourly_backfill"]  # state from before the update
    p.state_file.write_text(json.dumps(state))
    stats = run(p, NOW + timedelta(minutes=6), BERLIN, fetch=week_fetch, notifier=lambda n: True)
    c = stats["providers"]["claude"]
    assert c["breakdown"]["total"] == 22
    assert c["tokens"]["today"]["total"] == 11  # daily totals not counted twice
    assert json.loads(p.state_file.read_text())["claude"]["hourly_backfill"] is False


def test_fresh_state_without_hourly_is_not_counted_twice(tmp_path):
    p = breakdown_setup(tmp_path)
    p.state_file.parent.mkdir(parents=True, exist_ok=True)
    p.state_file.write_text('{"version": 1, "claude": {}, "codex": {}}')  # empty, without hourly
    b = run(p, NOW, BERLIN, fetch=week_fetch, notifier=lambda n: True)["providers"]["claude"]["breakdown"]
    assert b["total"] == 22


def test_state_keeps_legacy_labels_for_older_collectors(tmp_path):
    p = make_paths(tmp_path)
    run(p, NOW, BERLIN, fetch=ok_fetch)
    state = json.loads(p.state_file.read_text())
    assert all("label" in lim for lim in state["claude"]["limits"]["limits"])


def test_legacy_state_limits_are_published_with_model(tmp_path):
    p = make_paths(tmp_path)
    run(p, NOW, BERLIN, fetch=ok_fetch)
    state = json.loads(p.state_file.read_text())
    state["claude"]["limits"]["limits"].append(
        {"id": "seven_day_opus", "label": "Woche Opus", "used_percent": 3.0, "resets_at": None, "window_minutes": 10080}
    )
    state["claude"]["oauth_last_attempt"] = NOW.timestamp()  # throttled: keeps the saved limits
    p.state_file.write_text(json.dumps(state))

    def no_fetch(*a, **k):
        raise AssertionError("must not fetch while throttled")

    stats = run(p, NOW, BERLIN, fetch=no_fetch)
    opus = [lim for lim in stats["providers"]["claude"]["limits"] if lim["id"] == "seven_day_opus"]
    assert opus and opus[0]["model"] == "Opus" and "label" not in opus[0]


def codex_turn(ts, cwd, model):
    return json.dumps({"timestamp": ts, "type": "turn_context", "payload": {"cwd": cwd, "model": model}})


def codex_breakdown_setup(tmp_path):
    p = make_paths(tmp_path)
    repo = tmp_path / "work" / "linsens"
    (repo / ".git").mkdir(parents=True)
    (repo / "src").mkdir()
    (p.codex_root / "rollout-a.jsonl").write_text(
        "\n".join(
            [
                codex_turn("2026-10-03T09:59:00Z", str(repo / "src"), "gpt-6-astra"),
                codex_line("2026-10-03T10:00:00Z", 300),
                codex_turn("2026-10-03T10:59:00Z", str(tmp_path / "scratch"), "gpt-6-mini"),
                codex_line("2026-10-03T11:00:00Z", 400),  # last_token_usage of this turn: 400
            ]
        )
        + "\n"
    )
    return p


def test_codex_tokens_are_broken_down_by_project_and_model(tmp_path):
    p = codex_breakdown_setup(tmp_path)
    b = run(p, NOW, BERLIN, fetch=ok_fetch)["providers"]["codex"]["breakdown"]
    assert b["basis"] == "window"  # the Codex weekly limit from the session log
    assert b["total"] == 700
    assert b["projects"] == [{"name": "scratch", "total": 400}, {"name": "linsens", "total": 300}]
    assert b["models"] == [{"name": "gpt-6-mini", "total": 400}, {"name": "gpt-6-astra", "total": 300}]


def test_codex_backfill_for_existing_state_counts_once(tmp_path):
    p = codex_breakdown_setup(tmp_path)
    run(p, NOW, BERLIN, fetch=ok_fetch)
    state = json.loads(p.state_file.read_text())
    del state["codex"]["hourly"], state["codex"]["hourly_backfill"]  # state from before the update
    p.state_file.write_text(json.dumps(state))
    stats = run(p, NOW + timedelta(minutes=6), BERLIN, fetch=ok_fetch)
    x = stats["providers"]["codex"]
    assert x["breakdown"]["total"] == 700
    assert x["tokens"]["today"]["total"] == 700  # daily totals not counted twice
    assert json.loads(p.state_file.read_text())["codex"]["hourly_backfill"] is False
