import os
import subprocess
from pathlib import Path

import pytest

import check

PINS = {"ruff": "1.0", "mypy": "2.0", "pytest": "9.0", "pytest-cov": "7.0", "shellcheck-py": "0.11"}


def env(tmp_path, *, use_uv=False, in_ci=False, on_path=(), modules=(), qt_version="qmllint 6.12.0"):
    return check.Env(
        pins=PINS,
        use_uv=use_uv,
        in_ci=in_ci,
        which=lambda name: f"/bin/{name}" if name in on_path else None,
        has_module=lambda name: name in modules,
        qt_dirs=(tmp_path,),
        qt_version=lambda tool: qt_version,
    )


def test_read_pins_takes_exact_pins_and_skips_comments():
    assert check.read_pins("# tools\nruff==0.16.10  # linter\n\nPyTest==9.1.1\n") == {
        "ruff": "0.16.10",
        "pytest": "9.1.1",
    }


def test_read_pins_rejects_a_range():
    with pytest.raises(ValueError, match=r"ruff>=0\.16"):
        check.read_pins("ruff>=0.16\n")


def test_the_pin_file_pins_every_tool_check_uses():
    pins = check.read_pins(check.PINS_FILE.read_text(encoding="utf-8"))
    assert {"ruff", "mypy", "pytest", "pytest-cov", "shellcheck-py"} <= pins.keys()


def test_select_steps_defaults_to_all_and_expands_groups_once_in_order():
    assert check.select_steps([]) == list(check.STEPS)
    assert check.select_steps(["mypy", "fast", "qmllint"]) == ["mypy", "ruff", "format", "qmllint"]


def test_select_steps_rejects_unknown_names():
    with pytest.raises(ValueError, match="unknown step: lint"):
        check.select_steps(["lint"])


def test_python_tools_run_pinned_through_uv(tmp_path):
    step = check.plan_step("format", env(tmp_path, use_uv=True))
    assert step.command == ["uvx", "--from", "ruff==1.0", "ruff", "format", "--check", "collector", "tools"]
    assert step.cwd == check.ROOT


def test_python_tools_come_from_path_without_uv(tmp_path):
    assert check.plan_step("ruff", env(tmp_path, on_path={"ruff"})).command == [
        "/bin/ruff",
        "check",
        "collector",
        "tools",
    ]
    assert check.plan_step("mypy", env(tmp_path, on_path={"mypy"})).command == ["/bin/mypy"]


def test_pytest_runs_in_collector_with_the_coverage_floor(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # the commands must not depend on where check.py is started
    step = check.plan_step("pytest", env(tmp_path, use_uv=True))
    assert step.cwd == check.ROOT / "collector"
    assert step.command[:7] == ["uv", "run", "--no-project", "--with", "pytest==9.0", "--with", "pytest-cov==7.0"]
    assert f"--cov-fail-under={check.COVERAGE_FLOOR}" in step.command
    assert "--cov=limit_rings" in step.command
    assert "--cov-branch" in step.command
    assert check.COVERAGE_FLOOR == 98


def test_pytest_without_uv_needs_both_modules(tmp_path):
    assert check.plan_step("pytest", env(tmp_path, modules={"pytest"})).command is None
    step = check.plan_step("pytest", env(tmp_path, modules={"pytest", "pytest_cov"}))
    assert step.command[1:3] == ["-m", "pytest"]


def test_shellcheck_covers_every_script_and_the_hook(tmp_path):
    cmd = check.plan_step("shellcheck", env(tmp_path, use_uv=True)).command
    assert cmd[:4] == ["uvx", "--from", "shellcheck-py==0.11", "shellcheck"]
    assert {"install.sh", "uninstall.sh", "tools/install-lib.sh", "tools/hooks/pre-commit"} <= set(cmd)


def test_shell_files_without_git_come_from_the_tree(tmp_path):
    # a source tarball has no .git: the scripts are found by name instead
    (tmp_path / "tools" / "hooks").mkdir(parents=True)
    (tmp_path / "install.sh").write_text("")
    (tmp_path / "tools" / "lib.sh").write_text("")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "activate.sh").write_text("")
    assert check._shell_files(tmp_path) == ["install.sh", "tools/lib.sh", "tools/hooks/pre-commit"]


def test_qt_tools_prefer_qts_bin_directory(tmp_path):
    (tmp_path / "qmllint").write_text("")
    cmd = check.plan_step("qmllint", env(tmp_path, on_path={"qmllint6"})).command
    assert cmd[:3] == [str(tmp_path / "qmllint"), "--max-warnings", "0"]
    ui = "plasmoid/io.github.flexomatic81.limitrings/contents/"
    assert f"{ui}ui/main.qml" in cmd and f"{ui}code/format.js" in cmd


def test_qt_tools_fall_back_to_distribution_names(tmp_path):
    cmd = check.plan_step("qmltest", env(tmp_path, on_path={"qmltestrunner6"})).command
    assert cmd == ["/bin/qmltestrunner6", "-platform", "offscreen", "-input", "plasmoid/tests"]


def run(steps, e, returncode=0, error=None):
    calls = []

    def runner(cmd, cwd, check):
        calls.append((cmd, cwd))
        if error:
            raise error
        return subprocess.CompletedProcess(cmd, returncode)

    return check.run_steps(steps, e, runner), calls


