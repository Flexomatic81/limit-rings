"""The widget's entry point: one locked pass, the result as one JSON line on stdout, logs in a file."""

import ast
import fcntl
import json
import logging
import logging.handlers
import os
import runpy
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from limit_rings import widget
from limit_rings.collect import Paths
from limit_rings.notify import Notice

TZ = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 10, 5, 12, 0, tzinfo=TZ)
RUN_PY = Path(__file__).resolve().parents[1] / "run.py"
NOTICE = Notice("claude:five_hour", 80, "Claude: 5-hour limit at 81 %", "Reset in 2 h 0 min", False)


@pytest.fixture
def paths(tmp_path):
    return Paths.default(tmp_path)


@pytest.fixture(autouse=True)
def restore_umask():
    mask = os.umask(0o022)   # main() sets the process umask
    os.umask(mask)
    yield
    os.umask(mask)


@pytest.fixture(autouse=True)
def restore_logging():
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    for h in root.handlers:
        if h not in handlers:
            h.close()
    root.handlers[:], root.level = handlers, level


def lock_of(paths: Paths) -> Path:
    paths.stats_file.parent.mkdir(parents=True, exist_ok=True)
    return paths.stats_file.parent / ".lock"


def test_envelope_carries_stats_and_notices(paths, monkeypatch):
    def fake(p, now, tz, notifier, **kw):
        notifier(NOTICE)
        return {"schema": 2}
    monkeypatch.setattr(widget, "run_safely", fake)
    envelope, code = widget.collect_once(paths, lock_of(paths), lambda: NOW, TZ)
    assert code == 0
    assert envelope == {"envelope": 1, "stats": {"schema": 2}, "notices": [NOTICE.to_json()]}


def test_muted_instance_does_not_evaluate_notices(paths, monkeypatch):
    seen = []

    def fake(p, now, tz, notifier, **kw):
        seen.append(notifier)
        return {"schema": 2}
    monkeypatch.setattr(widget, "run_safely", fake)
    envelope, _ = widget.collect_once(paths, lock_of(paths), lambda: NOW, TZ, notify=False)
    assert seen == [None] and envelope["notices"] == []


