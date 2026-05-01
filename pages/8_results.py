from __future__ import annotations

import json
import sys
from pathlib import Path

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from pages._bottom_nav import render_page_nav
from pages._dashboard_shared import (
    apply_green_chart_theme,
    build_scenario_breakdown_figure,
    build_scenario_emission_figure,
    build_scenario_summary_dataframe,
    inject_green_dashboard_style,
    render_scenario_triptych,
)
from pages._route_analysis_shared import (
    add_route_map_legend,
    build_depot_results_dataframe,
    build_fleet_composition_dataframe,
    get_depot_display_name,
)
from pages._ui_shared import (
    anchor,
    inject_base_style,
    inject_sidebar_navigation_label,
    render_download_button,
    render_sidebar_navigation,
    render_title,
    render_top_nav,
)
from utils.comparison_scenarios import (
    get_comparison_scenarios,
    get_default_scenario_id,
    get_scenario_by_id,
)
from utils.file_reader import normalize_name
from utils.route_display import (
    build_route_context,
    get_ordered_route_names,
    get_ordered_route_nodes,
    get_ordered_route_segments,
    is_warehouse_depot_segment,
)

VEHICLE_NAME_MAP = {
    "diesel": "柴油重卡",
    "lng": "LNG天然气重卡",
    "hev": "混合动力 (HEV)",
    "phev": "插电混动 (PHEV)",
    "bev": "纯电动 (BEV)",
    "fcev": "氢燃料电池 (FCEV)",
    "mixed": "混合车队",
}

LOAD_DETAIL_COLUMNS = [
    ("general_materials_kg", "通用物资(kg)"),
    ("sports_equipment_kg", "体育器材(kg)"),
    ("medical_materials_kg", "医疗物资(kg)"),
    ("it_equipment_kg", "IT设备(kg)"),
    ("living_support_materials_kg", "生活保障物资(kg)"),
]


def get_vehicle_display_name(vehicle_type_id: str) -> str:
    return VEHICLE_NAME_MAP.get(vehicle_type_id, vehicle_type_id or "未知")


def get_result_vehicle_display_name(result_data: dict) -> str:
    display_name = str(result_data.get("vehicle_display_name") or "").strip()
    if display_name:
        return display_name
    return get_vehicle_display_name(str(result_data.get("vehicle_type_id") or result_data.get("vehicle_type") or ""))


def get_route_vehicle_display_name(route_result: dict, default_name: str) -> str:
    route_display_name = str(route_result.get("vehicle_type") or "").strip()
    if route_display_name:
        return route_display_name
    route_type_id = str(route_result.get("vehicle_type_id") or "").strip()
    if route_type_id:
        return get_vehicle_display_name(route_type_id)
    return default_name


def get_route_vehicle_capacity_ton(route_result: dict) -> float:
    try:
        return round(float(route_result.get("vehicle_capacity_kg", 0) or 0) / 1000.0, 2)
    except (TypeError, ValueError):
        return 0.0


def get_total_demand_value(demand_data: object) -> float:
    if isinstance(demand_data, dict):
        if "总需求量" in demand_data:
            return float(demand_data.get("总需求量", 0) or 0)
        return float(sum(value for value in demand_data.values() if isinstance(value, (int, float))))
    try:
        return float(demand_data or 0)
    except (TypeError, ValueError):
        return 0.0


def infer_total_demand_kg(route_results: list[dict], demands_dict: dict) -> float:
    route_total = sum(float(route.get("total_load_kg", 0) or 0) for route in route_results)
    if route_total > 0:
        return route_total
    return sum(get_total_demand_value(value) for value in demands_dict.values())


def get_route_path_names(route_result: dict, route_context: dict) -> list[str]:
    return get_ordered_route_names(route_result, route_context)


def add_scenario_columns(df: pd.DataFrame, *, scenario_id: str, scenario_label: str) -> pd.DataFrame:
    if df.empty:
        return df
    enriched = df.copy()
    enriched["scenario_id"] = scenario_id
    enriched["scenario_label"] = scenario_label
    return enriched


