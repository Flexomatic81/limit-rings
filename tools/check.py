"""Runs the project's checks – the same ones CI runs.

    python3 tools/check.py                   every step
    python3 tools/check.py fast              ruff, format and mypy (what the pre-commit hook runs)
    python3 tools/check.py qmllint qmltest   single steps, in the order given
    python3 tools/check.py --install-hook    run the fast checks before every commit

With uv installed, the Python tools run in the versions pinned in tools/requirements-dev.txt; without uv
(and always in CI) they are taken from PATH. qmllint and qmltestrunner come with Qt: missing locally, their
steps are skipped; in CI a missing tool fails the run.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINS_FILE = ROOT / "tools" / "requirements-dev.txt"
PACKAGE = ROOT / "plasmoid" / "io.github.flexomatic81.limitrings" / "contents"
QT_BIN = Path("/usr/lib/qt6/bin")
STEPS = ("ruff", "format", "mypy", "shellcheck", "qmllint", "pytest", "qmltest")
GROUPS = {"fast": ("ruff", "format", "mypy")}
QT_STEPS = {"qmllint", "qmltest"}
COVERAGE_FLOOR = 97
INSTALL_HINT = "install uv, or: python3 -m pip install -r tools/requirements-dev.txt"


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


@dataclass(frozen=True)
class Env:
    pins: dict[str, str]
    use_uv: bool
    in_ci: bool
    which: Callable[[str], str | None] = shutil.which
    has_module: Callable[[str], bool] = _has_module
    qt_bin: Path = QT_BIN


@dataclass(frozen=True)
class Step:
    name: str
    command: list[str] | None  # None: the tool is missing
    cwd: Path = ROOT
    missing: str = ""


def read_pins(text: str) -> dict[str, str]:
    """'name==version' lines → {name: version}; comments and blank lines are skipped, anything else is an error."""
    pins = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name, sep, version = line.partition("==")
        if not sep or not name.strip() or not version.strip():
            raise ValueError(f"not an exact pin: {raw!r}")
        pins[name.strip().lower()] = version.strip()
    return pins


def select_steps(args: Sequence[str]) -> list[str]:
    """Step and group names → steps in the order given, each once; no names → every step."""
    if not args:
        return list(STEPS)
    out: list[str] = []
    for arg in args:
        names: Sequence[str]
        if arg in GROUPS:
            names = GROUPS[arg]
        elif arg in STEPS:
            names = (arg,)
        else:
            raise ValueError(f"unknown step: {arg} (steps: {', '.join(STEPS)}; groups: {', '.join(GROUPS)})")
        out += [n for n in names if n not in out]
    return out


def detect_env() -> Env:
    in_ci = bool(os.environ.get("CI"))
    pins = read_pins(PINS_FILE.read_text(encoding="utf-8"))
    return Env(pins=pins, use_uv=not in_ci and shutil.which("uv") is not None, in_ci=in_ci)


def _python_tool(tool: str, package: str, env: Env) -> list[str] | None:
    if env.use_uv:
        return ["uvx", "--from", f"{package}=={env.pins[package]}", tool]
    found = env.which(tool)
    return [found] if found else None


def _qt_tool(name: str, env: Env) -> str | None:
    """Qt's own bin directory first (the plain names there are Qt 6), then the names distributions put on PATH."""
    if (env.qt_bin / name).is_file():
        return str(env.qt_bin / name)
    for candidate in (f"{name}6", f"{name}-qt6", name):
        found = env.which(candidate)
        if found:
            return found
    return None


