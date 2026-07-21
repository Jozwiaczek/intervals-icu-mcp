"""Format sport settings for MCP responses and Intervals.icu API write payloads."""

from typing import Any

from .models import SportSettings


def _fmt_pace_secs(total_secs: float) -> str:
    """Format seconds-per-km as M:SS."""
    total = round(total_secs)
    return f"{total // 60}:{total % 60:02d}"


def _format_hr_zones(zones: list[int], names: list[str] | None) -> list[str]:
    """Render HR zone ceilings (absolute bpm) as labelled ranges."""
    out: list[str] = []
    prev = 0
    for i, top in enumerate(zones):
        name = names[i] if names and i < len(names) else f"Zone {i + 1}"
        low = "0" if i == 0 else str(prev + 1)
        out.append(f"Z{i + 1} {name}: {low}-{top} bpm")
        prev = top
    return out


def _format_pct_zones(
    zones: list[float],
    names: list[str] | None,
    *,
    threshold_pace_min_km: float | None = None,
) -> list[str]:
    """Render %-of-threshold zone ceilings, optionally with computed pace ranges.

    Zone values are ceilings as % of threshold speed; a ceiling >= 999 means
    the top zone is open-ended. Pace ranges are derived from the threshold
    (higher % of threshold speed = faster pace), so they may differ from the
    Intervals.icu UI by a second due to rounding.
    """
    threshold_secs = threshold_pace_min_km * 60 if threshold_pace_min_km else None
    out: list[str] = []
    prev = 0.0
    for i, top in enumerate(zones):
        name = names[i] if names and i < len(names) else f"Zone {i + 1}"
        open_ended = top >= 999
        pct = f"{prev:g}%+" if open_ended else f"{prev:g}-{top:g}%"
        entry = f"Z{i + 1} {name}: {pct}"
        if threshold_secs:
            if open_ended:
                entry += f" (faster than {_fmt_pace_secs(threshold_secs * 100 / prev)}/km)"
            elif prev == 0:
                entry += f" ({_fmt_pace_secs(threshold_secs * 100 / top)}/km +)"
            else:
                fast = _fmt_pace_secs(threshold_secs * 100 / top)
                slow = _fmt_pace_secs(threshold_secs * 100 / prev)
                entry += f" ({fast}-{slow}/km)"
        out.append(entry)
        prev = top
    return out


def format_sport_settings_entry(
    settings: SportSettings,
    *,
    include_id: bool = True,
) -> dict[str, Any]:
    """Build an LLM-facing sport settings dict with consistent unit suffixes."""
    sport_info: dict[str, Any] = {}
    if include_id:
        sport_info["id"] = settings.id
    if settings.type is not None:
        sport_info["type"] = settings.type
    if settings.ftp is not None:
        sport_info["ftp_watts"] = settings.ftp
    if settings.indoor_ftp is not None:
        sport_info["indoor_ftp_watts"] = settings.indoor_ftp
    if settings.fthr is not None:
        sport_info["fthr_bpm"] = settings.fthr
    if settings.pace_threshold is not None:
        total = round(settings.pace_threshold * 60)
        sport_info["pace_threshold"] = f"{total // 60}:{total % 60:02d} /km"
    if settings.swim_threshold is not None:
        # round, not truncate — the m/s <-> min/100m conversion adds tiny float error
        total = round(settings.swim_threshold * 60)
        sport_info["swim_threshold"] = f"{total // 60}:{total % 60:02d} /100m"
    if settings.max_hr is not None:
        sport_info["max_hr_bpm"] = settings.max_hr
    if settings.hr_zones:
        sport_info["hr_zones"] = _format_hr_zones(settings.hr_zones, settings.hr_zone_names)
    if settings.pace_zones:
        sport_info["pace_zones"] = _format_pct_zones(
            settings.pace_zones,
            settings.pace_zone_names,
            threshold_pace_min_km=settings.pace_threshold,
        )
    if settings.power_zones:
        sport_info["power_zones_pct_of_ftp"] = _format_pct_zones(
            settings.power_zones, settings.power_zone_names
        )
    return sport_info


def build_sport_settings_api_payload(
    *,
    sport_type: str | None = None,
    ftp: int | None = None,
    indoor_ftp: int | None = None,
    fthr: int | None = None,
    pace_threshold: float | None = None,
    swim_threshold: float | None = None,
) -> dict[str, Any]:
    """Convert MCP tool parameters to Intervals.icu SportSettings JSON field names."""
    if pace_threshold is not None and swim_threshold is not None:
        raise ValueError(
            "Cannot set pace_threshold and swim_threshold in the same call; "
            "the API stores one pace threshold per sport settings record. "
            "Use separate calls for Run and Swim settings."
        )

    payload: dict[str, Any] = {}
    if sport_type is not None:
        payload["types"] = [sport_type]
    if ftp is not None:
        payload["ftp"] = ftp
    if indoor_ftp is not None:
        payload["indoor_ftp"] = indoor_ftp
    if fthr is not None:
        payload["lthr"] = fthr
    if pace_threshold is not None:
        payload["threshold_pace"] = pace_threshold
        payload["pace_units"] = "MINS_KM"
        payload["pace_load_type"] = "RUN"
    if swim_threshold is not None:
        # Intervals.icu stores swim threshold as SPEED in m/s (unlike run, which is
        # min/km). Convert min/100m -> m/s: 100 m / (minutes * 60) s. Sending the
        # pace value directly stored a bogus speed (4.0 -> 4 m/s -> 0:25/100m); the
        # old `* 60` sent seconds the API rejects with HTTP 422 (see #88).
        payload["threshold_pace"] = 100.0 / (swim_threshold * 60) if swim_threshold else 0.0
        payload["pace_units"] = "SECS_100M"
        payload["pace_load_type"] = "SWIM"
    return payload
