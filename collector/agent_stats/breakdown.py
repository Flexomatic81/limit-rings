"""Breakdown of Claude tokens by project and model, counted hourly.

Hourly because the Claude weekly window does not start at midnight (e.g. Tuesdays at 06:00).
"""

import re
from pathlib import Path

from .models import TokenEvent

KEEP_SECONDS = 8 * 86400

_MODEL_RE = re.compile(r"^claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?$")


def model_label(model_id: str | None) -> str | None:
    """claude-opus-5-5 → "Opus 5.5"; unknown IDs are kept as they are; <synthetic> → None."""
    if not model_id or model_id.startswith("<"):
        return None
    m = _MODEL_RE.match(model_id)
    if not m:
        return model_id
    family, major, minor = m.groups()
    return f"{family.capitalize()} {major}" + (f".{minor}" if minor else "")


class ProjectResolver:
    """Project = name of the working directory's Git repository (worktrees → main repository),
    otherwise the directory name. Results are cached per instance."""

    def __init__(self):
        self._cache: dict[str, str] = {}

    def name(self, cwd: str | None) -> str:
        if not cwd:
            return "?"
        if cwd not in self._cache:
            self._cache[cwd] = self._resolve(Path(cwd))
        return self._cache[cwd]

    @staticmethod
    def _resolve(path: Path) -> str:
        for candidate in (path, *path.parents):
            git = candidate / ".git"
            try:
                if git.is_dir():
                    return candidate.name
                if git.is_file():
                    target = git.read_text(encoding="utf-8").strip().removeprefix("gitdir:").strip()
                    parts = Path(target).parts
                    if ".git" in parts:  # …/<repo>/.git/worktrees/<name>
                        return parts[parts.index(".git") - 1]
                    return candidate.name
            except OSError:
                continue
        return path.name or "?"


def _hour(ev: TokenEvent) -> str:
    return str(int(ev.ts.timestamp()) // 3600 * 3600)


def add_event(hourly: dict, ev: TokenEvent, project: str, model: str | None) -> None:
    total = ev.input + ev.output + ev.cache_read + ev.cache_write
    bucket = hourly.setdefault(_hour(ev), {"p": {}, "m": {}})
    bucket["p"][project] = bucket["p"].get(project, 0) + total
    if model:
        bucket["m"][model] = bucket["m"].get(model, 0) + total


def prune_hourly(hourly: dict, now: float, keep: int = KEEP_SECONDS) -> None:
    for hour in [h for h in hourly if int(h) < now - keep]:
        del hourly[hour]


def _top(counts: dict[str, int], top: int) -> list[dict]:
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    out = [{"name": name, "total": total} for name, total in ranked[:top]]
    rest = sum(total for _, total in ranked[top:])
    if rest:
        out.append({"name": None, "other": True, "total": rest})
    return out


def summarize(hourly: dict, since: float, top: int = 4) -> dict:
    """Totals from the hour containing since: {"total", "projects": [...], "models": [...]}."""
    start = int(since) // 3600 * 3600
    projects: dict[str, int] = {}
    models: dict[str, int] = {}
    for hour, bucket in hourly.items():
        if int(hour) < start:
            continue
        for name, total in bucket["p"].items():
            projects[name] = projects.get(name, 0) + total
        for name, total in bucket["m"].items():
            models[name] = models.get(name, 0) + total
    return {"total": sum(projects.values()), "projects": _top(projects, top), "models": _top(models, top)}
