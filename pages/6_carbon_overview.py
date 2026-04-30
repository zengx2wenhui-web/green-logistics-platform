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
    inject_green_dashboard_style,
    tune_bar_value_labels,
)
from pages._route_analysis_shared import (
    build_route_map,
    build_route_overview_dataframe,
    build_route_segment_rows,
    get_vehicle_display_name,
    get_vehicle_type_id,
)
from ._ui_shared import (
    anchor,
    inject_base_style,
    inject_sidebar_navigation_label,
    render_sidebar_navigation,
    render_title,
    render_top_nav,
)
from utils.carbon_calc import carbon_equivalents, generate_optimization_suggestions
from utils.route_display import build_route_context


def build_fleet_dispatch_dataframe(route_results: list[dict], result_data: dict, vehicles: list[dict]) -> pd.DataFrame:
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

    rows = []
    for vehicle_type_id in sorted(set(max_counts) | set(used_counts)):
        used = int(used_counts.get(vehicle_type_id, 0) or 0)
        cap = int(max_counts.get(vehicle_type_id, 0) or 0)
        rows.append(
            {
                "车型": get_vehicle_display_name(vehicle_type_id, vehicle_type_id),
                "实际派车": used,
                "车队上限": cap,
                "剩余可用": max(cap - used, 0),
            }
        )
    return pd.DataFrame(rows)


def build_equivalent_dataframe(
    total_emission: float,
    tree_count: float,
    driving_km: float,
    avg_route_emission: float,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"指标": "总碳排放", "数值": f"{total_emission:.2f} kg CO2", "说明": "优化方案的总碳排放结果。"},
            {"指标": "树木碳汇等效", "数值": f"{tree_count:.1f} 棵", "说明": "按每棵树每年吸收约 12 kg CO2 估算。"},
            {"指标": "燃油车行驶等效", "数值": f"{driving_km:.1f} km", "说明": "按常规燃油车排放水平换算。"},
            {"指标": "平均单车碳排", "数值": f"{avg_route_emission:.2f} kg CO2", "说明": "按已执行路线平均计算。"},
        ]
    )


st.set_page_config(page_title="碳排放概览", page_icon="🌍", layout="wide", initial_sidebar_state="expanded")
inject_sidebar_navigation_label()
inject_base_style()
inject_green_dashboard_style("carbon-overview")
render_sidebar_navigation()

result = st.session_state.get("optimization_results") or st.session_state.get("results")
vehicles = st.session_state.get("vehicles", [])
has_result = bool(result and isinstance(result, dict) and result.get("route_results"))

render_top_nav(
    tabs=[("核心指标", "sec-summary"), ("路线展示", "sec-routes"), ("分段测算", "sec-detail"), ("优化建议", "sec-advice")]
    if has_result
    else [("核心指标", "sec-summary")],
    active_idx=0,
)
render_title("碳排放概览", "用更清晰的逻辑展示优化方案的总量结果、路线表现与分段测算。")

if not result or not isinstance(result, dict):
    anchor("sec-summary")
    st.warning("尚未生成优化结果，请先完成路径优化。")
    render_page_nav("pages/7_path_optimization.py", "pages/5_carbon_analysis.py", key_prefix="carbon-overview-nav")
    st.stop()

route_results = result.get("route_results", []) or []
if not route_results:
    anchor("sec-summary")
    st.warning("当前没有可展示的路线结果。")
    render_page_nav("pages/7_path_optimization.py", "pages/5_carbon_analysis.py", key_prefix="carbon-overview-nav")
    st.stop()

nodes = result.get("nodes", []) or []
depot_results = result.get("depot_results", []) or []
demands_dict = result.get("demands", {}) or {}
route_context = build_route_context(nodes, depot_results)

total_emission = float(result.get("total_emission", 0) or 0)
baseline_emission = float(result.get("baseline_emission", 0) or 0)
reduction_pct = float(result.get("reduction_percent", 0) or 0)
total_distance = float(result.get("total_distance_km", 0) or 0)
terminal_emission = float(result.get("terminal_emission", total_emission) or 0)
trunk_emission = float(result.get("trunk_emission", 0) or 0)
terminal_distance = float(result.get("terminal_distance_km", total_distance) or 0)
trunk_distance = float(result.get("trunk_distance_km", 0) or 0)
num_vehicles = int(result.get("num_vehicles_used", len(route_results)) or len(route_results))
carbon_reduction = max(baseline_emission - total_emission, 0.0)
has_trunk_breakdown = trunk_emission > 0 or trunk_distance > 0