def build_dispatch_dataframe(route_results: list[dict], vehicle_name: str, route_context: dict) -> pd.DataFrame:
    rows = []
    for index, route_result in enumerate(route_results, start=1):
        rows.append(
            {
                "车辆编号": route_result.get("vehicle_name", f"车辆 {index}"),
                "车型": get_route_vehicle_display_name(route_result, vehicle_name),
                "单车载重上限(吨/辆)": get_route_vehicle_capacity_ton(route_result) or None,
                "路线": " -> ".join(get_route_path_names(route_result, route_context)),
                "场馆数": len(route_result.get("visited_venue_names", route_result.get("visits", []))),
                "总装载(kg)": round(float(route_result.get("total_load_kg", 0) or 0), 2),
                "总距离(km)": round(float(route_result.get("total_distance_km", 0) or 0), 2),
                "总碳排放(kg CO2)": round(float(route_result.get("total_carbon_kg", 0) or 0), 2),
            }
        )
    return pd.DataFrame(rows)


def build_route_carbon_dataframe(route_results: list[dict], vehicle_name: str) -> pd.DataFrame:
    rows = []
    for index, route_result in enumerate(route_results, start=1):
        total_distance = float(route_result.get("total_distance_km", 0) or 0)
        total_carbon = float(route_result.get("total_carbon_kg", 0) or 0)
        rows.append(
            {
                "车辆编号": route_result.get("vehicle_name", f"车辆 {index}"),
                "车型": get_route_vehicle_display_name(route_result, vehicle_name),
                "单车载重上限(吨/辆)": get_route_vehicle_capacity_ton(route_result) or None,
                "总距离(km)": round(total_distance, 2),
                "总碳排放(kg CO2)": round(total_carbon, 2),
                "碳排效率(kg/km)": round(total_carbon / max(total_distance, 0.01), 4),
            }
        )
    return pd.DataFrame(rows)


def build_route_load_dataframe(route_result: dict) -> pd.DataFrame:
    rows = []
    for stop in route_result.get("load_details", []):
        row = {"场馆": stop.get("venue", "")}
        total_value = 0.0
        for field_name, label in LOAD_DETAIL_COLUMNS:
            value = float(stop.get(field_name, 0) or 0)
            row[label] = value
            total_value += value
        row["总需求(kg)"] = total_value
        rows.append(row)
    return pd.DataFrame(rows)


def build_load_export_dataframe(route_results: list[dict], vehicle_name: str, route_context: dict) -> pd.DataFrame:
    rows = []
    for index, route_result in enumerate(route_results, start=1):
        vehicle_id = route_result.get("vehicle_name", f"车辆 {index}")
        vehicle_type = get_route_vehicle_display_name(route_result, vehicle_name)
        route_path = " -> ".join(get_route_path_names(route_result, route_context))
        for stop in route_result.get("load_details", []):
            row = {
                "车辆编号": vehicle_id,
                "车型": vehicle_type,
                "单车载重上限(吨/辆)": get_route_vehicle_capacity_ton(route_result) or None,
                "路线": route_path,
                "场馆": stop.get("venue", ""),
            }
            total_value = 0.0
            for field_name, label in LOAD_DETAIL_COLUMNS:
                value = float(stop.get(field_name, 0) or 0)
                row[label] = value
                total_value += value
            row["总需求(kg)"] = total_value
            rows.append(row)
    return pd.DataFrame(rows)


def build_route_segment_export_dataframe(route_results: list[dict], vehicle_name: str) -> pd.DataFrame:
    rows = []
    for index, route_result in enumerate(route_results, start=1):
        segment_labels = route_result.get("segment_labels", []) or []
        segments = route_result.get("segments", []) or []
        for seg_index, segment in enumerate(segments, start=1):
            rows.append(
                {
                    "车辆编号": route_result.get("vehicle_name", f"车辆 {index}"),
                    "车型": get_route_vehicle_display_name(route_result, vehicle_name),
                    "单车载重上限(吨/辆)": get_route_vehicle_capacity_ton(route_result) or None,
                    "分段": segment_labels[seg_index - 1] if seg_index - 1 < len(segment_labels) else f"分段 {seg_index}",
                    "距离(km)": round(float(segment.get("distance_km", 0) or 0), 2),
                    "装载(kg)": round(float(segment.get("load_kg", 0) or 0), 2),
                    "碳排放(kg CO2)": round(float(segment.get("carbon_kg", 0) or 0), 4),
                }
            )
    return pd.DataFrame(rows)


def build_depot_dataframe(depot_results_list: list[dict]) -> pd.DataFrame:
    return build_depot_results_dataframe(depot_results_list)


