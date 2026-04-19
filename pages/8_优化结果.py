"""优化结果页面 - 最终结果展示与导出"""
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import json

from utils.vehicle_lib import VEHICLE_LIB

st.set_page_config(page_title="优化结果", page_icon="", layout="wide")
st.title(" 第八步：优化结果汇总")
st.markdown("物流优化最终结果展示 + 方案导出")

# 动力类型映射
POWER_TYPE_MAPPING = {
    "diesel": "柴油重卡",
    "lng": "LNG天然气重卡",
    "hev": "混合动力 (HEV)",
    "phev": "插电混动 (PHEV)",
    "bev": "纯电动 (BEV)",
    "fcev": "氢燃料电池 (FCEV)",
}

def translate_vehicle_type(vtype: str) -> str:
    """将底层变量名翻译为优美的中文"""
    if not vtype:
        return ""
    clean_vtype = str(vtype).split('_')[0].lower()
    return POWER_TYPE_MAPPING.get(clean_vtype, vtype)

def format_route_with_arrows(stops, start_label="总仓库", end_label="总仓库") -> str:
    route_points = [start_label] + list(stops) + [end_label]
    return " → ".join(route_points)

# ===================== 读取结果 =====================
results = st.session_state.get("optimization_results") or st.session_state.get("results")

if not results or not isinstance(results, dict):
    st.warning(" 尚未执行路径优化，请先完成第五步")
    st.info("请在左侧导航选择第五步，完成优化计算后再查看最终结果。")
    st.stop()

route_results = results.get("route_results", [])
depot_results = results.get("depot_results", [])
nodes = results.get("nodes", [])

if not route_results:
    st.error(" 无可用的路线数据")
    st.stop()

# ===================== 核心指标卡片 =====================
st.markdown("###  优化结果总览")

total_emission = results.get("total_emission", 0)
baseline_emission = results.get("baseline_emission", 0)
total_distance = results.get("total_distance_km", 0)
reduction_pct = results.get("reduction_percent", 0)
num_vehicles = results.get("num_vehicles_used", 0)
carbon_reduction = baseline_emission - total_emission

# 碳等效换算（12 kg CO2/棵年）
try:
    from utils.carbon_calc import carbon_equivalents
    equiv = carbon_equivalents(total_emission)
    tree_count = equiv.get("trees_per_year", total_emission / 12.0)
except Exception:
    tree_count = total_emission / 12.0

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric(" 总碳排放", f"{total_emission:.2f}", help="单位：kg CO₂")
with col2:
    st.metric(" 基线碳排放", f"{baseline_emission:.2f}", help="单位：kg CO₂")
with col3:
    st.metric(" 减排比例", f"{reduction_pct:.1f}%",
              delta=f"-{carbon_reduction:.2f} kg")
with col4:
    st.metric(" 总行驶距离", f"{total_distance:.2f}", help="单位：km")
with col5:
    st.metric(" 等效种树", f"{tree_count:.1f} 棵", help="12 kg CO₂/棵年")

st.markdown("---")

# ===================== 优化方案信息 =====================
st.markdown("###  优化方案信息")

fleet_used_by_type = results.get("fleet_used_by_type", {}) or {}
fleet_max_by_type = results.get("fleet_max_by_type", {}) or {}

info_data = {
    "优化算法": results.get("optimization_method", "未知"),
    "距离计算方法": results.get("distance_method", "未知"),
    "选址方法": results.get("clustering_method", "未知"),
    "计算时间": results.get("timestamp", "未知"),
}
df_info = pd.DataFrame(list(info_data.items()), columns=["配置项", "值"])
st.dataframe(df_info, width="stretch", hide_index=True)

