from __future__ import annotations

from typing import Any, Callable, Iterable


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return default


def _normalize_capacity_kg(capacity_kg: object) -> int:
    normalized = int(round(_safe_float(capacity_kg, 0.0)))
    return normalized if normalized > 0 else 0


def _resolve_display_name(
    vehicle_type_id: str,
    fallback_name: object = "",
    *,
    name_resolver: Callable[[str], str] | None = None,
) -> str:
    fallback_text = str(fallback_name or "").strip()
    if fallback_text:
        return fallback_text
    if name_resolver is not None:
        try:
            resolved = str(name_resolver(vehicle_type_id) or "").strip()
            if resolved:
                return resolved
        except Exception:
            pass
    return vehicle_type_id or "unknown"


def _append_summary_count(
    counts: dict[tuple[str, str, int], int],
    *,
    vehicle_type_id: str,
    vehicle_display_name: str,
    vehicle_capacity_kg: int,
    vehicle_count: int,
) -> None:
    if vehicle_count <= 0 or vehicle_capacity_kg <= 0:
        return

    key = (
        str(vehicle_type_id or "").strip(),
        str(vehicle_display_name or "").strip() or str(vehicle_type_id or "").strip() or "unknown",
        int(vehicle_capacity_kg),
    )
    counts[key] = counts.get(key, 0) + int(vehicle_count)


def _build_summary_rows(counts: dict[tuple[str, str, int], int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (vehicle_type_id, vehicle_display_name, vehicle_capacity_kg), vehicle_count in sorted(
        counts.items(),
        key=lambda item: (item[0][1], item[0][2], item[0][0]),
    ):
        capacity_ton = vehicle_capacity_kg / 1000.0
        rows.append(
            {
                "vehicle_type_id": vehicle_type_id,
                "vehicle_display_name": vehicle_display_name,
                "vehicle_capacity_kg": vehicle_capacity_kg,
                "vehicle_capacity_ton": round(capacity_ton, 3),
                "vehicle_count": int(vehicle_count),
                "total_capacity_kg": int(vehicle_capacity_kg * vehicle_count),
                "total_capacity_ton": round(capacity_ton * vehicle_count, 3),
                "vehicle_spec_label": f"{vehicle_display_name} {capacity_ton:g}t",
            }
        )
    return rows


def build_configured_fleet_summary(
    vehicle_list: Iterable[dict[str, Any]] | None,
    *,
    name_resolver: Callable[[str], str] | None = None,
) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str, int], int] = {}
    for vehicle in vehicle_list or []:
        vehicle_type_id = str(vehicle.get("vehicle_type", "") or "").strip()
        vehicle_display_name = _resolve_display_name(
            vehicle_type_id,
            vehicle.get("name", ""),
            name_resolver=name_resolver,
        )
        vehicle_capacity_kg = _normalize_capacity_kg(_safe_float(vehicle.get("load_ton", 0.0)) * 1000.0)
        vehicle_count = _safe_int(vehicle.get("count_max", vehicle.get("count", 0)))
        _append_summary_count(
            counts,
            vehicle_type_id=vehicle_type_id,
            vehicle_display_name=vehicle_display_name,
            vehicle_capacity_kg=vehicle_capacity_kg,
            vehicle_count=vehicle_count,
        )
    return _build_summary_rows(counts)


def build_vehicle_pool_summary(
    vehicle_types: Iterable[object] | None,
    vehicle_capacities_kg: Iterable[object] | None,
    *,
    active_vehicle_ids: Iterable[object] | None = None,
    name_resolver: Callable[[str], str] | None = None,
) -> list[dict[str, Any]]:
    types_list = [str(vehicle_type or "").strip() for vehicle_type in (vehicle_types or [])]
    capacities_list = [_normalize_capacity_kg(capacity) for capacity in (vehicle_capacities_kg or [])]
    indices = (
        [_safe_int(vehicle_id) for vehicle_id in active_vehicle_ids]
        if active_vehicle_ids is not None
        else list(range(min(len(types_list), len(capacities_list))))
    )

    counts: dict[tuple[str, str, int], int] = {}
    for vehicle_id in indices:
        if vehicle_id < 0 or vehicle_id >= len(types_list) or vehicle_id >= len(capacities_list):
            continue
        vehicle_type_id = types_list[vehicle_id]
        vehicle_display_name = _resolve_display_name(vehicle_type_id, "", name_resolver=name_resolver)
        _append_summary_count(
            counts,
            vehicle_type_id=vehicle_type_id,
            vehicle_display_name=vehicle_display_name,
            vehicle_capacity_kg=capacities_list[vehicle_id],
            vehicle_count=1,
        )
    return _build_summary_rows(counts)


def build_route_fleet_summary(
    route_results: Iterable[dict[str, Any]] | None,
    *,
    name_resolver: Callable[[str], str] | None = None,
) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str, int], int] = {}
    for route_result in route_results or []:
        vehicle_type_id = str(route_result.get("vehicle_type_id", "") or "").strip()
        vehicle_display_name = _resolve_display_name(
            vehicle_type_id,
            route_result.get("vehicle_display_name", route_result.get("vehicle_type", "")),
            name_resolver=name_resolver,
        )
        vehicle_capacity_kg = _normalize_capacity_kg(route_result.get("vehicle_capacity_kg", 0))
        _append_summary_count(
            counts,
            vehicle_type_id=vehicle_type_id,
            vehicle_display_name=vehicle_display_name,
            vehicle_capacity_kg=vehicle_capacity_kg,
            vehicle_count=1,
        )
    return _build_summary_rows(counts)


def merge_fleet_summary_rows(*summary_groups: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str, int], int] = {}
    for summary_group in summary_groups:
        for row in summary_group or []:
            _append_summary_count(
                counts,
                vehicle_type_id=str(row.get("vehicle_type_id", "") or "").strip(),
                vehicle_display_name=str(row.get("vehicle_display_name", "") or "").strip(),
                vehicle_capacity_kg=_normalize_capacity_kg(row.get("vehicle_capacity_kg", 0)),
                vehicle_count=_safe_int(row.get("vehicle_count", 0)),
            )
    return _build_summary_rows(counts)


def build_count_by_type(summary_rows: Iterable[dict[str, Any]] | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in summary_rows or []:
        vehicle_type_id = str(row.get("vehicle_type_id", "") or "").strip()
        if not vehicle_type_id:
            continue
        counts[vehicle_type_id] = counts.get(vehicle_type_id, 0) + _safe_int(row.get("vehicle_count", 0))
    return counts


def format_fleet_mix_text(summary_rows: Iterable[dict[str, Any]] | None) -> str:
    parts: list[str] = []
    for row in summary_rows or []:
        vehicle_display_name = str(row.get("vehicle_display_name", "") or row.get("vehicle_type_id", "") or "").strip()
        vehicle_count = _safe_int(row.get("vehicle_count", 0))
        vehicle_capacity_ton = _safe_float(row.get("vehicle_capacity_ton", 0.0))
        if vehicle_count <= 0 or not vehicle_display_name:
            continue
        if vehicle_capacity_ton > 0:
            parts.append(f"{vehicle_display_name} {vehicle_capacity_ton:g}t x{vehicle_count}")
        else:
            parts.append(f"{vehicle_display_name} x{vehicle_count}")
    return ", ".join(parts)
