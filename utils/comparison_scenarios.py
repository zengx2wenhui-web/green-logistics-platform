from __future__ import annotations

from typing import Any


SCENARIO_ORDER = [
    "baseline_direct",
    "diesel_same_routes",
    "optimized_current",
]

SCENARIO_LABELS = {
    "baseline_direct": "基线方案（总仓直发）",
    "diesel_same_routes": "全柴油方案（同路线）",
    "optimized_current": "优化方案",
}

SCENARIO_DESCRIPTIONS = {
    "baseline_direct": "总仓直接配送至各场馆，作为基准碳排放方案。",
    "diesel_same_routes": "复用优化后的线路结构，但统一按柴油车型核算碳排放。",
    "optimized_current": "采用当前优化后的中转枢纽与车型配置方案。",
}


def _looks_like_placeholder_text(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    stripped = text.replace("？", "").replace("?", "").strip()
    return not stripped


def _normalize_scenario_display_fields(scenario: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(scenario)
    scenario_id = str(normalized.get("id") or "").strip()
    fallback_label = SCENARIO_LABELS.get(scenario_id, scenario_id or "未命名方案")
    fallback_description = SCENARIO_DESCRIPTIONS.get(scenario_id, "方案说明待补充。")

    if _looks_like_placeholder_text(normalized.get("label")):
        normalized["label"] = fallback_label
    if _looks_like_placeholder_text(normalized.get("description")):
        normalized["description"] = fallback_description
    return normalized


def _scenario_sort_key(scenario: dict[str, Any]) -> tuple[int, str]:
    scenario_id = str(scenario.get("id") or "").strip()
    if scenario_id in SCENARIO_ORDER:
        return (SCENARIO_ORDER.index(scenario_id), scenario_id)
    return (len(SCENARIO_ORDER), scenario_id)


def _build_legacy_scenario(
    *,
    scenario_id: str,
    result_data: dict[str, Any],
    baseline_emission: float,
) -> dict[str, Any]:
    total_emission = float(result_data.get("total_emission", 0) or 0)
    reduction = max(baseline_emission - total_emission, 0.0)
    reduction_pct = (reduction / baseline_emission * 100) if baseline_emission > 0 else 0.0

    if scenario_id == "baseline_direct":
        return {
            "id": scenario_id,
            "label": SCENARIO_LABELS[scenario_id],
            "description": "兼容旧结果：仅保留基线总碳排。",
            "route_results": [],
            "depot_results": [],
            "total_emission": baseline_emission,
            "total_distance_km": float(result_data.get("baseline_distance_km", 0) or 0),
            "terminal_distance_km": float(result_data.get("baseline_distance_km", 0) or 0),
            "trunk_distance_km": 0.0,
            "terminal_emission": baseline_emission,
            "trunk_emission": 0.0,
            "num_vehicles_used": 0,
            "vehicle_type_id": "diesel",
            "vehicle_display_name": "柴油重卡",
            "reduction_vs_baseline": 0.0,
            "reduction_vs_baseline_pct": 0.0,
        }

    return {
        "id": scenario_id,
        "label": SCENARIO_LABELS[scenario_id],
        "description": "兼容旧结果：使用原优化结果。",
        "route_results": list(result_data.get("route_results", []) or []),
        "depot_results": list(result_data.get("depot_results", []) or []),
        "total_emission": total_emission,
        "total_distance_km": float(result_data.get("total_distance_km", 0) or 0),
        "terminal_distance_km": float(result_data.get("terminal_distance_km", 0) or 0),
        "trunk_distance_km": float(result_data.get("trunk_distance_km", 0) or 0),
        "terminal_emission": float(result_data.get("terminal_emission", 0) or 0),
        "trunk_emission": float(result_data.get("trunk_emission", 0) or 0),
        "num_vehicles_used": int(result_data.get("num_vehicles_used", 0) or 0),
        "vehicle_type_id": str(result_data.get("vehicle_type_id") or ""),
        "vehicle_display_name": str(result_data.get("vehicle_display_name") or result_data.get("vehicle_type") or ""),
        "reduction_vs_baseline": reduction,
        "reduction_vs_baseline_pct": reduction_pct,
    }


def get_comparison_scenarios(result_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(result_data, dict):
        return []

    scenarios = result_data.get("comparison_scenarios")
    if isinstance(scenarios, list) and scenarios:
        normalized = [
            _normalize_scenario_display_fields(scenario)
            for scenario in scenarios
            if isinstance(scenario, dict)
        ]
        return sorted(normalized, key=_scenario_sort_key)

    baseline_emission = float(result_data.get("baseline_emission", 0) or 0)
    return [
        _build_legacy_scenario(
            scenario_id="baseline_direct",
            result_data=result_data,
            baseline_emission=baseline_emission,
        ),
        _build_legacy_scenario(
            scenario_id="optimized_current",
            result_data=result_data,
            baseline_emission=baseline_emission,
        ),
    ]


def get_scenario_by_id(
    result_data: dict[str, Any] | None,
    scenario_id: str,
) -> dict[str, Any] | None:
    scenario_id = str(scenario_id or "").strip()
    for scenario in get_comparison_scenarios(result_data):
        if str(scenario.get("id") or "").strip() == scenario_id:
            return scenario
    return None


def get_default_scenario_id(result_data: dict[str, Any] | None) -> str:
    scenarios = get_comparison_scenarios(result_data)
    if not scenarios:
        return "optimized_current"

    preferred = get_scenario_by_id(result_data, "optimized_current")
    if preferred:
        return "optimized_current"
    return str(scenarios[0].get("id") or "optimized_current")
