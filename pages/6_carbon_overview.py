"""碳排放概览页面。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from pages._bottom_nav import render_page_nav
from pages._ui_shared import (
    anchor,
    inject_base_style,
    inject_sidebar_navigation_label,
    render_title,
    render_sidebar_navigation,
    render_top_nav,
)


POWER_TYPE_MAPPING = {
    "diesel": "柴油重卡",
    "diesel": "柴油重卡",
    "lng": "LNG天然气重卡",
    "hev": "混合动力 (HEV)",
    "phev": "插电混动 (PHEV)",
    "bev": "纯电动 (BEV)",
    "fcev": "氢燃料电池 (FCEV)",
    "mixed": "混合车队",
}


def get_vehicle_type_id(route_result: dict) -> str:
    vehicle_type_id = str(route_result.get("vehicle_type_id", "") or "").strip()
    if vehicle_type_id:
        return vehicle_type_id

    raw_type = str(route_result.get("vehicle_type", "") or "").strip().lower()
    reverse_map = {
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
    return reverse_map.get(raw_type, raw_type or "unknown")


def get_vehicle_display_name(vehicle_type_id: str, fallback: str = "未知") -> str:
    return POWER_TYPE_MAPPING.get(vehicle_type_id, fallback if fallback else vehicle_type_id)


def build_fleet_dispatch_dataframe(
    route_results: list[dict],
    result_data: dict,
    vehicles: list[dict],
) -> pd.DataFrame:
    used_counts: dict[str, int] = {}
    max_counts: dict[str, int] = {}

    for route_result in route_results:
        vehicle_type_id = get_vehicle_type_id(route_result)
        used_counts[vehicle_type_id] = used_counts.get(vehicle_type_id, 0) + 1

    for vehicle_type_id, count in (result_data.get("fleet_used_by_type", {}) or {}).items():
        used_counts[str(vehicle_type_id)] = max(used_counts.get(str(vehicle_type_id), 0), int(count or 0))

    for vehicle_type_id, count in (result_data.get("fleet_max_by_type", {}) or {}).items():
        max_counts[str(vehicle_type_id)] = int(count or 0)

    for vehicle in vehicles:
        vehicle_type_id = str(vehicle.get("vehicle_type", "") or "").strip()
        if not vehicle_type_id:
            continue
        max_counts[vehicle_type_id] = max_counts.get(vehicle_type_id, 0) + int(
            vehicle.get("count_max", vehicle.get("count", 0)) or 0
        )

    all_types = sorted(set(max_counts) | set(used_counts))
    rows = []
    for vehicle_type_id in all_types:
        used = int(used_counts.get(vehicle_type_id, 0) or 0)
        cap = int(max_counts.get(vehicle_type_id, 0) or 0)
        rows.append(
            {
                "动力类型": get_vehicle_display_name(vehicle_type_id, vehicle_type_id),
                "实际派车数": used,
                "可用上限": cap,
                "闲置车辆数": max(cap - used, 0),
            }
        )
    return pd.DataFrame(rows)


def build_vehicle_dataframe(route_results: list[dict]) -> pd.DataFrame:
    rows = []
    for index, route_result in enumerate(route_results, start=1):
        vehicle_type_id = get_vehicle_type_id(route_result)
        vehicle_type_name = route_result.get("vehicle_type") or get_vehicle_display_name(
            vehicle_type_id, vehicle_type_id
        )
        distance_km = float(route_result.get("total_distance_km", 0) or 0)
        load_kg = float(route_result.get("total_load_kg", 0) or 0)
        carbon_kg = float(route_result.get("total_carbon_kg", 0) or 0)
        rows.append(
            {
                "车辆": route_result.get("vehicle_name", f"车辆{index}"),
                "车型": vehicle_type_name,
                "距离(km)": round(distance_km, 2),
                "装载量(kg)": round(load_kg, 2),
                "碳排放(kg CO₂)": round(carbon_kg, 2),
                "访问场馆数": len(route_result.get("visits", [])),
                "碳效率(g CO₂/km)": round(carbon_kg * 1000 / distance_km, 2) if distance_km > 0 else 0.0,
                "碳效率(g CO₂/kg货物)": round(carbon_kg * 1000 / load_kg, 2) if load_kg > 0 else 0.0,
            }
        )
    return pd.DataFrame(rows)


st.set_page_config(page_title="碳排放概览", page_icon="📳", layout="wide", initial_sidebar_state="expanded")
inject_sidebar_navigation_label()
inject_base_style()
render_sidebar_navigation()

result = st.session_state.get("optimization_results") or st.session_state.get("results")
vehicles = st.session_state.get("vehicles", [])
has_result = bool(result and isinstance(result, dict) and result.get("route_results"))

render_top_nav(
    tabs=(
        [
            ("结果概览", "sec-summary"),
            ("对比分析", "sec-analysis"),
            ("车辆详情", "sec-detail"),
            ("优化建议", "sec-advice"),
        ]
        if has_result
        else [("结果提示", "sec-summary")]
    ),
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
    .st-key-carbon-overview-summary-card,
    .st-key-carbon-overview-analysis-card,
    .st-key-carbon-overview-vehicle-card,
    .st-key-carbon-overview-detail-card,
    .st-key-carbon-overview-advice-card,
    .st-key-carbon-overview-empty-card {
        background: linear-gradient(135deg, rgba(223, 239, 188, 0.94) 0%, rgba(214, 234, 174, 0.92) 100%);
        border: 1px solid #d0e2b4;
        border-radius: 28px;
        padding: 1.55rem 1.7rem 1.65rem;
        box-shadow: 0 8px 24px rgba(123, 145, 91, 0.22);
        margin-top: 1.25rem;
        overflow: hidden;
    }
    .st-key-carbon-overview-summary-card > div,
    .st-key-carbon-overview-analysis-card > div,
    .st-key-carbon-overview-vehicle-card > div,
    .st-key-carbon-overview-detail-card > div,
    .st-key-carbon-overview-advice-card > div,
    .st-key-carbon-overview-empty-card > div {
        gap: 0.95rem;
    }
    .st-key-carbon-overview-summary-card h3,
    .st-key-carbon-overview-analysis-card h3,
    .st-key-carbon-overview-vehicle-card h3,
    .st-key-carbon-overview-detail-card h3,
    .st-key-carbon-overview-advice-card h3 {
        font-size: 1.95rem;
        font-weight: 700;
        color: #111111;
        margin-bottom: 0.15rem;
    }
    [data-testid="stHorizontalBlock"] {
        gap: 1rem;
    }
    [data-testid="stCaptionContainer"] {
        font-size: 1rem;
        color: #1c1c1c;
    }
    div[data-testid="stAlert"] {
        border-radius: 18px !important;
        border: 0 !important;
    }
    div[data-testid="stDataFrame"] {
        background: rgba(255, 255, 255, 0.95) !important;
        border-radius: 18px !important;
        overflow: hidden !important;
    }
    div[data-testid="stPlotlyChart"] {
        background: transparent !important;
        border-radius: 18px !important;
        overflow: hidden;
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
        .st-key-carbon-overview-summary-card,
        .st-key-carbon-overview-analysis-card,
        .st-key-carbon-overview-vehicle-card,
        .st-key-carbon-overview-detail-card,
        .st-key-carbon-overview-advice-card,
        .st-key-carbon-overview-empty-card {
            padding: 1.2rem 1rem 1.35rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

render_title("碳排放概览", "物流碳排放总览与分析")

if not result or not isinstance(result, dict):
    anchor("sec-summary")
    with st.container(key="carbon-overview-empty-card"):
        st.warning("尚未执行路径优化，请先完成上一步计算。")
        st.info("当前页面已切换为基于优化结果的碳排放概览，生成路径结果后会展示核心指标、对比分析、车辆详情和优化建议。")
    render_page_nav("pages/7_path_optimization.py", "pages/5_carbon_analysis.py", key_prefix="carbon-overview-nav")
    st.stop()
    raise SystemExit

route_results = result.get("route_results", []) or []
if not route_results:
    anchor("sec-summary")
    with st.container(key="carbon-overview-empty-card"):
        st.warning("当前没有可用的路线数据。")
        st.info("请返回路径优化页面重新执行计算，然后再查看本页。")
    render_page_nav("pages/7_path_optimization.py", "pages/5_carbon_analysis.py", key_prefix="carbon-overview-nav")
    st.stop()
    raise SystemExit

total_emission = float(result.get("total_emission", 0) or 0)
baseline_emission = float(result.get("baseline_emission", 0) or 0)
reduction_pct = float(result.get("reduction_percent", 0) or 0)
total_distance = float(result.get("total_distance_km", 0) or 0)
num_vehicles = int(result.get("num_vehicles_used", len(route_results)) or len(route_results))
carbon_reduction = baseline_emission - total_emission

try:
    from utils.carbon_calc import carbon_equivalents, generate_optimization_suggestions

    equivalents = carbon_equivalents(total_emission)
    tree_count = float(equivalents.get("trees_per_year", total_emission / 12.0) or 0)
    driving_km = float(equivalents.get("gasoline_car_km", total_emission / 0.21) or 0)
except Exception:
    carbon_equivalents = None
    generate_optimization_suggestions = None
    tree_count = total_emission / 12.0
    driving_km = total_emission / 0.21

fleet_df = build_fleet_dispatch_dataframe(route_results, result, vehicles)
vehicle_df = build_vehicle_dataframe(route_results)

anchor("sec-summary")
with st.container(key="carbon-overview-summary-card"):
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "总碳排放",
            f"{total_emission:,.2f} kg CO₂",
            delta=f"-{reduction_pct:.1f}%" if reduction_pct > 0 else None,
        )
    with col2:
        st.metric("总行驶距离", f"{total_distance:,.2f} km")
    with col3:
        st.metric("使用车辆", f"{num_vehicles} 辆")
    with col4:
        st.metric("等效种树", f"{tree_count:,.1f} 棵")

    if not fleet_df.empty:
        st.subheader("车队派车情况（实际 / 上限）")
        st.dataframe(fleet_df, hide_index=True, width="stretch")
        st.caption("未被分配任务的车辆视为闲置，不计入本次碳排放。")

    equivalent_df = pd.DataFrame(
        [
            {"指标": "总碳排放", "数值": f"{total_emission:.2f} kg CO₂", "说明": "优化后排放量"},
            {"指标": "等效种树", "数值": f"{tree_count:.1f} 棵", "说明": "每棵树每年吸收约 12 kg CO₂"},
            {"指标": "等效驾驶", "数值": f"{driving_km:.1f} km", "说明": "普通轿车行驶里程折算"},
            {"指标": "减排量", "数值": f"{carbon_reduction:.2f} kg CO₂", "说明": f"比基线节省 {reduction_pct:.1f}%"},
        ]
    )
    st.subheader("碳排放等效换算")
    st.dataframe(equivalent_df, hide_index=True, width="stretch")

anchor("sec-analysis")
with st.container(key="carbon-overview-analysis-card"):
    st.subheader("基线 vs 优化 碳排放对比")
    col_left, col_right = st.columns(2)

    with col_left:
        compare_df = pd.DataFrame(
            {
                "方案": ["基线方案（单独配送）", "优化方案（FSMVRP调度）"],
                "碳排放(kg CO₂)": [baseline_emission, total_emission],
            }
        )
        fig_compare = px.bar(
            compare_df,
            x="方案",
            y="碳排放(kg CO₂)",
            color="方案",
            title="碳排放对比",
            text_auto=".2f",
            color_discrete_sequence=["#EF553B", "#00CC96"],
        )
        fig_compare.update_layout(
            showlegend=False,
            paper_bgcolor="rgba(0, 0, 0, 0)",
            plot_bgcolor="rgba(255, 255, 255, 0.65)",
        )
        st.plotly_chart(fig_compare, width="stretch")

    with col_right:
        gauge_max = baseline_emission * 1.2 if baseline_emission > 0 else max(total_emission * 1.2, 100)
        fig_gauge = go.Figure(
            go.Indicator(
                mode="gauge+number+delta",
                value=total_emission,
                delta={"reference": baseline_emission, "decreasing": {"color": "green"}},
                title={"text": "优化碳排放 (kg CO₂)"},
                gauge={
                    "axis": {"range": [0, gauge_max]},
                    "bar": {"color": "#00CC96"},
                    "steps": [
                        {"range": [0, gauge_max * 0.45], "color": "#d4edda"},
                        {"range": [gauge_max * 0.45, gauge_max * 0.8], "color": "#fff3cd"},
                        {"range": [gauge_max * 0.8, gauge_max], "color": "#f8d7da"},
                    ],
                    "threshold": {
                        "line": {"color": "red", "width": 4},
                        "thickness": 0.75,
                        "value": baseline_emission,
                    },
                },
            )
        )
        fig_gauge.update_layout(
            paper_bgcolor="rgba(0, 0, 0, 0)",
            plot_bgcolor="rgba(255, 255, 255, 0.65)",
        )
        st.plotly_chart(fig_gauge, width="stretch")

anchor("sec-detail")
with st.container(key="carbon-overview-detail-card"):
    st.subheader("各车辆碳排放分布")

    detail_col_left, detail_col_right = st.columns([1.1, 1], gap="large")
    chart_df = vehicle_df.sort_values("碳排放(kg CO₂)", ascending=True)
    bar_colors = px.colors.qualitative.Set3

    with detail_col_left:
        fig_bar = go.Figure(
            go.Bar(
                x=chart_df["碳排放(kg CO₂)"],
                y=chart_df["车辆"],
                orientation="h",
                text=chart_df["碳排放(kg CO₂)"].map(lambda value: f"{value:.2f}"),
                textposition="outside",
                marker={
                    "color": [bar_colors[index % len(bar_colors)] for index in range(len(chart_df))],
                    "cornerradius": 12,
                },
                hovertemplate="车辆: %{y}<br>碳排放: %{x:.2f} kg CO₂<extra></extra>",
            )
        )
        fig_bar.update_layout(
            title="各车辆碳排放量",
            xaxis_title="碳排放(kg CO₂)",
            yaxis_title="车辆",
            paper_bgcolor="rgba(0, 0, 0, 0)",
            plot_bgcolor="rgba(255, 255, 255, 0.65)",
            showlegend=False,
            bargap=0.28,
            margin={"l": 8, "r": 24, "t": 56, "b": 8},
        )
        st.plotly_chart(fig_bar, width="stretch")

    with detail_col_right:
        fig_pie = px.pie(
            vehicle_df,
            values="碳排放(kg CO₂)",
            names="车辆",
            title="各车辆碳排放占比",
            hole=0.4,
            color_discrete_sequence=bar_colors,
        )
        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
        fig_pie.update_layout(
            paper_bgcolor="rgba(0, 0, 0, 0)",
            plot_bgcolor="rgba(255, 255, 255, 0.65)",
        )
        st.plotly_chart(fig_pie, width="stretch")



    st.subheader("碳排放效率分析")
    fig_efficiency = px.bar(
        vehicle_df,
        x="车辆",
        y=["碳效率(g CO₂/km)", "碳效率(g CO₂/kg货物)"],
        barmode="group",
        title="车辆碳排放效率对比",
    )
    fig_efficiency.update_layout(
        yaxis_title="碳效率",
        paper_bgcolor="rgba(0, 0, 0, 0)",
        plot_bgcolor="rgba(255, 255, 255, 0.65)",
    )
    st.plotly_chart(fig_efficiency, width="stretch")

anchor("sec-advice")
with st.container(key="carbon-overview-advice-card"):
    st.subheader("优化建议")

    suggestions: list[str] = []
    if generate_optimization_suggestions:
        suggest_type = None
        fleet_used_by_type = result.get("fleet_used_by_type", {}) or {}
        if fleet_used_by_type:
            suggest_type = max(fleet_used_by_type.items(), key=lambda item: item[1])[0]
        try:
            suggestions = generate_optimization_suggestions(
                total_carbon_kg=total_emission,
                vehicle_type=suggest_type or "diesel",
                total_distance_km=total_distance,
            )
        except Exception:
            suggestions = []

    if not suggestions:
        if reduction_pct < 10:
            suggestions.append("当前减排比例较低，建议在车辆配置中适度提高新能源车型的可用上限。")
        if num_vehicles > 1:
            suggestions.append("可继续优化去程空载与回程空驶，优先提高车辆装载率与回程复用。")
        suggestions.append("可结合物流枢纽和场馆分布，继续压缩高频末端配送半径。")

    for suggestion in suggestions:
        st.markdown(f"- {suggestion}")

    st.caption(f"数据来源：第五步路径优化结果 | 计算时间：{result.get('timestamp', '未知')}")

render_page_nav("pages/7_path_optimization.py", "pages/5_carbon_analysis.py", key_prefix="carbon-overview-nav")
