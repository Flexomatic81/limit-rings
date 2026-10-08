"""Daily buckets and the totals derived from them. Pure functions, no I/O."""

from datetime import date, timedelta, tzinfo

from .models import TokenEvent

FIELDS = ("input", "output", "cache_read", "cache_write")


def _zero() -> dict[str, int]:
    return {f: 0 for f in FIELDS}


def add_event(buckets: dict[str, dict[str, int]], ev: TokenEvent, tz: tzinfo) -> None:
    day = ev.ts.astimezone(tz).date().isoformat()
    bucket = buckets.setdefault(day, _zero())
    for f in FIELDS:
        bucket[f] = bucket.get(f, 0) + getattr(ev, f)


def _sum_range(buckets, start: date, end: date) -> dict[str, int]:
    out = _zero()
    lo, hi = start.isoformat(), end.isoformat()
    for day, bucket in buckets.items():
        if lo <= day <= hi:
            for f in FIELDS:
                out[f] += bucket.get(f, 0)
    out["total"] = sum(out[f] for f in FIELDS)
    return out


def summarize(buckets, today: date) -> dict:
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    return {
        "today": _sum_range(buckets, today, today),
        "week": _sum_range(buckets, week_start, today),
        "month": _sum_range(buckets, month_start, today),
    }


def daily_series(buckets, today: date, days: int = 30) -> list[dict]:
    series = []
    for back in range(days - 1, -1, -1):
        day = (today - timedelta(days=back)).isoformat()
        bucket = buckets.get(day)
        total = sum(bucket.get(f, 0) for f in FIELDS) if bucket else 0
        series.append({"date": day, "total": total})
    return series


def _range_series(buckets, starts: list[date], end: date) -> list[dict]:
    """Totals from each start up to the next one (the last up to end), oldest first."""
    totals = [0] * len(starts)
    lo, hi = starts[0].isoformat(), end.isoformat()
    keys = [s.isoformat() for s in starts]
    for day, bucket in buckets.items():
        if lo <= day <= hi:
            i = max(n for n, k in enumerate(keys) if k <= day)
            totals[i] += sum(bucket.get(f, 0) for f in FIELDS)
    return [{"date": k, "total": t} for k, t in zip(keys, totals)]


def weekly_series(buckets, today: date, weeks: int = 13) -> list[dict]:
    monday = today - timedelta(days=today.weekday())
    return _range_series(buckets, [monday - timedelta(weeks=back) for back in range(weeks - 1, -1, -1)], today)


def monthly_series(buckets, today: date, months: int = 12) -> list[dict]:
    starts = []
    for back in range(months - 1, -1, -1):
        y, m = divmod(today.year * 12 + today.month - 1 - back, 12)
        starts.append(date(y, m + 1, 1))
    return _range_series(buckets, starts, today)


def prune_buckets(buckets, today: date, keep_days: int = 400) -> None:
    cutoff = (today - timedelta(days=keep_days)).isoformat()
    for day in [d for d in buckets if d < cutoff]:
        del buckets[day]
