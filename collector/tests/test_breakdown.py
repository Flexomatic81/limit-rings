from datetime import datetime

from agent_stats.breakdown import ProjectResolver, add_event, model_label, prune_hourly, summarize
from agent_stats.models import TokenEvent

T0 = 1_791_100_800  # full hour (2026-10-04 08:00 UTC)


def ev(offset, total, model="claude-opus-5", project="/x/website"):
    return TokenEvent(datetime.fromtimestamp(T0 + offset).astimezone(), total, 0, 0, 0, model=model, project=project)


def test_model_labels():
    assert model_label("claude-opus-5-5") == "Opus 5.5"
    assert model_label("claude-opus-5") == "Opus 5"
    assert model_label("claude-fable-5-1") == "Fable 5.1"
    assert model_label("claude-haiku-4-5-20251001") == "Haiku 4.5"
    assert model_label("claude-opus-4-7") == "Opus 4.7"
    assert model_label("gpt-6-astra") == "gpt-6-astra"
    assert model_label("<synthetic>") is None
    assert model_label(None) is None


def test_project_resolver_finds_git_root_worktree_and_fallbacks(tmp_path):
    repo = tmp_path / "website"
    (repo / ".git").mkdir(parents=True)
    (repo / "frontend" / "src").mkdir(parents=True)
    wt = tmp_path / "website-wt" / "feature-x"
    wt.mkdir(parents=True)
    (wt / ".git").write_text(f"gitdir: {repo}/.git/worktrees/feature-x\n")
    plain = tmp_path / "scratch"
    plain.mkdir()

    r = ProjectResolver()
    assert r.name(str(repo / "frontend" / "src")) == "website"
    assert r.name(str(repo)) == "website"
    assert r.name(str(wt)) == "website"
    assert r.name(str(plain)) == "scratch"
    assert r.name(str(tmp_path / "gone" / "agent-stats")) == "agent-stats"  # no longer exists
    assert r.name(None) == "?"


def test_resolver_caches_lookups(tmp_path, monkeypatch):
    (tmp_path / "p" / ".git").mkdir(parents=True)
    r = ProjectResolver()
    assert r.name(str(tmp_path / "p")) == "p"
    (tmp_path / "p" / ".git").rmdir()
    assert r.name(str(tmp_path / "p")) == "p"  # from the cache


def test_summarize_since_window_start_with_top_four_and_others():
    hourly = {}
    names = lambda e: ("website" if e.project == "/x/website" else e.project, model_label(e.model))
    events = [ev(-7200, 999)]  # before the window start → not counted
    events += [ev(0, 880), ev(600, 30, project="agent-stats"), ev(3600, 20, project="tools"),
               ev(3600, 10, project="a"), ev(7200, 5, project="b"), ev(7200, 5, project="c", model="claude-sonnet-5")]
    for e in events:
        add_event(hourly, e, *names(e))
    s = summarize(hourly, since=T0 + 900, top=4)  # window starts mid-hour → the whole hour counts
    assert s["total"] == 950
    assert s["projects"] == [{"name": "website", "total": 880}, {"name": "agent-stats", "total": 30},
                             {"name": "tools", "total": 20}, {"name": "a", "total": 10},
                             {"name": "Other", "total": 10}]
    assert s["models"] == [{"name": "Opus 5", "total": 945}, {"name": "Sonnet 5", "total": 5}]


def test_events_without_model_count_for_projects_only():
    hourly = {}
    add_event(hourly, ev(0, 50, model="<synthetic>"), "website", None)
    s = summarize(hourly, since=T0)
    assert s["projects"] == [{"name": "website", "total": 50}] and s["models"] == []


def test_prune_hourly_keeps_eight_days():
    hourly = {}
    add_event(hourly, ev(0, 1), "website", "Opus 5")
    add_event(hourly, ev(9 * 86400, 1), "website", "Opus 5")
    prune_hourly(hourly, now=T0 + 9 * 86400)
    assert list(hourly) == [str(T0 + 9 * 86400)]
