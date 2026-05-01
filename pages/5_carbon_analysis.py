from __future__ import annotations

import sys
from pathlib import Path

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
    tune_bar_value_labels,
)
from pages._route_analysis_shared import (
    build_fleet_summary_dataframe,
    build_route_dispatch_dataframe,
    build_route_map,
    build_route_overview_dataframe,
    build_route_segment_rows,
)
from pages._ui_shared import (
    anchor,
    inject_base_style,
    inject_sidebar_navigation_label,
    render_sidebar_navigation,
    render_title,
    render_top_nav,
)
from utils.comparison_scenarios import get_comparison_scenarios
from utils.route_display import build_route_context
from utils.vehicle_lib import VEHICLE_LIB

POWER_TYPE_MAPPING = {
    "diesel": "柴油重卡",
    "lng": "LNG天然气重卡",
    "hev": "混合动力 (HEV)",
    "phev": "插电混动 (PHEV)",
    "bev": "纯电动 (BEV)",
    "fcev": "氢燃料电池 (FCEV)",
    "mixed": "混合车队",
}

RATING_COLOR_MAP = {
    "优": "#80B332",
    "中": "#D8B452",
    "高": "#D94841",
}


def normalize_vehicle_type_id(raw_value: object) -> str:
    value = str(raw_value or "").strip().lower()
    if not value:
        return "unknown"
    value = value.split("_")[0] if value not in {"diesel"} else value
    alias_map = {
        "柴油重卡": "diesel",
        "lng天然气重卡": "lng",
        "混合动力": "hev",
        "混合动力 (hev)": "hev",
        "插电混动": "phev",
        "插电混动 (phev)": "phev",
        "纯电动": "bev",
        "纯电动 (bev)": "bev",
        "氢燃料电池": "fcev",
        "氢燃料电池 (fcev)": "fcev",
        "混合车队": "mixed",
    }
    return alias_map.get(value, value)


def get_vehicle_display_name(vehicle_type_id: str, fallback: str = "未知") -> str:
    normalized = normalize_vehicle_type_id(vehicle_type_id)
    return POWER_TYPE_MAPPING.get(normalized, fallback if fallback else normalized)


def get_scenario_record(comparison_scenarios: list[dict], scenario_id: str) -> dict:
    for scenario in comparison_scenarios:
        if str(scenario.get("id") or "").strip() == scenario_id:
            return scenario
    return {}


def build_vehicle_factor_dataframe() -> pd.DataFrame:
    rows = []
    for vehicle_type_id, info in VEHICLE_LIB.items():
        loaded_factor = float(info.get("intensity_g_per_tkm", 60) or 0) / 1000.0
        if loaded_factor < 0.04:
            rating = "优"
        elif loaded_factor < 0.06:
            rating = "中"
        else:
            rating = "高"
        rows.append(
            {
                "车型": get_vehicle_display_name(vehicle_type_id, vehicle_type_id),
                "主碳因子(kg/tkm)": round(loaded_factor, 3),
                "空驶因子(kg/km)": round(float(info.get("empty_g_per_km", 0) or 0) / 1000.0, 4),
                "冷启动(kg)": round(float(info.get("cold_start_g", 0) or 0) / 1000.0, 3),
                "等级": rating,
            }
        )
    return pd.DataFrame(rows)


def build_simulation_dataframe(total_distance_km: float, total_demand_kg: float) -> pd.DataFrame:
    baseline_factor = float(VEHICLE_LIB.get("diesel", {}).get("intensity_g_per_tkm", 60) or 60) / 1000.0
    baseline_emission = (total_demand_kg / 1000.0) * total_distance_km * baseline_factor

    rows = []
    for vehicle_type_id, info in VEHICLE_LIB.items():
        factor = float(info.get("intensity_g_per_tkm", 60) or 60) / 1000.0
        simulated_emission = (total_demand_kg / 1000.0) * total_distance_km * factor
        reduction = baseline_emission - simulated_emission
        reduction_pct = (reduction / baseline_emission * 100) if baseline_emission > 0 else 0.0
        rows.append(
            {
                "车型": get_vehicle_display_name(vehicle_type_id, vehicle_type_id),
                "模拟碳排放(kg CO2)": round(simulated_emission, 2),
                "基线碳排放(kg CO2)": round(baseline_emission, 2),
                "减排量(kg CO2)": round(reduction, 2),
                "减排比例(%)": round(reduction_pct, 1),
            }
        )
    return pd.DataFrame(rows)


