import csv
import io
import json
import runpy
import sys
from pathlib import Path

from limit_rings import export
from limit_rings.accounts import parse_accounts
from limit_rings.state import new_state

RUN_PY = Path(__file__).resolve().parents[1] / "run.py"


def bucket(i=0, o=0, cr=0, cw=0):
    return {"input": i, "output": o, "cache_read": cr, "cache_write": cw}


def make_cache(home: Path) -> Path:
    cache = home / ".cache" / "limit-rings"
    cache.mkdir(parents=True)
    main = new_state()
    main["claude"]["buckets"] = {"2026-10-02": bucket(1, 2, 3, 4), "2026-09-30": bucket(o=5)}
    main["codex"]["buckets"] = {"2026-10-02": bucket(i=7)}
    (cache / "state.json").write_text(json.dumps(main))
    (home / ".claude-work").mkdir()
    [work] = parse_accounts(json.dumps([{"id": "w1", "provider": "claude", "dir": "~/.claude-work",
                                         "name": "Work"}]), home)
    side = new_state()
    side["claude"]["buckets"] = {"2026-10-01": bucket(cr=9)}
    (cache / "accounts").mkdir()
    (cache / "accounts" / f"{work.state_key}.json").write_text(json.dumps(side))
    stats = {"schema": 2, "providers": {"claude": {}, "codex": {}},
             "accounts": {"w1": {"provider": "claude", "name": "Work", "dir": "~/.claude-work"}}}
    (cache / "stats.json").write_text(json.dumps(stats))
    return cache


def test_rows_cover_main_state_and_shown_accounts_sorted_by_date(tmp_path):
    make_cache(tmp_path)
    rows = export.rows(tmp_path)
    assert [(r["date"], r["provider"], r["account"], r["total"]) for r in rows] == [
        ("2026-09-30", "claude", None, 5),
        ("2026-10-01", "claude", "Work", 9),
        ("2026-10-02", "claude", None, 10),
        ("2026-10-02", "codex", None, 7)]
    assert rows[2] == {"date": "2026-10-02", "provider": "claude", "account": None, "input": 1, "output": 2,
                       "cache_read": 3, "cache_write": 4, "total": 10}


def test_csv_and_json_output_write_nothing(tmp_path, capsys):
    cache = make_cache(tmp_path)
    before = sorted(str(p) for p in cache.rglob("*"))
    assert export.main(["--export"], home=tmp_path) == 0
    table = list(csv.reader(io.StringIO(capsys.readouterr().out)))
    assert table[0] == ["date", "provider", "account", "input", "output", "cache_read", "cache_write", "total"]
    assert table[2] == ["2026-10-01", "claude", "Work", "0", "0", "9", "0", "9"]
    assert table[3] == ["2026-10-02", "claude", "", "1", "2", "3", "4", "10"]
    assert export.main(["--export", "--json"], home=tmp_path) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["export_version"] == 1 and len(out["days"]) == 4 and out["days"][0]["account"] is None
    assert sorted(str(p) for p in cache.rglob("*")) == before   # no log, no lock, no state written


def test_without_cache_only_the_header_and_nothing_created(tmp_path, capsys):
    assert export.main(["--export"], home=tmp_path) == 0
    assert capsys.readouterr().out.splitlines() == [
        "date,provider,account,input,output,cache_read,cache_write,total"]
    assert not (tmp_path / ".cache").exists()


def test_unreadable_account_entries_and_states_are_skipped(tmp_path):
    cache = make_cache(tmp_path)
    stats = json.loads((cache / "stats.json").read_text())
    stats["accounts"].update({"bad": {"provider": "claude", "name": "Gone", "dir": "relative/dir"},
                              "odd": "not a dict"})
    (cache / "stats.json").write_text(json.dumps(stats))
    for f in (cache / "accounts").iterdir():
        f.write_text("{broken")
    assert [r["account"] for r in export.rows(tmp_path)] == [None, None, None]


def test_run_py_dispatches_export_without_collecting(tmp_path, monkeypatch, capsys):
    import limit_rings.widget as widget_mod
    monkeypatch.setattr(widget_mod, "main", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not collect")))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "argv", [str(RUN_PY), "--export", "--json"])
    try:
        runpy.run_path(str(RUN_PY), run_name="__main__")
    except SystemExit as e:
        assert e.code == 0
    assert json.loads(capsys.readouterr().out) == {"export_version": 1, "days": []}