equivalents = carbon_equivalents(total_emission)
tree_count = float(equivalents.get("trees_per_year", total_emission / 12.0) or 0)
driving_km = float(equivalents.get("gasoline_car_km", total_emission / 0.21) or 0)

fleet_df = build_fleet_dispatch_dataframe(route_results, result, vehicles)
route_df = build_route_overview_dataframe(route_results, route_context)
equivalent_df = build_equivalent_dataframe(
    total_emission=total_emission,
    tree_count=tree_count,
    driving_km=driving_km,
    avg_route_emission=total_emission / len(route_results) if route_results else 0.0,
)

avg_route_emission = total_emission / len(route_results) if route_results else 0.0
avg_emission_per_km = total_emission / total_distance if total_distance > 0 else 0.0
utilization_series = pd.to_numeric(route_df["装载率(%)"], errors="coerce") if not route_df.empty else pd.Series(dtype=float)
avg_utilization = float(utilization_series.dropna().mean()) if utilization_series.notna().any() else 0.0

highest_emission_route = route_df.loc[route_df["总碳排放(kg CO2)"].idxmax()].to_dict() if not route_df.empty else None
highest_intensity_route = route_df.loc[route_df["碳排效率(kg/km)"].idxmax()].to_dict() if not route_df.empty else None
highest_utilization_route = route_df.loc[utilization_series.idxmax()].to_dict() if utilization_series.notna().any() else None

anchor("sec-summary")
with st.container(key="carbon-overview-card-summary"):
    st.markdown("#### 总量指标")
    total_col1, total_col2, total_col3, total_col4 = st.columns(4)
    with total_col1:
        st.metric("总碳排放", f"{total_emission:,.2f} kg CO2", delta=f"-{reduction_pct:.1f}%" if reduction_pct > 0 else None)
    with total_col2:
        st.metric("较基线减排", f"{carbon_reduction:,.2f} kg CO2")
    with total_col3:
        st.metric("总运输距离", f"{total_distance:,.2f} km")
    with total_col4:
        st.metric("使用车辆", f"{num_vehicles} 辆")

    st.markdown("#### 结构与效率")
    structure_col1, structure_col2, structure_col3, structure_col4 = st.columns(4)
    with structure_col1:
        st.metric("末端配送碳排", f"{terminal_emission:,.2f} kg CO2", delta=f"{terminal_distance:,.2f} km")
    with structure_col2:
        st.metric("干线补给碳排", f"{trunk_emission:,.2f} kg CO2", delta=f"{trunk_distance:,.2f} km")
    with structure_col3:
        st.metric("平均单车碳排", f"{avg_route_emission:,.2f} kg CO2")
    with structure_col4:
        st.metric("平均碳排效率", f"{avg_emission_per_km:.4f} kg/km")

    profile_col1, profile_col2 = st.columns([1.02, 0.98])
    with profile_col1:
        with st.container(key="carbon-overview-panel-fleet"):
            st.subheader("车队使用画像")
            if not fleet_df.empty:
                st.dataframe(fleet_df, hide_index=True, width="stretch")
            else:
                st.info("当前结果中暂无可统计的车队使用数据。")
    with profile_col2:
        with st.container(key="carbon-overview-panel-equivalent"):
            st.subheader("碳排放等效结果")
            st.dataframe(equivalent_df, hide_index=True, width="stretch")
            if has_trunk_breakdown and total_emission > 0:
                st.caption(
                    f"排放结构中，末端配送占 {terminal_emission / total_emission * 100:.1f}% ，"
                    f"干线补给占 {trunk_emission / total_emission * 100:.1f}% 。"
                )

    with st.container(key="carbon-overview-panel-insights"):
        st.subheader("关键路线诊断")
        insight_col1, insight_col2, insight_col3 = st.columns(3)
        with insight_col1:
            if highest_emission_route:
                route_share = float(highest_emission_route["总碳排放(kg CO2)"] or 0) / total_emission * 100 if total_emission > 0 else 0.0
                st.metric("最高排放路线", str(highest_emission_route["路线编号"]), delta=f"占比 {route_share:.1f}%")
        with insight_col2:
            if highest_intensity_route:
                st.metric("高强度路线", str(highest_intensity_route["路线编号"]), delta=f"{float(highest_intensity_route['碳排效率(kg/km)']):.4f} kg/km")
        with insight_col3:
            if highest_utilization_route:
                st.metric("最高装载率路线", str(highest_utilization_route["路线编号"]), delta=f"{float(highest_utilization_route['装载率(%)']):.1f}%")
            else:
                st.metric("平均装载率", f"{avg_utilization:.1f}%")

