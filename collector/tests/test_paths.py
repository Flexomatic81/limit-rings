from datetime import datetime

from limit_rings import paths


def test_local_zone_falls_back_to_etc_localtime(monkeypatch):
    monkeypatch.setenv("TZ", "Not/AZone")
    monkeypatch.setattr(paths.os.path, "realpath", lambda p: "/usr/share/zoneinfo/Europe/Berlin")
    assert str(paths.local_zone()) == "Europe/Berlin"


def test_local_zone_without_a_hint_uses_the_system_offset(monkeypatch):
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setattr(paths.os.path, "realpath", lambda p: "/etc/localtime")  # not a zoneinfo link
    assert datetime.now(paths.local_zone()).utcoffset() is not None


def test_local_zone_survives_an_unreadable_localtime(monkeypatch):
    monkeypatch.delenv("TZ", raising=False)

    def broken(p):
        raise OSError("no access")

    monkeypatch.setattr(paths.os.path, "realpath", broken)
    assert datetime.now(paths.local_zone()).utcoffset() is not None