def build_sensitivity_dataframe(total_distance_km: float, total_demand_kg: float) -> pd.DataFrame:
    rows = []
    for multiplier in [0.5, 0.75, 1.0, 1.25, 1.5]:
        for vehicle_type_id, info in VEHICLE_LIB.items():
            factor = float(info.get("intensity_g_per_tkm", 60) or 60) / 1000.0
            distance = total_distance_km * multiplier
            emission = distance * factor * (total_demand_kg / 1000.0)
            rows.append(
                {
                    "距离系数": f"{multiplier}x",
                    "距离(km)": round(distance, 1),
                    "车型": get_vehicle_display_name(vehicle_type_id, vehicle_type_id),
                    "碳排放(kg CO2)": round(emission, 2),
                }
            )
    return pd.DataFrame(rows)


def build_reduction_driver_dataframe(comparison_scenarios: list[dict]) -> pd.DataFrame:
    baseline_scenario = get_scenario_record(comparison_scenarios, "baseline_direct")
    diesel_same_scenario = get_scenario_record(comparison_scenarios, "diesel_same_routes")
    optimized_scenario = get_scenario_record(comparison_scenarios, "optimized_current")

    baseline_emission = float(baseline_scenario.get("total_emission", 0) or 0)
    diesel_same_emission = float(diesel_same_scenario.get("total_emission", 0) or 0)
    optimized_emission = float(optimized_scenario.get("total_emission", 0) or 0)
    total_reduction = max(baseline_emission - optimized_emission, 0.0)

    route_reduction = 0.0
    power_reduction = 0.0
    if baseline_scenario and diesel_same_scenario:
        route_reduction = max(baseline_emission - diesel_same_emission, 0.0)
        power_reduction = max(diesel_same_emission - optimized_emission, 0.0)
    elif baseline_scenario and optimized_scenario:
        route_reduction = total_reduction

    return pd.DataFrame(
        [
            {
                "驱动因素": "路线组织优化",
                "减排量(kg CO2)": round(route_reduction, 2),
                "贡献占比(%)": round(route_reduction / total_reduction * 100, 1) if total_reduction > 0 else 0.0,
                "分析说明": "通过中转仓布局、路径合并与绕行压缩降低运输活动量。",
            },
            {
                "驱动因素": "车型能源替代",
                "减排量(kg CO2)": round(power_reduction, 2),
                "贡献占比(%)": round(power_reduction / total_reduction * 100, 1) if total_reduction > 0 else 0.0,
                "分析说明": "在同等路线结构下，通过低碳车型降低单位运输排放。",
            },
        ]
    )


def build_scenario_efficiency_dataframe(comparison_scenarios: list[dict]) -> pd.DataFrame:
    rows = []
    for scenario in comparison_scenarios:
        total_emission = float(scenario.get("total_emission", 0) or 0)
        total_distance = float(scenario.get("total_distance_km", 0) or 0)
        num_vehicles = int(scenario.get("num_vehicles_used", 0) or 0)
        trunk_emission = float(scenario.get("trunk_emission", 0) or 0)
        rows.append(
            {
                "方案ID": str(scenario.get("id") or ""),
                "方案": str(scenario.get("label") or scenario.get("id") or "未命名方案"),
                "碳排效率(kg/km)": round(total_emission / total_distance, 4) if total_distance > 0 else 0.0,
                "单车平均碳排(kg/车)": round(total_emission / num_vehicles, 2) if num_vehicles > 0 else 0.0,
                "干线碳排占比(%)": round(trunk_emission / total_emission * 100, 1) if total_emission > 0 else 0.0,
                "车队构成": str(scenario.get("fleet_mix_text") or ""),
            }
        )
    return pd.DataFrame(rows)


