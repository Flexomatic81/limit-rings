# Contributing to Limit Rings

Thanks for wanting to help! Bug reports, translations and pull requests are all welcome.

For anything bigger than a small fix, please open an issue first, so that we can agree on the
approach before you spend time on it.

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Branches

- `main` is the released state – it is what `git clone && ./install.sh` installs.
- `dev` is where development happens. **Please open pull requests against `dev`.**

Pull requests are squash-merged, so one commit per pull request ends up in the history.

Please don't change the version or `CHANGELOG.md` – both are updated when a release is made, and
contributors are credited there.

## Setting up

You need KDE Plasma 6 and Python ≥ 3.10. To edit translations you also need gettext.

```bash
git clone https://github.com/Flexomatic81/limit-rings.git
cd limit-rings
git switch dev
./install.sh                                   # installs the widget from your checkout
plasmawindowed io.github.flexomatic81.limitrings
```

After changing QML files, run `./install.sh` again and restart `plasmawindowed` (or Plasma) to
see the result.

## Checks

CI runs these checks for every pull request, and they must pass. One command runs the same checks locally:

```bash
python3 tools/check.py                  # everything: lint, format, types, shell scripts, QML, tests
python3 tools/check.py fast             # ruff, format and mypy – a few seconds
python3 tools/check.py --install-hook   # run the fast checks before every commit
```

With [uv](https://docs.astral.sh/uv/) installed, the Python tools run in the versions pinned in
`tools/requirements-dev.txt`; without uv, install them with `python3 -m pip install -r tools/requirements-dev.txt`.
`qmllint` and `qmltestrunner` come with Qt 6's QML tools; without them the QML steps are skipped locally.

CI runs the collector tests on Python 3.10 and on the newest Python release, and fails if their coverage of
statements and branches drops below 98 %. Please add tests for new behaviour and for bug fixes.

Python code is formatted with `ruff format` (line length 120). One commit reformatted the whole code base; to
keep it out of `git blame`:

```bash
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

## Ground rules

- **Collector:** Python standard library only, and nothing newer than Python 3.10 (no `tomllib`,
  `except*`, …). Users should not have to install anything besides `python3`.
- **Login tokens** are only read – never stored, refreshed or logged – and only sent to the
  provider they belong to. Redirects stay refused, and the limit endpoints are queried at most
  every 5 minutes.
- **Network:** the README lists every host the widget talks to. A change that adds a new one
  needs an issue first.
- **Language:** code, comments, docs and commit messages are in English.

## Translations

User-facing texts go through `Format.i18n…` (QML/JS) or `i18n._()` (collector). After changing
texts, run `po/update.sh` and translate the new entries in every `po/*/<lang>.po`;
`collector/tests/test_translations.py` fails while a catalog is incomplete. How to add a new
language is described in the [README](README.md#translations).

## Commit messages

One sentence in the imperative that says what the change does, without a prefix – for example
"Skip a collector pass whose lock file was purged while it waited". Use the body to explain why,
if that is not obvious.

## Security issues

Please do not report security issues in public issues – see [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
