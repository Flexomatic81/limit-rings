import json
from datetime import timedelta

from collect_helpers import BERLIN, NOW, claude_line, codex_api, make_account, make_paths, ok_fetch

from limit_rings import collect
from limit_rings.collect import run


def test_without_accounts_the_output_only_gains_an_empty_section(tmp_path):
    p = make_paths(tmp_path)
    stats = run(p, NOW, BERLIN, fetch=ok_fetch)
    assert stats["accounts"] == {}
    assert not (p.state_file.parent / "accounts").exists()


def test_additional_accounts_are_collected_separately(tmp_path):
    p = make_paths(tmp_path)
    work, work_dir = make_account(tmp_path)
    (work_dir / "projects" / "proj" / "s.jsonl").write_text(claude_line("w1", "2026-10-03T10:00:00Z", out=99) + "\n")
    cx, _ = make_account(tmp_path, "codex", "c0d3x1", "Team")
    tokens = []

    def fetch(token, timeout=10.0):
        tokens.append(token)
        return ok_fetch(token) if token == "top-secret" else {"five_hour": {"utilization": 77.0, "resets_at": None}}

    notices = []
    stats = run(p, NOW, BERLIN, fetch=fetch, codex_fetch=codex_api, notifier=notices.append, accounts=[work, cx])
    assert sorted(tokens) == ["other-secret", "top-secret"]
    acc = stats["accounts"]["k7f3a2"]
    assert (acc["provider"], acc["name"], acc["dir"], acc["plan"]) == ("claude", "Work", str(work_dir), "max")
    assert [lim["used_percent"] for lim in acc["limits"]] == [77.0]
    assert acc["tokens"]["today"]["output"] == 99
    assert stats["providers"]["claude"]["tokens"]["today"]["total"] == 0  # main account untouched
    assert stats["accounts"]["c0d3x1"]["limits_source"] == "oauth"
    assert stats["accounts"]["c0d3x1"]["auth"]["status"] == "ok"
    assert (p.state_file.parent / "accounts" / f"{work.state_key}.json").exists()
    json.loads(p.stats_file.read_text())["accounts"]["k7f3a2"]


def test_changed_directory_starts_with_fresh_state(tmp_path):
    from limit_rings.accounts import parse_accounts

    p = make_paths(tmp_path)
    work, work_dir = make_account(tmp_path)
    (work_dir / "projects" / "proj" / "s.jsonl").write_text(claude_line("w1", "2026-10-03T10:00:00Z", out=11) + "\n")
    run(p, NOW, BERLIN, fetch=ok_fetch, accounts=[work])
    _other, other_dir = make_account(tmp_path, account_id="zz9")
    (other_dir / "projects" / "proj" / "s.jsonl").write_text(claude_line("o1", "2026-10-03T11:00:00Z", out=99) + "\n")
    (moved,) = parse_accounts(
        json.dumps([{"id": "k7f3a2", "provider": "claude", "dir": str(other_dir), "name": "Work"}]), tmp_path
    )
    stats = run(p, NOW + timedelta(minutes=10), BERLIN, fetch=ok_fetch, accounts=[moved])
    assert stats["accounts"]["k7f3a2"]["tokens"]["today"]["output"] == 99  # not 110


def test_account_notices_name_the_account(tmp_path):
    p = make_paths(tmp_path)
    work, _ = make_account(tmp_path)
    notices = []
    run(
        p,
        NOW,
        BERLIN,
        fetch=lambda token, timeout=10.0: {"five_hour": {"utilization": 85.0, "resets_at": None}},
        notifier=notices.append,
        accounts=[work],
    )
    assert sorted(n.summary for n in notices) == ["Claude (Work): 5-hour limit at 85 %", "Claude: 5-hour limit at 85 %"]


def test_rate_limit_in_an_account_pauses_only_that_account(tmp_path):
    import io
    import urllib.error

    p = make_paths(tmp_path)
    work, _ = make_account(tmp_path)

    def fetch(token, timeout=10.0):
        if token == "other-secret":
            raise urllib.error.HTTPError(
                "https://example.invalid", 429, "Too Many Requests", {"Retry-After": "1800"}, io.BytesIO(b"")
            )
        return ok_fetch(token)

    stats = run(p, NOW, BERLIN, fetch=fetch, accounts=[work])
    assert stats["accounts"]["k7f3a2"]["limits_paused_until"] is not None
    assert stats["providers"]["claude"]["limits_paused_until"] is None


