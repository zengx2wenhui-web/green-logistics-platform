"""优化结果页面。"""
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
from pages._ui_shared import (
    anchor,
    inject_base_style,
    inject_sidebar_navigation_label,
    render_download_button,
    render_sidebar_navigation,
    render_title,
    render_top_nav,
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
    "diesel": "柴油重卡",
    "lng": "LNG天然气重卡",
    "hev": "混合动力",
    "phev": "插电混动",
    "bev": "纯电动",
    "fcev": "氢燃料电池",
    "mixed": "混合车队",
}

LOAD_DETAIL_COLUMNS = [
    ("general_materials_kg", "通用赛事物资(kg)"),
    ("sports_equipment_kg", "专项运动器材(kg)"),
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


def get_total_demand_value(demand_data: object) -> float:
    if isinstance(demand_data, dict):
        if "总需求" in demand_data:
            return float(demand_data.get("总需求", 0) or 0)
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


def get_depot_display_name(depot: dict, index: int) -> str:
    return str(depot.get("仓库名称") or depot.get("中转仓编号") or f"中转仓{index}")


def get_depot_display_address(depot: dict) -> str:
    explicit_address = str(depot.get("建议地址") or "").strip()
    if explicit_address:
        return explicit_address

    province = str(depot.get("省") or "").strip()
    city = str(depot.get("市") or "").strip()
    if province or city:
        return f"{province}{city}".strip()

    lng = depot.get("经度")
    lat = depot.get("纬度")
    if lng not in (None, "") and lat not in (None, ""):
        return f"({float(lng):.4f}, {float(lat):.4f}) 附近"
    return "未知"


def build_dispatch_dataframe(route_results: list[dict], vehicle_name: str, route_context: dict) -> pd.DataFrame:
    rows = []
    for index, route_result in enumerate(route_results, start=1):
        rows.append(
            {
                "车辆编号": route_result.get("vehicle_name", f"车辆 {index}"),
                "车型": get_route_vehicle_display_name(route_result, vehicle_name),
                "含中转仓路线": " -> ".join(get_route_path_names(route_result, route_context)),
                "访问场馆数": len(route_result.get("visited_venue_names", route_result.get("visits", []))),
                "装载量(kg)": round(float(route_result.get("total_load_kg", 0) or 0), 2),
                "行驶距离(km)": round(float(route_result.get("total_distance_km", 0) or 0), 2),
                "碳排放(kg CO2)": round(float(route_result.get("total_carbon_kg", 0) or 0), 2),
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
                "行驶距离(km)": round(total_distance, 2),
                "碳排放(kg CO2)": round(total_carbon, 2),
                "单位里程碳排(kg/km)": round(total_carbon / max(total_distance, 0.01), 4),
            }
        )
    return pd.DataFrame(rows)


def build_route_load_dataframe(route_result: dict) -> pd.DataFrame:
    load_details = route_result.get("load_details", [])
    rows = []
    for stop in load_details:
        row = {"场馆": stop.get("venue", "")}
        total_value = 0.0
        for field_name, label in LOAD_DETAIL_COLUMNS:
            value = float(stop.get(field_name, 0) or 0)
            row[label] = value
            total_value += value
        row["总需求(kg)"] = total_value
        rows.append(row)

    detail_df = pd.DataFrame(rows)
    if detail_df.empty:
        return detail_df

    total_row = {"场馆": "合计"}
    for _, label in LOAD_DETAIL_COLUMNS:
        total_row[label] = detail_df[label].sum()
    total_row["总需求(kg)"] = detail_df["总需求(kg)"].sum()
    return pd.concat([detail_df, pd.DataFrame([total_row])], ignore_index=True)


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
                "含中转仓路线": route_path,
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


def build_depot_dataframe(depot_results_list: list[dict]) -> pd.DataFrame:
    if not depot_results_list:
        return pd.DataFrame()

    depot_df = pd.DataFrame(depot_results_list)
    preferred_columns = [
        "仓库名称",
        "省",
        "市",
        "建议地址",
        "经度",
        "纬度",
        "服务场馆数",
        "服务场馆列表",
        "物资总量(kg)",
        "平均距离(km)",
        "route_count",
        "trunk_distance_km",
        "trunk_carbon_kg",
    ]
    ordered_columns = [column for column in preferred_columns if column in depot_df.columns]
    other_columns = [column for column in depot_df.columns if column not in ordered_columns]
    return depot_df[ordered_columns + other_columns]


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
                    "路线段": segment_labels[seg_index - 1] if seg_index - 1 < len(segment_labels) else f"路段 {seg_index}",
                    "距离(km)": round(float(segment.get("distance_km", 0) or 0), 2),
                    "载重(kg)": round(float(segment.get("load_kg", 0) or 0), 2),
                    "碳排放(kg CO2)": round(float(segment.get("carbon_kg", 0) or 0), 4),
                }
            )
    return pd.DataFrame(rows)


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
                        f"当前路段：{segment_text}<br>"
                        f"路段序号：{segment_index}/{len(route_segments)}<br>"
                        f"距离：{float(route_result.get('total_distance_km', 0) or 0):.2f} km<br>"
                        f"碳排：{float(route_result.get('total_carbon_kg', 0) or 0):.2f} kg CO2"
                    ),
                ).add_to(map_chart)

    warehouse_node = nodes[0]
    folium.Marker(
        [warehouse_node["lat"], warehouse_node["lng"]],
        popup=f"<b>总仓库：{warehouse_node['name']}</b><br>地址：{warehouse_node.get('address', '')}",
        tooltip="总仓库",
        icon=folium.Icon(color="darkred", icon="star"),
    ).add_to(map_chart)

    for depot_index, depot in enumerate(depot_results_list, start=1):
        depot_lat = depot.get("纬度", 0)
        depot_lng = depot.get("经度", 0)
        if depot_lat and depot_lng:
            depot_name = get_depot_display_name(depot, depot_index)
            depot_address = get_depot_display_address(depot)
            assigned_count = depot.get("服务场馆数", 0)
            assigned_names = depot.get("服务场馆列表", "")
            total_load = float(depot.get("物资总量(kg)", 0) or 0)
            popup_html = (
                f"<b>{depot_name}</b><br>"
                f"地址：{depot_address}<br>"
                f"坐标：({float(depot_lng):.6f}, {float(depot_lat):.6f})<br>"
                f"服务场馆数：{assigned_count}<br>"
                f"服务场馆：{assigned_names}<br>"
                f"物资总量：{total_load:,.1f} kg"
            )
            folium.Marker(
                [depot_lat, depot_lng],
                popup=folium.Popup(popup_html, max_width=360),
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

    legend_html = """
        <div style="position: fixed; bottom: 20px; left: 20px; z-index: 1000;
                background: rgba(255, 255, 255, 0.94); padding: 8px 12px; border-radius: 6px;
                border: 1px solid #ccc; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
                min-width: 160px; font-family: sans-serif;">
        
        <div style="margin-bottom: 8px; font-size: 13px; font-weight: bold; color: #000; border-bottom: 1px solid #eee; padding-bottom: 4px;">路线图例</div>
        
        <div style="display: flex; align-items: center; gap: 8px; margin: 4px 0;">
            <svg style="width: 14px; height: 14px; filter: drop-shadow(0px 1px 2px rgba(0,0,0,0.4));" viewBox="0 0 24 24">
                <path fill="#e11d48" d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
            </svg>
            <span style="font-size: 12px; color: #333;">总仓节点</span>
        </div>

        <div style="display: flex; align-items: center; gap: 8px; margin: 4px 0;">
            <svg style="width: 13px; height: 13px;" viewBox="0 0 24 24">
                <path fill="#ef4444" d="M12 3L2 12h3v8h14v-8h3L12 3z"/>
            </svg>
            <span style="font-size: 12px; color: #333;">中转仓节点</span>
        </div>

        <div style="display: flex; align-items: center; gap: 8px; margin: 4px 0;">
            <span style="width: 10px; height: 10px; background: #ef4444; border-radius: 50%; display: inline-block;"></span>
            <span style="font-size: 12px; color: #333;">场馆节点</span>
        </div>

        <div style="display: flex; align-items: center; gap: 8px; margin: 4px 0;">
            <span style="width: 24px; height: 0; border-top: 2.5px solid #000; display: inline-block;"></span>
            <span style="font-size: 12px; color: #333;">配送主路线段</span>
        </div>

        <div style="display: flex; align-items: center; gap: 8px; margin: 4px 0;">
            <span style="width: 24px; height: 0; border-top: 2px dashed #000; display: inline-block;"></span>
            <span style="font-size: 12px; color: #333;">总仓与中转仓补给段</span>
        </div>
    </div>
    """
    map_chart.get_root().html.add_child(folium.Element(legend_html))
    return map_chart


def _json_default(value: object) -> str:
    return str(value)


st.set_page_config(page_title="优化结果", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
inject_sidebar_navigation_label()
inject_base_style()
render_sidebar_navigation()

results = st.session_state.get("optimization_results") or st.session_state.get("results")
has_results = bool(results)

render_top_nav(
    tabs=[("结果概览", "sec-summary"), ("地图与分析", "sec-tabs")] if has_results else [("结果概览", "sec-summary")],
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
    .st-key-results-empty-card,
    .st-key-results-summary-card,
    .st-key-results-depot-card,
    .st-key-results-tabs-card,
    .st-key-results-export-card,
    .st-key-results-footer-card {
        background: linear-gradient(135deg, rgba(223, 239, 188, 0.94) 0%, rgba(214, 234, 174, 0.92) 100%);
        border: 1px solid #d0e2b4;
        border-radius: 28px;
        padding: 1.55rem 1.7rem 1.65rem;
        box-shadow: 0 8px 24px rgba(123, 145, 91, 0.22);
        margin-top: 1.25rem;
        overflow: hidden;
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
    div[data-testid="stMetric"] {
        background: transparent !important;
        border: 0 !important;
        padding: 0.1rem 0 !important;
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
    div[data-testid="stExpander"] {
        border-radius: 18px !important;
        overflow: hidden;
        border: 1px solid rgba(0, 0, 0, 0.06) !important;
        background: rgba(255, 255, 255, 0.55) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

render_title("优化结果", "查看中转仓选址、物流路线、碳排对比与数据导出。")

if not results:
    anchor("sec-summary")
    with st.container(key="results-empty-card"):
        st.info("当前还没有优化结果，请先前往“路径优化”页面执行计算。")
    render_page_nav(
        "pages/7_path_optimization.py",
        "app.py",
        prev_label="上一页",
        next_label="返回首页",
        key_prefix="results-empty-nav",
    )
    st.stop()

route_results = results.get("route_results", [])
trunk_routes = results.get("trunk_routes", [])
nodes = results.get("nodes", [])
depot_results_list = results.get("depot_results", [])
demands_dict = results.get("demands", {})
vehicle_name = get_result_vehicle_display_name(results)
route_context = build_route_context(nodes, depot_results_list)

dispatch_df = build_dispatch_dataframe(route_results, vehicle_name, route_context)
route_carbon_df = build_route_carbon_dataframe(route_results, vehicle_name)
load_export_df = build_load_export_dataframe(route_results, vehicle_name, route_context)
segment_export_df = build_route_segment_export_dataframe(route_results, vehicle_name)
depot_df = build_depot_dataframe(depot_results_list)

total_emission = float(results.get("total_emission", 0) or 0)
baseline_emission = float(results.get("baseline_emission", 0) or 0)
reduction_pct = float(results.get("reduction_percent", 0) or 0)
total_distance_km = float(results.get("total_distance_km", 0) or 0)
terminal_distance_km = float(results.get("terminal_distance_km", 0) or 0)
trunk_distance_km = float(results.get("trunk_distance_km", 0) or 0)
terminal_emission = float(results.get("terminal_emission", 0) or 0)
trunk_emission = float(results.get("trunk_emission", 0) or 0)
carbon_reduction = max(baseline_emission - total_emission, 0.0)
total_demand_kg = infer_total_demand_kg(route_results, demands_dict)
optimization_method = str(results.get("optimization_method") or "OR-Tools FSMVRP")
distance_method = str(results.get("distance_method") or "坐标直线距离")
clustering_method = str(results.get("clustering_method") or "候选中转仓分配")
timestamp = str(results.get("timestamp") or "")
has_trunk_breakdown = bool(trunk_routes) or trunk_distance_km > 0 or trunk_emission > 0
distance_delta_text = (
    f"配送段 {terminal_distance_km:.2f} / 补给段 {trunk_distance_km:.2f}"
    if has_trunk_breakdown
    else "车辆全程"
)
primary_emission_label = "配送段碳排" if has_trunk_breakdown else "车辆全程碳排"
secondary_emission_label = "补给段碳排" if has_trunk_breakdown else "独立干线碳排"

anchor("sec-summary")
with st.container(key="results-summary-card"):
    st.markdown("### 结果概览")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总碳排放", f"{total_emission:.2f} kg CO2", delta=f"较基线减少 {carbon_reduction:.2f} kg")
    with col2:
        st.metric("总行驶距离", f"{total_distance_km:.2f} km", delta=distance_delta_text)
    with col3:
        st.metric("总物资需求", f"{total_demand_kg:,.1f} kg", delta=f"{len(route_results)} 条闭环路线")
    with col4:
        st.metric("减排比例", f"{reduction_pct:.2f}%", delta=f"{len(depot_results_list)} 个中转仓")

    st.caption(
        f"优化方式：{optimization_method} | 距离模型：{distance_method} | 中转仓分配：{clustering_method}"
        + (f" | 计算时间：{timestamp}" if timestamp else "")
    )

if not depot_df.empty:
    with st.container(key="results-depot-card"):
        st.markdown("### 中转仓选址结果")
        st.dataframe(depot_df, width="stretch", hide_index=True)

anchor("sec-tabs")
with st.container(key="results-tabs-card"):
    tab_map, tab_carbon, tab_dispatch, tab_export = st.tabs(["物流网络地图", "碳排放对比", "详细结果", "数据导出"])

    with tab_map:
        st.subheader("物流网络地图")
        map_chart = build_map(nodes, route_results, depot_results_list, demands_dict, vehicle_name, route_context)
        if map_chart is not None:
            st_folium(map_chart, width="100%", height=560)
        else:
            st.info("暂无可用的地图节点数据。")

    with tab_carbon:
        st.subheader("碳排放对比")
        compare_df = pd.DataFrame(
            {
                "方案": ["基线方案（总仓直发）", f"优化方案（{vehicle_name}）"],
                "碳排放(kg CO2)": [baseline_emission, total_emission],
            }
        )
        fig_compare = px.bar(
            compare_df,
            x="方案",
            y="碳排放(kg CO2)",
            color="方案",
            title="优化前后碳排放对比",
            text_auto=".2f",
            color_discrete_sequence=["#D94841", "#2E9D52"],
        )
        fig_compare.update_layout(
            showlegend=False,
            paper_bgcolor="rgba(0, 0, 0, 0)",
            plot_bgcolor="rgba(255, 255, 255, 0.65)",
        )
        st.plotly_chart(fig_compare, width="stretch")

        breakdown_col1, breakdown_col2 = st.columns(2)
        with breakdown_col1:
            st.metric(primary_emission_label, f"{terminal_emission:.2f} kg CO2", delta=f"{terminal_distance_km:.2f} km")
        with breakdown_col2:
            st.metric(secondary_emission_label, f"{trunk_emission:.2f} kg CO2", delta=f"{trunk_distance_km:.2f} km")

        if not route_carbon_df.empty:
            fig_route = px.bar(
                route_carbon_df,
                x="车辆编号",
                y="碳排放(kg CO2)",
                color="行驶距离(km)",
                title="各车辆路线碳排放分布",
                text_auto=True,
            )
            fig_route.update_layout(
                paper_bgcolor="rgba(0, 0, 0, 0)",
                plot_bgcolor="rgba(255, 255, 255, 0.65)",
            )
            st.plotly_chart(fig_route, width="stretch")
            st.dataframe(route_carbon_df, hide_index=True, width="stretch")

    with tab_dispatch:
        st.subheader("车辆调度详情")

        if not dispatch_df.empty:
            st.dataframe(dispatch_df, hide_index=True, width="stretch")

        if route_results:
            for index, route_result in enumerate(route_results, start=1):
                vehicle_label = (
                    f"{route_result.get('vehicle_name', f'车辆 {index}')} "
                    f"（{get_route_vehicle_display_name(route_result, vehicle_name)}）"
                )
                with st.expander(vehicle_label, expanded=False):
                    st.markdown(f"**路线：** {' -> '.join(get_route_path_names(route_result, route_context))}")
                    st.divider()

                    detail_df = build_route_load_dataframe(route_result)
                    if not detail_df.empty:
                        st.dataframe(detail_df, width="stretch", hide_index=True)
                    else:
                        st.info("该车辆暂无装载明细。")

                    st.divider()
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        max_load = float(route_result.get("vehicle_capacity_kg", results.get("vehicle_capacity_kg", 0)) or 0)
                        total_load = float(route_result.get("total_load_kg", 0) or 0)
                        utilization = (total_load / max_load * 100) if max_load > 0 else 0
                        st.metric("总装载量", f"{total_load:.1f} kg", delta=f"装载率 {utilization:.1f}%")
                    with col2:
                        st.metric("总距离", f"{float(route_result.get('total_distance_km', 0) or 0):.2f} km")
                    with col3:
                        st.metric("总碳排", f"{float(route_result.get('total_carbon_kg', 0) or 0):.2f} kg CO2")
        else:
            st.info("暂无车辆调度结果。")

    with tab_export:
        st.subheader("数据导出")
        st.caption("可以导出车辆调度、中转仓结果、分段碳排明细和完整原始 JSON。")

        export_col1, export_col2 = st.columns(2)
        with export_col1:
            render_download_button(
                label="导出车辆调度汇总 CSV",
                data=dispatch_df.to_csv(index=False).encode("utf-8-sig"),
                key="results-export-dispatch",
                file_name="车辆调度汇总.csv",
                mime="text/csv",
                width="stretch",
            )
            if not load_export_df.empty:
                render_download_button(
                    label="导出场馆装载明细 CSV",
                    data=load_export_df.to_csv(index=False).encode("utf-8-sig"),
                    key="results-export-load-details",
                    file_name="场馆装载明细.csv",
                    mime="text/csv",
                    width="stretch",
                )

        with export_col2:
            if not depot_df.empty:
                render_download_button(
                    label="导出中转仓结果 CSV",
                    data=depot_df.to_csv(index=False).encode("utf-8-sig"),
                    key="results-export-depots",
                    file_name="中转仓选址结果.csv",
                    mime="text/csv",
                    width="stretch",
                )
            if not segment_export_df.empty:
                render_download_button(
                    label="导出分段碳排明细 CSV",
                    data=segment_export_df.to_csv(index=False).encode("utf-8-sig"),
                    key="results-export-segments",
                    file_name="分段碳排明细.csv",
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

with st.container(key="results-footer-card"):
    render_page_nav(
        "pages/5_carbon_analysis.py",
        "app.py",
        prev_label="上一页",
        next_label="返回首页",
        key_prefix="results-footer-nav",
    )
