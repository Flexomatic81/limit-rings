import json
import os

from limit_rings.accounts import MAX_ACCOUNTS, account_paths, parse_accounts, prune_account_states

NOW = 1_791_300_000.0


def entry(**kw):
    return {"id": "k7f3a2", "provider": "claude", "dir": "~/.claude-arbeit", "name": "Arbeit", **kw}


def test_valid_entries_resolve_the_home_directory(tmp_path):
    accounts = parse_accounts(json.dumps([entry(), entry(id="x2", provider="codex", dir="/srv/codex b",
                                                         name="Büro \"2\" 'x'")]), tmp_path)
    a, b = accounts
    assert (a.id, a.provider, a.dir, a.dir_text, a.name, a.error) == (
        "k7f3a2", "claude", (tmp_path / ".claude-arbeit").resolve(), "~/.claude-arbeit", "Arbeit", None)
    assert a.label == "Claude (Arbeit)"
    assert (b.provider, str(b.dir), b.name) == ("codex", "/srv/codex b", "Büro \"2\" 'x'")


def test_missing_or_broken_text_gives_no_accounts(tmp_path):
    for text in (None, "", "not json", "{}", "[1, 2]", '[{"id": "BAD!"}]'):
        assert parse_accounts(text, tmp_path) == [], text


def test_invalid_entries_with_a_usable_id_become_error_accounts(tmp_path):
    bad = [entry(id="a1", provider="gemini"), entry(id="a2", dir="relative/path"), entry(id="a3", dir=""),
           entry(id="a4", dir="~/.claude"), entry(id="a5", provider="codex", dir="~/.codex")]
    accounts = parse_accounts(json.dumps(bad), tmp_path)
    assert [(a.id, a.error) for a in accounts] == [(i, "account_invalid") for i in ("a1", "a2", "a3", "a4", "a5")]
    assert accounts[0].provider is None and accounts[1].provider == "claude"


def test_duplicate_ids_and_directories_and_the_limit(tmp_path):
    accounts = parse_accounts(json.dumps([entry(id="a1"), entry(id="a1", dir="~/.claude-x"),
                                          entry(id="a2"), entry(id="a3", provider="codex")]), tmp_path)
    # second "a1" dropped (id taken); "a2" has the directory of "a1" for the same provider; codex may share it
    assert [(a.id, a.error) for a in accounts] == [("a1", None), ("a2", "account_invalid"), ("a3", None)]
    many = [entry(id=f"a{i}", dir=f"~/.claude-{i}") for i in range(MAX_ACCOUNTS + 3)]
    assert len(parse_accounts(json.dumps(many), tmp_path)) == MAX_ACCOUNTS


def test_aliases_of_a_directory_count_as_the_same_directory(tmp_path):
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")
    (tmp_path / ".claude").mkdir()
    accounts = parse_accounts(json.dumps([
        entry(id="a1", dir=str(tmp_path / "real")),
        entry(id="a2", dir=str(tmp_path / "link")),                 # symlink to a1's directory
        entry(id="a3", dir=str(tmp_path / "real" / ".." / "real")),  # ".." alias of a1's directory
        entry(id="a4", dir="~/.claude/../.claude"),                  # the main account's directory
    ]), tmp_path)
    assert [(a.id, a.error) for a in accounts] == [("a1", None), ("a2", "account_invalid"),
                                                   ("a3", "account_invalid"), ("a4", "account_invalid")]


def test_state_key_follows_provider_and_directory(tmp_path):
    (a,) = parse_accounts(json.dumps([entry()]), tmp_path)
    (same,) = parse_accounts(json.dumps([entry(name="Renamed", short="R")]), tmp_path)
    (moved,) = parse_accounts(json.dumps([entry(dir="~/.claude-neu")]), tmp_path)
    (other,) = parse_accounts(json.dumps([entry(provider="codex")]), tmp_path)
    (twin,) = parse_accounts(json.dumps([entry(id="zz1")]), tmp_path)   # same directory, other widget
    assert a.state_key.startswith("claude-") and len(a.state_key) == len("claude-") + 12
    assert same.state_key == a.state_key and twin.state_key == a.state_key
    assert moved.state_key != a.state_key and other.state_key != a.state_key


def test_empty_name_falls_back_to_the_provider(tmp_path):
    (a,) = parse_accounts(json.dumps([entry(name="  ")]), tmp_path)
    assert a.name == "Claude 2" and a.label == "Claude (Claude 2)"


def test_paths_per_provider(tmp_path):
    claude, codex = parse_accounts(json.dumps([entry(), entry(id="c1", provider="codex", dir="~/.codex-b")]),
                                   tmp_path)
    home = tmp_path.resolve()
    p = account_paths(claude, tmp_path / "cache")
    assert p.credentials == home / ".claude-arbeit" / ".credentials.json"
    assert p.claude_root == home / ".claude-arbeit" / "projects"
    assert p.statusline_cache is None
    assert p.state_file == tmp_path / "cache" / "accounts" / f"{claude.state_key}.json"
    q = account_paths(codex, tmp_path / "cache")
    assert q.codex_auth == home / ".codex-b" / "auth.json"
    assert q.codex_root == home / ".codex-b" / "sessions"


def test_prune_keeps_shown_and_recently_hidden_account_states(tmp_path):
    folder = tmp_path / "accounts"
    folder.mkdir()
    for name, age_days in (("shown.json", 90), ("hidden.json", 10), ("gone.json", 31), ("gone.json.corrupt", 40),
                           ("other.txt", 90)):
        f = folder / name
        f.write_text("{}")
        os.utime(f, (NOW - age_days * 86400, NOW - age_days * 86400))
    prune_account_states(tmp_path, {"shown"}, NOW)
    assert sorted(p.name for p in folder.iterdir()) == ["hidden.json", "other.txt", "shown.json"]
    prune_account_states(tmp_path / "missing", set(), NOW)  # no folder: nothing to do