def build_map(
    nodes: list[dict],
    route_results: list[dict],
    depot_results_list: list[dict],
    demands_dict: dict,
    vehicle_name: str,
    route_context: dict,
) -> folium.Map | None:
    if not nodes:
        return None

    center_lat = sum(float(node["lat"]) for node in nodes) / len(nodes)
    center_lng = sum(float(node["lng"]) for node in nodes) / len(nodes)
    route_colors = ["#D94841", "#2F6BFF", "#2E9D52", "#8A46D8", "#F08C2B", "#D6336C", "#0F766E", "#2B8A3E"]

    map_chart = folium.Map(location=[center_lat, center_lng], zoom_start=12)
    node_route_colors: dict[str, str] = {}

    for route_index, route_result in enumerate(route_results):
        route_color = route_colors[route_index % len(route_colors)]
        route_nodes = get_ordered_route_nodes(route_result, route_context)
        for route_node in route_nodes:
            if route_node.get("node_type") == "venue" and route_node.get("name"):
                node_route_colors[normalize_name(route_node["name"])] = route_color

        route_segments = get_ordered_route_segments(route_result, route_context)
        if route_segments:
            route_name = route_result.get("vehicle_name", f"派车 {route_index + 1}")
            route_text = " -> ".join(get_route_path_names(route_result, route_context))
            for segment_index, segment in enumerate(route_segments, start=1):
                from_node = segment["from_node"]
                to_node = segment["to_node"]
                is_trunk_segment = is_warehouse_depot_segment(from_node, to_node)
                segment_text = f"{from_node['name']} -> {to_node['name']}"
                folium.PolyLine(
                    segment["coords"],
                    color="#6B7280" if is_trunk_segment else route_color,
                    weight=3 if is_trunk_segment else 4,
                    opacity=0.75 if is_trunk_segment else 0.85,
                    dash_array="8,8" if is_trunk_segment else None,
                    popup=(
                        f"{route_name} ({get_route_vehicle_display_name(route_result, vehicle_name)})<br>"
                        f"路线：{route_text}<br>"
                        f"分段：{segment_text}<br>"
                        f"序号：{segment_index}/{len(route_segments)}<br>"
                        f"总距离：{float(route_result.get('total_distance_km', 0) or 0):.2f} km<br>"
                        f"总碳排：{float(route_result.get('total_carbon_kg', 0) or 0):.2f} kg CO2"
                    ),
                ).add_to(map_chart)

    warehouse_node = nodes[0]
    folium.Marker(
        [warehouse_node["lat"], warehouse_node["lng"]],
        popup=f"<b>总仓</b><br>{warehouse_node['name']}<br>{warehouse_node.get('address', '')}",
        tooltip="总仓",
        icon=folium.Icon(color="darkred", icon="star"),
    ).add_to(map_chart)

    for depot_index, depot in enumerate(depot_results_list, start=1):
        depot_lat = depot.get("纬度", depot.get("çº¬åº¦", 0))
        depot_lng = depot.get("经度", depot.get("ç»åº¦", 0))
        if depot_lat and depot_lng:
            depot_name = get_depot_display_name(depot, depot_index)
            folium.Marker(
                [depot_lat, depot_lng],
                popup=folium.Popup(f"<b>{depot_name}</b>", max_width=360),
                tooltip=depot_name,
                icon=folium.Icon(color="red", icon="home", prefix="fa"),
            ).add_to(map_chart)

    for node in nodes[1:]:
        demand_value = get_total_demand_value(demands_dict.get(node["name"], 0))
        marker_color = node_route_colors.get(normalize_name(node["name"]), "#2F6BFF")
        folium.CircleMarker(
            [node["lat"], node["lng"]],
            radius=8,
            popup=f"<b>{node['name']}</b><br>总需求：{demand_value:.1f} kg",
            tooltip=f"{node['name']} ({demand_value:.1f} kg)",
            color=marker_color,
            weight=2,
            fill=True,
            fill_color=marker_color,
            fill_opacity=0.95,
        ).add_to(map_chart)

    add_route_map_legend(map_chart)
    return map_chart


def _json_default(value: object) -> str:
    return str(value)


