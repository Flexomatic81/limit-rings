"""Daily buckets and the totals derived from them. Pure functions, no I/O."""

from datetime import date, timedelta, tzinfo

from .models import JsonDict, TokenEvent

FIELDS = ("input", "output", "cache_read", "cache_write")


def _zero() -> dict[str, int]:
    return dict.fromkeys(FIELDS, 0)


def add_event(buckets: dict[str, dict[str, int]], ev: TokenEvent, tz: tzinfo) -> None:
    day = ev.ts.astimezone(tz).date().isoformat()
    bucket = buckets.setdefault(day, _zero())
    for f in FIELDS:
        bucket[f] = bucket.get(f, 0) + getattr(ev, f)


def _sum_range(buckets: JsonDict, start: date, end: date) -> dict[str, int]:
    out = _zero()
    lo, hi = start.isoformat(), end.isoformat()
    for day, bucket in buckets.items():
        if lo <= day <= hi:
            for f in FIELDS:
                out[f] += bucket.get(f, 0)
    out["total"] = sum(out[f] for f in FIELDS)
    return out


def summarize(buckets: JsonDict, today: date) -> JsonDict:
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    return {
        "today": _sum_range(buckets, today, today),
        "week": _sum_range(buckets, week_start, today),
        "month": _sum_range(buckets, month_start, today),
    }


def daily_series(buckets: JsonDict, today: date, days: int = 30) -> list[JsonDict]:
    series = []
    for back in range(days - 1, -1, -1):
        day = (today - timedelta(days=back)).isoformat()
        bucket = buckets.get(day)
        total = sum(bucket.get(f, 0) for f in FIELDS) if bucket else 0
        series.append({"date": day, "total": total})
    return series


def _range_series(buckets: JsonDict, starts: list[date], end: date) -> list[JsonDict]:
    """Totals from each start up to the next one (the last up to end), oldest first."""
    totals = [0] * len(starts)
    lo, hi = starts[0].isoformat(), end.isoformat()
    keys = [s.isoformat() for s in starts]
    for day, bucket in buckets.items():
        if lo <= day <= hi:
            i = max(n for n, k in enumerate(keys) if k <= day)
            totals[i] += sum(bucket.get(f, 0) for f in FIELDS)
    return [{"date": k, "total": t} for k, t in zip(keys, totals, strict=True)]


def weekly_series(buckets: JsonDict, today: date, weeks: int = 13) -> list[JsonDict]:
    monday = today - timedelta(days=today.weekday())
    return _range_series(buckets, [monday - timedelta(weeks=back) for back in range(weeks - 1, -1, -1)], today)


def monthly_series(buckets: JsonDict, today: date, months: int = 12) -> list[JsonDict]:
    starts = []
    for back in range(months - 1, -1, -1):
        y, m = divmod(today.year * 12 + today.month - 1 - back, 12)
        starts.append(date(y, m + 1, 1))
    return _range_series(buckets, starts, today)


def prune_buckets(buckets: JsonDict, today: date, keep_days: int = 400) -> None:
    cutoff = (today - timedelta(days=keep_days)).isoformat()
    for day in [d for d in buckets if d < cutoff]:
        del buckets[day]