def test_main_reads_the_notification_setting_from_the_environment(tmp_path, monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(widget, "run_safely", lambda p, now, tz, notifier, **kw: seen.append(notifier) or {"schema": 2})
    monkeypatch.setenv("LIMIT_RINGS_NOTIFY", "0")
    widget.main(home=tmp_path)
    assert seen == [None]


def test_lock_is_held_during_the_run(paths, monkeypatch):
    lock = lock_of(paths)

    def fake(p, now, tz, notifier, **kw):
        fd = os.open(lock, os.O_RDWR)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(fd)
        return {"schema": 2}
    monkeypatch.setattr(widget, "run_safely", fake)
    assert widget.collect_once(paths, lock, lambda: NOW, TZ)[1] == 0


def test_waits_for_a_busy_lock_and_then_runs_its_own_pass(paths, monkeypatch):
    lock = lock_of(paths)
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    threading.Timer(0.3, os.close, [fd]).start()   # the other instance finishes its pass

    def fake(p, now, tz, notifier, **kw):
        notifier(NOTICE)
        return {"schema": 2}
    monkeypatch.setattr(widget, "run_safely", fake)
    envelope, code = widget.collect_once(paths, lock, lambda: NOW, TZ, wait=5)
    assert code == 0 and envelope["notices"] == [NOTICE.to_json()]


def test_pass_waiting_while_the_cache_is_purged_does_not_run(paths, monkeypatch):
    # uninstall.sh deletes the cache under the lock; a pass waiting on the old lock inode must not run afterwards,
    # or it would recreate the directory that was just deleted.
    lock = lock_of(paths)
    cache = paths.stats_file.parent
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    monkeypatch.setattr(widget, "run_safely", lambda *a: pytest.fail("must not run after the cache was purged"))
    result = {}
    waiting = threading.Thread(target=lambda: result.update(
        out=widget.collect_once(paths, lock, lambda: NOW, TZ, wait=5)))
    waiting.start()
    time.sleep(0.3)
    shutil.rmtree(cache)       # as uninstall.sh does while holding the lock
    os.close(fd)
    waiting.join()
    assert result["out"] == ({"envelope": 1, "stats": None, "notices": []}, 0)
    assert not cache.exists()


def test_main_leaves_no_cache_behind_when_it_was_purged_during_the_wait(tmp_path, monkeypatch, capsys):
    cache = tmp_path / ".cache/limit-rings"

    def purged_while_waiting(fd, wait):
        shutil.rmtree(cache)
        return True
    monkeypatch.setattr(widget, "_acquire", purged_while_waiting)
    monkeypatch.setattr(widget, "run_safely", lambda *a: pytest.fail("must not run after the cache was purged"))
    assert widget.main(home=tmp_path) == 0
    assert json.loads(capsys.readouterr().out) == {"envelope": 1, "stats": None, "notices": []}
    assert not cache.exists()


def test_clock_is_read_after_waiting_for_the_lock(paths, monkeypatch):
    seen = []
    monkeypatch.setattr(widget, "run_safely", lambda p, now, tz, notifier, **kw: seen.append(now) or {"schema": 2})
    widget.collect_once(paths, lock_of(paths), lambda: NOW, TZ)
    assert seen == [NOW]


def test_busy_lock_returns_the_last_stats_without_running(paths, monkeypatch):
    lock = lock_of(paths)
    paths.stats_file.write_text('{"schema": 2, "generated_at": "x"}')
    monkeypatch.setattr(widget, "run_safely", lambda *a: pytest.fail("must not run while another pass holds the lock"))
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        envelope, code = widget.collect_once(paths, lock, lambda: NOW, TZ, wait=0)
    finally:
        os.close(fd)
    assert code == 0
    assert envelope == {"envelope": 1, "stats": {"schema": 2, "generated_at": "x"}, "notices": []}


@pytest.mark.parametrize("content", [None, "{not json", "[1, 2]"])
def test_busy_lock_with_corrupt_stats_gives_null(paths, monkeypatch, content):
    lock = lock_of(paths)
    if content is not None:
        paths.stats_file.write_text(content)
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        envelope, _ = widget.collect_once(paths, lock, lambda: NOW, TZ, wait=0)
    finally:
        os.close(fd)
    assert envelope["stats"] is None


def test_failed_run_returns_last_stats_exit_1_and_no_notices(paths, monkeypatch):
    lock = lock_of(paths)
    paths.stats_file.write_text('{"schema": 2}')

    def fake(p, now, tz, notifier, **kw):
        notifier(NOTICE)   # recorded before the crash, but state.json was not saved: must not be shown
        return None
    monkeypatch.setattr(widget, "run_safely", fake)
    envelope, code = widget.collect_once(paths, lock, lambda: NOW, TZ)
    assert code == 1
    assert envelope == {"envelope": 1, "stats": {"schema": 2}, "notices": []}


def test_main_prints_one_json_line_and_logs_to_a_file(tmp_path, monkeypatch, capsys):
    def fake(p, now, tz, notifier, **kw):
        logging.getLogger("limit_rings").warning("something odd")
        return {"schema": 2, "note": "5-Stunden-Limit für Ä"}
    monkeypatch.setattr(widget, "run_safely", fake)
    os.umask(0o022)
    assert widget.main(home=tmp_path) == 0
    out, err = capsys.readouterr()
    assert out.endswith("\n") and out.count("\n") == 1
    assert out.isascii()   # independent of the encoding of stdout
    assert json.loads(out)["stats"] == {"schema": 2, "note": "5-Stunden-Limit für Ä"}
    assert err == ""
    log = tmp_path / ".cache/limit-rings/collector.log"
    assert "something odd" in log.read_text()
    assert oct(log.stat().st_mode & 0o777) == "0o600"
    assert oct((tmp_path / ".cache/limit-rings").stat().st_mode & 0o777) == "0o700"


def test_log_file_is_capped(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(widget, "run_safely", lambda *a, **k: {"schema": 2})
    widget.main(home=tmp_path)
    handler = next(h for h in logging.getLogger().handlers if isinstance(h, logging.handlers.RotatingFileHandler))
    assert (handler.maxBytes, handler.backupCount) == (256 * 1024, 1)


def test_run_py_parses_with_old_python():
    ast.parse(RUN_PY.read_text(), feature_version=(3, 6))


def test_run_py_rejects_old_python(monkeypatch, capsys):
    monkeypatch.setattr(sys, "version_info", (3, 8, 10, "final", 0))
    with pytest.raises(SystemExit) as exit_:
        runpy.run_path(str(RUN_PY), run_name="__main__")
    assert exit_.value.code == 3
    assert json.loads(capsys.readouterr().out) == {"envelope": 1, "error": "python-too-old", "version": "3.8.10"}


def test_run_py_runs_the_widget_entry_point(monkeypatch):
    monkeypatch.setattr(widget, "main", lambda: 0)
    monkeypatch.setattr(sys, "dont_write_bytecode", False)   # restored after the test
    with pytest.raises(SystemExit) as exit_:
        runpy.run_path(str(RUN_PY), run_name="__main__")
    assert exit_.value.code == 0
    assert sys.dont_write_bytecode   # no .pyc next to the package: its files keep fixed mtimes across updates


def test_legacy_timer_stops_collection_and_is_reported(tmp_path, monkeypatch, capsys):
    (tmp_path / ".config/systemd/user").mkdir(parents=True)
    (tmp_path / ".config/systemd/user/limit-rings.timer").write_text("")
    (tmp_path / ".cache/limit-rings").mkdir(parents=True)
    (tmp_path / ".cache/limit-rings/stats.json").write_text('{"schema": 2}')
    monkeypatch.setattr(widget, "run_safely", lambda *a: pytest.fail("must not collect next to the old timer"))
    assert widget.main(home=tmp_path) == 0
    assert json.loads(capsys.readouterr().out) == {"envelope": 1, "error": "legacy-timer",
                                                   "stats": {"schema": 2}, "notices": []}


def test_main_reads_the_shown_providers_from_the_environment(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(widget, "run_safely",
                        lambda p, now, tz, notifier, providers, **kw: seen.append(providers) or {"schema": 2})
    for value, expected in ((None, {"claude", "codex"}), ("codex", {"codex"}), ("claude,codex", {"claude", "codex"}),
                            ("", set()), ("codex,gemini, claude", {"claude", "codex"})):
        if value is None:
            monkeypatch.delenv("LIMIT_RINGS_PROVIDERS", raising=False)
        else:
            monkeypatch.setenv("LIMIT_RINGS_PROVIDERS", value)
        widget.main(home=tmp_path)
        assert seen[-1] == expected, value


def test_notice_settings_from_the_environment():
    assert widget.notice_thresholds(None) == (80, 95)
    assert widget.notice_thresholds("50,75") == (50, 75)
    assert widget.notice_thresholds(" 60 , 90 ") == (60, 90)
    for bad in ("", "80", "95,80", "80,80", "0,50", "50,101", "a,b", "50,75,90"):
        assert widget.notice_thresholds(bad) == (80, 95), bad
    assert widget.reset_notice(None) is False
    assert widget.reset_notice("1") is True and widget.reset_notice("0") is False


def test_main_passes_the_notice_settings(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(widget, "run_safely",
                        lambda p, now, tz, notifier, providers=None, thresholds=None, reset_notice=None, accounts=(),
                        login=None: seen.append((thresholds, reset_notice)) or {"schema": 2})
    monkeypatch.setenv("LIMIT_RINGS_THRESHOLDS", "60,85")
    monkeypatch.setenv("LIMIT_RINGS_RESET_NOTICE", "1")
    widget.main(home=tmp_path)
    assert seen == [((60, 85), True)]


def test_main_reads_the_additional_accounts(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(widget, "run_safely", lambda p, now, tz, notifier, **kw: seen.append(kw["accounts"])
                        or {"schema": 2})
    monkeypatch.setenv("LIMIT_RINGS_ACCOUNTS", '[{"id":"k7f3a2","provider":"codex","dir":"~/.codex-b","name":"B"}]')
    widget.main(home=tmp_path)
    assert [(a.id, a.dir) for a in seen[0]] == [("k7f3a2", (tmp_path / ".codex-b").resolve())]
    monkeypatch.delenv("LIMIT_RINGS_ACCOUNTS")
    widget.main(home=tmp_path)
    assert seen[1] == []


def test_login_providers_from_the_environment():
    assert widget.login_providers(None) == {"claude", "codex"}   # old widgets and manual runs keep the login
    assert widget.login_providers("") == set()
    assert widget.login_providers("codex") == {"codex"}
    assert widget.login_providers("codex,gemini, claude") == {"claude", "codex"}


def test_main_passes_the_login_setting(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(widget, "run_safely", lambda p, now, tz, notifier, **kw: seen.append(kw["login"])
                        or {"schema": 2})
    monkeypatch.setenv("LIMIT_RINGS_LOGIN", "claude")
    widget.main(home=tmp_path)
    monkeypatch.delenv("LIMIT_RINGS_LOGIN")
    widget.main(home=tmp_path)
    assert seen == [{"claude"}, {"claude", "codex"}]