def attach_route_capacity_column(df: pd.DataFrame, route_results: list[dict]) -> pd.DataFrame:
    if df.empty:
        return df

    enriched = df.copy()
    capacities = []
    for route_result in route_results[: len(enriched)]:
        try:
            capacity_ton = round(float(route_result.get("vehicle_capacity_kg", 0) or 0) / 1000.0, 2)
        except (TypeError, ValueError):
            capacity_ton = 0.0
        capacities.append(capacity_ton if capacity_ton > 0 else None)

    while len(capacities) < len(enriched):
        capacities.append(None)

    enriched["单车载重上限(吨/辆)"] = capacities
    return enriched


def build_analysis_insights(
    driver_df: pd.DataFrame,
    efficiency_df: pd.DataFrame,
    baseline_emission: float,
    actual_total_emission: float,
) -> list[str]:
    insights: list[str] = []
    if not driver_df.empty:
        primary_driver = driver_df.sort_values("减排量(kg CO2)", ascending=False).iloc[0]
        insights.append(f"当前减排主要来自{primary_driver['驱动因素']}，贡献约 {float(primary_driver['贡献占比(%)']):.1f}% 。")

    if baseline_emission > 0:
        total_drop_pct = max(baseline_emission - actual_total_emission, 0.0) / baseline_emission * 100
        insights.append(f"优化方案相较基线方案的总碳排下降约 {total_drop_pct:.1f}% 。")

    baseline_eff_row = efficiency_df[efficiency_df["方案ID"] == "baseline_direct"]
    optimized_eff_row = efficiency_df[efficiency_df["方案ID"] == "optimized_current"]
    if not baseline_eff_row.empty and not optimized_eff_row.empty:
        baseline_eff = float(baseline_eff_row.iloc[0]["碳排效率(kg/km)"] or 0)
        optimized_eff = float(optimized_eff_row.iloc[0]["碳排效率(kg/km)"] or 0)
        if baseline_eff > 0:
            intensity_drop_pct = max(baseline_eff - optimized_eff, 0.0) / baseline_eff * 100
            insights.append(f"优化方案的单位里程碳排较基线下降约 {intensity_drop_pct:.1f}% 。")

    optimized_trunk_row = efficiency_df[efficiency_df["方案ID"] == "optimized_current"]
    if not optimized_trunk_row.empty:
        trunk_share = float(optimized_trunk_row.iloc[0]["干线碳排占比(%)"] or 0)
        insights.append(f"当前优化方案中，干线补给碳排占总碳排约 {trunk_share:.1f}% 。")

    return insights


st.set_page_config(page_title="碳排放分析", page_icon="🌿", layout="wide", initial_sidebar_state="expanded")
inject_sidebar_navigation_label()
inject_base_style()
inject_green_dashboard_style("carbon-analysis")
render_sidebar_navigation("pages/5_carbon_analysis.py")
render_top_nav(
    tabs=[
        ("分析摘要", "sec-summary"),
        ("方案对比", "sec-analysis"),
        ("路线展示", "sec-routes"),
        ("车型模拟", "sec-simulation"),
        ("敏感性分析", "sec-sensitivity"),
    ],
    active_idx=0,
)
render_title("碳排放分析", "在保持现有风格的前提下，集中展示三方案对比、可切换路线与专业分析结果。")

results = st.session_state.get("optimization_results") or st.session_state.get("results")

if not results or not isinstance(results, dict):
    anchor("sec-summary")
    st.warning("尚未执行路径优化，请先完成“路径优化”页面的计算。")
    render_page_nav("pages/7_path_optimization.py", "pages/8_results.py", key_prefix="carbon-analysis-nav")
    st.stop()

