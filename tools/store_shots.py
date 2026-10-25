"""Renders the parts of the KDE Store images into docs/store/shots/ (see docs/store/description.md).

    python3 tools/store_shots.py [--out DIR]

The widget in the images is real: the scenes in tools/store_shots/ show its QML components with invented data
(tools/store_shots/fake.js) at three times the size, in the stock Breeze Dark colours, whatever this desktop uses.
Needs Qt 6 with qmltestrunner and qml6, Kirigami, KCMUtils and the stock Breeze colour scheme. The settings page
runs as a widget application: Kirigami's form layout draws its labels only there.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENTS = ROOT / "plasmoid" / "io.github.flexomatic81.limitrings" / "contents"
SCENES = ROOT / "tools" / "store_shots"
COLORS = Path("/usr/share/color-schemes/BreezeDark.colors")
SCALE = "3"

# Stand-ins for KDE's i18n()/i18nc(), which only Plasma provides; the settings page calls them.
I18N_STAND_INS = """\
    function _subst(text, args) {
        return text.replace(/%(\\d)/g, (m, n) => args[n - 1] !== undefined ? String(args[n - 1]) : m)
    }
    function i18n(text, ...args) { return _subst(text, args) }
    function i18nc(context, text, ...args) { return _subst(text, args) }
"""


def _qt_tool(name: str) -> str:
    for directory in (Path("/usr/lib/qt6/bin"), Path("/usr/lib64/qt6/bin")):
        if (directory / name).is_file():
            return str(directory / name)
    found = shutil.which(name) or shutil.which(name + "6")
    if not found:
        sys.exit(f"{name} not found (it comes with Qt 6's QML tools)")
    return found


def _environment(config: Path) -> dict[str, str]:
    """Only the stock Breeze Dark scheme and the KDE platform theme: the desktop's own settings stay out."""
    if not COLORS.is_file():
        sys.exit(f"{COLORS} is missing; install the Breeze theme of the distribution")
    (config / "kdeglobals").write_text(
        COLORS.read_text(encoding="utf-8") + "\n[General]\nColorScheme=BreezeDark\n\n[Icons]\nTheme=breeze-dark\n",
        encoding="utf-8",
    )
    return {
        **os.environ,
        "XDG_CONFIG_HOME": str(config),
        "XDG_CONFIG_DIRS": str(config / "none"),
        "QT_QPA_PLATFORMTHEME": "kde",
        "QT_QUICK_CONTROLS_STYLE": "org.kde.desktop",
        "QT_SCALE_FACTOR": SCALE,
        "QT_FORCE_STDERR_LOGGING": "1",
        "LANGUAGE": "en",
        "LC_ALL": "en_US.UTF-8",
    }


def _settings_page(ui: Path) -> None:
    """A copy of the settings page with the i18n stand-ins; label bindings call them on the page itself."""
    shutil.copy(CONTENTS / "ui" / "FolderPicker.qml", ui)
    text = (CONTENTS / "ui" / "configGeneral.qml").read_text(encoding="utf-8")
    text = re.sub(r"([^.\w])(i18nc?)\(", r"\1page.\2(", text)
    head = "KCM.SimpleKCM {\n    id: page\n"
    if head not in text:
        sys.exit("configGeneral.qml has changed: its root is no longer KCM.SimpleKCM with id page")
    (ui / "ConfigPage.qml").write_text(text.replace(head, head + I18N_STAND_INS), encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "store" / "shots")
    out = parser.parse_args(argv).out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        env = _environment(work)
        shutil.copy(SCENES / "fake.js", work)
        scene = (SCENES / "Shots.qml").read_text(encoding="utf-8")
        scene = scene.replace("@UI@", (CONTENTS / "ui").as_uri()).replace("@CODE@", (CONTENTS / "code").as_uri())
        (work / "tst_shots.qml").write_text(scene.replace("@OUT@", str(out)), encoding="utf-8")
        shots = subprocess.run(
            [_qt_tool("qmltestrunner"), "-platform", "offscreen", "-input", str(work / "tst_shots.qml")],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        print("\n".join(line for line in shots.stdout.splitlines() if "MARKS" in line or "FAIL" in line))
        if shots.returncode != 0:
            print(shots.stdout + shots.stderr, file=sys.stderr)
            return 1
        ui = work / "ui"
        (work / "code").mkdir()
        ui.mkdir()
        for js in (CONTENTS / "code").glob("*.js"):
            shutil.copy(js, work / "code")
        _settings_page(ui)
        settings = (SCENES / "SettingsScene.qml").read_text(encoding="utf-8")
        (work / "SettingsScene.qml").write_text(settings.replace("@OUT@", str(out)), encoding="utf-8")
        page = subprocess.run(
            [_qt_tool("qml6"), "--apptype", "widget", "-platform", "offscreen", str(work / "SettingsScene.qml")],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if page.returncode != 0 or not (out / "settings.png").is_file():
            print(page.stdout + page.stderr, file=sys.stderr)
            return 1
    print(f"store shots written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