def _shell_files() -> list[str]:
    listed = subprocess.run(["git", "ls-files", "*.sh"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [*listed.stdout.split(), "tools/hooks/pre-commit"]


def _qml_files() -> list[str]:
    files = sorted((PACKAGE / "ui").glob("*.qml")) + sorted((PACKAGE / "code").glob("*.js"))
    return [str(f.relative_to(ROOT)) for f in files]


def plan_step(name: str, env: Env) -> Step:
    """The command of one step; every step runs from the repository root, pytest from collector/."""
    if name in ("ruff", "format"):
        ruff = _python_tool("ruff", "ruff", env)
        args = ["check"] if name == "ruff" else ["format", "--check"]
        return Step(name, [*ruff, *args, "collector", "tools"] if ruff else None, missing="ruff")
    if name == "mypy":
        return Step(name, _python_tool("mypy", "mypy", env), missing="mypy")  # files and options: mypy.ini
    if name == "shellcheck":
        shellcheck = _python_tool("shellcheck", "shellcheck-py", env)
        return Step(name, [*shellcheck, *_shell_files()] if shellcheck else None, missing="shellcheck")
    if name == "pytest":
        args = ["-q", "--cov=limit_rings", f"--cov-fail-under={COVERAGE_FLOOR}",
                "--cov-report=term-missing:skip-covered"]
        command: list[str] | None = None
        if env.use_uv:
            command = ["uv", "run", "--no-project", "--with", f"pytest=={env.pins['pytest']}",
                       "--with", f"pytest-cov=={env.pins['pytest-cov']}", "python", "-m", "pytest", *args]
        elif env.has_module("pytest") and env.has_module("pytest_cov"):
            command = [sys.executable, "-m", "pytest", *args]
        return Step(name, command, cwd=ROOT / "collector", missing="pytest or pytest-cov")
    if name == "qmllint":
        qmllint = _qt_tool("qmllint", env)
        # qmllint exits 0 on warnings unless told otherwise; infos never fail it.
        return Step(name, [qmllint, "--max-warnings", "0", *_qml_files()] if qmllint else None, missing="qmllint")
    if name == "qmltest":
        runner = _qt_tool("qmltestrunner", env)
        command = [runner, "-platform", "offscreen", "-input", "plasmoid/tests"] if runner else None
        return Step(name, command, missing="qmltestrunner")
    raise ValueError(f"unknown step: {name}")


def run_steps(steps: Sequence[Step], env: Env,
              runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run) -> dict[str, tuple[str, str]]:
    """Runs every step, also after a failure → {name: (passed|failed|skipped, detail)}."""
    results: dict[str, tuple[str, str]] = {}
    for step in steps:
        print(f"\n== {step.name} ==", flush=True)
        if step.command is None:
            if step.name in QT_STEPS and not env.in_ci:
                results[step.name] = ("skipped", f"{step.missing} not found")
            elif step.name in QT_STEPS:
                results[step.name] = ("failed", f"{step.missing} not found")
            else:
                results[step.name] = ("failed", f"{step.missing} not found – {INSTALL_HINT}")
            print(" – ".join(results[step.name]), flush=True)
            continue
        try:
            code = runner(step.command, cwd=step.cwd, check=False).returncode
        except OSError as e:
            print(f"{step.command[0]}: {e.strerror}", file=sys.stderr, flush=True)
            code = 127
        results[step.name] = ("passed", "") if code == 0 else ("failed", "")
    return results


def install_hook(root: Path) -> int:
    """Points git at tools/hooks – unless the hooks directory holds hooks of its own, which would stop running."""
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()

    if git("config", "--default", "", "core.hooksPath") == "tools/hooks":
        print("The pre-commit hook is already active.")
        return 0
    hooks = root / git("rev-parse", "--git-path", "hooks")
    own = sorted(p.name for p in hooks.iterdir() if p.is_file() and not p.name.endswith(".sample")) \
        if hooks.is_dir() else []
    if own:
        print(f"Nothing changed: {hooks} holds hooks of its own ({', '.join(own)}) that would stop running. "
              "Call 'python3 tools/check.py fast' from your pre-commit hook instead.", file=sys.stderr)
        return 1
    git("config", "core.hooksPath", "tools/hooks")
    print("Pre-commit hook active: the fast checks run before every commit ('git commit --no-verify' skips them).")
    return 0


def main(argv: list[str]) -> int:
    if argv == ["--install-hook"]:
        return install_hook(ROOT)
    try:
        names = select_steps(argv)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    env = detect_env()
    results = run_steps([plan_step(n, env) for n in names], env)
    print("\nSummary:")
    for name, (status, detail) in results.items():
        print(f"  {name:<11} {status}" + (f" ({detail})" if detail else ""))
    return 1 if any(status == "failed" for status, _ in results.values()) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