st.set_page_config(page_title="优化结果", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
inject_sidebar_navigation_label()
inject_base_style()
inject_green_dashboard_style("results")
render_sidebar_navigation("pages/8_results.py")

results = st.session_state.get("optimization_results") or st.session_state.get("results")
has_results = bool(results)

render_top_nav(
    tabs=[("结果摘要", "sec-summary"), ("地图与结果", "sec-tabs")] if has_results else [("结果摘要", "sec-summary")],
    active_idx=0,
)

render_title("优化结果", "查看三方案对比、中转仓、路线与导出结果。")

if not results:
    anchor("sec-summary")
    st.info("当前还没有优化结果，请先前往“路径优化”页面执行计算。")
    render_page_nav(
        "pages/7_path_optimization.py",
        "app.py",
        prev_label="返回上一步",
        next_label="回到首页",
        key_prefix="results-empty-nav",
    )
    st.stop()

route_results = results.get("route_results", [])
trunk_routes = results.get("trunk_routes", [])
nodes = results.get("nodes", [])
depot_results_list = results.get("depot_results", [])
demands_dict = results.get("demands", {})
vehicle_name = get_result_vehicle_display_name(results)
comparison_scenarios = get_comparison_scenarios(results)
scenario_df = build_scenario_summary_dataframe(comparison_scenarios)
scenario_options = {
    str(scenario.get("id") or ""): str(scenario.get("label") or scenario.get("id") or "未命名方案")
    for scenario in comparison_scenarios
}
default_scenario_id = get_default_scenario_id(results)
selected_scenario_id = str(st.session_state.get("results_selected_scenario_id") or "")
if not scenario_options:
    selected_scenario_id = ""
elif selected_scenario_id not in scenario_options:
    selected_scenario_id = default_scenario_id if default_scenario_id in scenario_options else next(iter(scenario_options))
st.session_state["results_selected_scenario_id"] = selected_scenario_id


baseline_emission = float(results.get("baseline_emission", 0) or 0)
total_emission = float(results.get("total_emission", 0) or 0)
reduction_pct = float(results.get("reduction_percent", 0) or 0)
total_distance_km = float(results.get("total_distance_km", 0) or 0)
terminal_distance_km = float(results.get("terminal_distance_km", 0) or 0)
trunk_distance_km = float(results.get("trunk_distance_km", 0) or 0)
terminal_emission = float(results.get("terminal_emission", 0) or 0)
trunk_emission = float(results.get("trunk_emission", 0) or 0)
carbon_reduction = max(baseline_emission - total_emission, 0.0)
total_demand_kg = infer_total_demand_kg(route_results, demands_dict)
has_trunk_breakdown = bool(trunk_routes) or trunk_distance_km > 0 or trunk_emission > 0
distance_delta_text = f"末端 {terminal_distance_km:.2f} / 干线 {trunk_distance_km:.2f}" if has_trunk_breakdown else "配送闭环"
primary_emission_label = "末端配送碳排" if has_trunk_breakdown else "路线碳排"
secondary_emission_label = "干线碳排" if has_trunk_breakdown else "附加碳排"
depot_df = build_depot_dataframe(depot_results_list)

combined_dispatch_df = pd.concat(
    [
        add_scenario_columns(
            build_dispatch_dataframe(
                list(scenario.get("route_results", []) or []),
                str(scenario.get("vehicle_display_name") or vehicle_name),
                build_route_context(nodes, list(scenario.get("depot_results", []) or [])),
            ),
            scenario_id=str(scenario.get("id") or ""),
            scenario_label=str(scenario.get("label") or scenario.get("id") or ""),
        )
        for scenario in comparison_scenarios
    ],
    ignore_index=True,
) if comparison_scenarios else pd.DataFrame()

combined_load_export_df = pd.concat(
    [
        add_scenario_columns(
            build_load_export_dataframe(
                list(scenario.get("route_results", []) or []),
                str(scenario.get("vehicle_display_name") or vehicle_name),
                build_route_context(nodes, list(scenario.get("depot_results", []) or [])),
            ),
            scenario_id=str(scenario.get("id") or ""),
            scenario_label=str(scenario.get("label") or scenario.get("id") or ""),
        )
        for scenario in comparison_scenarios
    ],
    ignore_index=True,
) if comparison_scenarios else pd.DataFrame()

combined_segment_export_df = pd.concat(
    [
        add_scenario_columns(
            build_route_segment_export_dataframe(
                list(scenario.get("route_results", []) or []),
                str(scenario.get("vehicle_display_name") or vehicle_name),
            ),
            scenario_id=str(scenario.get("id") or ""),
            scenario_label=str(scenario.get("label") or scenario.get("id") or ""),
        )
        for scenario in comparison_scenarios
    ],
    ignore_index=True,
) if comparison_scenarios else pd.DataFrame()

anchor("sec-summary")
with st.container(key="results-card-summary"):
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总碳排放", f"{total_emission:.2f} kg CO2", delta=f"较基线减少 {carbon_reduction:.2f} kg")
    with col2:
        st.metric("总距离", f"{total_distance_km:.2f} km", delta=distance_delta_text)
    with col3:
        st.metric("总物资需求", f"{total_demand_kg:,.1f} kg", delta=f"{len(route_results)} 条路线")
    with col4:
        st.metric("减排比例", f"{reduction_pct:.2f}%", delta=f"{len(depot_results_list)} 个中转仓")

    if not depot_df.empty:
        st.markdown("### 中转仓结果")
        st.dataframe(depot_df, width="stretch", hide_index=True)

anchor("sec-tabs")
with st.container(key="results-card-tabs"):
    st.selectbox(
        "路线展示方案",
        options=list(scenario_options.keys()),
        format_func=lambda scenario_id: scenario_options.get(scenario_id, scenario_id),
        key="results_selected_scenario_id",
    )
    active_scenario = get_scenario_by_id(results, st.session_state.get("results_selected_scenario_id") or default_scenario_id) or {}
    active_route_results = list(active_scenario.get("route_results", route_results) or [])
    active_depot_results = list(active_scenario.get("depot_results", depot_results_list) or [])
    active_vehicle_name = str(active_scenario.get("vehicle_display_name") or vehicle_name)
    active_route_context = build_route_context(nodes, active_depot_results)
    active_dispatch_df = build_dispatch_dataframe(active_route_results, active_vehicle_name, active_route_context)
    active_route_carbon_df = build_route_carbon_dataframe(active_route_results, active_vehicle_name)
    active_configured_fleet_rows = list(active_scenario.get("configured_fleet_by_type_capacity", []) or [])
    if not active_configured_fleet_rows and str(active_scenario.get("id") or "") == "optimized_current":
        active_configured_fleet_rows = list(results.get("configured_fleet_by_type_capacity", []) or [])
    active_fleet_df = build_fleet_composition_dataframe(
        active_configured_fleet_rows,
        list(active_scenario.get("fleet_used_by_type_capacity", []) or []),
    )

    active_scenario_summary = (
        scenario_df[scenario_df["方案ID"] == st.session_state.get("results_selected_scenario_id")]
        if not scenario_df.empty
        else pd.DataFrame()
    )
    if not active_scenario_summary.empty:
        summary_row = active_scenario_summary.iloc[0]
        active_col1, active_col2, active_col3, active_col4 = st.columns(4)
        with active_col1:
            st.metric("当前方案碳排", f"{float(summary_row['总碳排放(kg CO2)']):.2f} kg CO2")
        with active_col2:
            st.metric("当前方案距离", f"{float(summary_row['总距离(km)']):.2f} km")
        with active_col3:
            st.metric("当前方案车辆数", f"{int(summary_row['车辆数'])} 辆")
        with active_col4:
            st.metric("当前方案枢纽数", f"{int(summary_row['中转枢纽数'])} 个")

    if not active_fleet_df.empty:
        st.markdown("#### 当前方案异构车队构成")
        st.dataframe(active_fleet_df, hide_index=True, width="stretch")

    map_tab, carbon_tab, dispatch_tab, export_tab = st.tabs(["物流网络地图", "碳排放对比", "详细结果", "数据导出"])

    with map_tab:
        map_chart = build_map(nodes, active_route_results, active_depot_results, demands_dict, active_vehicle_name, active_route_context)
        if map_chart is not None:
            st_folium(map_chart, width="100%", height=560)
        else:
            st.info("当前方案没有可展示的路线地图。")

    with carbon_tab:
        render_scenario_triptych(scenario_df)
        compare_col1, compare_col2 = st.columns(2)
        with compare_col1:
            st.plotly_chart(
                build_scenario_emission_figure(scenario_df, title="三方案综合碳排对比"),
                width="stretch",
            )
        with compare_col2:
            st.plotly_chart(
                build_scenario_breakdown_figure(
                    scenario_df,
                    value_columns=("末端距离(km)", "干线距离(km)"),
                    legend_labels=("末端配送", "干线补给"),
                    title="方案距离结构拆解",
                ),
                width="stretch",
            )

        breakdown_col1, breakdown_col2 = st.columns(2)
        with breakdown_col1:
            st.metric(primary_emission_label, f"{terminal_emission:.2f} kg CO2", delta=f"{terminal_distance_km:.2f} km")
        with breakdown_col2:
            st.metric(secondary_emission_label, f"{trunk_emission:.2f} kg CO2", delta=f"{trunk_distance_km:.2f} km")

        if not scenario_df.empty:
            st.dataframe(
                scenario_df[
                    [
                        "方案",
                        "总碳排放(kg CO2)",
                        "减排量(kg CO2)",
                        "减排比例(%)",
                        "总距离(km)",
                        "车辆数",
                        "中转枢纽数",
                        "车队构成",
                    ]
                ],
                hide_index=True,
                width="stretch",
            )

        if not active_route_carbon_df.empty:
            fig_route = px.bar(
                active_route_carbon_df,
                x="车辆编号",
                y="总碳排放(kg CO2)",
                color="总距离(km)",
                title="当前选中方案的单路线碳排放",
                text_auto=True,
            )
            apply_green_chart_theme(fig_route, height=380)
            st.plotly_chart(fig_route, width="stretch")
            st.dataframe(active_route_carbon_df, hide_index=True, width="stretch")

    with dispatch_tab:
        if not active_dispatch_df.empty:
            st.dataframe(active_dispatch_df, hide_index=True, width="stretch")

        if active_route_results:
            for index, route_result in enumerate(active_route_results, start=1):
                vehicle_capacity_ton = get_route_vehicle_capacity_ton(route_result)
                capacity_suffix = f" / {vehicle_capacity_ton:.1f} 吨" if vehicle_capacity_ton > 0 else ""
                vehicle_label = (
                    f"{route_result.get('vehicle_name', f'车辆 {index}')}（"
                    f"{get_route_vehicle_display_name(route_result, active_vehicle_name)}{capacity_suffix}"
                    f"）"
                )
                with st.expander(vehicle_label, expanded=False):
                    st.markdown(f"**路线** {' -> '.join(get_route_path_names(route_result, active_route_context))}")
                    detail_df = build_route_load_dataframe(route_result)
                    if not detail_df.empty:
                        st.dataframe(detail_df, width="stretch", hide_index=True)
                    max_load = float(route_result.get("vehicle_capacity_kg", results.get("vehicle_capacity_kg", 0)) or 0)
                    total_load = float(route_result.get("total_load_kg", 0) or 0)
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("总装载量", f"{total_load:.1f} kg", delta=f"装载率 {total_load / max_load * 100:.1f}%" if max_load > 0 else "--")
                    with col2:
                        st.metric("单车载重上限", f"{vehicle_capacity_ton:.1f} 吨" if vehicle_capacity_ton > 0 else "--")
                    with col3:
                        st.metric("总距离", f"{float(route_result.get('total_distance_km', 0) or 0):.2f} km")
                    with col4:
                        st.metric("总碳排放", f"{float(route_result.get('total_carbon_kg', 0) or 0):.2f} kg CO2")
        else:
            st.info("当前方案没有可展示的路线明细。")

    with export_tab:
        export_col1, export_col2 = st.columns(2)
        with export_col1:
            render_download_button(
                label="导出路线汇总 CSV",
                data=combined_dispatch_df.to_csv(index=False).encode("utf-8-sig"),
                key="results-export-dispatch",
                file_name="路线汇总.csv",
                mime="text/csv",
                width="stretch",
            )
            if not combined_load_export_df.empty:
                render_download_button(
                    label="导出装载明细 CSV",
                    data=combined_load_export_df.to_csv(index=False).encode("utf-8-sig"),
                    key="results-export-load-details",
                    file_name="装载明细.csv",
                    mime="text/csv",
                    width="stretch",
                )
        with export_col2:
            if not depot_df.empty:
                render_download_button(
                    label="导出中转仓结果 CSV",
                    data=depot_df.to_csv(index=False).encode("utf-8-sig"),
                    key="results-export-depots",
                    file_name="中转仓结果.csv",
                    mime="text/csv",
                    width="stretch",
                )
            if not combined_segment_export_df.empty:
                render_download_button(
                    label="导出分段碳排 CSV",
                    data=combined_segment_export_df.to_csv(index=False).encode("utf-8-sig"),
                    key="results-export-segments",
                    file_name="分段碳排.csv",
                    mime="text/csv",
                    width="stretch",
                )

        raw_json = json.dumps(results, ensure_ascii=False, indent=2, default=_json_default)
        render_download_button(
            label="导出完整优化结果 JSON",
            data=raw_json.encode("utf-8"),
            key="results-export-json",
            file_name="优化结果.json",
            mime="application/json",
            width="stretch",
        )

render_page_nav(
    "pages/5_carbon_analysis.py",
    "app.py",
    prev_label="返回上一步",
    next_label="回到首页",
    key_prefix="results-footer-nav",
)