anchor("sec-routes")
with st.container(key="carbon-overview-card-routes"):
    st.subheader("路线展示")
    route_tab_map, route_tab_diag = st.tabs(["地图总览", "路线诊断"])

    with route_tab_map:
        route_map = build_route_map(nodes, route_results, depot_results, demands_dict, route_context)
        if route_map is not None:
            st_folium(route_map, width="100%", height=560)
            st.caption("地图弹窗中可查看每条分段的距离、载重与分段碳排测算。")
        else:
            st.info("当前没有可展示的路线地图。")

    with route_tab_diag:
        diag_col1, diag_col2 = st.columns([1.05, 0.95])
        with diag_col1:
            chart_df = route_df.sort_values("总碳排放(kg CO2)", ascending=True)
            fig_total = px.bar(
                chart_df,
                x="总碳排放(kg CO2)",
                y="路线编号",
                orientation="h",
                text_auto=".2f",
                color_discrete_sequence=["#2F6BFF"],
                title="路线总碳排放排序",
            )
            fig_total.update_traces(
                hovertemplate="<b>%{y}</b><br>总碳排放：%{x:.2f} kg CO2<extra></extra>"
            )
            apply_green_chart_theme(fig_total, height=400, showlegend=False, right_margin=48)
            tune_bar_value_labels(fig_total, orientation="h", headroom_ratio=0.12)
            st.plotly_chart(fig_total, width="stretch")

        with diag_col2:
            fig_eff = px.bar(
                route_df.sort_values("碳排效率(kg/km)", ascending=False),
                x="路线编号",
                y="碳排效率(kg/km)",
                text_auto=".4f",
                color_discrete_sequence=["#80B332"],
                title="路线单位里程碳排",
            )
            fig_eff.update_traces(
                hovertemplate="<b>%{x}</b><br>碳排效率：%{y:.4f} kg/km<extra></extra>"
            )
            fig_eff.update_xaxes(tickangle=-12)
            apply_green_chart_theme(fig_eff, height=400, showlegend=False, top_margin=76, bottom_margin=42)
            tune_bar_value_labels(fig_eff, orientation="v", headroom_ratio=0.22)
            st.plotly_chart(fig_eff, width="stretch")

        st.dataframe(
            route_df[
                [
                    "路线编号",
                    "车型",
                    "场馆数",
                    "装载率(%)",
                    "总距离(km)",
                    "总碳排放(kg CO2)",
                    "碳排效率(kg/km)",
                ]
            ].sort_values("总碳排放(kg CO2)", ascending=False),
            hide_index=True,
            width="stretch",
        )

anchor("sec-detail")
with st.container(key="carbon-overview-card-detail"):
    st.subheader("分段测算")
    detail_tab_summary, detail_tab_segments = st.tabs(["路线汇总", "分段明细"])

    with detail_tab_summary:
        st.dataframe(
            route_df[
                [
                    "路线编号",
                    "车辆",
                    "车型",
                    "场馆数",
                    "装载(kg)",
                    "装载率(%)",
                    "总距离(km)",
                    "总碳排放(kg CO2)",
                    "碳排效率(kg/km)",
                    "碳排强度(g/kg)",
                ]
            ],
            hide_index=True,
            width="stretch",
        )

    with detail_tab_segments:
        for idx, route_result in enumerate(route_results, start=1):
            route_row = route_df.iloc[idx - 1].to_dict() if idx - 1 < len(route_df) else {}
            segment_rows = build_route_segment_rows(route_result, route_context)
            with st.expander(f"{route_row.get('路线编号', f'路线{idx}')}：{route_row.get('车辆', route_result.get('vehicle_name', f'车辆{idx}'))}", expanded=False):
                st.markdown(f"**路线** {route_row.get('路线', '--')}")
                metric_row1, metric_row2, metric_row3, metric_row4 = st.columns(4)
                with metric_row1:
                    st.metric("总装载量", f"{float(route_result.get('total_load_kg', 0) or 0):.1f} kg")
                with metric_row2:
                    st.metric("总距离", f"{float(route_result.get('total_distance_km', 0) or 0):.2f} km")
                with metric_row3:
                    st.metric("总碳排放", f"{float(route_result.get('total_carbon_kg', 0) or 0):.2f} kg CO2")
                with metric_row4:
                    st.metric("碳排效率", f"{float(route_row.get('碳排效率(kg/km)', 0) or 0):.4f} kg/km")

                if segment_rows:
                    segment_df = pd.DataFrame(segment_rows)
                    segment_col1 = st.container()
                    segment_col2 = st.container()
                    with segment_col1:
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
                    with segment_col2:
                        st.dataframe(segment_df, hide_index=True, width="stretch")
                        st.caption("柱状图横坐标使用分段序号，完整路径名称可在下表或悬停提示中查看。")
                else:
                    st.info("该路线暂无可展示的分段测算结果。")