route_results = results.get("route_results", []) or []
if not route_results:
    anchor("sec-summary")
    st.warning("当前没有可展示的路线结果。")
    render_page_nav("pages/7_path_optimization.py", "pages/8_results.py", key_prefix="carbon-analysis-nav")
    st.stop()

nodes = results.get("nodes", []) or []
demands_dict = results.get("demands", {}) or {}
actual_total_distance = float(results.get("total_distance_km", 0) or 0)
actual_total_emission = float(results.get("total_emission", 0) or 0)
baseline_emission = float(results.get("baseline_emission", 0) or 0)
reduction_pct = float(results.get("reduction_percent", 0) or 0)
total_demand_kg = sum(float(route.get("total_load_kg", 0) or 0) for route in route_results)

comparison_scenarios = get_comparison_scenarios(results)
scenario_df = build_scenario_summary_dataframe(comparison_scenarios)
vehicle_factor_df = build_vehicle_factor_dataframe()
simulation_df = build_simulation_dataframe(actual_total_distance, total_demand_kg)
sensitivity_df = build_sensitivity_dataframe(actual_total_distance, total_demand_kg)
driver_df = build_reduction_driver_dataframe(comparison_scenarios)
efficiency_df = build_scenario_efficiency_dataframe(comparison_scenarios)
insights = build_analysis_insights(driver_df, efficiency_df, baseline_emission, actual_total_emission)
configured_fleet_df = build_fleet_summary_dataframe(
    list(results.get("configured_fleet_by_type_capacity", []) or []),
    count_label="配置数量(辆)",
)
used_fleet_df = build_fleet_summary_dataframe(
    list(results.get("fleet_used_by_type_capacity", []) or []),
    count_label="实际用车(辆)",
)

primary_driver = driver_df.sort_values("减排量(kg CO2)", ascending=False).iloc[0].to_dict() if not driver_df.empty else None

default_scenario_id = "optimized_current" if get_scenario_record(comparison_scenarios, "optimized_current") else str(comparison_scenarios[0].get("id") or "")
scenario_options = {str(scenario.get("id") or ""): str(scenario.get("label") or scenario.get("id") or "未命名方案") for scenario in comparison_scenarios}
selected_scenario_id = st.session_state.get("carbon_analysis_selected_scenario_id") or default_scenario_id
if selected_scenario_id not in scenario_options:
    selected_scenario_id = default_scenario_id
st.session_state["carbon_analysis_selected_scenario_id"] = selected_scenario_id

active_scenario = get_scenario_record(comparison_scenarios, selected_scenario_id) or comparison_scenarios[0]
active_route_results = list(active_scenario.get("route_results", []) or [])
active_depot_results = list(active_scenario.get("depot_results", []) or [])
active_route_context = build_route_context(nodes, active_depot_results)
active_route_df = attach_route_capacity_column(
    build_route_overview_dataframe(active_route_results, active_route_context),
    active_route_results,
)
active_dispatch_df = attach_route_capacity_column(
    build_route_dispatch_dataframe(active_route_results, active_route_context),
    active_route_results,
)
active_fleet_df = build_fleet_summary_dataframe(
    list(active_scenario.get("fleet_used_by_type_capacity", []) or []),
    count_label="实际用车(辆)",
)
active_summary_df = scenario_df[scenario_df["方案ID"] == str(active_scenario.get("id") or "")]
active_summary_row = active_summary_df.iloc[0].to_dict() if not active_summary_df.empty else {}

