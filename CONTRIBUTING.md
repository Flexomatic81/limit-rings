# Contributing to Limit Rings

Thanks for wanting to help! Bug reports, translations and pull requests are all welcome.

For anything bigger than a small fix, please open an issue first, so that we can agree on the
approach before you spend time on it.

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

## Tests

The test suites and the lint check run in CI for every pull request and must pass:

```bash
cd collector && uv run --no-project --with pytest pytest -q   # or: python3 -m pytest -q
/usr/lib/qt6/bin/qmltestrunner -input plasmoid/tests
uvx ruff check collector tools                                # or: ruff check collector tools
```

CI runs the collector tests on Python 3.10 and on the newest Python release. Please add tests for
new behaviour and for bug fixes.

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
