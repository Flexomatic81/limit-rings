import json
import logging
import subprocess
import sys

import pytest

from limit_rings.sources import keychain

LOGIN = {"claudeAiOauth": {"accessToken": "top-secret", "expiresAt": 1_791_303_600_000, "subscriptionType": "max"}}


def fake_run(stdout="", returncode=0, raises=None, calls=None):
    def run(cmd, **kwargs):
        if calls is not None:
            calls.append((cmd, kwargs))
        if raises is not None:
            raise raises
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")
    return run


def test_reads_the_login_of_the_entry():
    calls = []
    oauth = keychain.read_login(run=fake_run(json.dumps(LOGIN) + "\n", calls=calls))
    assert oauth == LOGIN["claudeAiOauth"]
    cmd, kwargs = calls[0]
    assert cmd == ["/usr/bin/security", "find-generic-password", "-s", "Claude Code-credentials", "-w"]
    assert kwargs["timeout"] > 0 and kwargs["capture_output"] is True


def test_a_given_keychain_file_is_searched_alone():
    calls = []
    keychain.read_login("Svc", keychain="/tmp/x.keychain-db", run=fake_run(json.dumps(LOGIN), calls=calls))
    assert calls[0][0] == ["/usr/bin/security", "find-generic-password", "-s", "Svc", "-w", "/tmp/x.keychain-db"]


@pytest.mark.parametrize("run", [
    fake_run(returncode=44),                                        # no such entry
    fake_run(returncode=51),                                        # access denied in the prompt
    fake_run(raises=subprocess.TimeoutExpired(["security"], 10)),   # prompt left open
    fake_run(raises=FileNotFoundError()),                           # no security tool
    fake_run('{"claudeAiOauth": "top-secret"'),                     # broken JSON
    fake_run(json.dumps({"other": "top-secret"})),
    fake_run(json.dumps({"claudeAiOauth": ["top-secret"]})),
])
def test_failures_give_no_login_and_never_log_the_secret(run, caplog):
    caplog.set_level(logging.DEBUG)
    assert keychain.read_login(run=run) is None
    assert "top-secret" not in caplog.text


@pytest.mark.skipif(sys.platform != "darwin", reason="needs the macOS security tool")
def test_reads_a_real_keychain_entry(tmp_path):
    kc = str(tmp_path / "test.keychain-db")
    subprocess.run(["security", "create-keychain", "-p", "test", kc], check=True)
    try:
        subprocess.run(["security", "unlock-keychain", "-p", "test", kc], check=True)
        subprocess.run(["security", "add-generic-password", "-s", "Limit Rings Test", "-a", "test",
                        "-w", json.dumps(LOGIN), "-T", "/usr/bin/security", kc], check=True)
        assert keychain.read_login("Limit Rings Test", keychain=kc) == LOGIN["claudeAiOauth"]
    finally:
        subprocess.run(["security", "delete-keychain", kc], check=False)