if fleet_used_by_type or fleet_max_by_type:
    st.markdown("####  车队派车组成（实际 / 上限）")
    all_types = sorted(set(list(fleet_max_by_type.keys()) + list(fleet_used_by_type.keys())))
    rows = []
    for vtype in all_types:
        used = int(fleet_used_by_type.get(vtype, 0) or 0)
        cap = int(fleet_max_by_type.get(vtype, 0) or 0)
        rows.append({
            "动力类型": POWER_TYPE_MAPPING.get(vtype, vtype),
            "实际派车数": used,
            "可用上限": cap,
            "闲置车辆数": max(cap - used, 0),
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

st.markdown("---")

# ===================== 中转仓选址结果 =====================
if depot_results:
    st.markdown("###  中转仓选址结果")
    st.info(f"共设置 **{len(depot_results)}** 个中转仓")

    df_depot = pd.DataFrame(depot_results)
    st.dataframe(df_depot, width="stretch", hide_index=True)

    # 中转仓地图
    with st.expander(" 中转仓位置地图", expanded=True):
        if nodes:
            center_lat = nodes[0]["lat"]
            center_lng = nodes[0]["lng"]
        else:
            center_lat = sum(d.get("纬度", 0) for d in depot_results) / len(depot_results)
            center_lng = sum(d.get("经度", 0) for d in depot_results) / len(depot_results)

        m_depot = folium.Map(location=[center_lat, center_lng], zoom_start=11)

        # 总仓库
        if nodes:
            wh = nodes[0]
            folium.Marker(
                [wh["lat"], wh["lng"]],
                popup=f"<b>总仓库: {wh.get('name', '')}</b>",
                tooltip="总仓库",
                icon=folium.Icon(color="darkred", icon="star"),
            ).add_to(m_depot)

        # 中转仓
        depot_colors = ["red", "blue", "green", "purple", "orange", "cadetblue"]
        for i, depot in enumerate(depot_results):
            d_lat = depot.get("纬度", 0)
            d_lng = depot.get("经度", 0)
            if d_lat != 0 and d_lng != 0:
                popup_html = (
                    f"<b>{depot.get('中转仓编号', f'中转仓{i+1}')}</b><br>"
                    f"地址：{depot.get('建议地址', '未知')}<br>"
                    f"坐标：({d_lng:.6f}, {d_lat:.6f})<br>"
                    f"服务场馆数：{depot.get('服务场馆数', 0)}<br>"
                    f"服务场馆：{depot.get('服务场馆列表', '')}<br>"
                    f"物资总量：{depot.get('物资总量(kg)', 0):,.0f} kg"
                )
                color = depot_colors[i % len(depot_colors)]
                folium.Marker(
                    [d_lat, d_lng],
                    popup=folium.Popup(popup_html, max_width=350),
                    tooltip=depot.get("中转仓编号", f"中转仓{i+1}"),
                    icon=folium.Icon(color=color, icon="home", prefix="fa"),
                ).add_to(m_depot)

        st_folium(m_depot, width="100%", height=450)

    st.markdown("---")

# ===================== Tab展示 =====================
tab_map, tab_schedule, tab_carbon, tab_export = st.tabs([
    " 完整路线地图", " 详细调度表", " 碳排放汇总", " 数据导出"
])

# ===== Tab 1: 完整路线地图 =====
with tab_map:
    st.subheader(" 完整物流路线地图")
    if nodes:
        center_lat = sum(nd["lat"] for nd in nodes) / len(nodes)
        center_lng = sum(nd["lng"] for nd in nodes) / len(nodes)
        m = folium.Map(location=[center_lat, center_lng], zoom_start=12)

        colors = ["red", "blue", "green", "purple", "orange", "darkred",
                   "cadetblue", "pink", "darkblue", "darkgreen"]

        # 总仓库
        wh_node = nodes[0]
        folium.Marker(
            [wh_node["lat"], wh_node["lng"]],
            popup=f"<b> 总仓库: {wh_node['name']}</b><br>{wh_node.get('address', '')}",
            tooltip="总仓库",
            icon=folium.Icon(color="darkred", icon="star"),
        ).add_to(m)

        # 中转仓标记
        for depot in depot_results:
            d_lat = depot.get("纬度", 0)
            d_lng = depot.get("经度", 0)
            if d_lat != 0 and d_lng != 0:
                folium.Marker(
                    [d_lat, d_lng],
                    popup=f"<b>{depot.get('中转仓编号', '')}</b><br>{depot.get('建议地址', '')}",
                    tooltip=depot.get("中转仓编号", "中转仓"),
                    icon=folium.Icon(color="red", icon="home", prefix="fa"),
                ).add_to(m)

        # 场馆
        for nd in nodes[1:]:
            folium.CircleMarker(
                [nd["lat"], nd["lng"]],
                radius=8, color="blue", fill=True, fillOpacity=0.7,
                popup=f"<b>{nd['name']}</b>",
                tooltip=nd["name"],
            ).add_to(m)

        # 路线
        for i, rr in enumerate(route_results):
            color = colors[i % len(colors)]
            route_coords = rr.get("route_coords", [])
            if len(route_coords) >= 2:
                folium.PolyLine(
                    route_coords, color=color, weight=4, opacity=0.8,
                    popup=f"{rr['vehicle_name']}: {rr['total_distance_km']:.2f}km",
                ).add_to(m)

        st_folium(m, width="100%", height=550)
    else:
        st.info("无节点数据")

# ===== Tab 2: 详细调度表 =====
with tab_schedule:
    st.subheader(" 车辆调度明细")
    for rr in route_results:
        label = f" {rr['vehicle_name']}（{translate_vehicle_type(rr['vehicle_type'])}）"
        with st.expander(label, expanded=True):
            route_str = format_route_with_arrows(rr.get("visits", []), start_label="总仓库", end_label="总仓库")
            st.markdown(f"**路线：** {route_str}")

            load_details = rr.get("load_details", [])
            if load_details:
                # 动态列：优先使用 optimization result 中保存的物资列顺序，其次使用 session_state
                material_columns = results.get("material_columns") or st.session_state.get("material_columns") or ["通用赛事物资", "专项运动器材", "医疗物资", "IT设备"]
                expected_columns = ["场馆"] + [f"{c}(kg)" for c in material_columns] + ["小计(kg)"]

                rows = []
                for stop in load_details:
                    row = {"场馆": stop.get("venue", "")}
                    for c in material_columns:
                        row[f"{c}(kg)"] = float(stop.get(c, 0) or 0)
                    row["小计(kg)"] = sum(row[f"{c}(kg)"] for c in material_columns)
                    rows.append(row)

                df_detail = pd.DataFrame(rows)
                # 强制列顺序并填补缺失
                if df_detail.empty:
                    df_detail = pd.DataFrame(columns=expected_columns)
                else:
                    for col in expected_columns:
                        if col not in df_detail.columns:
                            df_detail[col] = 0
                    df_detail = df_detail[expected_columns]

                # 添加合计行
                if not df_detail.empty:
                    total_row = {col: (df_detail[col].sum() if col != "场馆" else "合计") for col in expected_columns}
                    df_detail = pd.concat([df_detail, pd.DataFrame([total_row])], ignore_index=True)

                st.dataframe(df_detail.fillna(0), width="stretch", hide_index=True)

            col1, col2, col3 = st.columns(3)
            with col1:
                cap = rr.get("vehicle_capacity_kg", results.get("vehicle_capacity_kg", 15000))
                load = rr.get("total_load_kg", 0)
                util = (load / cap * 100) if cap > 0 else 0
                st.metric("装载量", f"{load:.0f} kg", delta=f"利用率 {util:.0f}%")
            with col2:
                st.metric("行驶距离", f"{rr['total_distance_km']:.2f} km")
            with col3:
                st.metric("碳排放", f"{rr['total_carbon_kg']:.2f} kg CO₂")

    # 汇总表
    st.markdown("---")
    st.subheader(" 汇总表")
    summary_rows = [{
        "指令编号": rr["vehicle_name"], 
        "派发车型": translate_vehicle_type(rr["vehicle_type"]),
        "规划路径": format_route_with_arrows(rr.get("visits", [])),
        "作业网点数": len(rr.get("visits", [])),
        "装载负荷(kg)": rr["total_load_kg"],
        "行车距离(km)": rr["total_distance_km"],
        "单车碳排(kg CO₂)": rr["total_carbon_kg"],
    } for rr in route_results]
    st.dataframe(pd.DataFrame(summary_rows), width="stretch", hide_index=True)

# ===== Tab 3: 碳排放汇总 =====
with tab_carbon:
    st.subheader(" 碳排放汇总分析")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("优化碳排放", f"{total_emission:.2f} kg CO₂")
    with col2:
        st.metric("基线碳排放", f"{baseline_emission:.2f} kg CO₂")
    with col3:
        st.metric("减排量", f"{carbon_reduction:.2f} kg CO₂",
                  delta=f"-{reduction_pct:.1f}%")

    import plotly.express as px

    # 碳对比柱状图
    df_carbon = pd.DataFrame({
        "方案": ["基线方案（单独配送）", "优化方案（FSMVRP调度）"],
        "碳排放(kg CO₂)": [baseline_emission, total_emission],
    })
    fig = px.bar(df_carbon, x="方案", y="碳排放(kg CO₂)", color="方案",
                 title="碳排放对比", text_auto=True,
                 color_discrete_sequence=["#EF553B", "#00CC96"])
    fig.update_layout(showlegend=False, height=400)
    st.plotly_chart(fig, width="stretch")

    # 碳等效
    st.markdown("####  碳排放等效换算")
    st.markdown(f"""
    | 指标 | 数值 |
    |------|------|
    | 优化碳排放 | **{total_emission:.2f} kg CO₂** |
    | 等效种树 | **{tree_count:.1f} 棵**（12 kg CO₂/棵年） |
    | 等效驾驶 | **{total_emission / 0.21:.1f} km**（普通轿车） |
    | 减排等效种树 | **{carbon_reduction / 12.0:.1f} 棵** |
    """)

# ===== Tab 4: 数据导出 =====
with tab_export:
    st.subheader(" 数据导出")
    st.markdown("将优化结果导出为CSV文件，便于后续分析和报告。")

    col_e1, col_e2 = st.columns(2)

    # 导出1: 车辆调度表
    with col_e1:
        st.markdown("** 车辆调度表**")
        csv_rows = []
        for rr in route_results:
            route_str = format_route_with_arrows(rr.get("visits", []), start_label="总仓库", end_label="总仓库")
            csv_rows.append({
                "车辆编号": rr["vehicle_name"],
                "车型": translate_vehicle_type(rr["vehicle_type"]),
                "路线": route_str,
                "访问场馆数": len(rr.get("visits", [])),
                "装载量(kg)": rr["total_load_kg"],
                "距离(km)": rr["total_distance_km"],
                "碳排放(kg CO₂)": rr["total_carbon_kg"],
            })
        df_dispatch = pd.DataFrame(csv_rows)
        st.download_button(
            " 下载车辆调度表",
            data=df_dispatch.to_csv(index=False, encoding="utf-8-sig"),
            file_name="车辆调度表.csv", mime="text/csv",
        )

    # 导出2: 中转仓选址结果
    with col_e2:
        st.markdown("** 中转仓选址表**")
        if depot_results:
            df_depot_export = pd.DataFrame(depot_results)
            st.download_button(
                " 下载中转仓选址表",
                data=df_depot_export.to_csv(index=False, encoding="utf-8-sig"),
                file_name="中转仓选址表.csv", mime="text/csv",
            )
        else:
            st.info("无中转仓数据")

    # 导出3: 碳排放汇总
    st.markdown("---")
    st.markdown("** 碳排放汇总表**")
    carbon_summary = [{
        "指标": "优化碳排放", "值": f"{total_emission:.2f}", "单位": "kg CO₂",
    }, {
        "指标": "基线碳排放", "值": f"{baseline_emission:.2f}", "单位": "kg CO₂",
    }, {
        "指标": "减排量", "值": f"{carbon_reduction:.2f}", "单位": "kg CO₂",
    }, {
        "指标": "减排比例", "值": f"{reduction_pct:.1f}", "单位": "%",
    }, {
        "指标": "等效种树", "值": f"{tree_count:.1f}", "单位": "棵/年(12 kg CO₂/棵)",
    }, {
        "指标": "总行驶距离", "值": f"{total_distance:.2f}", "单位": "km",
    }, {
        "指标": "使用车辆数", "值": f"{num_vehicles}", "单位": "辆",
    }]
    df_carbon_export = pd.DataFrame(carbon_summary)
    st.download_button(
        " 下载碳排放汇总表",
        data=df_carbon_export.to_csv(index=False, encoding="utf-8-sig"),
        file_name="碳排放汇总表.csv", mime="text/csv",
    )

    # 导出4: 完整JSON
    st.markdown("---")
    st.markdown("** 完整优化结果 (JSON)**")
    json_result = {
        "total_emission": total_emission,
        "baseline_emission": baseline_emission,
        "reduction_percent": reduction_pct,
        "total_distance_km": total_distance,
        "num_vehicles": num_vehicles,
        "fleet_used_by_type": fleet_used_by_type,
        "fleet_max_by_type": fleet_max_by_type,
        "optimization_method": results.get("optimization_method", ""),
        "timestamp": results.get("timestamp", ""),
        "depot_count": len(depot_results),
        "route_count": len(route_results),
    }
    st.download_button(
        " 下载完整结果 (JSON)",
        data=json.dumps(json_result, ensure_ascii=False, indent=2),
        file_name="optimization_result.json", mime="application/json",
    )

st.markdown("---")
st.caption(f"优化结果 | 计算时间：{results.get('timestamp', '未知')} | "
           f"树等效标准：12 kg CO₂/棵年")

st.markdown("---")
if st.button("返回首页 🏠", type="primary", width="stretch"):
    st.switch_page("app.py")