# Security Policy

Limit Rings reads the login tokens of Claude Code and Codex to query their usage limits, so
security issues matter here – especially anything that could leak a token, send it to a host
other than its provider, or write it to disk or a log.

## Reporting a vulnerability

Please **do not open a public issue**. Report it privately via
[GitHub's private vulnerability reporting](https://github.com/Flexomatic81/limit-rings/security/advisories/new)
instead. Describe what you found and, if possible, how to reproduce it.

You can expect a first answer within a week. Once the issue is confirmed, a fix is released as
soon as possible, and you are credited in the advisory unless you prefer otherwise.

## Supported versions

Only the latest release receives security fixes.
