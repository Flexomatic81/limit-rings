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
