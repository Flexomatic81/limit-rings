"""install.sh and uninstall.sh in a scratch HOME; systemctl, kpackagetool6 and pgrep are stubs that log their calls."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ID = "io.github.flexomatic81.limitrings"
OLD_ID = "io.github.flexomatic81.agentstats"
MARKER = "# limit-rings: record limits for the plasmoid"
SNIPPET = "\n".join(line for line in (ROOT / "statusline-snippet.sh").read_text().splitlines()
                    if not line.startswith("#"))

STUB = r"""#!/bin/sh
call="$(basename "$0") $*"
echo "$call" >> "$STUB_LOG"
case "$call" in
    "kpackagetool6 -t Plasma/Applet --show "*) grep -qxF "${call##* }" "$STUB_PACKAGES" ;;
    "kpackagetool6 -t Plasma/Applet --install "*) [ -z "$STUB_INSTALL_FAIL" ] ;;
    "systemctl --user is-active --quiet plasma-plasmashell") [ -n "$STUB_SHELL_ACTIVE" ] ;;
    "systemctl --user is-active --quiet agent-stats"*) [ -n "$STUB_OLD_ACTIVE" ] ;;
    "systemctl --user stop agent-stats"*)
        if [ -d "$HOME/.cache/agent-stats" ]; then echo "old cache present at stop" >> "$STUB_LOG"; fi ;;
    "systemctl --user stop plasma-plasmashell")
        if grep -q agentstats "$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc"; then
            echo "old plugin present at shell stop" >> "$STUB_LOG"; fi ;;
    "pgrep "*) [ -n "$STUB_SHELL_RUNNING" ] ;;
esac
"""


@pytest.fixture
def env(tmp_path):
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name in ("systemctl", "kpackagetool6", "pgrep"):
        (stubs / name).write_text(STUB)
        (stubs / name).chmod(0o755)
    (tmp_path / "home").mkdir()
    (tmp_path / "packages").write_text("")
    (tmp_path / "calls").write_text("")
    return {"HOME": str(tmp_path / "home"), "PATH": f"{stubs}:/usr/bin:/bin", "LANG": "C.UTF-8",
            "STUB_LOG": str(tmp_path / "calls"), "STUB_PACKAGES": str(tmp_path / "packages")}


def home(env) -> Path:
    return Path(env["HOME"])


def run(script: str, env: dict, *args: str, **extra: str) -> str:
    r = subprocess.run(["bash", str(ROOT / script), *args], env={**env, **extra}, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, check=True)
    assert "stopped early" not in r.stderr  # the ERR trap must not fire on a successful run
    return r.stdout


def calls(env) -> list[str]:
    return Path(env["STUB_LOG"]).read_text().splitlines()


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_fresh_install_uses_the_new_names(env):
    out = run("install.sh", env)
    h = home(env)
    assert (h / ".local/share/limit-rings/limit_rings/collect.py").is_file()
    assert "-m limit_rings.collect" in (h / ".local/bin/limit-rings-collect").read_text()
    assert "limit-rings-collect" in (h / ".config/systemd/user/limit-rings.service").read_text()
    assert (h / ".config/systemd/user/limit-rings.timer").is_file()
    assert "systemctl --user enable --now limit-rings.timer" in calls(env)
    assert f"kpackagetool6 -t Plasma/Applet --install {ROOT}/plasmoid/{ID}" in calls(env)
    assert 'Drag the "Limit Rings" widget' in out


@pytest.mark.skipif(not shutil.which("msgfmt"), reason="gettext missing")
def test_fresh_install_compiles_translations_under_the_new_domains(env):
    run("install.sh", env)
    h = home(env)
    assert (h / f".local/share/locale/de/LC_MESSAGES/plasma_applet_{ID}.mo").is_file()
    assert (h / ".local/share/limit-rings/limit_rings/locale/de/LC_MESSAGES/limit-rings.mo").is_file()


def test_statusline_hook_inserted_with_the_new_marker(env):
    sl = write(home(env) / ".claude/statusline-command.sh", "#!/bin/sh\ninput=$(cat)\necho hi\n")
    run("install.sh", env, "--statusline")
    assert sl.read_text() == f"#!/bin/sh\ninput=$(cat)\n{MARKER}\n{SNIPPET}\necho hi\n"
    run("install.sh", env, "--statusline")  # already present → unchanged
    assert sl.read_text().count(MARKER) == 1


def test_uninstall_removes_the_new_names(env):
    run("install.sh", env)
    write(home(env) / ".cache/limit-rings/stats.json", "{}")
    run("uninstall.sh", env, "--purge")
    h = home(env)
    for gone in (".local/share/limit-rings", ".local/bin/limit-rings-collect", ".cache/limit-rings",
                 ".config/systemd/user/limit-rings.timer", ".config/systemd/user/limit-rings.service"):
        assert not (h / gone).exists(), gone
    assert "systemctl --user stop limit-rings.timer limit-rings.service" in calls(env)
    assert f"kpackagetool6 -t Plasma/Applet --remove {ID}" in calls(env)


OLD_MARKER = "# agent-stats: record limits for the plasmoid"
OLD_MARKER_DE = "# agent-stats: Limits für das Plasmoid mitschneiden"
OLD_SNIPPET = SNIPPET.replace("limit-rings", "agent-stats")
APPLETSRC = ".config/plasma-org.kde.plasma.desktop-appletsrc"
APPLETS = f"""[Containments][117][Applets][146]
immutability=1
plugin={OLD_ID}

