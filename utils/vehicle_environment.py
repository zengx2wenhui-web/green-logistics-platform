from __future__ import annotations

from typing import Any, Iterable, Mapping

from utils.vehicle_lib import VEHICLE_LIB


DEFAULT_SEASON = "夏"
DEFAULT_H2_SOURCE = "工业副产氢"


def _get_vehicle_count(vehicle: Mapping[str, Any]) -> int:
    try:
        return int(vehicle.get("count_max", vehicle.get("count", 0)) or 0)
    except (TypeError, ValueError):
        return 0


def _get_active_vehicle_types(vehicle_list: Iterable[Mapping[str, Any]] | None) -> list[str]:
    active_vehicle_types: list[str] = []
    for vehicle in vehicle_list or []:
        if not isinstance(vehicle, Mapping):
            continue
        if _get_vehicle_count(vehicle) <= 0:
            continue
        vehicle_type = str(vehicle.get("vehicle_type", "") or "").strip()
        if vehicle_type:
            active_vehicle_types.append(vehicle_type)
    return active_vehicle_types


def _coerce_text(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text or default


def build_vehicle_environment_config(
    vehicle_list: Iterable[Mapping[str, Any]] | None,
    *,
    season: Any = DEFAULT_SEASON,
    h2_source: Any = DEFAULT_H2_SOURCE,
) -> dict[str, object]:
    active_vehicle_types = _get_active_vehicle_types(vehicle_list)
    has_new_energy = any(VEHICLE_LIB.get(vehicle_type, {}).get("is_new_energy", False) for vehicle_type in active_vehicle_types)
    has_fcev = "fcev" in active_vehicle_types

    return {
        "season": _coerce_text(season, DEFAULT_SEASON) if has_new_energy else None,
        "h2_source": _coerce_text(h2_source, DEFAULT_H2_SOURCE) if has_fcev else None,
        "has_new_energy": has_new_energy,
        "has_fcev": has_fcev,
    }


def resolve_vehicle_environment_config(
    vehicle_list: Iterable[Mapping[str, Any]] | None,
    raw_config: Mapping[str, Any] | None = None,
    *,
    fallback_season: Any = DEFAULT_SEASON,
    fallback_h2_source: Any = DEFAULT_H2_SOURCE,
) -> dict[str, object]:
    season = fallback_season
    h2_source = fallback_h2_source

    if isinstance(raw_config, Mapping):
        raw_season = raw_config.get("season")
        raw_h2_source = raw_config.get("h2_source")
        if raw_season not in (None, ""):
            season = raw_season
        if raw_h2_source not in (None, ""):
            h2_source = raw_h2_source

    return build_vehicle_environment_config(
        vehicle_list,
        season=season,
        h2_source=h2_source,
    )


def format_vehicle_environment_summary(environment_config: Mapping[str, Any] | None) -> str:
    config = environment_config if isinstance(environment_config, Mapping) else {}
    season = str(config.get("season") or "不适用") if bool(config.get("has_new_energy")) else "不适用"
    h2_source = str(config.get("h2_source") or "不适用") if bool(config.get("has_fcev")) else "不适用"
    return f"季节：{season} | 氢源：{h2_source}"