anchor("sec-summary")
with st.container(key="carbon-analysis-card-summary"):
    st.markdown("#### 分析结论")
    summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
    with summary_col1:
        st.metric("基线碳排放", f"{baseline_emission:.2f} kg CO2")
    with summary_col2:
        st.metric("当前优化碳排", f"{actual_total_emission:.2f} kg CO2")
    with summary_col3:
        st.metric("总减排量", f"{max(baseline_emission - actual_total_emission, 0):.2f} kg CO2", delta=f"-{reduction_pct:.1f}%")
    with summary_col4:
        if primary_driver:
            st.metric("核心减排驱动", str(primary_driver["驱动因素"]), delta=f"贡献 {float(primary_driver['贡献占比(%)']):.1f}%")
        else:
            st.metric("核心减排驱动", "--")

    render_scenario_triptych(scenario_df)

    fleet_col1, fleet_col2 = st.columns(2)
    with fleet_col1:
        st.markdown("#### 车队配置")
        if not configured_fleet_df.empty:
            st.dataframe(configured_fleet_df, hide_index=True, width="stretch")
        else:
            st.info("当前结果未记录车队配置摘要。")
    with fleet_col2:
        st.markdown("#### 实际用车")
        if not used_fleet_df.empty:
            st.dataframe(used_fleet_df, hide_index=True, width="stretch")
        else:
            st.info("当前结果未记录实际用车摘要。")

    insight_col1, insight_col2 = st.columns([1.02, 0.98], gap="large", vertical_alignment="center")
    with insight_col1:
        fig_driver = px.bar(
            driver_df.sort_values("减排量(kg CO2)", ascending=True),
            x="减排量(kg CO2)",
            y="驱动因素",
            orientation="h",
            text_auto=".2f",
            color_discrete_sequence=["#2F6BFF"],
            title="优化方案减排驱动拆解",
        )
        apply_green_chart_theme(fig_driver, height=380, showlegend=False, right_margin=48)
        tune_bar_value_labels(fig_driver, orientation="h", headroom_ratio=0.12)
        st.plotly_chart(fig_driver, width="stretch")
    with insight_col2:
        with st.container(key="carbon-analysis-panel-insights"):
            st.subheader("专业判断")
            for insight in insights:
                st.markdown(f"- {insight}")
            if not efficiency_df.empty:
                st.dataframe(
                    efficiency_df[["方案", "碳排效率(kg/km)", "单车平均碳排(kg/车)", "干线碳排占比(%)", "车队构成"]],
                    hide_index=True,
                    width="stretch",
                )

anchor("sec-analysis")
with st.container(key="carbon-analysis-card-compare"):
    st.subheader("三方案对比")
    compare_col1, compare_col2 = st.columns(2, gap="large", vertical_alignment="center")
    with compare_col1:
        st.plotly_chart(
            build_scenario_emission_figure(scenario_df, title="三方案综合碳排对比"),
            width="stretch",
        )
    with compare_col2:
        fig_breakdown = build_scenario_breakdown_figure(
            scenario_df,
            value_columns=("末端碳排(kg CO2)", "干线碳排(kg CO2)"),
            legend_labels=("末端配送", "干线补给"),
            title="方案碳排结构拆解",
        )
        apply_green_chart_theme(
            fig_breakdown,
            height=410,
            showlegend=True,
            legend_x=0.5,
            legend_y=-0.2,
            legend_xanchor="center",
            legend_yanchor="top",
            bottom_margin=72,
        )
        st.plotly_chart(fig_breakdown, width="stretch")

    efficiency_col1, efficiency_col2 = st.columns([0.95, 1.05], gap="large", vertical_alignment="center")
    with efficiency_col1:
        fig_efficiency = px.bar(
            efficiency_df,
            x="方案",
            y="碳排效率(kg/km)",
            text_auto=".4f",
            color_discrete_sequence=["#80B332"],
            title="三方案单位里程碳排对比",
        )
        fig_efficiency.update_xaxes(tickangle=-10)
        apply_green_chart_theme(fig_efficiency, height=380, showlegend=False, top_margin=76, bottom_margin=46)
        tune_bar_value_labels(fig_efficiency, orientation="v", headroom_ratio=0.22)
        st.plotly_chart(fig_efficiency, width="stretch")
    with efficiency_col2:
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

