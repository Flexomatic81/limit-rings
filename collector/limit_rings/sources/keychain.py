"""Claude login from the macOS keychain, where Claude Code keeps it instead of .credentials.json.

The entry is only read, through Apple's security tool. Its output is never logged: on failure only the exit
code or the type of the error.
"""

import json
import logging
import subprocess

log = logging.getLogger(__name__)

SERVICE = "Claude Code-credentials"
SECURITY = "/usr/bin/security"
TIMEOUT = 30.0  # the first read shows a permission prompt; a pass must not wait for it much longer


def read_login(service: str = SERVICE, keychain: str | None = None, run=subprocess.run) -> dict | None:
    """The claudeAiOauth object of the entry, or None. keychain: search only this keychain file."""
    cmd = [SECURITY, "find-generic-password", "-s", service, "-w"] + ([keychain] if keychain else [])
    try:
        out = run(cmd, capture_output=True, text=True, timeout=TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("keychain read failed: %s", type(e).__name__)
        return None
    if out.returncode != 0:  # 44: no such entry; others: access denied or keychain locked
        log.info("keychain read failed: exit code %s", out.returncode)
        return None
    try:
        oauth = json.loads(out.stdout)["claudeAiOauth"]
    except (ValueError, KeyError, TypeError):
        log.warning("keychain entry has unexpected shape")
        return None
    return oauth if isinstance(oauth, dict) else None
