<!-- Please open pull requests against `dev`, not `main`. See CONTRIBUTING.md. -->

## What and why

<!-- What does this change, and why? Link the issue if there is one ("Fixes #123"). -->

## Checklist

- [ ] The pull request targets `dev`.
- [ ] Both test suites pass (`pytest` in `collector/`, `qmltestrunner -input plasmoid/tests`).
- [ ] New behaviour and bug fixes come with tests.
- [ ] New or changed user-facing texts go through i18n, and `po/update.sh` has been run.
- [ ] The collector still needs nothing but the Python 3.10 standard library.
