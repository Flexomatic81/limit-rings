"""macos/install.sh in a scratch HOME; curl, codesign, spctl, ditto, shasum, open, pgrep and uname are stubs."""

import hashlib
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "macos" / "install.sh"
APP = "Übersicht.app"
WELCOME = "export const command = 'echo hi'\n"   # stands in for Übersicht's GettingStarted.jsx
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell")

STUBS = {
    "uname": 'echo "${STUB_UNAME:-Darwin}"\n',
    # curl -fsSL [-o FILE] URL: the page, or a fixture by the URL's last path part
    "curl": r'''
out=""; url=""
while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift;; -*) ;; *) url="$1";; esac; shift; done
echo "curl $url" >> "$STUB_LOG"
case "$url" in
  "$LIMIT_RINGS_UEBERSICHT_PAGE") src="$FIXTURES/page.html";;
  *) src="$FIXTURES/${url##*/}";;
esac
[ -f "$src" ] || exit 22
if [ -n "$out" ]; then cp "$src" "$out"; else cat "$src"; fi
''',
    "codesign": r'''
echo "codesign $*" >> "$STUB_LOG"
case "$1" in
  --verify) [ -z "$STUB_CODESIGN_FAIL" ];;
  -dv) echo "Authority=Developer ID Application: Someone" >&2; echo "TeamIdentifier=${STUB_TEAM:-S3P44NRLCW}" >&2;;
esac
''',
    "spctl": 'echo "spctl $*" >> "$STUB_LOG"; [ -z "$STUB_SPCTL_FAIL" ]\n',
    # ditto -x -k ZIP DIR
    # ditto -x -k ZIP DIR, with the Python running the tests (macOS runners have no usable /usr/bin/python3)
    "ditto": f'"{sys.executable}" -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$3" "$4"\n',
    # the real shasum on macOS; GNU sha256sum on Linux
    "shasum": r'''
[ -x /usr/bin/shasum ] && exec /usr/bin/shasum "$@"
[ "$1" = "-a" ] && shift 2
if [ "$1" = "-c" ]; then sha256sum -c "$2"; else sha256sum "$@"; fi
''',
    "open": 'echo "open $*" >> "$STUB_LOG"\n',
    "pgrep": '[ -n "$STUB_RUNNING" ]\n',
}


def _zip(path: Path, files: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, text in files.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (0o755 if name.endswith(".sh") else 0o644) << 16
            zf.writestr(info, text)
    return path


def _sha256_file(path: Path) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n")


@pytest.fixture
def env(tmp_path):
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, body in STUBS.items():
        (stubs / name).write_text("#!/bin/sh\n" + body)
        (stubs / name).chmod(0o755)
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "page.html").write_text(
        '<a href="https://tracesof.net/uebersicht/releases/Uebersicht-1.6.82.app.zip">Download</a>')
    _zip(fixtures / "Uebersicht-1.6.82.app.zip", {f"{APP}/Contents/Info.plist": "<plist/>"})
    # the widget: a run.sh that answers --which like a found Python 3.13
    widget = _zip(fixtures / "limit-rings-macos.zip", {
        "limit-rings.widget/index.jsx": "export const render = () => null\n",
        "limit-rings.widget/run.sh": '#!/bin/sh\n[ "$1" = --which ] && echo /usr/local/bin/python3 && exit "${STUB_PY:-0}"\n'})
    _sha256_file(widget)
    home = tmp_path / "home"
    home.mkdir()
    (tmp_path / "system-apps").mkdir()
    return {"HOME": str(home), "PATH": f"{stubs}:/usr/bin:/bin", "LANG": "C.UTF-8",
            "STUB_LOG": str(tmp_path / "calls"), "FIXTURES": str(fixtures),
            "LIMIT_RINGS_RELEASE_BASE": "https://example.invalid/releases",
            "LIMIT_RINGS_UEBERSICHT_PAGE": "https://example.invalid/uebersicht/",
            "LIMIT_RINGS_SYSTEM_APPS": str(tmp_path / "system-apps")}


def install(env, *args, **extra):
    with SCRIPT.open("rb") as script:   # like curl … | sh: the script arrives on stdin
        return subprocess.run(["sh", "-s", "--", *args], stdin=script, env={**env, **extra},
                              capture_output=True, text=True)


def calls(env) -> list[str]:
    p = Path(env["STUB_LOG"])
    return p.read_text().splitlines() if p.exists() else []