anchor("sec-routes")
with st.container(key="carbon-analysis-card-routes"):
    st.subheader("三方案路线展示")
    st.selectbox(
        "选择路线展示方案",
        options=list(scenario_options.keys()),
        format_func=lambda scenario_id: scenario_options.get(scenario_id, scenario_id),
        key="carbon_analysis_selected_scenario_id",
    )

    active_scenario = get_scenario_record(comparison_scenarios, st.session_state.get("carbon_analysis_selected_scenario_id") or default_scenario_id) or comparison_scenarios[0]
    active_route_results = list(active_scenario.get("route_results", []) or [])
    active_depot_results = list(active_scenario.get("depot_results", []) or [])
    active_route_context = build_route_context(nodes, active_depot_results)
    active_route_df = attach_route_capacity_column(
        build_route_overview_dataframe(active_route_results, active_route_context),
        active_route_results,
    )
    active_dispatch_df = attach_route_capacity_column(
        build_route_dispatch_dataframe(active_route_results, active_route_context),
        active_route_results,
    )
    active_fleet_df = build_fleet_summary_dataframe(
        list(active_scenario.get("fleet_used_by_type_capacity", []) or []),
        count_label="实际用车(辆)",
    )
    active_summary_df = scenario_df[scenario_df["方案ID"] == str(active_scenario.get("id") or "")]
    active_summary_row = active_summary_df.iloc[0].to_dict() if not active_summary_df.empty else {}

    st.caption(str(active_scenario.get("description") or ""))

    route_metric_col1, route_metric_col2, route_metric_col3, route_metric_col4 = st.columns(4)
    with route_metric_col1:
        st.metric("当前方案碳排", f"{float(active_summary_row.get('总碳排放(kg CO2)', 0) or 0):.2f} kg CO2")
    with route_metric_col2:
        st.metric("当前方案距离", f"{float(active_summary_row.get('总距离(km)', 0) or 0):.2f} km")
    with route_metric_col3:
        st.metric("当前方案车辆数", f"{int(active_summary_row.get('车辆数', 0) or 0)} 辆")
    with route_metric_col4:
        st.metric("当前方案枢纽数", f"{int(active_summary_row.get('中转枢纽数', 0) or 0)} 个")

    if not active_fleet_df.empty:
        st.markdown("#### 当前方案异构车队构成")
        st.dataframe(active_fleet_df, hide_index=True, width="stretch")

    route_tab_map, route_tab_summary, route_tab_segments = st.tabs(["地图展示", "路线汇总", "分段明细"])

    with route_tab_map:
        route_map = build_route_map(nodes, active_route_results, active_depot_results, demands_dict, active_route_context)
        if route_map is not None:
            st_folium(route_map, width="100%", height=560)
        else:
            st.info("当前方案没有可展示的路线地图。")

    with route_tab_summary:
        summary_view_col1, summary_view_col2 = st.columns([1.0, 1.0], gap="large", vertical_alignment="center")
        with summary_view_col1:
            if not active_route_df.empty:
                fig_route = px.bar(
                    active_route_df.sort_values("总碳排放(kg CO2)", ascending=False),
                    x="路线编号",
                    y="总碳排放(kg CO2)",
                    text_auto=".2f",
                    color_discrete_sequence=["#2F6BFF"],
                    title="当前方案单路线碳排放",
                )
                fig_route.update_xaxes(tickangle=-12)
                apply_green_chart_theme(fig_route, height=380, showlegend=False, top_margin=76, bottom_margin=48)
                tune_bar_value_labels(fig_route, orientation="v", headroom_ratio=0.24)
                st.plotly_chart(fig_route, width="stretch")
        with summary_view_col2:
            if not active_dispatch_df.empty:
                st.dataframe(
                    active_dispatch_df[
                        ["路线编号", "车辆", "车型", "单车载重上限(吨/辆)", "场馆数", "总装载(kg)", "总距离(km)", "总碳排放(kg CO2)"]
                    ],
                    hide_index=True,
                    width="stretch",
                )
            else:
                st.info("当前方案暂无可展示的路线汇总。")

    with route_tab_segments:
        if active_route_results:
            for idx, route_result in enumerate(active_route_results, start=1):
                route_row = active_route_df.iloc[idx - 1].to_dict() if idx - 1 < len(active_route_df) else {}
                segment_rows = build_route_segment_rows(route_result, active_route_context)
                with st.expander(f"{route_row.get('路线编号', f'路线{idx}')}：{route_row.get('车辆', route_result.get('vehicle_name', f'车辆{idx}'))}", expanded=False):
                    st.markdown(f"**路线** {route_row.get('路线', '--')}")
                    seg_metric_col1, seg_metric_col2, seg_metric_col3, seg_metric_col4, seg_metric_col5 = st.columns(5)
                    with seg_metric_col1:
                        st.metric("总装载量", f"{float(route_result.get('total_load_kg', 0) or 0):.1f} kg")
                    with seg_metric_col2:
                        capacity_ton = float(route_row.get('单车载重上限(吨/辆)', 0) or 0)
                        st.metric("单车载重上限", f"{capacity_ton:.1f} 吨" if capacity_ton > 0 else "--")
                    with seg_metric_col3:
                        st.metric("总距离", f"{float(route_result.get('total_distance_km', 0) or 0):.2f} km")
                    with seg_metric_col4:
                        st.metric("总碳排放", f"{float(route_result.get('total_carbon_kg', 0) or 0):.2f} kg CO2")
                    with seg_metric_col5:
                        st.metric("碳排效率", f"{float(route_row.get('碳排效率(kg/km)', 0) or 0):.4f} kg/km")

                    if segment_rows:
                        segment_df = pd.DataFrame(segment_rows)
                        seg_col1 = st.container()
                        seg_col2 = st.container()
                        with seg_col1:
                            fig_segment = px.bar(
                                segment_df,
                                x="序号",
                                y="碳排放(kg CO2)",
                                text_auto=".3f",
                                color_discrete_sequence=["#80B332"],
                                title="分段碳排分布",
                            )
                            fig_segment.update_traces(
                                customdata=segment_df[["分段", "距离(km)", "装载(吨)"]].values,
                                hovertemplate=(
                                    "<b>分段 %{x}</b><br>"
                                    "路径：%{customdata[0]}<br>"
                                    "距离：%{customdata[1]:.2f} km<br>"
                                    "装载：%{customdata[2]:.3f} 吨<br>"
                                    "碳排放：%{y:.4f} kg CO2<extra></extra>"
                                ),
                            )
                            fig_segment.update_xaxes(title="分段序号", tickmode="linear", dtick=1, tickfont={"size": 11})
                            apply_green_chart_theme(fig_segment, height=420, showlegend=False, top_margin=76, bottom_margin=72)
                            tune_bar_value_labels(fig_segment, orientation="v", headroom_ratio=0.24)
                            st.plotly_chart(fig_segment, width="stretch")
                        with seg_col2:
                            st.dataframe(segment_df, hide_index=True, width="stretch")
                            st.caption("柱状图横坐标使用分段序号，完整路径名称可在下表或悬停提示中查看。")
                    else:
                        st.info("该路线暂无可展示的分段测算结果。")
        else:
            st.info("当前方案暂无可展示的分段明细。")