[Containments][117][Applets][146][Configuration][General]
warnThreshold=70

[Containments][117][Applets][147]
plugin=org.kde.plasma.digitalclock
"""


def old_install(env):
    """What Agent Stats 0.1 left behind."""
    h = home(env)
    write(h / ".local/share/agent-stats/agent_stats/collect.py", "")
    write(h / ".local/bin/agent-stats-collect", "#!/bin/sh\n")
    write(h / ".config/systemd/user/agent-stats.timer", "")
    write(h / ".config/systemd/user/agent-stats.service", "")
    write(h / ".cache/agent-stats/state.json", '{"claude": {"days": "history"}}')
    write(h / ".cache/agent-stats/stats.json", "{}")
    Path(env["STUB_PACKAGES"]).write_text(OLD_ID + "\n")


def test_unknown_option_is_rejected(env):
    r = subprocess.run(["bash", str(ROOT / "install.sh"), "--bogus"], env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True)
    assert r.returncode == 2 and "Unknown option" in r.stderr


def test_migration_stops_the_old_timer_before_moving_the_cache(env):
    old_install(env)
    out = run("install.sh", env)
    h = home(env)
    assert "→ Migrating from Agent Stats" in out
    assert "systemctl --user stop agent-stats.timer agent-stats.service" in calls(env)
    assert "old cache present at stop" in calls(env)
    assert "systemctl --user disable agent-stats.timer" in calls(env)
    assert (h / ".cache/limit-rings/state.json").read_text() == '{"claude": {"days": "history"}}'
    for gone in (".cache/agent-stats", ".local/share/agent-stats", ".local/bin/agent-stats-collect",
                 ".config/systemd/user/agent-stats.timer", ".config/systemd/user/agent-stats.service"):
        assert not (h / gone).exists(), gone


def test_migration_fills_an_existing_cache_without_state(env):
    old_install(env)
    write(home(env) / ".cache/limit-rings/stats.json", "new")
    out = run("install.sh", env)
    h = home(env)
    assert (h / ".cache/limit-rings/state.json").read_text() == '{"claude": {"days": "history"}}'
    assert (h / ".cache/limit-rings/stats.json").read_text() == "new"
    assert not (h / ".cache/agent-stats").exists()
    assert "cache merged" in out


def test_failed_install_can_simply_be_rerun(env):
    old_install(env)
    before = f"input=$(cat)\n{OLD_MARKER}\n{OLD_SNIPPET}\n"
    sl = write(home(env) / ".claude/statusline-command.sh", before)
    r = subprocess.run(["bash", str(ROOT / "install.sh")], env={**env, "STUB_INSTALL_FAIL": "1"},
                       stdin=subprocess.DEVNULL, capture_output=True, text=True)
    assert r.returncode != 0 and "run it again" in r.stderr
    run("install.sh", env)
    assert sl.read_text() == f"input=$(cat)\n{MARKER}\n{SNIPPET}\n"
    assert (home(env) / ".cache/limit-rings/state.json").read_text() == '{"claude": {"days": "history"}}'


def test_migration_removes_the_old_widget_translations(env):
    old_install(env)
    mo = write(home(env) / f".local/share/locale/de/LC_MESSAGES/plasma_applet_{OLD_ID}.mo", "")
    run("install.sh", env)
    assert not mo.exists()


def test_migration_keeps_both_caches_when_the_new_one_exists(env):
    old_install(env)
    write(home(env) / ".cache/limit-rings/state.json", "new")
    out = run("install.sh", env)
    assert (home(env) / ".cache/limit-rings/state.json").read_text() == "new"
    assert (home(env) / ".cache/agent-stats/state.json").is_file()
    assert "left untouched" in out


@pytest.mark.parametrize("old_marker, indent", [(OLD_MARKER, ""), (OLD_MARKER_DE, "    ")])
def test_migration_rewrites_the_statusline_hook(env, old_marker, indent):
    before = f"#!/bin/sh\ninput=$(cat)\n{indent}{old_marker}\n{indent}{OLD_SNIPPET}\necho hi\n"
    after = f"#!/bin/sh\ninput=$(cat)\n{MARKER}\n{SNIPPET}\necho hi\n"
    sl = write(home(env) / ".claude/statusline-command.sh", before)
    sl.chmod(0o755)
    run("install.sh", env)
    assert sl.read_text() == after
    assert sl.stat().st_mode & 0o777 == 0o755
    assert (home(env) / ".claude/statusline-command.sh.bak-limit-rings").read_text() == before
    run("install.sh", env)
    assert sl.read_text() == after


def test_failed_statusline_rewrite_leaves_the_script_intact(env, tmp_path):
    before = f"#!/bin/sh\ninput=$(cat)\n{OLD_MARKER}\n{OLD_SNIPPET}\n"
    sl = write(home(env) / ".claude/statusline-command.sh", before)
    failing_awk(tmp_path)
    out = run("install.sh", env, STUB_AWK_FAIL='ENVIRON["OLD"]')
    assert sl.read_text() == before
    assert "could not be rewritten" in out
    assert [p.name for p in sl.parent.glob(sl.name + "*")] == [sl.name]


def test_migration_aborts_when_the_old_collector_does_not_stop(env):
    old_install(env)
    r = subprocess.run(["bash", str(ROOT / "install.sh")], env={**env, "STUB_OLD_ACTIVE": "1"},
                       stdin=subprocess.DEVNULL, capture_output=True, text=True)
    h = home(env)
    assert r.returncode == 1 and "could not be stopped" in r.stderr
    assert (h / ".cache/agent-stats/state.json").is_file() and not (h / ".cache/limit-rings").exists()
    assert (h / ".local/share/agent-stats").is_dir()


def test_migration_warns_when_the_old_cache_path_remains(env):
    sl = write(home(env) / ".claude/statusline-command.sh",
               f"input=$(cat)\n{OLD_MARKER}\necho 'my own line'\nd=$HOME/.cache/agent-stats\n")
    out = run("install.sh", env)
    assert "still refers to ~/.cache/agent-stats" in out
    assert "echo 'my own line'" in sl.read_text()
    assert MARKER in sl.read_text()


def test_widgets_switched_while_the_shell_is_stopped(env):
    old_install(env)
    rc = write(home(env) / APPLETSRC, APPLETS)
    run("install.sh", env, "--migrate-widgets", STUB_SHELL_ACTIVE="1")
    assert rc.read_text() == APPLETS.replace(f"plugin={OLD_ID}", f"plugin={ID}")
    assert (home(env) / (APPLETSRC + ".bak-limit-rings")).read_text() == APPLETS
    log = calls(env)
    assert "old plugin present at shell stop" in log
    stop = log.index("systemctl --user stop plasma-plasmashell")
    start = log.index("systemctl --user start plasma-plasmashell")
    assert stop < log.index(f"kpackagetool6 -t Plasma/Applet --remove {OLD_ID}") < start


FAILING_AWK = """#!/bin/sh
# Simulates a write that breaks off: partial output, then failure – for calls whose arguments contain $STUB_AWK_FAIL.
case "$*" in
    *"$STUB_AWK_FAIL"*) echo "partial"; exit 1 ;;