anchor("sec-advice")
with st.container(key="carbon-overview-card-advice"):
    st.subheader("优化建议")
    suggestions: list[str] = []
    diagnostic_rows: list[dict[str, str]] = []

    fleet_used_by_type = result.get("fleet_used_by_type", {}) or {}
    if not fleet_used_by_type:
        for route_result in route_results:
            vehicle_type_id = get_vehicle_type_id(route_result)
            fleet_used_by_type[vehicle_type_id] = fleet_used_by_type.get(vehicle_type_id, 0) + 1

    if fleet_used_by_type:
        suggest_type = max(fleet_used_by_type.items(), key=lambda item: item[1])[0]
        suggestions.extend(
            generate_optimization_suggestions(
                total_carbon_kg=total_emission,
                vehicle_type=suggest_type,
                total_distance_km=total_distance,
            )
        )

    if highest_emission_route and total_emission > 0:
        highest_route_share = float(highest_emission_route["总碳排放(kg CO2)"] or 0) / total_emission * 100
        diagnostic_rows.append(
            {
                "诊断维度": "最高排放路线占比",
                "当前值": f"{highest_route_share:.1f}%",
                "业务解读": "占比过高时，应优先从该路线寻找减排空间。",
            }
        )
        if highest_route_share >= 35:
            suggestions.append(
                f"{highest_emission_route['路线编号']} 占总碳排 {highest_route_share:.1f}% ，建议优先复核其经停顺序、回程空驶和中转仓配置。"
            )

    if avg_utilization > 0:
        diagnostic_rows.append(
            {
                "诊断维度": "平均装载率",
                "当前值": f"{avg_utilization:.1f}%",
                "业务解读": "装载率偏低会推高单位里程碳排，可通过并单和回程复用改善。",
            }
        )
        if avg_utilization < 75:
            suggestions.append("当前平均装载率偏低，建议优先合并低载路线，并检查是否存在回程空驶。")

    if has_trunk_breakdown and total_emission > 0:
        trunk_share = trunk_emission / total_emission * 100
        diagnostic_rows.append(
            {
                "诊断维度": "干线碳排占比",
                "当前值": f"{trunk_share:.1f}%",
                "业务解读": "可用来判断中转仓补给是否带来了额外排放压力。",
            }
        )
        if trunk_share > 25:
            suggestions.append("干线补给碳排占比较高，建议复核中转仓选址半径和补给频次。")

    if highest_intensity_route and avg_emission_per_km > 0:
        highest_intensity = float(highest_intensity_route["碳排效率(kg/km)"] or 0)
        if highest_intensity > avg_emission_per_km * 1.2:
            suggestions.append(
                f"{highest_intensity_route['路线编号']} 的单位里程碳排显著高于平均水平，建议优先检查该线路的绕行与低载问题。"
            )

    if not suggestions:
        suggestions.append("当前路线结构已较均衡，可继续围绕高频场馆需求波动做滚动复盘。")
        suggestions.append("建议定期对分段碳排与装载率做联动监控，及时发现低效路线。")

    advice_col1, advice_col2 = st.columns([1.02, 0.98])
    with advice_col1:
        if diagnostic_rows:
            st.dataframe(pd.DataFrame(diagnostic_rows), hide_index=True, width="stretch")
        else:
            st.info("当前暂无可展示的诊断结果。")
    with advice_col2:
        for suggestion in list(dict.fromkeys(suggestions)):
            st.markdown(f"- {suggestion}")

st.caption(f"数据来源：路径优化结果 | 计算时间：{result.get('timestamp', '未知')}")
render_page_nav("pages/7_path_optimization.py", "pages/5_carbon_analysis.py", key_prefix="carbon-overview-nav")