anchor("sec-simulation")
with st.container(key="carbon-analysis-card-simulation"):
    st.subheader("车型模拟")
    sim_col1, sim_col2 = st.columns(2, gap="large", vertical_alignment="center")
    with sim_col1:
        fig_factor = px.bar(
            vehicle_factor_df,
            x="车型",
            y="主碳因子(kg/tkm)",
            color="等级",
            text_auto=".2f",
            color_discrete_map=RATING_COLOR_MAP,
            title="各车型主碳因子对比（越低越好）",
        )
        fig_factor.update_xaxes(tickangle=-10)
        apply_green_chart_theme(
            fig_factor,
            height=410,
            showlegend=True,
            legend_x=0.5,
            legend_y=-0.24,
            legend_xanchor="center",
            legend_yanchor="top",
            top_margin=76,
            bottom_margin=76,
        )
        tune_bar_value_labels(fig_factor, orientation="v", headroom_ratio=0.22)
        st.plotly_chart(fig_factor, width="stretch")
    with sim_col2:
        fig_sim = px.bar(
            simulation_df,
            x="车型",
            y="模拟碳排放(kg CO2)",
            text_auto=".1f",
            color_discrete_sequence=["#2F6BFF"],
            title="不同车型的模拟碳排放",
        )
        fig_sim.update_xaxes(tickangle=-10)
        apply_green_chart_theme(fig_sim, height=410, showlegend=False, top_margin=76, bottom_margin=52)
        tune_bar_value_labels(fig_sim, orientation="v", headroom_ratio=0.22)
        st.plotly_chart(fig_sim, width="stretch")

    best_simulated = simulation_df.loc[simulation_df["模拟碳排放(kg CO2)"].idxmin()] if not simulation_df.empty else None
    worst_simulated = simulation_df.loc[simulation_df["模拟碳排放(kg CO2)"].idxmax()] if not simulation_df.empty else None
    if best_simulated is not None and worst_simulated is not None:
        compare_left, compare_right = st.columns(2)
        with compare_left:
            st.success(
                f"最优模拟车型：{best_simulated['车型']}\n模拟碳排放：{best_simulated['模拟碳排放(kg CO2)']:.2f} kg CO2\n减排比例：{best_simulated['减排比例(%)']:.1f}%"
            )
        with compare_right:
            st.error(
                f"最高排放车型：{worst_simulated['车型']}\n模拟碳排放：{worst_simulated['模拟碳排放(kg CO2)']:.2f} kg CO2\n减排比例：{worst_simulated['减排比例(%)']:.1f}%"
            )

    st.dataframe(
        vehicle_factor_df[["车型", "主碳因子(kg/tkm)", "空驶因子(kg/km)", "冷启动(kg)", "等级"]],
        hide_index=True,
        width="stretch",
    )

