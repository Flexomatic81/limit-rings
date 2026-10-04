from limit_rings.limits import make_limit, normalize_codex, public_limit, window_text


def test_window_text_is_language_neutral():
    assert window_text(300) == "5 h"
    assert window_text(10080) == "7 d"
    assert window_text(2880) == "2 d"
    assert window_text(120) == "2 h"
    assert window_text(45) == "45 min"


def test_make_limit_keeps_the_legacy_label_for_rollbacks_and_model_only_when_given():
    assert make_limit("five_hour", 5, None, 300) == {
        "id": "five_hour", "label": "5 h", "used_percent": 5.0, "resets_at": None, "window_minutes": 300}
    opus = make_limit("seven_day_opus", 5, 7, 10080, "Opus")
    assert (opus["label"], opus["model"]) == ("Week Opus", "Opus")
    assert make_limit("primary", 5, None, None)["label"] == "primary"
    assert make_limit("x", 5, None, 2880)["label"] == "2 d"


def test_public_limit_drops_label_and_migrates_legacy_scoped_labels():
    base = {"id": "x", "used_percent": 1.0, "resets_at": None, "window_minutes": 10080}
    assert public_limit(base | {"label": "Week"}) == base
    assert public_limit(base | {"label": "Woche Opus"}) == base | {"model": "Opus"}
    assert public_limit(base | {"label": "Week Fable"}) == base | {"model": "Fable"}
    assert public_limit(base | {"label": "Woche"}) == base
    assert public_limit(base | {"model": "Sonnet"}) == base | {"model": "Sonnet"}
    assert public_limit(base | {"model": None, "label": "5 h"}) == base


def test_normalize_codex_skips_missing_secondary():
    rl = {"primary": {"used_percent": 8.0, "window_minutes": 10080, "resets_at": 1791280728},
          "secondary": None, "plan_type": "plus"}
    assert normalize_codex(rl) == [
        {"id": "primary", "label": "Week", "used_percent": 8.0,
         "resets_at": 1791280728, "window_minutes": 10080}]


def test_normalize_codex_two_windows():
    rl = {"primary": {"used_percent": 30, "window_minutes": 300, "resets_at": 1},
          "secondary": {"used_percent": 5, "window_minutes": 10080, "resets_at": 2}}
    assert [l["label"] for l in normalize_codex(rl)] == ["5 h", "Week"]