def test_missing_qt_tool_is_skipped_locally_but_fails_in_ci(tmp_path):
    steps = [check.plan_step("qmllint", env(tmp_path))]
    assert run(steps, env(tmp_path))[0] == {"qmllint": ("skipped", "Qt 6 qmllint not found")}
    assert run(steps, env(tmp_path, in_ci=True))[0]["qmllint"][0] == "failed"


def test_missing_python_tool_fails_with_an_install_hint(tmp_path):
    results, calls = run([check.plan_step("ruff", env(tmp_path))], env(tmp_path))
    status, detail = results["ruff"]
    assert status == "failed" and "pip install -r tools/requirements-dev.txt" in detail
    assert calls == []


def test_exit_codes_and_unstartable_commands(tmp_path):
    e = env(tmp_path, use_uv=True)
    steps = [check.plan_step("mypy", e)]
    assert run(steps, e, returncode=0)[0] == {"mypy": ("passed", "")}
    assert run(steps, e, returncode=1)[0] == {"mypy": ("failed", "")}
    assert run(steps, e, error=FileNotFoundError(2, "No such file or directory"))[0]["mypy"][0] == "failed"


def test_ci_never_uses_uv(monkeypatch):
    monkeypatch.setenv("CI", "true")
    e = check.detect_env()
    assert e.in_ci and not e.use_uv


def test_main_rejects_unknown_steps():
    assert check.main(["nonsense"]) == 2


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False).stdout.strip()


@pytest.fixture
def isolated_git(monkeypatch):
    """git without the developer's global or system config, so their own hooksPath or hook templates don't leak in."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def test_install_hook_points_git_at_tools_hooks(tmp_path, isolated_git):
    git(tmp_path, "init", "-q", "--template=")
    assert check.install_hook(tmp_path) == 0
    assert git(tmp_path, "config", "core.hooksPath") == "tools/hooks"
    assert check.install_hook(tmp_path) == 0  # a second call changes nothing


def test_install_hook_keeps_existing_own_hooks_working(tmp_path, capsys, isolated_git):
    git(tmp_path, "init", "-q", "--template=")
    (tmp_path / ".git" / "hooks").mkdir(exist_ok=True)
    (tmp_path / ".git" / "hooks" / "pre-push").write_text("#!/bin/sh\n")
    assert check.install_hook(tmp_path) == 1
    assert git(tmp_path, "config", "core.hooksPath") == ""
    assert "pre-push" in capsys.readouterr().err


def test_the_hook_runs_the_fast_checks():
    hook = check.ROOT / "tools" / "hooks" / "pre-commit"
    assert hook.stat().st_mode & 0o111
    assert "tools/check.py fast" in hook.read_text()


def test_a_qt_tool_on_path_must_be_qt6(tmp_path):
    e = env(tmp_path, on_path={"qmllint"})
    e5 = check.Env(**{**e.__dict__, "qt_version": lambda tool: "qmllint 5.15.2"})
    assert check.plan_step("qmllint", e5).command is None
    e6 = check.Env(**{**e.__dict__, "qt_version": lambda tool: "qmllint 6.8.1"})
    assert check.plan_step("qmllint", e6).command[0] == "/bin/qmllint"


@pytest.mark.parametrize(
    ("output", "qt6"),
    [
        ("qmllint 6.12.0\n", True),
        ("qmllint 6.8\n", True),
        ("qmllint 5.15.2\n", False),
        ("qmllint 5.6.3\n", False),
        ("", False),
    ],
)
def test_only_major_version_6_counts(output, qt6):
    assert check._is_qt6(output) is qt6


def test_a_failing_version_probe_yields_nothing(tmp_path):
    fails = tmp_path / "fails"
    fails.write_text("#!/bin/sh\necho 'qmllint 6.8.1'\nexit 1\n")
    fails.chmod(0o755)
    works = tmp_path / "works"
    works.write_text("#!/bin/sh\necho 'qmllint 6.8.1'\n")
    works.chmod(0o755)
    assert check._qt_version(str(fails)) == ""
    assert check._qt_version(str(works)) == "qmllint 6.8.1\n"
    assert check._qt_version(str(tmp_path / "missing")) == ""


def test_a_plain_qmltestrunner_on_path_is_not_trusted(tmp_path):
    assert check.plan_step("qmltest", env(tmp_path, on_path={"qmltestrunner"})).command is None
    cmd = check.plan_step("qmltest", env(tmp_path, on_path={"qmltestrunner-qt6"})).command
    assert cmd[0] == "/bin/qmltestrunner-qt6"


def test_fedoras_qt6_directory_is_known():
    assert Path("/usr/lib64/qt6/bin") in check.QT_DIRS


def test_the_install_hint_works_on_externally_managed_pythons():
    assert "virtual environment" in check.INSTALL_HINT


def test_a_plain_qmltestrunner_next_to_a_qt6_qmllint_is_trusted(tmp_path):
    e = env(tmp_path, on_path={"qmltestrunner", "qmllint"})
    assert check.plan_step("qmltest", e).command[0] == "/bin/qmltestrunner"
    e5 = env(tmp_path, on_path={"qmltestrunner", "qmllint"}, qt_version="qmllint 5.15.2")
    assert check.plan_step("qmltest", e5).command is None


def test_a_qt5_qmllint_is_reported_as_no_qt6_qmllint(tmp_path):
    e5 = env(tmp_path, on_path={"qmllint"}, qt_version="qmllint 5.15.2")
    results, _ = run([check.plan_step("qmllint", e5)], e5)
    assert results == {"qmllint": ("skipped", "Qt 6 qmllint not found")}
