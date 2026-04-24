"""碳排放分析页面。"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from pages._bottom_nav import render_page_nav
from pages._ui_shared import (
    anchor,
    inject_base_style,
    inject_sidebar_navigation_label,
    render_sidebar_navigation,
    render_title,
    render_top_nav,
)
from utils.vehicle_lib import VEHICLE_LIB


POWER_TYPE_MAPPING = {
    "diesel_heavy": "柴油重卡",
    "diesel": "柴油重卡",
    "lng": "LNG天然气重卡",
    "hev": "混合动力 (HEV)",
    "phev": "插电混动 (PHEV)",
    "bev": "纯电动 (BEV)",
    "fcev": "氢燃料电池 (FCEV)",
    "mixed": "混合车队",
}

RATING_COLOR_MAP = {
    "🟢 低碳": "#80B332",
    "🟡 中碳": "#D8B452",
    "🔴 高碳": "#D94841",
}


def normalize_vehicle_type_id(raw_value: object) -> str:
    value = str(raw_value or "").strip().lower()
    if not value:
        return "unknown"
    value = value.split("_")[0] if value not in {"diesel_heavy"} else value
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


def get_vehicle_type_id(route_result: dict) -> str:
    vehicle_type_id = str(route_result.get("vehicle_type_id", "") or "").strip().lower()
    if vehicle_type_id:
        return normalize_vehicle_type_id(vehicle_type_id)
    return normalize_vehicle_type_id(route_result.get("vehicle_type", ""))


def get_vehicle_display_name(vehicle_type_id: str, fallback: str = "未知") -> str:
    normalized = normalize_vehicle_type_id(vehicle_type_id)
    return POWER_TYPE_MAPPING.get(normalized, fallback if fallback else normalized)


def build_fleet_dispatch_dataframe(
    route_results: list[dict],
    vehicles: list[dict],
    fleet_used_by_type: dict,
    fleet_max_by_type: dict,
) -> pd.DataFrame:
    used_counts: dict[str, int] = {}
    max_counts: dict[str, int] = {}

    for vehicle_type, used in (fleet_used_by_type or {}).items():
        normalized = normalize_vehicle_type_id(vehicle_type)
        used_counts[normalized] = used_counts.get(normalized, 0) + int(used or 0)

    for vehicle_type, cap in (fleet_max_by_type or {}).items():
        normalized = normalize_vehicle_type_id(vehicle_type)
        max_counts[normalized] = max_counts.get(normalized, 0) + int(cap or 0)

    if not used_counts:
        for route_result in route_results:
            vehicle_type_id = get_vehicle_type_id(route_result)
            used_counts[vehicle_type_id] = used_counts.get(vehicle_type_id, 0) + 1

    if not max_counts:
        for vehicle in vehicles:
            vehicle_type_id = normalize_vehicle_type_id(vehicle.get("vehicle_type", ""))
            if vehicle_type_id == "unknown":
                continue
            max_counts[vehicle_type_id] = max_counts.get(vehicle_type_id, 0) + int(
                vehicle.get("count_max", vehicle.get("count", 0)) or 0
            )

    rows = []
    for vehicle_type_id in sorted(set(used_counts) | set(max_counts)):
        used = used_counts.get(vehicle_type_id, 0)
        cap = max_counts.get(vehicle_type_id, 0)
        rows.append(
            {
                "动力类型": get_vehicle_display_name(vehicle_type_id, vehicle_type_id),
                "实际派车数": used,
                "可用上限": cap,
                "闲置车辆数": max(cap - used, 0),
            }
        )
    return pd.DataFrame(rows)


def build_route_segment_rows(route_result: dict, nodes: list[dict]) -> list[dict]:
    rows: list[dict] = []
    segments = route_result.get("segments", []) or []
    route = route_result.get("route", []) or []
    segment_labels = route_result.get("segment_labels", []) or []
    if not segments:
        return rows

    for seg_idx, segment in enumerate(segments):
        from_idx = route[seg_idx] if seg_idx < len(route) else None
        to_idx = route[seg_idx + 1] if seg_idx + 1 < len(route) else None

        from_name = f"节点{from_idx}"
        to_name = f"节点{to_idx}"
        if isinstance(from_idx, int) and 0 <= from_idx < len(nodes):
            from_name = nodes[from_idx].get("name", from_name)
        if isinstance(to_idx, int) and 0 <= to_idx < len(nodes):
            to_name = nodes[to_idx].get("name", to_name)

        rows.append(
            {
                "行驶区间": f"{from_name} -> {to_name}",
                "区间距离 (km)": round(float(segment.get("distance_km", 0) or 0), 2),
                "当前实际载重 (吨)": round(float(segment.get("load_kg", 0) or 0) / 1000.0, 3),
                "区间碳排 (kg CO2)": round(float(segment.get("carbon_kg", 0) or 0), 4),
            }
        )
    return rows


def build_vehicle_factor_dataframe() -> pd.DataFrame:
    return _build_vehicle_factor_dataframe_impl()


def build_route_segment_rows(route_result: dict, nodes: list[dict]) -> list[dict]:
    rows: list[dict] = []
    segments = route_result.get("segments", []) or []
    route = route_result.get("route", []) or []
    segment_labels = route_result.get("segment_labels", []) or []
    if not segments:
        return rows

    for seg_idx, segment in enumerate(segments):
        if seg_idx < len(segment_labels):
            segment_name = str(segment_labels[seg_idx])
        else:
            from_idx = route[seg_idx] if seg_idx < len(route) else None
            to_idx = route[seg_idx + 1] if seg_idx + 1 < len(route) else None

            from_name = f"节点{from_idx}"
            to_name = f"节点{to_idx}"
            if isinstance(from_idx, int) and 0 <= from_idx < len(nodes):
                from_name = nodes[from_idx].get("name", from_name)
            if isinstance(to_idx, int) and 0 <= to_idx < len(nodes):
                to_name = nodes[to_idx].get("name", to_name)
            segment_name = f"{from_name} -> {to_name}"

        rows.append(
            {
                "路段": segment_name,
                "路段距离 (km)": round(float(segment.get("distance_km", 0) or 0), 2),
                "运输负载 (吨)": round(float(segment.get("load_kg", 0) or 0) / 1000.0, 3),
                "路段碳排 (kg CO2)": round(float(segment.get("carbon_kg", 0) or 0), 4),
            }
        )
    return rows


def _build_vehicle_factor_dataframe_impl() -> pd.DataFrame:
    rows = []
    for vehicle_type_id, info in VEHICLE_LIB.items():
        loaded_factor = float(info.get("intensity_g_per_tkm", 60) or 0) / 1000.0
        if loaded_factor < 0.04:
            rating = "🟢 低碳"
        elif loaded_factor < 0.06:
            rating = "🟡 中碳"
        else:
            rating = "🔴 高碳"

        rows.append(
            {
                "车型名称": get_vehicle_display_name(vehicle_type_id, vehicle_type_id),
                "有载碳因子 (kg/吨km)": round(loaded_factor, 3),
                "空跑碳因子 (kg/km)": round(float(info.get("empty_g_per_km", 0) or 0) / 1000.0, 4),
                "冷启动 (kg)": round(float(info.get("cold_start_g", 0) or 0) / 1000.0, 3),
                "碳排放评级": rating,
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
                "减排量 (kg CO2)": round(reduction, 2),
                "减排比例(%)": round(reduction_pct, 1),
                "等效种树 (棵/年)": round(simulated_emission / 12.0, 1),
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
                    "距离缩放倍数": f"{multiplier}x",
                    "距离(km)": round(distance, 1),
                    "车型": get_vehicle_display_name(vehicle_type_id, vehicle_type_id),
                    "碳排放(kg CO2)": round(emission, 2),
                }
            )
    return pd.DataFrame(rows)


st.set_page_config(page_title="碳排放分析", page_icon="📩", layout="wide", initial_sidebar_state="expanded")
inject_sidebar_navigation_label()
inject_base_style()
render_sidebar_navigation()
render_top_nav(
    tabs=[("路径明细", "sec-factors"), ("动力横评", "sec-analysis"), ("模拟推演", "sec-ranking"), ("敏感性分析", "sec-config")],
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
    .st-key-materials-upload-card,
    .st-key-materials-online-card,
    .st-key-carbon-ranking-card,
    .st-key-carbon-config-card,
    .st-key-carbon-tip-card {
        background: linear-gradient(135deg, rgba(223, 239, 188, 0.94) 0%, rgba(214, 234, 174, 0.92) 100%);
        border: 1px solid #d0e2b4;
        border-radius: 28px;
        padding: 1.55rem 1.7rem 1.65rem;
        box-shadow: 0 8px 24px rgba(123, 145, 91, 0.22);
        margin-top: 1.25rem;
        overflow: hidden;
    }
    .st-key-materials-upload-card > div,
    .st-key-materials-online-card > div,
    .st-key-carbon-ranking-card > div,
    .st-key-carbon-config-card > div,
    .st-key-carbon-tip-card > div {
        gap: 0.95rem;
    }
    .st-key-materials-upload-card h3,
    .st-key-materials-online-card h3,
    .st-key-carbon-ranking-card h3,
    .st-key-carbon-config-card h3 {
        font-size: 1.95rem;
        font-weight: 700;
        color: #111111;
        margin-bottom: 0.15rem;
    }
    [data-testid="stHorizontalBlock"] { gap: 1rem; }
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
    div[data-testid="stExpander"] {
        border-radius: 18px !important;
        overflow: hidden;
        border: 1px solid rgba(0, 0, 0, 0.06) !important;
        background: rgba(255, 255, 255, 0.55) !important;
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
        .st-key-materials-upload-card,
        .st-key-materials-online-card,
        .st-key-carbon-ranking-card,
        .st-key-carbon-config-card,
        .st-key-carbon-tip-card {
            padding: 1.2rem 1rem 1.35rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

render_title("碳排放分析", "保留原页面视觉风格，展示路径级碳排明细、动力对比、车型模拟与减排敏感性分析")

results = st.session_state.get("optimization_results") or st.session_state.get("results")
vehicles = st.session_state.get("vehicles", [])

if not results or not isinstance(results, dict):
    anchor("sec-factors")
    with st.container(key="materials-upload-card"):
        st.warning("尚未执行路径优化，请先完成“路径优化”页面的计算。")
        st.info("当前页面已切换为深度碳排分析视图，需要先生成路线、载重和碳排结果。")
    render_page_nav("pages/7_path_optimization.py", "pages/8_results.py", key_prefix="carbon-analysis-nav")
    st.stop()
    raise SystemExit

route_results = results.get("route_results", []) or []
nodes = results.get("nodes", []) or []
fleet_used_by_type = results.get("fleet_used_by_type", {}) or {}
fleet_max_by_type = results.get("fleet_max_by_type", {}) or {}

if not route_results:
    anchor("sec-factors")
    with st.container(key="materials-upload-card"):
        st.warning("当前没有可用的路线结果。")
        st.info("请返回“路径优化”页面重新执行计算后，再查看碳排放分析。")
    render_page_nav("pages/7_path_optimization.py", "pages/8_results.py", key_prefix="carbon-analysis-nav")
    st.stop()
    raise SystemExit

actual_total_distance = float(results.get("total_distance_km", 0) or 0)
actual_total_emission = float(results.get("total_emission", 0) or 0)
baseline_emission = float(results.get("baseline_emission", 0) or 0)
reduction_pct = float(results.get("reduction_percent", 0) or 0)
total_demand_kg = sum(float(route.get("total_load_kg", 0) or 0) for route in route_results)
total_vehicle_count = int(results.get("num_vehicles_used", len(route_results)) or 0)

fleet_dispatch_df = build_fleet_dispatch_dataframe(route_results, vehicles, fleet_used_by_type, fleet_max_by_type)
vehicle_factor_df = build_vehicle_factor_dataframe()
simulation_df = build_simulation_dataframe(actual_total_distance, total_demand_kg)
sensitivity_df = build_sensitivity_dataframe(actual_total_distance, total_demand_kg)

best_simulated = simulation_df.loc[simulation_df["模拟碳排放(kg CO2)"].idxmin()] if not simulation_df.empty else None
worst_simulated = simulation_df.loc[simulation_df["模拟碳排放(kg CO2)"].idxmax()] if not simulation_df.empty else None

anchor("sec-factors")
with st.container(key="materials-upload-card"):
    st.subheader("🔍 路径碳排明细")
    st.caption("本页总碳排已计入冷启动基数，下方按车辆路线和分段载重展示更细粒度的碳排核算。")



    if not fleet_dispatch_df.empty:
        st.markdown("#### 本次方案派车组成（实际 / 上限）")
        st.dataframe(fleet_dispatch_df, hide_index=True, width="stretch")

    for idx, route_result in enumerate(route_results, start=1):
        vehicle_type_id = get_vehicle_type_id(route_result)
        vehicle_name = route_result.get("vehicle_name", f"车辆{idx}")
        vehicle_label = get_vehicle_display_name(vehicle_type_id, str(route_result.get("vehicle_type", "") or vehicle_type_id))
        with st.expander(f"车辆{idx}：{vehicle_name} [{vehicle_label}]", expanded=False):
            total_load = float(route_result.get("initial_load_kg", route_result.get("total_load_kg", 0)) or 0)
            st.markdown(
                f"**路线总载重**：{total_load / 1000.0:.2f} 吨  |  "
                f"**总距离**：{float(route_result.get('total_distance_km', 0) or 0):.2f} km  |  "
                f"**总碳排**：{float(route_result.get('total_carbon_kg', 0) or 0):.2f} kg CO2"
            )

            if route_result.get("route_path_names"):
                st.markdown(f"**\u542b\u4e2d\u8f6c\u4ed3\u8def\u7ebf\uff1a** {' -> '.join(route_result.get('route_path_names', []))}")
            segment_rows = build_route_segment_rows(route_result, nodes)
            if segment_rows:
                st.dataframe(pd.DataFrame(segment_rows), hide_index=True, width="stretch")
            elif route_result.get("segments"):
                st.dataframe(pd.DataFrame(route_result.get("segments", [])), hide_index=True, width="stretch")
            else:
                st.info("当前路线未包含分段碳排明细。")

anchor("sec-analysis")
with st.container(key="materials-online-card"):
    st.subheader("🧬 核心动力类型碳因子横评")


    fig_factor = px.bar(
        vehicle_factor_df,
        x="车型名称",
        y="有载碳因子 (kg/吨km)",
        color="碳排放评级",
        title="各车型主碳因子对比（越低越好）",
        text_auto=".3f",
        color_discrete_map=RATING_COLOR_MAP,
    )
    fig_factor.update_layout(
        height=420,
        paper_bgcolor="rgba(0, 0, 0, 0)",
        plot_bgcolor="rgba(255, 255, 255, 0.65)",
        legend_title_text="",
    )
    st.plotly_chart(fig_factor, width="stretch")



    if baseline_emission > 0:
        compare_df = pd.DataFrame(
            {
                "方案": ["基线方案（柴油直发）", "当前优化调度"],
                "碳排放(kg CO2)": [baseline_emission, actual_total_emission],
            }
        )
        fig_compare = px.bar(
            compare_df,
            x="方案",
            y="碳排放(kg CO2)",
            color="方案",
            title="基线方案 vs 当前优化方案",
            text_auto=".2f",
            color_discrete_sequence=["#D94841", "#80B332"],
        )
        fig_compare.update_layout(
            showlegend=False,
            height=380,
            paper_bgcolor="rgba(0, 0, 0, 0)",
            plot_bgcolor="rgba(255, 255, 255, 0.65)",
        )
        st.plotly_chart(fig_compare, width="stretch")

anchor("sec-ranking")
with st.container(key="carbon-ranking-card"):
    st.subheader("🧪 车型换算模拟推演")
    st.caption(
        f"基于本次最优路径，总距离 {actual_total_distance:.2f} km、总货物量 {total_demand_kg:,.0f} kg，"
        "推演如果全部使用单一车型执行运输，碳排表现将如何变化。"
    )

    fig_sim = px.bar(
        simulation_df,
        x="车型",
        y="模拟碳排放(kg CO2)",
        color="车型",
        title="单一车型全包换算模拟",
        text_auto=".1f",
        color_discrete_sequence=["#80B332", "#D8B452", "#6AA84F", "#C97C5D", "#9BBB59", "#B6C59D"],
    )
    if not simulation_df.empty:
        fig_sim.add_hline(
            y=float(simulation_df["基线碳排放(kg CO2)"].max()),
            line_dash="dash",
            line_color="#D94841",
            annotation_text="基线碳排放（柴油单独配送）",
        )
    fig_sim.update_layout(
        showlegend=False,
        height=430,
        paper_bgcolor="rgba(0, 0, 0, 0)",
        plot_bgcolor="rgba(255, 255, 255, 0.65)",
    )
    st.plotly_chart(fig_sim, width="stretch")


    fig_radar = go.Figure()
    fig_radar.add_trace(
        go.Scatterpolar(
            r=simulation_df["减排比例(%)"].tolist(),
            theta=simulation_df["车型"].tolist(),
            fill="toself",
            name="减排比例(%)",
            marker={"color": "#80B332"},
        )
    )
    fig_radar.update_layout(
        title="相比传统柴油直发的减排百分比",
        height=420,
        paper_bgcolor="rgba(0, 0, 0, 0)",
        polar={"radialaxis": {"visible": True, "ticksuffix": "%"}},
    )
    st.plotly_chart(fig_radar, width="stretch")


    if best_simulated is not None and worst_simulated is not None:
        summary_col1, summary_col2 = st.columns(2)
        with summary_col1:
            st.success(
                "\n".join(
                    [
                        f"绿色先锋推荐：{best_simulated['车型']}",
                        f"模拟碳排放：{best_simulated['模拟碳排放(kg CO2)']:.2f} kg CO2",
                        f"减排比例：{best_simulated['减排比例(%)']:.1f}%",
                        f"等效种树：{best_simulated['等效种树 (棵/年)']:.1f} 棵/年",
                    ]
                )
            )
        with summary_col2:
            st.error(
                "\n".join(
                    [
                        f"高碳排放警示：{worst_simulated['车型']}",
                        f"模拟碳排放：{worst_simulated['模拟碳排放(kg CO2)']:.2f} kg CO2",
                        f"减排比例：{worst_simulated['减排比例(%)']:.1f}%",
                    ]
                )
            )

anchor("sec-config")
with st.container(key="carbon-config-card"):
    st.subheader("📉 里程-碳排敏感性分析")
    st.caption("分析距离变化时，不同车型的碳排放趋势与放大效应。")

    fig_sensitivity = px.line(
        sensitivity_df,
        x="距离(km)",
        y="碳排放(kg CO2)",
        color="车型",
        title="碳排放敏感性分析（距离变化）",
        markers=True,
        color_discrete_sequence=["#80B332", "#D8B452", "#6AA84F", "#C97C5D", "#9BBB59", "#B6C59D"],
    )
    fig_sensitivity.update_layout(
        height=430,
        paper_bgcolor="rgba(0, 0, 0, 0)",
        plot_bgcolor="rgba(255, 255, 255, 0.65)",
    )
    st.plotly_chart(fig_sensitivity, width="stretch")

    summary_col1, summary_col2, summary_col3 = st.columns(3)
    with summary_col1:
        st.metric("基线碳排放", f"{baseline_emission:.2f} kg CO2")
    with summary_col2:
        st.metric("当前优化碳排", f"{actual_total_emission:.2f} kg CO2")
    with summary_col3:
        st.metric("减排比例", f"{max(baseline_emission - actual_total_emission, 0):.2f} kg CO2", delta=f"-{reduction_pct:.1f}%")

with st.container(key="carbon-tip-card"):
    st.caption(
        f"数据来源：路径优化结果 | 计算时间：{results.get('timestamp', '未知')} | "
    )

render_page_nav("pages/7_path_optimization.py", "pages/8_results.py", key_prefix="carbon-analysis-nav")