anchor("sec-sensitivity")
with st.container(key="carbon-analysis-card-sensitivity"):
    st.subheader("敏感性分析")
    fig_sensitivity = px.line(
        sensitivity_df,
        x="距离(km)",
        y="碳排放(kg CO2)",
        color="车型",
        title="距离变化下的碳排放敏感性",
        markers=True,
    )
    apply_green_chart_theme(
        fig_sensitivity,
        height=400,
        showlegend=True,
        legend_x=0.5,
        legend_y=-0.24,
        legend_xanchor="center",
        legend_yanchor="top",
        bottom_margin=80,
    )
    st.plotly_chart(fig_sensitivity, width="stretch")

    sensitivity_col1, sensitivity_col2, sensitivity_col3 = st.columns(3)
    with sensitivity_col1:
        st.metric("分析基准距离", f"{actual_total_distance:.2f} km")
    with sensitivity_col2:
        st.metric("分析总需求", f"{total_demand_kg / 1000.0:.2f} 吨")
    with sensitivity_col3:
        st.metric("当前减排比例", f"{reduction_pct:.1f}%")

    reference_df = sensitivity_df[sensitivity_df["距离系数"].isin(["1.0x", "1.5x"])]
    st.dataframe(reference_df, hide_index=True, width="stretch")

st.caption(f"数据来源：路径优化结果 | 计算时间：{results.get('timestamp', '未知')}")
render_page_nav("pages/7_path_optimization.py", "pages/8_results.py", key_prefix="carbon-analysis-nav")
