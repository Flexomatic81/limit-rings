"""macos/…/run.sh picks the first Python ≥ 3.10 and otherwise lets run.py report the old one."""

import os
import shutil
import subprocess
import sys
import time

import pytest
from build_plasmoid import ROOT

RUN_SH = ROOT / "macos" / "limit-rings.widget" / "run.sh"
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell")


def fake_python(path, version, log):
    """A stand-in that answers the version check like that Python and logs any other call."""
    major, minor = version
    path.write_text(f"""#!/bin/sh
if [ "$1" = "-c" ]; then [ {minor} -ge 10 ] && [ {major} -eq 3 ]; exit $?; fi
echo "$0 $*" >> {log}
echo '{{"envelope": 1}}'
""")
    path.chmod(0o755)
    return path


def run(candidates, tmp_path, **extra):
    env = {**os.environ, "LIMIT_RINGS_PYTHONS": " ".join(str(c) for c in candidates), **extra}
    return subprocess.run(["sh", str(RUN_SH)], capture_output=True, text=True, env=env, cwd=tmp_path)


def test_prefers_a_suitable_python_over_an_old_one(tmp_path):
    log = tmp_path / "log"
    old = fake_python(tmp_path / "py39", (3, 9), log)
    new = fake_python(tmp_path / "py313", (3, 13), log)
    res = run([old, new], tmp_path)
    assert res.returncode == 0 and res.stdout.strip() == '{"envelope": 1}'
    assert log.read_text().startswith(f"{new} ") and log.read_text().rstrip().endswith("collector/run.py")


def test_without_a_suitable_one_runs_the_first_so_run_py_reports_it(tmp_path):
    log = tmp_path / "log"
    old = fake_python(tmp_path / "py39", (3, 9), log)
    run([tmp_path / "missing", old], tmp_path)
    assert log.read_text().startswith(f"{old} ")


def test_skips_the_apple_stub_without_developer_tools(tmp_path):
    # /usr/bin/python3 without the Command Line Tools opens an install dialog on ANY call, even the probe.
    log = tmp_path / "log"
    calls = tmp_path / "calls"
    apple = tmp_path / "apple"
    apple.write_text(f"#!/bin/sh\necho \"$0 $*\" >> {calls}\nexit 1\n")
    apple.chmod(0o755)
    new = fake_python(tmp_path / "py312", (3, 12), log)
    res = run([apple, new], tmp_path, LIMIT_RINGS_APPLE_PYTHON=str(apple),
              LIMIT_RINGS_XCODE_SELECT=shutil.which("false"))
    assert res.returncode == 0 and not calls.exists()   # the stub is not even probed
    assert log.read_text().startswith(f"{new} ")
    # With the tools it is a real Python and gets used.
    real = fake_python(apple, (3, 13), log)
    run([real], tmp_path, LIMIT_RINGS_APPLE_PYTHON=str(real), LIMIT_RINGS_XCODE_SELECT=shutil.which("true"))
    assert log.read_text().splitlines()[-1].startswith(f"{real} ")


def test_the_apple_stub_alone_without_developer_tools_is_127(tmp_path):
    apple = fake_python(tmp_path / "apple", (3, 13), tmp_path / "log")
    res = run([apple], tmp_path, LIMIT_RINGS_APPLE_PYTHON=str(apple),
              LIMIT_RINGS_XCODE_SELECT=shutil.which("false"))
    assert res.returncode == 127 and res.stdout == "" and not (tmp_path / "log").exists()


def test_a_hung_pass_is_killed_at_the_deadline(tmp_path):
    hung = tmp_path / "hung"
    hung.write_text("#!/bin/sh\nif [ \"$1\" = \"-c\" ]; then exit 0; fi\nexec sleep 30\n")
    hung.chmod(0o755)
    start = time.monotonic()
    res = run([hung], tmp_path, LIMIT_RINGS_DEADLINE="1")
    assert res.returncode == 124 and time.monotonic() - start < 10


def test_no_python_at_all_is_127(tmp_path):
    res = run([tmp_path / "missing"], tmp_path)
    assert res.returncode == 127 and res.stdout == ""
