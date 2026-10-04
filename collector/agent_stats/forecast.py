"""Prognose für 5-h- und Wochenlimits: Wann ist das Limit bei aktuellem Tempo voll?

Grundlage sind die Prozentwerte, die der Collector je Lauf sieht. Das Tempo ist der Anstieg über
einen zur Fensterart passenden Zeitraum: 30 Minuten beim 5-h-Fenster, 24 Stunden bei der Woche.
Weil die Werte nur in ganzen Prozent kommen, braucht es einen Mindestabstand der Messpunkte.
"""

from dataclasses import dataclass

from .limits import same_window


@dataclass(frozen=True)
class Profile:
    rate_span: int  # Zeitraum, aus dem das Tempo berechnet wird
    min_span: int   # Mindestabstand der Messpunkte für eine Prognose
    keep: int       # so lange werden Punkte aufbewahrt
    max_age: int    # älter darf der jüngste Punkt nicht sein
    min_gap: int    # Mindestabstand zwischen gespeicherten Punkten


PROFILES = {
    300: Profile(rate_span=30 * 60, min_span=10 * 60, keep=60 * 60, max_age=30 * 60, min_gap=0),
    10080: Profile(rate_span=24 * 3600, min_span=2 * 3600, keep=24 * 3600, max_age=6 * 3600, min_gap=10 * 60),
}


def update_history(history: dict, providers: dict[str, tuple[list[dict], float | None]]) -> None:
    """Schreibt den Verlauf je 5-h- und Wochenlimit fort (Schlüssel „anbieter:limit-id“).

    providers bildet den Anzeigenamen auf (Limits, Zeitpunkt der Daten) ab. Ein neuer Punkt entsteht
    nur, wenn die Daten neuer sind als der letzte Punkt (und bei der Woche mindestens 10 Minuten
    später); ein neues Fenster beginnt den Verlauf neu.
    """
    current = set()
    for name, (limits, updated_at) in providers.items():
        for limit in limits:
            profile = PROFILES.get(limit.get("window_minutes"))
            if profile is None:
                continue
            key = f"{name.lower()}:{limit['id']}"
            current.add(key)
            entry = history.get(key)
            if entry is None or not same_window(entry["resets_at"], limit.get("resets_at")):
                entry = history[key] = {"resets_at": limit.get("resets_at"), "points": []}
            entry["resets_at"] = limit.get("resets_at")
            points = entry["points"]
            newer = updated_at is not None and (
                not points or (updated_at > points[-1][0] and updated_at - points[-1][0] >= profile.min_gap))
            if newer:
                points.append([updated_at, limit["used_percent"]])
            if points:
                entry["points"] = [p for p in points if p[0] >= points[-1][0] - profile.keep]
    for gone in set(history) - current:
        del history[gone]


def forecast(entry: dict, resets_at, now: float, window_minutes: int = 300) -> dict | None:
    """{"status": "full", "eta": Epoch} | {"status": "enough"} | None (zu wenig oder veraltete Daten)."""
    profile = PROFILES.get(window_minutes)
    points = entry["points"]
    if profile is None or not points or (resets_at is not None and resets_at <= now):
        return None
    newest_ts, newest_pct = points[-1]
    if newest_ts < now - profile.max_age:
        return None
    ref_ts, ref_pct = next(p for p in points if p[0] >= newest_ts - profile.rate_span)
    span = newest_ts - ref_ts
    if span < profile.min_span:
        return None
    rate = (newest_pct - ref_pct) / span
    if rate <= 0:
        return {"status": "enough"}
    eta = newest_ts + (100.0 - newest_pct) / rate
    if resets_at is not None and eta >= resets_at:
        return {"status": "enough"}
    return {"status": "full", "eta": int(eta)}