esac
exec /usr/bin/awk "$@"
"""


def failing_awk(tmp_path):
    awk = write(tmp_path / "stubs" / "awk", FAILING_AWK)
    awk.chmod(0o755)


def test_failed_widget_switch_leaves_the_layout_intact(env, tmp_path):
    old_install(env)
    rc = write(home(env) / APPLETSRC, APPLETS)
    failing_awk(tmp_path)
    out = run("install.sh", env, "--migrate-widgets", STUB_SHELL_ACTIVE="1", STUB_AWK_FAIL="plugin=")
    assert rc.read_text() == APPLETS
    assert "switching failed" in out
    assert [p.name for p in rc.parent.glob(rc.name + "*")] == [rc.name]  # no temp file, no backup of a failed try
    assert "systemctl --user start plasma-plasmashell" in calls(env)


def test_widgets_not_switched_without_consent(env):
    old_install(env)
    rc = write(home(env) / APPLETSRC, APPLETS)
    out = run("install.sh", env, STUB_SHELL_ACTIVE="1")
    assert rc.read_text() == APPLETS
    assert "--migrate-widgets" in out
    assert not any("plasma-plasmashell" in c or f"--remove {OLD_ID}" in c for c in calls(env))


def test_widgets_not_switched_when_plasmashell_runs_outside_systemd(env):
    old_install(env)
    rc = write(home(env) / APPLETSRC, APPLETS)
    out = run("install.sh", env, "--migrate-widgets", STUB_SHELL_RUNNING="1")
    assert rc.read_text() == APPLETS
    assert "kquitapp6 plasmashell" in out


def test_widgets_switched_directly_when_no_shell_runs(env):
    old_install(env)
    rc = write(home(env) / APPLETSRC, APPLETS)
    run("install.sh", env, "--migrate-widgets")
    assert f"plugin={ID}" in rc.read_text()
    assert not any(c in ("systemctl --user stop plasma-plasmashell", "systemctl --user start plasma-plasmashell")
                   for c in calls(env))


def test_old_package_removed_when_no_widget_is_placed(env):
    old_install(env)
    run("install.sh", env)
    assert f"kpackagetool6 -t Plasma/Applet --remove {OLD_ID}" in calls(env)


def test_second_run_after_migration_does_not_migrate_again(env):
    old_install(env)
    write(home(env) / APPLETSRC, APPLETS)
    run("install.sh", env, "--migrate-widgets")
    Path(env["STUB_LOG"]).write_text("")
    out = run("install.sh", env)
    assert "Migrating" not in out
    # only systemctl calls: kpackagetool6 calls carry the checkout path, which may itself contain "agent-stats"
    assert not any(c.startswith("systemctl") and ("agent-stats" in c or "plasma-plasmashell" in c)
                   for c in calls(env))


def test_symlinked_statusline_stays_a_symlink(env, tmp_path):
    after = f"#!/bin/sh\ninput=$(cat)\n{MARKER}\n{SNIPPET}\n"
    target = write(tmp_path / "dotfiles" / "statusline-command.sh",
                   f"#!/bin/sh\ninput=$(cat)\n{OLD_MARKER}\n{OLD_SNIPPET}\n")
    sl = home(env) / ".claude/statusline-command.sh"
    sl.parent.mkdir(parents=True)
    sl.symlink_to(target)
    run("install.sh", env)
    assert sl.is_symlink()
    assert target.read_text() == after


@pytest.mark.parametrize("tail", [" ", "\t", "\r"])
def test_migration_recognises_a_marker_with_trailing_whitespace(env, tail):
    sl = write(home(env) / ".claude/statusline-command.sh",
               f"input=$(cat)\n{OLD_MARKER}{tail}\n{OLD_SNIPPET}{tail}\n")
    out = run("install.sh", env)
    assert sl.read_text() == f"input=$(cat)\n{MARKER}\n{SNIPPET}\n"
    assert "switched from agent-stats" in out


def test_unrecognised_old_marker_is_reported_instead_of_switched(env):
    before = f"input=$(cat)\n{OLD_MARKER} – edited by hand\necho mine\n"
    sl = write(home(env) / ".claude/statusline-command.sh", before)
    out = run("install.sh", env)
    assert sl.read_text() == before
    assert "switched" not in out
    assert "please adjust it by hand" in out


def test_leftover_old_cache_with_state_only_repeats_the_hint(env):
    old_install(env)
    write(home(env) / ".cache/limit-rings/state.json", "new")
    run("install.sh", env)
    Path(env["STUB_LOG"]).write_text("")
    out = run("install.sh", env)
    assert "rm -r " + str(home(env) / ".cache/agent-stats") in out
    assert not any(c.startswith("systemctl") and "agent-stats" in c for c in calls(env))


def test_leftovers_of_an_interrupted_merge_are_completed(env):
    write(home(env) / ".cache/limit-rings/state.json", "merged")
    write(home(env) / ".cache/agent-stats/claude-statusline-limits.json", "{}")
    out = run("install.sh", env)
    h = home(env)
    assert (h / ".cache/limit-rings/state.json").read_text() == "merged"
    assert (h / ".cache/limit-rings/claude-statusline-limits.json").is_file()
    assert not (h / ".cache/agent-stats").exists()
    assert "cache merged" in out


def test_a_leftover_old_timer_alone_triggers_the_migration(env):
    timer = write(home(env) / ".config/systemd/user/agent-stats.timer", "")
    run("install.sh", env)
    assert "systemctl --user stop agent-stats.timer agent-stats.service" in calls(env)
    assert not timer.exists()


def test_migration_removes_the_old_timer_link_even_if_disable_does_not(env):
    old_install(env)
    wants = home(env) / ".config/systemd/user/timers.target.wants"
    wants.mkdir(parents=True)
    (wants / "agent-stats.timer").symlink_to("../agent-stats.timer")
    run("install.sh", env)
    assert not (wants / "agent-stats.timer").is_symlink()


def test_uninstall_removes_the_timer_link_even_if_disable_does_not(env):
    run("install.sh", env)
    wants = home(env) / ".config/systemd/user/timers.target.wants"
    wants.mkdir(parents=True)
    (wants / "limit-rings.timer").symlink_to("../limit-rings.timer")
    run("uninstall.sh", env, "--purge")
    assert not (wants / "limit-rings.timer").is_symlink()