def widgets(env) -> Path:
    return Path(env["HOME"]) / "Library" / "Application Support" / "Übersicht" / "widgets"


def user_app(env) -> Path:
    return Path(env["HOME"]) / "Applications" / APP


def test_runs_from_stdin_like_curl_pipe_sh(env):
    res = install(env)
    assert res.returncode == 0, res.stderr
    assert "Limit Rings: " in res.stdout


def test_refuses_to_run_outside_macos(env):
    res = install(env, STUB_UNAME="Linux")
    assert res.returncode == 1 and "macOS" in res.stderr
    assert calls(env) == []


def test_unknown_option_and_bad_version_are_refused(env):
    assert install(env, "--frobnicate").returncode == 1
    assert install(env, "--version", "latest").returncode == 1
    assert install(env, "--version").returncode == 1


def test_missing_uebersicht_is_downloaded_and_verified(env):
    res = install(env)
    assert res.returncode == 0, res.stderr
    assert (user_app(env) / "Contents" / "Info.plist").is_file()
    log = calls(env)
    assert "curl https://example.invalid/uebersicht/" in log
    assert "curl https://tracesof.net/uebersicht/releases/Uebersicht-1.6.82.app.zip" in log
    assert any(c.startswith("codesign --verify --deep --strict") for c in log)
    assert any(c.startswith("spctl -a -t exec") for c in log)


@pytest.mark.parametrize("stub", [{"STUB_CODESIGN_FAIL": "1"}, {"STUB_SPCTL_FAIL": "1"}, {"STUB_TEAM": "ABCDE12345"}])
def test_untrusted_uebersicht_is_not_installed(env, stub):
    res = install(env, **stub)
    assert res.returncode == 1 and "not installed" in res.stderr
    assert not user_app(env).exists() and not (widgets(env) / "limit-rings.widget").exists()


def test_download_link_must_point_to_tracesof(env):
    Path(env["FIXTURES"], "page.html").write_text('<a href="https://evil.example/Uebersicht-1.6.82.app.zip">x</a>')
    res = install(env)
    assert res.returncode == 1 and not user_app(env).exists()


def test_second_installer_at_the_same_time_is_refused(env):
    lock = Path(env["HOME"]) / "Library" / "Application Support" / "Übersicht" / "limit-rings-install.lock"
    lock.mkdir(parents=True)
    res = install(env)
    assert res.returncode == 1 and "another installer" in res.stderr
    assert lock.is_dir() and calls(env) == []          # the other run's lock stays, nothing was touched


def test_stale_lock_of_a_killed_run_is_taken_over_and_its_widget_restored(env):
    base = Path(env["HOME"]) / "Library" / "Application Support" / "Übersicht"
    dead = subprocess.run(["sh", "-c", "echo $$"], capture_output=True, text=True).stdout.strip()   # finished
    (base / "limit-rings-install.lock").mkdir(parents=True)
    (base / "limit-rings-install.lock" / "pid").write_text(dead + "\n")
    (base / "limit-rings-staging" / "previous").mkdir(parents=True)
    (base / "limit-rings-staging" / "previous" / "index.jsx").write_text("old")
    Path(env["FIXTURES"], "limit-rings-macos.zip").unlink()      # even offline, the widget comes back
    res = install(env)
    assert "took over the lock" in res.stdout
    assert (widgets(env) / "limit-rings.widget" / "index.jsx").read_text() == "old"
    assert not (base / "limit-rings-install.lock").exists()


def test_lock_of_a_running_installer_is_respected(env):
    lock = Path(env["HOME"]) / "Library" / "Application Support" / "Übersicht" / "limit-rings-install.lock"
    lock.mkdir(parents=True)
    (lock / "pid").write_text(f"{os.getpid()}\n")               # this test process is alive
    res = install(env)
    assert res.returncode == 1 and "another installer" in res.stderr and lock.is_dir()


def test_lock_is_released_after_a_run(env):
    install(env)
    assert not (Path(env["HOME"]) / "Library" / "Application Support" / "Übersicht" / "limit-rings-install.lock").exists()


def test_existing_system_uebersicht_is_kept(env):
    system = Path(env["LIMIT_RINGS_SYSTEM_APPS"]) / APP
    (system / "Contents").mkdir(parents=True)
    res = install(env)
    assert res.returncode == 0, res.stderr
    assert not user_app(env).exists()
    assert not any("tracesof" in c or "uebersicht/" in c for c in calls(env))