def test_broken_or_missing_accounts_do_not_disturb_the_others(tmp_path, monkeypatch):
    from limit_rings.accounts import parse_accounts

    p = make_paths(tmp_path)
    work, _ = make_account(tmp_path)
    missing, invalid = parse_accounts(
        json.dumps(
            [
                {"id": "m1", "provider": "codex", "dir": str(tmp_path / "nowhere"), "name": "Gone"},
                {"id": "i1", "provider": "gemini", "dir": "/x", "name": "Bad"},
            ]
        ),
        tmp_path,
    )
    real_pass = collect._pass

    def flaky(paths, *a, **k):
        if paths.state_file.name == f"{work.state_key}.json":
            raise RuntimeError("boom")
        return real_pass(paths, *a, **k)

    (p.state_file.parent / "accounts").mkdir(parents=True)
    (p.state_file.parent / "accounts" / f"{work.state_key}.json").write_text("{}")
    monkeypatch.setattr(collect, "_pass", flaky)
    stats = run(p, NOW, BERLIN, fetch=ok_fetch, accounts=[work, missing, invalid])
    assert stats["providers"]["claude"]["limits_source"] == "oauth"
    assert stats["accounts"]["k7f3a2"]["errors"] == [{"code": "logs_failed"}]
    assert (p.state_file.parent / "accounts" / f"{work.state_key}.json.corrupt").exists()
    gone = stats["accounts"]["m1"]
    assert gone["auth"]["status"] == "missing" and gone["limits"] == [] and gone["tokens"]["today"]["total"] == 0
    assert stats["accounts"]["i1"]["errors"] == [{"code": "account_invalid"}]
    assert stats["accounts"]["i1"]["provider"] is None


def test_failed_run_sets_the_account_states_aside_too(tmp_path, monkeypatch):
    p = make_paths(tmp_path)
    p.credentials.unlink()  # no logins: no network in run_safely's default fetchers
    work, work_dir = make_account(tmp_path)
    (work_dir / ".credentials.json").unlink()
    (work_dir / "projects" / "proj" / "s.jsonl").write_text(claude_line("w1", "2026-10-03T10:00:00Z") + "\n")
    real = collect.write_json_atomic

    def failing(path, obj):
        if path == p.stats_file:
            raise OSError("disk full")
        return real(path, obj)

    monkeypatch.setattr(collect, "write_json_atomic", failing)
    assert collect.run_safely(p, NOW, BERLIN, None, accounts=[work]) is None
    folder = p.state_file.parent / "accounts"
    assert (folder / f"{work.state_key}.json.corrupt").exists()
    assert not (folder / f"{work.state_key}.json").exists()


def test_hidden_account_states_are_pruned_after_30_days(tmp_path):
    import os

    p = make_paths(tmp_path)
    folder = p.state_file.parent / "accounts"
    folder.mkdir(parents=True)
    old = folder / "claude-0123456789ab.json"
    old.write_text("{}")
    os.utime(old, (NOW.timestamp() - 31 * 86400,) * 2)
    run(p, NOW, BERLIN, fetch=ok_fetch)
    assert not old.exists()


def test_a_new_window_shows_up_as_a_change(tmp_path):
    p = make_paths(tmp_path)
    responses = iter([ok_fetch(None), {**ok_fetch(None), "seven_day_opus": {"utilization": 3.0, "resets_at": None}}])

    def fetch(token, timeout=10.0):
        return next(responses)

    first = run(p, NOW, BERLIN, fetch=fetch, notifier=lambda n: True)
    assert first["providers"]["claude"]["changes"] == [] and first["providers"]["codex"]["changes"] == []
    later = NOW + timedelta(minutes=6)
    stats = run(p, later, BERLIN, fetch=fetch, notifier=lambda n: True)
    assert stats["providers"]["claude"]["changes"] == [
        {
            "kind": "new",
            "limit": {"id": "seven_day_opus", "window_minutes": 10080, "model": "Opus"},
            "at": "2026-10-03T19:48:00+02:00",
        }
    ]
