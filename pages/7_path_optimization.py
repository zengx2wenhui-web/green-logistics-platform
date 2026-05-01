"""路径优化页面。"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import sys
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from pages._bottom_nav import render_page_nav
from pages._route_analysis_shared import add_route_map_legend, build_depot_results_dataframe, build_fleet_summary_dataframe
from pages._ui_shared import (
    anchor,
    get_data_status,
    inject_base_style,
    inject_sidebar_navigation_label,
    render_pending_step_state,
    render_title,
    render_sidebar_navigation,
    render_top_nav,
)
from utils.amap_api import DEFAULT_AMAP_API_KEY
from utils.carbon_calc import calc_emission, compute_route_emission
from utils.distance_matrix import build_distance_matrix_from_coords
from utils.fleet_summary import (
    build_configured_fleet_summary,
    build_count_by_type,
    build_route_fleet_summary,
    format_fleet_mix_text,
)
from utils.file_reader import normalize_name
from utils.route_display import (
    build_route_context,
    get_ordered_route_names,
    get_ordered_route_nodes,
    get_ordered_route_segments,
    is_warehouse_depot_segment,
)
from utils.vehicle_environment import (
    DEFAULT_H2_SOURCE,
    DEFAULT_SEASON,
    format_vehicle_environment_summary,
    resolve_vehicle_environment_config,
)
from utils.vehicle_lib import get_vehicle_params


VEHICLE_NAME_MAP = {
    "diesel": "柴油重卡",
    "diesel": "柴油重卡",
    "lng": "LNG天然气重卡",
    "hev": "混合动力",
    "phev": "插电混动",
    "bev": "纯电动",
    "fcev": "氢燃料电池",
    "mixed": "混合车队",
}


st.set_page_config(page_title="路径优化", page_icon="🗺️", layout="wide", initial_sidebar_state="expanded")
inject_sidebar_navigation_label()
inject_base_style()
render_sidebar_navigation("pages/7_path_optimization.py")
render_top_nav(
    tabs=[("数据检查", "sec-check"), ("执行优化", "sec-exec"), ("优化结果", "sec-results")],
    active_idx=0,
)

st.markdown(
    """
    <style>
    .stApp { background: #dfe7d6; }
    .block-container {
        max-width: 1240px;
        padding-top: 1.25rem;
        padding-left: 3rem;
        padding-right: 3rem;
        padding-bottom: 4rem;
    }
    .block-container h1 {
        margin: 0.35rem 0 0.25rem;
        font-size: 3.2rem;
        font-weight: 700;
        color: #111111;
        letter-spacing: -0.02em;
    }
    .block-container p {
        color: #111111;
        font-size: 1.05rem;
    }
    .st-key-path-opt-check-card,
    .st-key-path-opt-summary-card,
    .st-key-path-opt-exec-card,
    .st-key-path-opt-results-card,
    .st-key-path-opt-empty-card {
        background: linear-gradient(135deg, rgba(223, 239, 188, 0.94) 0%, rgba(214, 234, 174, 0.92) 100%);
        border: 1px solid #d0e2b4;
        border-radius: 28px;
        padding: 1.55rem 1.7rem 1.65rem;
        box-shadow: 0 8px 24px rgba(123, 145, 91, 0.22);
        margin-top: 1.25rem;
        overflow: hidden;
    }
    .st-key-path-opt-check-card > div,
    .st-key-path-opt-summary-card > div,
    .st-key-path-opt-exec-card > div,
    .st-key-path-opt-results-card > div,
    .st-key-path-opt-empty-card > div {
        gap: 0.95rem;
    }
    .st-key-path-opt-check-card h3,
    .st-key-path-opt-summary-card h3,
    .st-key-path-opt-exec-card h3,
    .st-key-path-opt-results-card h3 {
        font-size: 1.95rem;
        font-weight: 700;
        color: #111111;
        margin-bottom: 0.15rem;
    }
    [data-testid="stHorizontalBlock"] { gap: 1rem; }
    div[data-testid="stAlert"] {
        border-radius: 18px !important;
        border: 0 !important;
    }
    div[data-testid="stDataFrame"] {
        background: rgba(255, 255, 255, 0.95) !important;
        border-radius: 18px !important;
        overflow: hidden !important;
    }
    div[data-testid="stMetric"] {
        background: transparent !important;
        border: 0 !important;
        padding: 0.1rem 0 !important;
    }
    div[data-testid="stMetric"] label {
        color: #111111 !important;
        font-size: 1rem !important;
        font-weight: 600 !important;
    }
    div[data-testid="stMetricValue"] {
        color: #111111 !important;
        font-size: 2rem !important;
        font-weight: 700 !important;
    }
    div[data-testid="stPlotlyChart"] {
        background: transparent !important;
        border-radius: 18px !important;
        overflow: hidden;
    }
    div[data-testid="stExpander"] {
        border-radius: 18px !important;
        overflow: hidden;
        border: 1px solid rgba(0, 0, 0, 0.06) !important;
        background: rgba(255, 255, 255, 0.55) !important;
    }
    .stButton > button,
    .stDownloadButton > button {
        height: 3rem !important;
        border-radius: 14px !important;
        font-size: 1.08rem !important;
        border: 0 !important;
        box-shadow: 0 5px 13px rgba(0, 0, 0, 0.18) !important;
    }
    .stButton > button[kind="primary"] {
        background: #2cb46d !important;
        color: #ffffff !important;
    }
    .st-key-path-opt-run-button-running .stButton > button {
        background: #9aa0a6 !important;
        color: #ffffff !important;
        cursor: not-allowed !important;
        box-shadow: none !important;
    }
    .st-key-path-opt-run-button-completed .stButton > button {
        background: #80B332 !important;
        color: #ffffff !important;
    }
    .stDownloadButton > button,
    .stButton > button:not([kind="primary"]) {
        background: #ffffff !important;
        color: #111111 !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.45rem;
        padding-bottom: 0.3rem;
    }
    .stTabs [data-baseweb="tab"] {
        background: rgba(255, 255, 255, 0.58);
        border-radius: 14px 14px 0 0;
        padding: 0.55rem 1rem;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(255, 255, 255, 0.92);
    }
    .glp-bottom-nav {
        margin-top: 2.5rem !important;
        gap: 4rem !important;
        font-size: 1.65rem !important;
    }
    @media (max-width: 900px) {
        .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
            padding-bottom: 3rem;
        }
        .block-container h1 {
            font-size: 2.55rem;
        }
        .st-key-path-opt-check-card,
        .st-key-path-opt-summary-card,
        .st-key-path-opt-exec-card,
        .st-key-path-opt-results-card,
        .st-key-path-opt-empty-card {
            padding: 1.2rem 1rem 1.35rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

render_title("路径优化", "执行物流网络优化计算，并将全局环境参数纳入碳排放核算。")


def display_vehicle_name(vehicle_type_id: str) -> str:
    return VEHICLE_NAME_MAP.get(vehicle_type_id, vehicle_type_id or "未知")


def get_total_demand_value(demand_data: object) -> float:
    if isinstance(demand_data, dict):
        if "总需求" in demand_data:
            return float(demand_data.get("总需求", 0) or 0)
        return float(sum(v for v in demand_data.values() if isinstance(v, (int, float))))
    try:
        return float(demand_data or 0)
    except Exception:
        return 0.0


def get_venue_demand(venue_name: str, demand_map: dict) -> object:
    normalized_name = normalize_name(venue_name)
    return demand_map.get(normalized_name) or demand_map.get(venue_name, {})


def build_load_detail(venue_name: str, venue_demand: object) -> tuple[dict, float]:
    if isinstance(venue_demand, dict):
        detail = {
            "venue": venue_name,
            "general_materials_kg": float(venue_demand.get("通用赛事物资", 0) or 0),
            "sports_equipment_kg": float(venue_demand.get("专项运动器材", 0) or 0),
            "medical_materials_kg": float(venue_demand.get("医疗物资", 0) or 0),
            "it_equipment_kg": float(venue_demand.get("IT设备", 0) or 0),
            "living_support_materials_kg": float(venue_demand.get("生活保障物资", 0) or 0),
        }
        return detail, get_total_demand_value(venue_demand)

    total = get_total_demand_value(venue_demand)
    return {
        "venue": venue_name,
        "general_materials_kg": total,
        "sports_equipment_kg": 0.0,
        "medical_materials_kg": 0.0,
        "it_equipment_kg": 0.0,
        "living_support_materials_kg": 0.0,
    }, total


def build_route_path_names(start_name: str, visits: list[str], end_name: str | None = None) -> list[str]:
    tail_name = end_name if end_name is not None else start_name
    return [start_name, *list(visits), tail_name]


def build_segment_labels(path_names: list[str]) -> list[str]:
    labels: list[str] = []
    for idx in range(max(len(path_names) - 1, 0)):
        labels.append(f"{path_names[idx]} -> {path_names[idx + 1]}")
    return labels


def build_multi_depot_full_path_names(
    warehouse_name: str,
    depot_name: str,
    visits: list[str],
) -> list[str]:
    return [warehouse_name, depot_name, *list(visits), depot_name, warehouse_name]


def build_route_node(
    *,
    name: str,
    lng: float,
    lat: float,
    node_type: str,
    address: str = "",
) -> dict[str, object]:
    return {
        "name": str(name or "").strip(),
        "lng": float(lng),
        "lat": float(lat),
        "node_type": node_type,
        "address": str(address or "").strip(),
    }


def build_route_node_from_source(node: dict, node_type: str | None = None) -> dict[str, object]:
    inferred_type = node_type
    if not inferred_type:
        if node.get("is_warehouse"):
            inferred_type = "warehouse"
        elif node.get("is_depot"):
            inferred_type = "depot"
        else:
            inferred_type = "venue"

    return build_route_node(
        name=str(node.get("name") or "").strip(),
        lng=float(node.get("lng", 0) or 0),
        lat=float(node.get("lat", 0) or 0),
        node_type=inferred_type,
        address=str(node.get("address") or "").strip(),
    )


def build_route_segment_types(route_nodes: list[dict[str, object]]) -> list[str]:
    segment_types: list[str] = []
    for idx in range(max(len(route_nodes) - 1, 0)):
        from_node = route_nodes[idx]
        to_node = route_nodes[idx + 1]
        node_types = {str(from_node.get("node_type") or ""), str(to_node.get("node_type") or "")}
        segment_types.append("trunk_transfer" if node_types == {"warehouse", "depot"} else "delivery")
    return segment_types


def finalize_route_result(
    *,
    route_info: dict,
    ordered_route_nodes: list[dict[str, object]],
    segment_distances: list[float],
    segment_demands: list[float],
    vehicle_type_id: str,
    season: str,
    h2_source: str,
) -> dict:
    route_path_names = [str(node.get("name") or "") for node in ordered_route_nodes if str(node.get("name") or "").strip()]
    route_coords = [[float(node["lat"]), float(node["lng"])] for node in ordered_route_nodes]
    segment_labels = build_segment_labels(route_path_names)
    segment_types = build_route_segment_types(ordered_route_nodes)

    emission_summary = compute_route_emission(
        distances=segment_distances,
        demands_kg=segment_demands,
        vehicle_type=vehicle_type_id,
        season=season,
        h2_source=h2_source,
        include_cold_start=True,
    )

    annotated_segments: list[dict[str, object]] = []
    trunk_distance_km = 0.0
    trunk_carbon_kg = 0.0
    for seg_idx, segment in enumerate(emission_summary.get("segments", [])):
        segment_label = segment_labels[seg_idx] if seg_idx < len(segment_labels) else f"路段 {seg_idx + 1}"
        segment_type = segment_types[seg_idx] if seg_idx < len(segment_types) else "delivery"
        segment_distance = float(segment.get("distance_km", 0) or 0)
        segment_carbon = float(segment.get("carbon_kg", 0) or 0)
        if segment_type == "trunk_transfer":
            trunk_distance_km += segment_distance
            trunk_carbon_kg += segment_carbon

        annotated_segments.append(
            {
                **segment,
                "segment_label": segment_label,
                "segment_type": segment_type,
            }
        )

    total_distance_km = float(emission_summary.get("total_distance_km", 0) or 0)
    total_carbon_kg = float(emission_summary.get("total_carbon_kg", 0) or 0)

    route_info["ordered_route_nodes"] = ordered_route_nodes
    route_info["route_coords"] = route_coords
    route_info["route_path_names"] = route_path_names
    route_info["segment_labels"] = segment_labels
    route_info["segment_types"] = segment_types
    route_info["segments"] = annotated_segments
    route_info["total_distance_km"] = total_distance_km
    route_info["total_carbon_kg"] = total_carbon_kg
    route_info["initial_load_kg"] = float(emission_summary.get("initial_load_kg", sum(segment_demands)) or 0)
    route_info["trunk_distance_km"] = round(trunk_distance_km, 2)
    route_info["trunk_carbon_kg"] = round(trunk_carbon_kg, 4)
    route_info["delivery_distance_km"] = round(max(total_distance_km - trunk_distance_km, 0.0), 2)
    route_info["delivery_carbon_kg"] = round(max(total_carbon_kg - trunk_carbon_kg, 0.0), 4)
    return route_info


def clone_route_result_as_diesel(
    route_result: dict,
    *,
    season: str,
    h2_source: str,
) -> dict:
    cloned_route = deepcopy(route_result)
    diesel_display_name = display_vehicle_name("diesel")
    diesel_params = get_vehicle_params("diesel") or {}
    cloned_route["vehicle_type_id"] = "diesel"
    cloned_route["vehicle_type"] = diesel_display_name
    cloned_route["vehicle_display_name"] = diesel_display_name
    cloned_route["vehicle_spec_label"] = f"{diesel_display_name} / {float(cloned_route.get('vehicle_capacity_kg', 0) or 0) / 1000.0:.1f} t"
    cloned_route["cold_start_g"] = diesel_params.get("cold_start_g", 0)

    updated_segments: list[dict[str, object]] = []
    total_carbon_kg = float(diesel_params.get("cold_start_g", 0) or 0) / 1000.0
    trunk_carbon_kg = 0.0
    for segment in cloned_route.get("segments", []) or []:
        updated_segment = dict(segment)
        distance_km = float(updated_segment.get("distance_km", 0) or 0)
        load_kg = float(updated_segment.get("load_kg", 0) or 0)
        carbon_kg = round(calc_emission(distance_km, load_kg, "diesel", season, h2_source), 4)
        updated_segment["carbon_kg"] = carbon_kg
        updated_segments.append(updated_segment)
        total_carbon_kg += carbon_kg
        if str(updated_segment.get("segment_type") or "") == "trunk_transfer":
            trunk_carbon_kg += carbon_kg

    cloned_route["segments"] = updated_segments
    cloned_route["trunk_carbon_kg"] = round(trunk_carbon_kg, 4)
    cloned_route["delivery_carbon_kg"] = round(max(total_carbon_kg - trunk_carbon_kg, 0.0), 4)
    cloned_route["total_carbon_kg"] = round(total_carbon_kg, 4)
    return cloned_route


def build_baseline_direct_route_results(
    *,
    nodes: list[dict],
    demands: dict,
    distance_matrix: list[list[float]],
    season: str,
    h2_source: str,
) -> list[dict]:
    if not nodes:
        return []

    warehouse_route_node = build_route_node_from_source(nodes[0], "warehouse")
    diesel_display_name = display_vehicle_name("diesel")
    route_results: list[dict] = []

    for venue_idx in range(1, len(nodes)):
        venue_node = nodes[venue_idx]
        venue_name = str(venue_node.get("name") or f"venue_{venue_idx}")
        detail, total_venue_demand = build_load_detail(venue_name, get_venue_demand(venue_name, demands))
        venue_route_node = build_route_node_from_source(venue_node, "venue")
        route_info = {
            "vehicle_name": f"直发车{venue_idx}",
            "vehicle_type_id": "diesel",
            "vehicle_type": diesel_display_name,
            "vehicle_display_name": diesel_display_name,
            "vehicle_capacity_kg": 0,
            "cold_start_g": (get_vehicle_params("diesel") or {}).get("cold_start_g", 0),
            "route": [0, venue_idx, 0],
            "visits": [venue_name],
            "visited_venue_names": [venue_name],
            "load_details": [detail],
            "route_coords": [],
            "route_path_names": [],
            "ordered_route_nodes": [],
            "segment_labels": [],
            "segment_types": [],
            "route_scope": "baseline_direct",
            "total_load_kg": total_venue_demand,
            "total_distance_km": 0.0,
            "total_carbon_kg": 0.0,
            "delivery_distance_km": 0.0,
            "delivery_carbon_kg": 0.0,
            "trunk_distance_km": 0.0,
            "trunk_carbon_kg": 0.0,
            "segments": [],
        }
        ordered_route_nodes = [
            dict(warehouse_route_node),
            dict(venue_route_node),
            dict(warehouse_route_node),
        ]
        segment_distances = [
            float(distance_matrix[0][venue_idx] or 0),
            float(distance_matrix[venue_idx][0] or 0),
        ]
        segment_demands = [float(total_venue_demand or 0)]
        finalize_route_result(
            route_info=route_info,
            ordered_route_nodes=ordered_route_nodes,
            segment_distances=segment_distances,
            segment_demands=segment_demands,
            vehicle_type_id="diesel",
            season=season,
            h2_source=h2_source,
        )
        route_results.append(route_info)

    return route_results


def build_comparison_scenario(
    *,
    scenario_id: str,
    label: str,
    description: str,
    route_results: list[dict],
    depot_results: list[dict],
    baseline_emission: float,
    vehicle_type_id: str,
    vehicle_display_name: str,
) -> dict[str, object]:
    total_emission = round(sum(float(route.get("total_carbon_kg", 0) or 0) for route in route_results), 4)
    total_distance_km = round(sum(float(route.get("total_distance_km", 0) or 0) for route in route_results), 2)
    terminal_distance_km = round(
        sum(float(route.get("delivery_distance_km", route.get("total_distance_km", 0)) or 0) for route in route_results),
        2,
    )
    trunk_distance_km = round(sum(float(route.get("trunk_distance_km", 0) or 0) for route in route_results), 2)
    trunk_emission = round(sum(float(route.get("trunk_carbon_kg", 0) or 0) for route in route_results), 4)
    terminal_emission = round(max(total_emission - trunk_emission, 0.0), 4)
    reduction_vs_baseline = round(max(baseline_emission - total_emission, 0.0), 4)
    reduction_vs_baseline_pct = round(
        (reduction_vs_baseline / baseline_emission * 100) if baseline_emission > 0 else 0.0,
        2,
    )
    fleet_used_by_type_capacity = build_route_fleet_summary(
        route_results,
        name_resolver=display_vehicle_name,
    )
    return {
        "id": scenario_id,
        "label": label,
        "description": description,
        "route_results": route_results,
        "depot_results": depot_results,
        "total_emission": total_emission,
        "total_distance_km": total_distance_km,
        "terminal_distance_km": terminal_distance_km,
        "trunk_distance_km": trunk_distance_km,
        "terminal_emission": terminal_emission,
        "trunk_emission": trunk_emission,
        "num_vehicles_used": len(route_results),
        "vehicle_type_id": vehicle_type_id,
        "vehicle_display_name": vehicle_display_name,
        "fleet_used_by_type": build_count_by_type(fleet_used_by_type_capacity),
        "fleet_used_by_type_capacity": fleet_used_by_type_capacity,
        "fleet_mix_text": format_fleet_mix_text(fleet_used_by_type_capacity),
        "reduction_vs_baseline": reduction_vs_baseline,
        "reduction_vs_baseline_pct": reduction_vs_baseline_pct,
    }


def build_comparison_scenarios(
    *,
    nodes: list[dict],
    demands: dict,
    distance_matrix: list[list[float]],
    optimized_route_results: list[dict],
    optimized_depot_results: list[dict],
    season: str,
    h2_source: str,
    optimized_vehicle_type_id: str,
    optimized_vehicle_display_name: str,
) -> list[dict[str, object]]:
    baseline_route_results = build_baseline_direct_route_results(
        nodes=nodes,
        demands=demands,
        distance_matrix=distance_matrix,
        season=season,
        h2_source=h2_source,
    )
    baseline_emission = round(
        sum(float(route.get("total_carbon_kg", 0) or 0) for route in baseline_route_results),
        4,
    )
    diesel_route_results = [
        clone_route_result_as_diesel(route_result, season=season, h2_source=h2_source)
        for route_result in optimized_route_results
    ]
    return [
        build_comparison_scenario(
            scenario_id="baseline_direct",
            label="基线方案（总仓直发）",
            description="总仓直接配送至各场馆，作为基准碳排放方案。",
            route_results=baseline_route_results,
            depot_results=[],
            baseline_emission=baseline_emission,
            vehicle_type_id="diesel",
            vehicle_display_name=display_vehicle_name("diesel"),
        ),
        build_comparison_scenario(
            scenario_id="diesel_same_routes",
            label="全柴油方案（同路线）",
            description="复用优化后的线路结构，但统一按柴油车型核算碳排放。",
            route_results=diesel_route_results,
            depot_results=deepcopy(optimized_depot_results),
            baseline_emission=baseline_emission,
            vehicle_type_id="diesel",
            vehicle_display_name=display_vehicle_name("diesel"),
        ),
        build_comparison_scenario(
            scenario_id="optimized_current",
            label="优化方案",
            description="采用当前优化后的中转枢纽与车型配置方案。",
            route_results=deepcopy(optimized_route_results),
            depot_results=deepcopy(optimized_depot_results),
            baseline_emission=baseline_emission,
            vehicle_type_id=optimized_vehicle_type_id,
            vehicle_display_name=optimized_vehicle_display_name,
        ),
    ]


def infer_depot_region(depot_name: str) -> tuple[str, str]:
    name = str(depot_name or "")
    region_map = {
        "广州": ("广东省", "广州市"),
        "东莞": ("广东省", "东莞市"),
        "深圳": ("广东省", "深圳市"),
        "佛山": ("广东省", "佛山市"),
        "肇庆": ("广东省", "肇庆市"),
    }
    for keyword, region in region_map.items():
        if keyword in name:
            return region
    return "", ""


def resolve_depot_region(
    depot_name: str,
    lng: float,
    lat: float,
    province: str,
    city: str,
    api_key: str,
) -> tuple[str, str]:
    if province and city:
        return province, city

    guessed_province, guessed_city = infer_depot_region(depot_name)
    if guessed_province and guessed_city:
        return guessed_province, guessed_city

    if not api_key:
        return province or "", city or ""

    try:
        import re

        from utils.amap_api import reverse_geocode

        address = reverse_geocode(lng, lat, api_key)
        if address and "未知" not in address:
            match = re.match(r"^([^省]+省|[^自治区]+自治区|[^市]+市)([^市]+市|[^自治州]+自治州|[^区]+区)", address)
            if match:
                return match.group(1), match.group(2)
            return address[:3], address[3:6]
    except Exception:
        pass

    return province or "", city or ""


class OptimizationPrecheckError(Exception):
    """Raised when optimization should stop after a user-facing precheck failure."""


def build_fleet_capacity_snapshot(vehicle_list: list[dict]) -> dict[str, object]:
    max_cap_kg = 0
    total_cap_kg = 0
    normalized_fleet: list[dict[str, object]] = []

    for vehicle in vehicle_list:
        count_max = int(vehicle.get("count_max", vehicle.get("count", 0)) or 0)
        load_ton = float(vehicle.get("load_ton", 0) or 0)
        if count_max <= 0 or load_ton <= 0:
            continue

        normalized_fleet.append(
            {
                "vehicle_type": vehicle.get("vehicle_type", ""),
                "name": vehicle.get("name", display_vehicle_name(vehicle.get("vehicle_type", ""))),
                "count_max": count_max,
                "load_ton": load_ton,
            }
        )
        single_cap = int(round(load_ton * 1000))
        max_cap_kg = max(max_cap_kg, single_cap)
        total_cap_kg += single_cap * count_max

    configured_fleet_summary = build_configured_fleet_summary(
        normalized_fleet,
        name_resolver=display_vehicle_name,
    )

    return {
        "normalized_fleet": normalized_fleet,
        "max_cap_kg": max_cap_kg,
        "total_cap_kg": total_cap_kg,
        "fleet_config_by_type": build_count_by_type(configured_fleet_summary),
        "fleet_config_by_type_capacity": configured_fleet_summary,
        "fleet_config_summary_text": format_fleet_mix_text(configured_fleet_summary),
    }


def _get_vehicle_capacity_kg(load_ton: object) -> int:
    try:
        return int(round(float(load_ton or 0) * 1000))
    except (TypeError, ValueError):
        return 0


def _get_fleet_entry_key(vehicle: dict[str, object]) -> tuple[str, int]:
    return (
        str(vehicle.get("vehicle_type", "") or "").strip(),
        _get_vehicle_capacity_kg(vehicle.get("load_ton", 0)),
    )


def _clone_normalized_fleet(vehicle_list: list[dict[str, object]]) -> list[dict[str, object]]:
    cloned_fleet: list[dict[str, object]] = []
    for vehicle in vehicle_list or []:
        cloned_vehicle = dict(vehicle)
        count_max = int(cloned_vehicle.get("count_max", cloned_vehicle.get("count", 0)) or 0)
        capacity_kg = _get_vehicle_capacity_kg(cloned_vehicle.get("load_ton", 0))
        if count_max <= 0 or capacity_kg <= 0:
            continue

        cloned_vehicle["count_max"] = count_max
        cloned_vehicle["load_ton"] = capacity_kg / 1000.0
        cloned_fleet.append(cloned_vehicle)
    return cloned_fleet


def _get_total_fleet_capacity_kg(vehicle_list: list[dict[str, object]]) -> int:
    total_capacity_kg = 0
    for vehicle in vehicle_list or []:
        count_max = int(vehicle.get("count_max", vehicle.get("count", 0)) or 0)
        if count_max <= 0:
            continue
        total_capacity_kg += _get_vehicle_capacity_kg(vehicle.get("load_ton", 0)) * count_max
    return total_capacity_kg


def _consume_used_fleet(
    available_fleet: list[dict[str, object]],
    solver_result: dict,
) -> list[dict[str, object]]:
    used_counts: dict[tuple[str, int], int] = {}
    route_vehicle_ids = list(solver_result.get("route_vehicle_ids", []) or [])
    vehicle_types = list(solver_result.get("vehicle_types", []) or [])
    vehicle_capacities_kg = list(solver_result.get("vehicle_capacities_kg", []) or [])

    for vehicle_pool_id in route_vehicle_ids:
        if not (0 <= vehicle_pool_id < len(vehicle_types) and 0 <= vehicle_pool_id < len(vehicle_capacities_kg)):
            raise RuntimeError("OR-Tools returned an invalid vehicle index while updating the remaining fleet.")

        key = (
            str(vehicle_types[vehicle_pool_id] or "").strip(),
            int(vehicle_capacities_kg[vehicle_pool_id] or 0),
        )
        used_counts[key] = used_counts.get(key, 0) + 1

    remaining_fleet: list[dict[str, object]] = []
    for vehicle in available_fleet or []:
        cloned_vehicle = dict(vehicle)
        key = _get_fleet_entry_key(cloned_vehicle)
        available_count = int(cloned_vehicle.get("count_max", cloned_vehicle.get("count", 0)) or 0)
        consume_count = min(available_count, used_counts.get(key, 0))
        remaining_count = available_count - consume_count

        if consume_count:
            next_count = used_counts.get(key, 0) - consume_count
            if next_count > 0:
                used_counts[key] = next_count
            else:
                used_counts.pop(key, None)

        if remaining_count > 0:
            cloned_vehicle["count_max"] = remaining_count
            remaining_fleet.append(cloned_vehicle)

    if used_counts:
        overflow_desc = " | ".join(
            f"{vehicle_type}/{capacity_kg}kg x{count}"
            for (vehicle_type, capacity_kg), count in sorted(used_counts.items())
        )
        raise RuntimeError(f"Multi-depot routing exceeded the available fleet: {overflow_desc}")

    return remaining_fleet


def get_saved_vehicle_environment_config() -> dict[str, object]:
    return resolve_vehicle_environment_config(
        st.session_state.get("vehicles", []),
        st.session_state.get("vehicle_environment_config"),
        fallback_season=st.session_state.get("global_season", DEFAULT_SEASON),
        fallback_h2_source=st.session_state.get("global_h2_source", DEFAULT_H2_SOURCE),
    )


def solve_multi_depot_routes(
    *,
    warehouse: dict,
    venue_nodes: list[dict],
    demands: dict,
    normalized_fleet: list[dict],
    clustering_result: dict,
    depot_results: list[dict],
    time_limit: int,
    season: str,
    h2_source: str,
) -> tuple[list[dict], list[dict], list[list[int]], list[dict], dict[str, object]]:
    route_results: list[dict] = []
    trunk_routes: list[dict] = []
    routes: list[list[int]] = []
    global_vehicle_index = 0
    remaining_fleet = _clone_normalized_fleet(normalized_fleet)
    depot_solver_meta: list[dict[str, object]] = []
    warehouse_name = str(warehouse.get("name") or "总仓库")
    warehouse_route_node = build_route_node(
        name=warehouse_name,
        lng=float(warehouse.get("lng", 0) or 0),
        lat=float(warehouse.get("lat", 0) or 0),
        node_type="warehouse",
        address=str(warehouse.get("address") or "").strip(),
    )

    depot_assignments: dict[int, list[int]] = {}
    for assignment in clustering_result.get("venue_assignments", []) or []:
        warehouse_idx = int(assignment.get("warehouse_idx", -1))
        venue_idx = int(assignment.get("venue_idx", -1))
        if warehouse_idx < 0 or venue_idx < 0:
            continue
        depot_assignments.setdefault(warehouse_idx, []).append(venue_idx)

    updated_depot_results = [dict(item) for item in (depot_results or [])]
    depot_jobs: list[tuple[int, dict, list[int], float]] = []

    for depot_idx, warehouse_result in enumerate(clustering_result.get("warehouses", []) or []):
        assigned_indices = [
            idx for idx in depot_assignments.get(depot_idx, [])
            if 0 <= idx < len(venue_nodes)
        ]
        if not assigned_indices:
            continue

        assigned_demand_kg = sum(
            get_total_demand_value(get_venue_demand(venue_nodes[idx]["name"], demands))
            for idx in assigned_indices
        )
        depot_jobs.append((depot_idx, warehouse_result, assigned_indices, assigned_demand_kg))

    depot_jobs.sort(key=lambda item: item[3], reverse=True)

    for depot_idx, warehouse_result, assigned_indices, assigned_demand_kg in depot_jobs:

        depot_name = warehouse_result.get("nearest_candidate_name", f"中转仓{depot_idx + 1}")
        depot_lng = float(warehouse_result.get("lng", 0) or 0)
        depot_lat = float(warehouse_result.get("lat", 0) or 0)
        depot_address = f"{warehouse_result.get('province', '')}{warehouse_result.get('city', '')}".strip()
        depot_node = {
            "name": depot_name,
            "lng": depot_lng,
            "lat": depot_lat,
            "address": depot_address,
            "is_depot": True,
        }

        assigned_venues = [
            venue_nodes[idx]
            for idx in assigned_indices
            if 0 <= idx < len(venue_nodes)
        ]
        if not assigned_venues:
            continue

        local_nodes = [depot_node] + assigned_venues
        local_coords = [(node["lng"], node["lat"]) for node in local_nodes]
        local_demands = [0.0]
        for venue_node in assigned_venues:
            local_demands.append(
                get_total_demand_value(get_venue_demand(venue_node["name"], demands))
            )

        remaining_capacity_kg = _get_total_fleet_capacity_kg(remaining_fleet)
        if not remaining_fleet or remaining_capacity_kg <= 0:
            raise RuntimeError(
                f"中转仓 {depot_name} 仍需配送 {assigned_demand_kg:,.0f} kg，但全局车队已无可用车辆。"
            )
        if assigned_demand_kg > remaining_capacity_kg:
            raise RuntimeError(
                f"中转仓 {depot_name} 需要 {assigned_demand_kg:,.0f} kg 运力，但剩余全局车队只有 {remaining_capacity_kg:,.0f} kg。"
            )

        local_distance_matrix = build_distance_matrix_from_coords(
            local_coords,
            road_factor=1.3,
        )
        solver_result = solve_fsmvrp_ortools(
            distance_matrix_km=local_distance_matrix,
            demands_kg=local_demands,
            fleet=remaining_fleet,
            depot=0,
            time_limit_seconds=time_limit,
            season=season,
            h2_source=h2_source,
        )
        if not solver_result or not solver_result.get("success"):
            raise RuntimeError(f"中转仓 {depot_name} 的末端配送路线求解失败")

        depot_distance_matrix = build_distance_matrix_from_coords(
            [(warehouse["lng"], warehouse["lat"]), (depot_lng, depot_lat)],
            road_factor=1.3,
        )
        trunk_one_way_km = float(depot_distance_matrix[0][1] or 0)
        depot_route_node = build_route_node(
            name=depot_name,
            lng=depot_lng,
            lat=depot_lat,
            node_type="depot",
            address=depot_address,
        )

        local_routes = solver_result.get("routes", [])
        local_route_vehicle_ids = solver_result.get("route_vehicle_ids", [])
        local_vehicle_types = solver_result.get("vehicle_types", [])
        local_vehicle_capacities = solver_result.get("vehicle_capacities_kg", [])
        local_fleet_used_summary = list(solver_result.get("fleet_used_by_type_capacity", []) or [])
        depot_route_records: list[dict] = []

        for local_route_idx, route in enumerate(local_routes):
            vehicle_pool_id = local_route_vehicle_ids[local_route_idx]
            vehicle_type_id = local_vehicle_types[vehicle_pool_id]
            vehicle_capacity_kg = int(local_vehicle_capacities[vehicle_pool_id])
            vehicle_display_name = display_vehicle_name(vehicle_type_id)
            vehicle_params = get_vehicle_params(vehicle_type_id)

            global_vehicle_index += 1
            route_info = {
                "vehicle_name": f"车辆{global_vehicle_index}",
                "vehicle_type_id": vehicle_type_id,
                "vehicle_type": vehicle_display_name,
                "vehicle_display_name": vehicle_display_name,
                "vehicle_capacity_kg": vehicle_capacity_kg,
                "vehicle_spec_label": f"{vehicle_display_name} / {vehicle_capacity_kg / 1000.0:.1f} t",
                "cold_start_g": vehicle_params.get("cold_start_g", 0),
                "route": route,
                "visits": [],
                "visited_venue_names": [],
                "load_details": [],
                "route_coords": [],
                "route_path_names": [],
                "ordered_route_nodes": [],
                "segment_labels": [],
                "segment_types": [],
                "route_scope": "terminal",
                "depot_name": depot_name,
                "depot_lng": depot_lng,
                "depot_lat": depot_lat,
                "total_load_kg": 0.0,
                "total_distance_km": 0.0,
                "total_carbon_kg": 0.0,
                "delivery_distance_km": 0.0,
                "delivery_carbon_kg": 0.0,
                "trunk_distance_km": 0.0,
                "trunk_carbon_kg": 0.0,
                "segments": [],
            }

            for stop_idx in route:
                node = local_nodes[stop_idx]
                if stop_idx == 0:
                    continue
                venue_name = node["name"]
                detail, total_venue_demand = build_load_detail(
                    venue_name,
                    get_venue_demand(venue_name, demands),
                )
                route_info["visits"].append(venue_name)
                route_info["visited_venue_names"].append(venue_name)
                route_info["load_details"].append(detail)
                route_info["total_load_kg"] += total_venue_demand

            local_segment_distances: list[float] = []
            local_segment_demands: list[float] = []
            for seg_idx in range(len(route) - 1):
                from_idx = route[seg_idx]
                to_idx = route[seg_idx + 1]
                local_segment_distances.append(local_distance_matrix[from_idx][to_idx])
                if to_idx != 0:
                    local_segment_demands.append(local_demands[to_idx])

            ordered_route_nodes = [
                dict(warehouse_route_node),
                dict(depot_route_node),
                *[
                    build_route_node_from_source(local_nodes[stop_idx], "venue")
                    for stop_idx in route
                    if stop_idx != 0
                ],
                dict(depot_route_node),
                dict(warehouse_route_node),
            ]
            full_segment_distances = [trunk_one_way_km, *local_segment_distances, trunk_one_way_km]
            full_segment_demands = [0.0, *local_segment_demands, 0.0, 0.0]
            route_info["route_scope"] = "multi_depot_full"
            finalize_route_result(
                route_info=route_info,
                ordered_route_nodes=ordered_route_nodes,
                segment_distances=full_segment_distances,
                segment_demands=full_segment_demands,
                vehicle_type_id=vehicle_type_id,
                season=season,
                h2_source=h2_source,
            )
            route_results.append(route_info)
            depot_route_records.append(route_info)
            routes.append(route)
            trunk_routes.append(
                {
                    "depot_name": depot_name,
                    "vehicle_name": route_info["vehicle_name"],
                    "vehicle_type_id": vehicle_type_id,
                    "vehicle_display_name": vehicle_display_name,
                    "vehicle_capacity_kg": vehicle_capacity_kg,
                    "round_trip_distance_km": round(trunk_one_way_km * 2, 2),
                    "carbon_kg": route_info["trunk_carbon_kg"],
                    "served_venues": len(route_info["visits"]),
                    "total_load_kg": round(float(route_info.get("total_load_kg", 0) or 0), 1),
                }
            )

        remaining_fleet = _consume_used_fleet(remaining_fleet, solver_result)
        remaining_fleet_summary = build_configured_fleet_summary(
            remaining_fleet,
            name_resolver=display_vehicle_name,
        )
        depot_solver_meta.append(
            {
                "depot_name": depot_name,
                "num_vehicles_used": int(solver_result.get("num_vehicles_used", 0) or 0),
                "fleet_used_by_type": dict(solver_result.get("fleet_used_by_type", {}) or {}),
                "fleet_used_by_type_capacity": local_fleet_used_summary,
                "fleet_used_summary_text": format_fleet_mix_text(local_fleet_used_summary),
                "remaining_fleet_by_type_capacity": remaining_fleet_summary,
                "remaining_fleet_summary_text": format_fleet_mix_text(remaining_fleet_summary),
                "refinement_meta": dict(solver_result.get("refinement_meta", {}) or {}),
                "cost_model": str(solver_result.get("cost_model") or ""),
            }
        )

        if depot_idx < len(updated_depot_results):
            updated_depot_results[depot_idx]["trunk_distance_km"] = round(
                sum(item.get("trunk_distance_km", 0) for item in depot_route_records),
                2,
            )
            updated_depot_results[depot_idx]["trunk_carbon_kg"] = round(
                sum(item.get("trunk_carbon_kg", 0) for item in depot_route_records),
                4,
            )
            updated_depot_results[depot_idx]["trunk_trip_count"] = len(depot_route_records)
            updated_depot_results[depot_idx]["route_count"] = len(depot_route_records)
            updated_depot_results[depot_idx]["allocated_vehicle_count"] = len(depot_route_records)
            updated_depot_results[depot_idx]["fleet_used_by_type"] = dict(solver_result.get("fleet_used_by_type", {}) or {})
            updated_depot_results[depot_idx]["fleet_used_by_type_capacity"] = local_fleet_used_summary
            updated_depot_results[depot_idx]["fleet_used_summary_text"] = format_fleet_mix_text(local_fleet_used_summary)
            updated_depot_results[depot_idx]["remaining_fleet_by_type_capacity"] = remaining_fleet_summary
            updated_depot_results[depot_idx]["remaining_fleet_summary_text"] = format_fleet_mix_text(remaining_fleet_summary)
            updated_depot_results[depot_idx]["solver_refinement_meta"] = dict(solver_result.get("refinement_meta", {}) or {})
            updated_depot_results[depot_idx]["cost_model"] = str(solver_result.get("cost_model") or "")

    fleet_used_by_type_capacity = build_route_fleet_summary(
        route_results,
        name_resolver=display_vehicle_name,
    )
    remaining_fleet_by_type_capacity = build_configured_fleet_summary(
        remaining_fleet,
        name_resolver=display_vehicle_name,
    )
    multi_depot_solver_result = {
        "success": True,
        "routes": routes,
        "route_vehicle_ids": [],
        "num_vehicles_pool": sum(int(vehicle.get("count_max", vehicle.get("count", 0)) or 0) for vehicle in normalized_fleet),
        "num_vehicles_used": len(route_results),
        "vehicle_used_flags": [],
        "vehicle_types": [],
        "vehicle_capacities_kg": [],
        "active_vehicle_ids": [],
        "fleet_used_by_type": build_count_by_type(fleet_used_by_type_capacity),
        "fleet_used_by_type_capacity": fleet_used_by_type_capacity,
        "remaining_fleet_by_type": build_count_by_type(remaining_fleet_by_type_capacity),
        "remaining_fleet_by_type_capacity": remaining_fleet_by_type_capacity,
        "cost_model": "fixed cold-start carbon + proxy arc carbon cost (grams CO2 integer) within per-depot OR-Tools decomposition",
        "refinement_meta": {
            "objective_model": "Per-depot OR-Tools heterogeneous fleet proxy arc carbon + exact-carbon local refinement",
            "refinement_applied": any(
                bool((item.get("refinement_meta", {}) or {}).get("refinement_applied"))
                for item in depot_solver_meta
            ),
            "depot_solver_meta": depot_solver_meta,
        },
    }

    return route_results, trunk_routes, routes, updated_depot_results, multi_depot_solver_result


def reset_path_opt_state() -> None:
    st.session_state.path_opt_button_state = "idle"
    st.session_state.path_opt_run_requested = False


def set_path_opt_error(message: str) -> None:
    reset_path_opt_state()
    st.session_state.path_opt_error_message = message


def abort_optimization(message: str) -> None:
    set_path_opt_error(message)
    raise OptimizationPrecheckError(message)


warehouse = st.session_state.get("warehouse", {})
venues = st.session_state.get("venues", [])
demands = st.session_state.get("demands", {})
vehicles = st.session_state.get("vehicles", [])
if "vehicle_environment_config" not in st.session_state and vehicles:
    st.session_state.vehicle_environment_config = resolve_vehicle_environment_config(
        vehicles,
        None,
        fallback_season=st.session_state.get("global_season", DEFAULT_SEASON),
        fallback_h2_source=st.session_state.get("global_h2_source", DEFAULT_H2_SOURCE),
    )
saved_vehicle_environment_config = get_saved_vehicle_environment_config()
if vehicles:
    st.session_state.vehicle_environment_config = saved_vehicle_environment_config
g_season = saved_vehicle_environment_config.get("season")
g_h2_source = saved_vehicle_environment_config.get("h2_source")
environment_summary = format_vehicle_environment_summary(saved_vehicle_environment_config)
vehicle_status = get_data_status("vehicles")

try:
    from utils.fsmvrp_ortools import solve_fsmvrp_ortools
    solver_import_error = ""
except Exception as exc:
    solve_fsmvrp_ortools = None
    solver_import_error = str(exc)

total_demand = sum(get_total_demand_value(v) for v in demands.values()) if isinstance(demands, dict) else 0.0
total_vehicles = sum(int(v.get("count_max", v.get("count", 0)) or 0) for v in vehicles)
if "path_opt_button_state" not in st.session_state:
    st.session_state.path_opt_button_state = "idle"
if "path_opt_run_requested" not in st.session_state:
    st.session_state.path_opt_run_requested = False
if "path_opt_error_message" not in st.session_state:
    st.session_state.path_opt_error_message = ""

if vehicle_status != "saved":
    if vehicle_status == "dirty":
        warning_message = "检测到车辆或环境参数存在未保存改动。"
        info_message = "路径优化只会基于已保存的车辆与环境快照执行，请先返回“车辆配置”页面保存后再继续。"
    else:
        warning_message = "尚未完成车辆与环境配置，请先完成上一步。"
        info_message = "当前页面需要使用已保存的车辆与环境快照，只有完成“车辆配置”页面并点击保存后，才能继续执行路径优化。"
    render_pending_step_state(
        anchor_name="sec-check",
        container_key="path-opt-empty-card",
        warning_message=warning_message,
        info_message=info_message,
        prev_page="pages/4_vehicles.py",
        next_page="pages/6_carbon_overview.py",
        key_prefix="path-opt-guard-nav",
        next_block_message="请先完成并保存车辆与环境配置后，再继续执行路径优化。",
    )

fleet_snapshot = build_fleet_capacity_snapshot(vehicles)
total_fleet_capacity_kg = int(fleet_snapshot["total_cap_kg"] or 0)

anchor("sec-check")
with st.container(key="path-opt-check-card"):
    st.markdown("### 数据完整性与环境检查")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        if warehouse.get("lng") is not None and warehouse.get("lat") is not None:
            st.success("仓库已配置")
        else:
            st.error("仓库未配置")
    with col2:
        st.metric("场馆数量", len(venues))
    with col3:
        st.metric("总需求", f"{total_demand:,.0f} kg")
    with col4:
        st.metric("车队上限", f"{total_vehicles} 辆")
    with col5:
        st.metric("当前环境", environment_summary)

    missing = []
    if warehouse.get("lng") is None or warehouse.get("lat") is None:
        missing.append("仓库坐标")
    if not venues:
        missing.append("场馆")
    if not demands:
        missing.append("物资需求")
    if not vehicles:
        missing.append("车辆配置")

    if missing:
        st.warning("数据不完整：" + "、".join(missing))
        render_page_nav("pages/4_vehicles.py", "pages/6_carbon_overview.py", key_prefix="path-opt-nav")
        st.stop()

with st.container(key="path-opt-summary-card"):
    st.markdown("### 已满足执行条件")
    col_s1, col_s2, col_s3 = st.columns([5, 3, 6], gap="large", vertical_alignment="center")
    with col_s1:
        warehouse_address = warehouse.get("address", "未设置")
        st.metric("总仓地址", warehouse_address[:15] + "..." if len(warehouse_address) > 15 else warehouse_address)
    with col_s2:
        st.metric("场馆数量", len(venues))
    with col_s3:
        vehicle_summary = ", ".join(
            f"{v.get('name', display_vehicle_name(v.get('vehicle_type', '')))}:{int(v.get('count_max', v.get('count', 0)) or 0)}辆"
            for v in vehicles
            if int(v.get("count_max", v.get("count", 0)) or 0) > 0
        )
        st.metric("车队配置", vehicle_summary[:24] + "..." if len(vehicle_summary) > 24 else vehicle_summary)

    st.caption(f"当前车队满载总运力：{total_fleet_capacity_kg:,.0f} kg")

anchor("sec-exec")
with st.container(key="path-opt-exec-card"):
    st.markdown("### 执行优化计算")
    api_key = str(st.session_state.get("api_key_amap") or DEFAULT_AMAP_API_KEY)
    st.session_state.api_key_amap = api_key
    time_limit = st.slider(
        "OR-Tools 求解时间上限（秒）",
        5,
        120,
        30,
        help="时间越长，求解质量通常越高，且会自动复用后台配置的地理补全能力。",
    )

    if solver_import_error:
        st.warning(f"OR-Tools solver is unavailable in the current environment: {solver_import_error}")

    button_state = st.session_state.get("path_opt_button_state", "idle")
    button_label_map = {
        "idle": "开始优化计算",
        "running": "正在优化计算",
        "completed": "优化计算完成",
    }
    with st.container(key=f"path-opt-run-button-{button_state}"):
        run_clicked = st.button(
            button_label_map.get(button_state, "开始优化计算"),
            type="primary",
            width='stretch',
            disabled=button_state == "running" or solve_fsmvrp_ortools is None,
        )

    if run_clicked and button_state != "running":
        st.session_state.path_opt_error_message = ""
        if not fleet_snapshot["normalized_fleet"]:
            set_path_opt_error("未找到有效车辆配置，无法进行调度，请先返回“车辆配置”页面完成车队设置。")
        elif total_demand > total_fleet_capacity_kg:
            set_path_opt_error("当前总需求超过车队满载总运力，无法进行调度，请调整运力或物资需求！")
        else:
            st.session_state.path_opt_button_state = "running"
            st.session_state.path_opt_run_requested = True
            st.rerun()

    if st.session_state.get("path_opt_error_message"):
        st.error(st.session_state.path_opt_error_message)
        quick_col1, quick_col2 = st.columns(2)
        with quick_col1:
            if st.button("返回车辆配置", width='stretch', key="path-opt-go-vehicles"):
                st.switch_page("pages/4_vehicles.py")
        with quick_col2:
            if st.button("返回物资需求", width='stretch', key="path-opt-go-materials"):
                st.switch_page("pages/3_materials.py")

    if st.session_state.get("path_opt_run_requested"):
        progress_bar = st.progress(0)
        status_text = st.empty()

        try:
            st.session_state.path_opt_error_message = ""
            status_text.text("Step A: 构建节点与需求")
            progress_bar.progress(0.05)

            nodes = [
                {
                    "name": warehouse.get("name", "总仓库"),
                    "lng": warehouse["lng"],
                    "lat": warehouse["lat"],
                    "address": warehouse.get("address", ""),
                    "is_warehouse": True,
                }
            ]
            node_demands = [0.0]

            for venue in venues:
                if venue.get("lng") is None or venue.get("lat") is None:
                    continue
                nodes.append(
                    {
                        "name": venue["name"],
                        "lng": venue["lng"],
                        "lat": venue["lat"],
                        "address": venue.get("address", ""),
                        "is_warehouse": False,
                    }
                )
                node_demands.append(get_total_demand_value(get_venue_demand(venue["name"], demands)))

            if len(nodes) < 2:
                abort_optimization("至少需要 1 个已定位场馆才能执行路径优化，请先返回场馆录入页面补全坐标。")

            status_text.text("Step B: 计算距离矩阵")
            coords = [(node["lng"], node["lat"]) for node in nodes]

            def progress_callback(prog: float, msg: str) -> None:
                progress_bar.progress(0.10 + 0.20 * prog)
                status_text.text(msg)

            distance_matrix = build_distance_matrix_from_coords(
                coords,
                road_factor=1.3,
                progress_callback=progress_callback,
            )
            distance_method = "Haversine × 1.3"
            st.session_state.distance_matrix = distance_matrix
            progress_bar.progress(0.3)

            status_text.text("Step C: 运力可行性检查")
            normalized_fleet = list(fleet_snapshot["normalized_fleet"])
            max_cap_kg = int(fleet_snapshot["max_cap_kg"] or 0)
            total_cap_kg = int(fleet_snapshot["total_cap_kg"] or 0)

            if not normalized_fleet:
                abort_optimization("未找到有效车辆配置，无法进行调度，请先返回“车辆配置”页面完成车队设置。")

            max_demand_kg = max(node_demands) if node_demands else 0
            total_demand_kg = sum(node_demands)
            if max_demand_kg > max_cap_kg:
                abort_optimization(
                    f"单个场馆最大需求 {max_demand_kg:,.0f} kg 超过单车最大载荷 {max_cap_kg:,.0f} kg，请调整物资需求或车辆载重配置。"
                )
            if total_demand_kg > total_cap_kg:
                abort_optimization(
                    "当前总需求超过车队满载总运力，无法进行调度，请调整运力或物资需求！"
                )
            progress_bar.progress(0.4)

            status_text.text("Step D: 中转枢纽选址分析")
            depot_results = []
            clustering_result = None
            clustering_method = "场馆数≤5，直达配送"
            venue_nodes = [node for node in nodes if not node.get("is_warehouse")]
            if len(venue_nodes) > 5:
                try:
                    from utils.clustering import haversine_distance, select_warehouse_from_national_candidates

                    clustering_result, err = select_warehouse_from_national_candidates(
                        [(node["lng"], node["lat"]) for node in venue_nodes],
                        node_demands[1:],
                        max_warehouses=6,
                    )
                    if err:
                        raise RuntimeError(err)

                    optimal_k = clustering_result.get("optimal_k", 1)
                    clustering_method = f"K-Medoids 真实候选枢纽选址 (K={optimal_k})"
                    st.session_state.clustering_result = clustering_result

                    for idx, warehouse_result in enumerate(clustering_result.get("warehouses", [])[:optimal_k]):
                        depot_name = warehouse_result.get("nearest_candidate_name", f"真实枢纽{idx + 1}")
                        depot_lng = float(warehouse_result.get("lng", 0) or 0)
                        depot_lat = float(warehouse_result.get("lat", 0) or 0)
                        province, city = resolve_depot_region(
                            depot_name=depot_name,
                            lng=depot_lng,
                            lat=depot_lat,
                            province=str(warehouse_result.get("province", "") or ""),
                            city=str(warehouse_result.get("city", "") or ""),
                            api_key=api_key,
                        )
                        served_indices = warehouse_result.get("venues", []) or []
                        served_names = [venue_nodes[i]["name"] for i in served_indices if 0 <= i < len(venue_nodes)]
                        average_distance_km = 0.0
                        if served_indices:
                            total_distance_km = sum(
                                haversine_distance(
                                    depot_lng,
                                    depot_lat,
                                    venue_nodes[i]["lng"],
                                    venue_nodes[i]["lat"],
                                )
                                for i in served_indices
                                if 0 <= i < len(venue_nodes)
                            )
                            average_distance_km = total_distance_km / len(served_indices)

                        depot_results.append(
                            {
                                "仓库名称": depot_name,
                                "省": province,
                                "市": city,
                                "经度": round(depot_lng, 6),
                                "纬度": round(depot_lat, 6),
                                "服务场馆数": len(served_names),
                                "服务场馆列表": "、".join(served_names[:5]) + (f" 等{len(served_names)}个" if len(served_names) > 5 else ""),
                                "物资总量(kg)": round(float(warehouse_result.get("weight", 0) or 0), 1),
                                "平均距离(km)": round(average_distance_km, 2) if average_distance_km > 0 else "N/A",
                            }
                        )
                except Exception:
                    clustering_method = "选址降级: 无中转枢纽"
            progress_bar.progress(0.5)

            status_text.text("Step E: OR-Tools 异构车队求解(请耐心等待...)")
            use_multi_depot = bool(clustering_result and depot_results)
            trunk_routes = []
            if not use_multi_depot:
                route_results = []
            if use_multi_depot:
                route_results, trunk_routes, routes, depot_results, solver_result = solve_multi_depot_routes(
                    warehouse=warehouse,
                    venue_nodes=venue_nodes,
                    demands=demands,
                    normalized_fleet=normalized_fleet,
                    clustering_result=clustering_result,
                    depot_results=depot_results,
                    time_limit=time_limit,
                    season=g_season,
                    h2_source=g_h2_source,
                )
            else:
                solver_result = solve_fsmvrp_ortools(
                    distance_matrix_km=distance_matrix,
                    demands_kg=node_demands,
                    fleet=normalized_fleet,
                    depot=0,
                    time_limit_seconds=time_limit,
                    season=g_season,
                    h2_source=g_h2_source,
                )
            if not solver_result or not solver_result.get("success"):
                st.error("未找到可行解，请检查车辆配置或适当提高求解时间。")
                st.stop()

            routes = routes if use_multi_depot else solver_result["routes"]
            route_vehicle_ids = [] if use_multi_depot else solver_result.get("route_vehicle_ids", [])
            vehicle_types_pool = [] if use_multi_depot else solver_result.get("vehicle_types", [])
            vehicle_capacities_pool = [] if use_multi_depot else solver_result.get("vehicle_capacities_kg", [])
            progress_bar.progress(0.7)

            status_text.text("Step F: 分段碳排精算")
            if not use_multi_depot:
                route_results = []
            for route_idx, route in enumerate([] if use_multi_depot else routes):
                vehicle_pool_id = route_vehicle_ids[route_idx]
                vehicle_type_id = vehicle_types_pool[vehicle_pool_id]
                vehicle_capacity_kg = int(vehicle_capacities_pool[vehicle_pool_id])
                vehicle_display_name = display_vehicle_name(vehicle_type_id)
                vehicle_params = get_vehicle_params(vehicle_type_id)

                route_info = {
                    "vehicle_name": f"派车{route_idx + 1}",
                    "vehicle_type_id": vehicle_type_id,
                    "vehicle_type": vehicle_display_name,
                    "vehicle_display_name": vehicle_display_name,
                    "vehicle_capacity_kg": vehicle_capacity_kg,
                    "vehicle_spec_label": f"{vehicle_display_name} / {vehicle_capacity_kg / 1000.0:.1f} t",
                    "cold_start_g": vehicle_params.get("cold_start_g", 0),
                    "route": route,
                    "visits": [],
                    "visited_venue_names": [],
                    "load_details": [],
                    "route_coords": [],
                    "route_path_names": [],
                    "ordered_route_nodes": [],
                    "segment_labels": [],
                    "segment_types": [],
                    "route_scope": "direct",
                    "total_load_kg": 0.0,
                    "total_distance_km": 0.0,
                    "total_carbon_kg": 0.0,
                    "delivery_distance_km": 0.0,
                    "delivery_carbon_kg": 0.0,
                    "trunk_distance_km": 0.0,
                    "trunk_carbon_kg": 0.0,
                    "segments": [],
                }

                segment_distances = []
                segment_demands = []
                ordered_route_nodes: list[dict[str, object]] = []

                for stop_idx in route:
                    node = nodes[stop_idx]
                    ordered_route_nodes.append(build_route_node_from_source(node))
                    if stop_idx == 0:
                        continue
                    venue_name = node["name"]
                    detail, total_venue_demand = build_load_detail(venue_name, get_venue_demand(venue_name, demands))
                    route_info["visits"].append(venue_name)
                    route_info["visited_venue_names"].append(venue_name)
                    route_info["load_details"].append(detail)
                    route_info["total_load_kg"] += total_venue_demand

                for i in range(len(route) - 1):
                    from_idx = route[i]
                    to_idx = route[i + 1]
                    segment_distances.append(distance_matrix[from_idx][to_idx])
                    if to_idx != 0:
                        segment_demands.append(node_demands[to_idx])

                finalize_route_result(
                    route_info=route_info,
                    ordered_route_nodes=ordered_route_nodes,
                    segment_distances=segment_distances,
                    segment_demands=segment_demands,
                    vehicle_type_id=vehicle_type_id,
                    season=g_season,
                    h2_source=g_h2_source,
                )
                route_results.append(route_info)
            progress_bar.progress(0.85)

            status_text.text("Step G: 汇总结果")
            terminal_distance_km = sum(route.get("delivery_distance_km", route.get("total_distance_km", 0)) for route in route_results)
            terminal_carbon = sum(route.get("delivery_carbon_kg", route.get("total_carbon_kg", 0)) for route in route_results)
            trunk_distance_km = sum(route.get("trunk_distance_km", 0) for route in route_results)
            trunk_carbon = sum(route.get("trunk_carbon_kg", 0) for route in route_results)
            optimized_carbon = sum(route.get("total_carbon_kg", 0) for route in route_results)
            refinement_meta = solver_result.get("refinement_meta") if isinstance(solver_result, dict) else None

            used_vehicle_type_ids = sorted({route["vehicle_type_id"] for route in route_results})
            result_vehicle_type_id = used_vehicle_type_ids[0] if len(used_vehicle_type_ids) == 1 else "mixed"
            result_vehicle_display_name = display_vehicle_name(result_vehicle_type_id)
            comparison_scenarios = build_comparison_scenarios(
                nodes=nodes,
                demands=demands,
                distance_matrix=distance_matrix,
                optimized_route_results=route_results,
                optimized_depot_results=depot_results,
                season=g_season,
                h2_source=g_h2_source,
                optimized_vehicle_type_id=result_vehicle_type_id,
                optimized_vehicle_display_name=result_vehicle_display_name,
            )
            baseline_scenario = next(
                (scenario for scenario in comparison_scenarios if scenario.get("id") == "baseline_direct"),
                {},
            )
            baseline_carbon = float(baseline_scenario.get("total_emission", 0) or 0)
            baseline_distance = float(baseline_scenario.get("total_distance_km", 0) or 0)
            reduction_pct = ((baseline_carbon - optimized_carbon) / baseline_carbon * 100) if baseline_carbon > 0 else 0.0
            configured_fleet_by_type_capacity = list(fleet_snapshot.get("fleet_config_by_type_capacity", []) or [])
            configured_fleet_by_type = dict(fleet_snapshot.get("fleet_config_by_type", {}) or {})
            solver_fleet_used_by_type_capacity = list(solver_result.get("fleet_used_by_type_capacity", []) or [])
            fleet_used_by_type_capacity = build_route_fleet_summary(
                route_results,
                name_resolver=display_vehicle_name,
            )
            if not fleet_used_by_type_capacity:
                fleet_used_by_type_capacity = solver_fleet_used_by_type_capacity
            fleet_used_by_type = build_count_by_type(fleet_used_by_type_capacity)
            remaining_fleet_by_type_capacity = list(solver_result.get("remaining_fleet_by_type_capacity", []) or [])
            if not remaining_fleet_by_type_capacity and not use_multi_depot:
                try:
                    remaining_fleet_by_type_capacity = build_configured_fleet_summary(
                        _consume_used_fleet(_clone_normalized_fleet(normalized_fleet), solver_result),
                        name_resolver=display_vehicle_name,
                    )
                except Exception:
                    remaining_fleet_by_type_capacity = []
            remaining_fleet_by_type = dict(
                solver_result.get("remaining_fleet_by_type", {}) or build_count_by_type(remaining_fleet_by_type_capacity)
            )
            active_vehicle_ids = list(solver_result.get("active_vehicle_ids", []) or [])
            vehicle_used_flags = list(solver_result.get("vehicle_used_flags", []) or [])
            num_vehicles_pool = int(solver_result.get("num_vehicles_pool", total_vehicles) or total_vehicles)
            cost_model = str(
                solver_result.get("cost_model")
                or "fixed cold-start carbon + proxy arc carbon cost (grams CO2 integer)"
            )

            optimization_results = {
                "route_results": route_results,
                "trunk_routes": trunk_routes,
                "total_emission": optimized_carbon,
                "baseline_emission": baseline_carbon,
                "baseline_distance_km": baseline_distance,
                "reduction_percent": reduction_pct,
                "total_distance_km": sum(route.get("total_distance_km", 0) for route in route_results),
                "terminal_distance_km": terminal_distance_km,
                "trunk_distance_km": trunk_distance_km,
                "terminal_emission": terminal_carbon,
                "trunk_emission": trunk_carbon,
                "num_vehicles_used": len(route_results),
                "num_vehicles_pool": num_vehicles_pool,
                "optimization_method": "OR-Tools heterogeneous fleet + fixed cold-start carbon + proxy arc carbon + exact-carbon local refinement",
                "distance_method": distance_method,
                "clustering_method": clustering_method,
                "cost_model": cost_model,
                "vehicle_type_id": result_vehicle_type_id,
                "vehicle_type": result_vehicle_display_name,
                "vehicle_display_name": result_vehicle_display_name,
                "vehicle_capacity_kg": max((route["vehicle_capacity_kg"] for route in route_results), default=0),
                "used_vehicle_type_ids": used_vehicle_type_ids,
                "active_vehicle_ids": active_vehicle_ids,
                "vehicle_used_flags": vehicle_used_flags,
                "configured_fleet_by_type": configured_fleet_by_type,
                "configured_fleet_by_type_capacity": configured_fleet_by_type_capacity,
                "configured_fleet_summary_text": format_fleet_mix_text(configured_fleet_by_type_capacity),
                "fleet_used_by_type": fleet_used_by_type,
                "fleet_used_by_type_capacity": fleet_used_by_type_capacity,
                "solver_fleet_used_by_type_capacity": solver_fleet_used_by_type_capacity,
                "fleet_used_summary_text": format_fleet_mix_text(fleet_used_by_type_capacity),
                "remaining_fleet_by_type": remaining_fleet_by_type,
                "remaining_fleet_by_type_capacity": remaining_fleet_by_type_capacity,
                "remaining_fleet_summary_text": format_fleet_mix_text(remaining_fleet_by_type_capacity),
                "nodes": nodes,
                "routes": routes,
                "demands": demands,
                "depot_results": depot_results,
                "comparison_scenarios": comparison_scenarios,
                "solver_refinement_meta": refinement_meta,
                "environment_context": dict(saved_vehicle_environment_config),
                "season": g_season,
                "h2_source": g_h2_source,
                "timestamp": datetime.now().isoformat(),
            }
            st.session_state["optimization_results"] = optimization_results
            st.session_state["results"] = optimization_results

            progress_bar.progress(1.0)
            status_text.text("优化完成")
            st.session_state.path_opt_button_state = "completed"
            st.session_state.path_opt_run_requested = False
            st.session_state.path_opt_error_message = ""
            st.success("优化计算已完成。")
            st.rerun()

        except OptimizationPrecheckError:
            progress_bar.empty()
            status_text.empty()
            st.rerun()

        except Exception as exc:
            progress_bar.empty()
            status_text.empty()
            reset_path_opt_state()
            st.error(f"优化过程出错: {exc}")
            import traceback

            st.code(traceback.format_exc())

results = st.session_state.get("optimization_results") or st.session_state.get("results")

if results:
    route_results_list = results.get("route_results", [])
    nodes = results.get("nodes", [])
    depot_results_list = results.get("depot_results", [])
    demands_result = results.get("demands", demands)
    route_context = build_route_context(nodes, depot_results_list)

    anchor("sec-results")
    with st.container(key="path-opt-results-card"):
        st.markdown("### 优化结果")

        if depot_results_list:
            st.subheader("中转仓分析结果")
            st.dataframe(build_depot_results_dataframe(depot_results_list), width="stretch", hide_index=True)

        fleet_config_df = build_fleet_summary_dataframe(
            list(results.get("configured_fleet_by_type_capacity", []) or []),
            count_label="配置数量(辆)",
        )
        fleet_used_df = build_fleet_summary_dataframe(
            list(results.get("fleet_used_by_type_capacity", []) or []),
            count_label="实际用车(辆)",
        )
        if not fleet_used_df.empty or not fleet_config_df.empty:
            fleet_col1, fleet_col2 = st.columns(2)
            with fleet_col1:
                st.subheader("车队配置")
                if not fleet_config_df.empty:
                    st.dataframe(fleet_config_df, width="stretch", hide_index=True)
            with fleet_col2:
                st.subheader("实际用车")
                if not fleet_used_df.empty:
                    st.dataframe(fleet_used_df, width="stretch", hide_index=True)

        tab_map, tab_table = st.tabs(["路线地图", "车辆调度详情"])

        with tab_map:
            st.subheader("物流路线地图")
            if nodes:
                center_lat = sum(node["lat"] for node in nodes) / len(nodes)
                center_lng = sum(node["lng"] for node in nodes) / len(nodes)
                m = folium.Map(location=[center_lat, center_lng], zoom_start=12, width="100%")
                colors = ["#D94841", "#2F6BFF", "#2E9D52", "#8A46D8", "#F08C2B", "#D6336C", "#0F766E"]
                node_route_colors = {}

                for idx, route_result in enumerate(route_results_list):
                    route_color = colors[idx % len(colors)]
                    for route_node in get_ordered_route_nodes(route_result, route_context):
                        if route_node.get("node_type") == "venue" and route_node.get("name"):
                            node_route_colors[normalize_name(route_node["name"])] = route_color

                warehouse_node = nodes[0]
                folium.Marker(
                    [warehouse_node["lat"], warehouse_node["lng"]],
                    popup=f"<b>总仓库</b><br>{warehouse_node['name']}",
                    tooltip="总仓库",
                    icon=folium.Icon(color="darkred", icon="star"),
                ).add_to(m)

                for depot_index, depot in enumerate(depot_results_list, start=1):
                    depot_lat = depot.get("纬度", 0)
                    depot_lng = depot.get("经度", 0)
                    if depot_lat and depot_lng:
                        depot_name = str(depot.get("仓库名称") or f"中转仓{depot_index}")
                        folium.Marker(
                            [depot_lat, depot_lng],
                            popup=f"<b>{depot_name}</b>",
                            tooltip=depot_name,
                            icon=folium.Icon(color="red", icon="home", prefix="fa"),
                        ).add_to(m)

                for node in nodes[1:]:
                    venue_demand = get_total_demand_value(get_venue_demand(node["name"], demands_result))
                    marker_color = node_route_colors.get(normalize_name(node["name"]), "#2F6BFF")
                    folium.CircleMarker(
                        [node["lat"], node["lng"]],
                        popup=f"<b>{node['name']}</b><br>总需求: {venue_demand:.1f} kg",
                        tooltip=node["name"],
                        radius=5,
                        color=marker_color,
                        weight=2,
                        fill=True,
                        fill_color=marker_color,
                        fill_opacity=1,
                    ).add_to(m)

                for idx, route_result in enumerate(route_results_list):
                    route_color = colors[idx % len(colors)]
                    route_names = get_ordered_route_names(route_result, route_context)
                    route_segments = get_ordered_route_segments(route_result, route_context)
                    if not route_segments:
                        continue

                    route_text = " -> ".join(route_names)
                    for segment_index, segment in enumerate(route_segments, start=1):
                        from_node = segment["from_node"]
                        to_node = segment["to_node"]
                        is_trunk_segment = is_warehouse_depot_segment(from_node, to_node)
                        folium.PolyLine(
                            segment["coords"],
                            color="#6B7280" if is_trunk_segment else route_color,
                            weight=3 if is_trunk_segment else 4,
                            opacity=0.75 if is_trunk_segment else 0.8,
                            dash_array="8,8" if is_trunk_segment else None,
                            popup=(
                                f"{route_result['vehicle_name']} ({route_result['vehicle_type']})<br>"
                                f"路线：{route_text}<br>"
                                f"当前路段：{from_node['name']} -> {to_node['name']}<br>"
                                f"路段序号：{segment_index}/{len(route_segments)}"
                            ),
                        ).add_to(m)

                add_route_map_legend(m)

                st_folium(m, width="100%", height=500)
            else:
                st.info("暂无可展示的节点数据。")

        with tab_table:
            st.subheader("车辆调度详情")
            detail_columns = [
                ("general_materials_kg", "通用赛事物资(kg)"),
                ("sports_equipment_kg", "专项运动器材(kg)"),
                ("medical_materials_kg", "医疗物资(kg)"),
                ("it_equipment_kg", "IT设备(kg)"),
                ("living_support_materials_kg", "生活保障物资(kg)"),
            ]
            for route_result in route_results_list:
                vehicle_label = f"{route_result['vehicle_name']}（{route_result['vehicle_type']}）"
                with st.expander(vehicle_label, expanded=False):
                    route_text = " -> ".join(get_ordered_route_names(route_result, route_context))
                    st.markdown(f"**路线：** {route_text}")
                    st.divider()

                    load_details = route_result.get("load_details", [])
                    if load_details:
                        detail_rows = []
                        for stop in load_details:
                            row = {"场馆": stop.get("venue", "")}
                            total_value = 0.0
                            for field_name, label in detail_columns:
                                value = float(stop.get(field_name, 0) or 0)
                                row[label] = value
                                total_value += value
                            row["总需求(kg)"] = total_value
                            detail_rows.append(row)
                        st.dataframe(pd.DataFrame(detail_rows), width="stretch", hide_index=True)
                    else:
                        st.info("该车辆暂无装载明细。")

                    st.divider()
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        vehicle_capacity_kg = route_result.get("vehicle_capacity_kg", 0)
                        utilization = (route_result.get("total_load_kg", 0) / vehicle_capacity_kg * 100) if vehicle_capacity_kg else None
                        utilization_text = f"装载率 {utilization:.1f}%" if utilization is not None else "--"
                        st.metric("总装载量", f"{route_result.get('total_load_kg', 0):.1f} kg", delta=utilization_text)
                    with col2:
                        st.metric("总距离", f"{route_result.get('total_distance_km', 0):.2f} km")
                    with col3:
                        st.metric("总碳排", f"{route_result.get('total_carbon_kg', 0):.2f} kg CO2")

            summary_df = pd.DataFrame(
                [
                    {
                        "车辆编号": route["vehicle_name"],
                        "车型": route["vehicle_type"],
                        "访问场馆数": len(route["visits"]),
                        "装载量(kg)": round(route["total_load_kg"], 2),
                        "距离(km)": round(route["total_distance_km"], 2),
                        "碳排放(kg CO2)": round(route["total_carbon_kg"], 2),
                    }
                    for route in route_results_list
                ]
            )
            st.subheader("调度汇总")
            st.dataframe(summary_df, hide_index=True, width="stretch")

else:
    anchor("sec-results")
    with st.container(key="path-opt-empty-card"):
        st.info("当前还没有优化结果，请完成数据检查后执行优化计算。")

render_page_nav("pages/4_vehicles.py", "pages/6_carbon_overview.py", key_prefix="path-opt-nav")
