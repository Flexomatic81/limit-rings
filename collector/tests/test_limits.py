from agent_stats.limits import normalize_codex, window_label


def test_window_labels():
    assert window_label(300) == "5 h"
    assert window_label(10080) == "Woche"
    assert window_label(2880) == "2 d"
    assert window_label(120) == "2 h"
    assert window_label(45) == "45 min"


def test_normalize_codex_skips_missing_secondary():
    rl = {"primary": {"used_percent": 8.0, "window_minutes": 10080, "resets_at": 1791280728},
          "secondary": None, "plan_type": "plus"}
    assert normalize_codex(rl) == [
        {"id": "primary", "label": "Woche", "used_percent": 8.0,
         "resets_at": 1791280728, "window_minutes": 10080}]


def test_normalize_codex_two_windows():
    rl = {"primary": {"used_percent": 30, "window_minutes": 300, "resets_at": 1},
          "secondary": {"used_percent": 5, "window_minutes": 10080, "resets_at": 2}}
    assert [l["label"] for l in normalize_codex(rl)] == ["5 h", "Woche"]
