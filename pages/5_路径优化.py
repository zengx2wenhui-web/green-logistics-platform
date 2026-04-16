"""路径优化页面 - 执行VRP优化计算

核心特性：
- 移除 sidebar API密钥输入（避免页面自动刷新）
- 使用贪心最近邻 VRP 求解器（稳定可靠，无外部依赖）
- 使用 utils.distance_matrix 构建距离矩阵
- 使用 utils.clustering 进行中转仓选址
- 中转仓结果完整保存（坐标、地址、服务场馆）
- 碳排放使用标准公式精确计算（逐站载重递减）
- API密钥存入 session_state 防止页面刷新丢失
"""
import streamlit as st
import pandas as pd
import math
import folium
from streamlit_folium import st_folium
from datetime import datetime

st.set_page_config(page_title="路径优化", page_icon="")
st.title(" 第五步：路径优化")
st.markdown("执行物流网络优化计算（K-Means选址 + 贪心最近邻VRP）")


# ===================== 数据完整性检查 =====================
st.markdown("###  数据完整性检查")

warehouse = st.session_state.get("warehouse", {})
venues = st.session_state.get("venues", [])
demands = st.session_state.get("demands", {})
vehicles = st.session_state.get("vehicles", [])

col1, col2, col3, col4 = st.columns(4)
with col1:
    if warehouse.get("lng"):
        st.success(" 仓库已设置")
    else:
        st.error(" 仓库未设置")
with col2:
    st.info(f" {len(venues)} 个场馆")
with col3:
    total_demand = 0.0
    for v in demands.values():
        if isinstance(v, dict):
            total_demand += v.get("总需求", sum(val for val in v.values() if isinstance(val, (int, float))))
        else:
            total_demand += float(v)
    st.metric("总需求", f"{total_demand:,.0f} kg")
with col4:
    total_vehicles = sum(v.get("count", 0) for v in vehicles)
    st.metric("车辆数", f"{total_vehicles} 辆")

# 检查数据是否完整
missing = []
if not warehouse.get("lng"):
    missing.append("仓库坐标")
if len(venues) == 0:
    missing.append("场馆")
if not demands:
    missing.append("物资需求")
if len(vehicles) == 0:
    missing.append("车辆配置")

if missing:
    st.warning(f" 数据不完整：{'、'.join(missing)}")
    st.info("请先完成第一步~第四步的数据录入")
    st.stop()

st.success(" 数据完整，可以开始优化")
st.markdown("---")

# ===================== 优化参数（主区域，不在侧边栏） =====================
st.markdown("###  优化参数设置")

col_p1, col_p2 = st.columns(2)
with col_p1:
    api_key = st.text_input(
        "高德API密钥（可选，用于逆地理编码）",
        value=st.session_state.get("api_key_amap", ""),
        type="password",
        help="不填则中转仓地址仅显示坐标，不影响路径优化计算",
        key="api_key_input",
    )
    if api_key:
        st.session_state.api_key_amap = api_key

with col_p2:
    time_limit = st.slider("求解时间上限（秒）", 10, 120, 60,
                           help="贪心算法通常几秒内完成，此参数为预留扩展")

st.markdown("---")

# ===================== 开始优化 =====================
st.markdown("###  执行优化计算")

if st.button(" 开始优化计算", type="primary", width="stretch"):
    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        # ======== Step A: 构建节点列表 ========
        status_text.text(" 步骤A: 构建节点列表...")
        progress_bar.progress(0.05)

        nodes = [{
            "name": warehouse.get("name", "总仓库"),
            "lng": warehouse["lng"], "lat": warehouse["lat"],
            "address": warehouse.get("address", ""),
            "is_warehouse": True,
        }]
        node_demands = [0.0]

        venues_with_coords = []
        for v in venues:
            if v.get("lng") is not None and v.get("lat") is not None:
                venues_with_coords.append(v)
                nodes.append({
                    "name": v["name"], "lng": v["lng"], "lat": v["lat"],
                    "address": v.get("address", ""), "is_warehouse": False,
                })
                venue_demand = demands.get(v["name"], {})
                if isinstance(venue_demand, dict):
                    total = venue_demand.get("总需求", sum(
                        val for val in venue_demand.values() if isinstance(val, (int, float))
                    ))
                else:
                    total = float(venue_demand)
                node_demands.append(total)

        n = len(nodes)
        if n < 2:
            st.error(" 需要至少1个有坐标的场馆")
            st.stop()

        coords = [(nd["lng"], nd["lat"]) for nd in nodes]
        skipped = len(venues) - len(venues_with_coords)
        st.success(f" 节点构建完成：1个仓库 + {n - 1}个场馆" +
                   (f"（跳过{skipped}个无坐标场馆）" if skipped else ""))
        progress_bar.progress(0.10)

        # ======== Step B: 构建距离矩阵 ========
        status_text.text(" 步骤B: 构建距离矩阵...")
        progress_bar.progress(0.15)

        from utils.distance_matrix import build_distance_matrix_from_coords

        def dm_progress(prog, msg):
            progress_bar.progress(0.15 + 0.20 * prog)
            status_text.text(f" {msg}")

        distance_matrix = build_distance_matrix_from_coords(
            coords, road_factor=1.3, progress_callback=dm_progress,
        )
        distance_method = "Haversine  1.3"
        st.session_state.distance_matrix = distance_matrix

        st.success(f" 距离矩阵构建完成 ({n}{n})，方法: {distance_method}")
        progress_bar.progress(0.35)

        # ======== Step C: K-Means 中转仓选址 ========
        status_text.text(" 步骤C: K-Means 中转仓选址...")
        progress_bar.progress(0.40)

        venue_nodes = [nd for nd in nodes if not nd.get("is_warehouse")]
        depot_results = []  # 中转仓结果列表

        if len(venue_nodes) <= 5:
            optimal_k = 1
            clustering_method = "场馆数5，无需中转仓"
            st.info("ℹ 场馆数量5，不设中转仓，直接从仓库配送")
        else:
            try:
                from utils.clustering import select_warehouse_locations

                venue_coords = [(v["lng"], v["lat"]) for v in venue_nodes]
                venue_weights = [node_demands[i + 1] for i in range(len(venue_nodes))]

                clustering_result = select_warehouse_locations(
                    venue_coords, venue_weights, max_warehouses=6,
                )
                st.session_state.clustering_result = clustering_result

                optimal_k = clustering_result.get("optimal_k", 1)
                clustering_method = f"加权K-Means (K={optimal_k})"
                st.success(f" 选址完成，最优中转仓数量: {optimal_k}")

                # 构建中转仓详情（含坐标、地址、服务场馆）
                if optimal_k >= 1 and clustering_result.get("warehouses"):
                    labels = clustering_result.get("labels", [])
                    for i, wh in enumerate(clustering_result["warehouses"]):
                        wh_lng = wh.get("lng", 0)
                        wh_lat = wh.get("lat", 0)

                        # 获取地址（逆地理编码）
                        address = f"({wh_lng:.4f}, {wh_lat:.4f})"
                        if api_key:
                            try:
                                from utils.amap_api import reverse_geocode
                                addr = reverse_geocode(wh_lng, wh_lat, api_key)
                                if addr and "未知" not in addr:
                                    address = addr
                            except Exception:
                                pass

                        # 获取服务的场馆列表
                        served_indices = wh.get("venues", [])
                        served_names = [venue_nodes[j]["name"] for j in served_indices if j < len(venue_nodes)]
                        served_str = "、".join(served_names[:5])
                        if len(served_names) > 5:
                            served_str += f"等{len(served_names)}个"

                        depot_results.append({
                            "中转仓编号": f"中转仓{i + 1}",
                            "建议地址": address,
                            "经度": round(wh_lng, 6),
                            "纬度": round(wh_lat, 6),
                            "服务场馆数": len(served_names),
                            "服务场馆列表": served_str,
                            "物资总量(kg)": round(wh.get("weight", 0), 1),
                        })

                    st.markdown("** 中转仓选址结果：**")
                    st.dataframe(pd.DataFrame(depot_results), width="stretch", hide_index=True)

            except Exception as e:
                st.warning(f"K-Means选址异常: {e}，将直接从仓库配送")
                optimal_k = 1
                clustering_method = "选址失败，无中转仓"

        progress_bar.progress(0.50)

        # ======== Step D: VRP 求解 ========
        status_text.text(" 步骤D: VRP求解...")
        progress_bar.progress(0.55)

        # 获取车辆配置
        if vehicles:
            v = vehicles[0]
            vehicle_type = v.get("vehicle_type", "diesel_heavy")
            vehicle_name = v.get("name", vehicle_type)
            emission_factor = v.get("emission_factor", 0.060)
            load_ton = v.get("load_ton", 15.0)
            vehicle_capacity = int(load_ton * 1000)
            num_vehicles = sum(vv.get("count", 0) for vv in vehicles)
        else:
            vehicle_type, vehicle_name = "diesel_heavy", "柴油重卡"
            emission_factor, load_ton = 0.060, 15.0
            vehicle_capacity, num_vehicles = 15000, 3

        if num_vehicles <= 0:
            num_vehicles = 3
        if vehicle_capacity <= 0:
            vehicle_capacity = 15000

        demands_list = node_demands
        optimization_method = "贪心最近邻"
        routes = []

        # 使用 VRP 求解器（贪心最近邻算法）
        try:
            from utils.vrp_solver import solve_green_cvrp
            status_text.text(" 步骤D: VRP 求解中...")

            result = solve_green_cvrp(
                distance_matrix=distance_matrix,
                demands=demands_list,
                vehicle_capacity=vehicle_capacity,
                num_vehicles=num_vehicles,
                vehicle_type=vehicle_type,
                time_limit_seconds=time_limit,
            )
            if result and result.get("success"):
                routes = result["routes"]
                optimization_method = "贪心最近邻 VRP"
                st.success(f" VRP求解成功，生成 {len(routes)} 条路线")
            else:
                st.warning("VRP求解未找到可行解，请检查数据")
        except Exception as e:
            st.warning(f"VRP求解异常: {e}")

        if not routes:
            st.error(" 未生成有效路线，请检查车辆数量和载重配置")
            st.stop()

        progress_bar.progress(0.65)

        # ======== Step E: 生成调度方案和碳排放计算 ========
        status_text.text(" 步骤E: 生成调度方案...")
        progress_bar.progress(0.70)

        route_results = []
        for vehicle_idx, route in enumerate(routes):
            route_info = {
                "vehicle_id": vehicle_idx + 1,
                "vehicle_name": f"车辆{vehicle_idx + 1}",
                "vehicle_type": vehicle_name,
                "emission_factor": emission_factor,
                "route": route,
                "visits": [],
                "load_details": [],
                "total_load_kg": 0,
                "total_distance_km": 0,
                "total_carbon_kg": 0,
                "route_coords": [],
            }

            for stop_idx in route:
                node = nodes[stop_idx]
                route_info["route_coords"].append([node["lat"], node["lng"]])
                if stop_idx == 0:
                    continue
                venue_name = node["name"]
                venue_demand = demands.get(venue_name, {})
                if isinstance(venue_demand, dict):
                    detail = {
                        "venue": venue_name,
                        "general_materials_kg": venue_demand.get("通用赛事物资", 0),
                        "sports_equipment_kg": venue_demand.get("专项运动器材", 0),
                        "medical_materials_kg": venue_demand.get("医疗物资", 0),
                        "it_equipment_kg": venue_demand.get("IT设备", 0),
                    }
                    total_venue = venue_demand.get("总需求", sum(
                        val for val in venue_demand.values() if isinstance(val, (int, float))
                    ))
                else:
                    total_venue = float(venue_demand)
                    detail = {
                        "venue": venue_name, "general_materials_kg": total_venue,
                        "sports_equipment_kg": 0, "medical_materials_kg": 0, "it_equipment_kg": 0,
                    }
                route_info["visits"].append(venue_name)
                route_info["load_details"].append(detail)
                route_info["total_load_kg"] += total_venue

            # 碳排放精确计算（逐站载重递减）
            total_distance = 0.0
            total_carbon = 0.0
            current_load_kg = route_info["total_load_kg"]
            for i in range(len(route) - 1):
                from_idx, to_idx = route[i], route[i + 1]
                dist = distance_matrix[from_idx][to_idx]
                load_ton_val = current_load_kg / 1000.0
                carbon = dist * emission_factor * load_ton_val
                total_distance += dist
                total_carbon += carbon
                current_load_kg -= demands_list[to_idx]
                current_load_kg = max(current_load_kg, 0.0)

            route_info["total_distance_km"] = round(total_distance, 2)
            route_info["total_carbon_kg"] = round(total_carbon, 4)
            route_results.append(route_info)

        progress_bar.progress(0.80)

        # ======== Step F: 碳排放对比 ========
        status_text.text(" 步骤F: 碳排放对比...")

        # 基线碳排放（柴油车单独配送）
        baseline_ef = 0.080
        baseline_distance = sum(
            distance_matrix[0][i] + distance_matrix[i][0] for i in range(1, n)
        )
        baseline_carbon = sum(demands_list) / 1000 * baseline_distance * baseline_ef

        optimized_carbon = sum(r["total_carbon_kg"] for r in route_results)
        carbon_reduction = baseline_carbon - optimized_carbon
        reduction_pct = (carbon_reduction / baseline_carbon * 100) if baseline_carbon > 0 else 0

        progress_bar.progress(0.90)

        # ======== 保存结果 ========
        status_text.text(" 保存结果...")

        opt_result = {
            "route_results": route_results,
            "total_emission": optimized_carbon,
            "baseline_emission": baseline_carbon,
            "reduction_percent": reduction_pct,
            "total_distance_km": sum(r["total_distance_km"] for r in route_results),
            "num_vehicles_used": len(routes),
            "optimization_method": optimization_method,
            "distance_method": distance_method,
            "clustering_method": clustering_method,
            "vehicle_type": vehicle_name,
            "vehicle_capacity_kg": vehicle_capacity,
            "emission_factor": emission_factor,
            "nodes": nodes,
            "routes": routes,
            "demands": demands,
            "depot_results": depot_results,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        st.session_state["optimization_results"] = opt_result
        st.session_state["results"] = opt_result

        progress_bar.progress(1.0)
        status_text.text(" 优化完成！")
        st.balloons()

        # 简要结果
        st.markdown("---")
        st.success(" **优化计算完成！**")
        col_r1, col_r2, col_r3, col_r4 = st.columns(4)
        with col_r1:
            st.metric("总距离", f"{opt_result['total_distance_km']:.2f} km")
        with col_r2:
            st.metric("总碳排放", f"{opt_result['total_emission']:.2f} kg CO₂")
        with col_r3:
            st.metric("使用车辆", f"{opt_result['num_vehicles_used']} 辆")
        with col_r4:
            st.metric("减排比例", f"{opt_result['reduction_percent']:.1f}%")

        # 导出按钮
        st.markdown("---")
        csv_data = []
        for rr in route_results:
            route_str = "总仓库  " + "  ".join(rr["visits"]) + "  总仓库"
            csv_data.append({
                "车辆编号": rr["vehicle_name"], "车型": rr["vehicle_type"],
                "路线": route_str, "访问场馆数": len(rr["visits"]),
                "总装载量(kg)": rr["total_load_kg"],
                "总距离(km)": rr["total_distance_km"],
                "总碳排放(kg CO₂)": rr["total_carbon_kg"],
            })
        df_csv = pd.DataFrame(csv_data)
        st.download_button(
            " 下载车辆调度表(CSV)",
            data=df_csv.to_csv(index=False, encoding="utf-8-sig"),
            file_name="vehicle_dispatch.csv", mime="text/csv",
        )

    except Exception as e:
        st.error(f"优化过程出错: {e}")
        import traceback
        with st.expander("错误详情"):
            st.code(traceback.format_exc())

# ===================== 结果展示（从 session_state 持久读取） =====================
res = st.session_state.get("optimization_results") or st.session_state.get("results")
if res and isinstance(res, dict) and res.get("route_results"):
    results = res
    st.markdown("---")
    st.markdown("###  优化结果")

    route_results_list = results.get("route_results", [])
    nodes_list = results.get("nodes", [])
    depot_results_list = results.get("depot_results", [])

    # 中转仓选址结果表格
    if depot_results_list:
        st.subheader(" 中转仓选址结果")
        st.dataframe(pd.DataFrame(depot_results_list), width="stretch", hide_index=True)

    # Tab 展示
    tab_map, tab_table, tab_carbon = st.tabs([" 路线地图", " 车辆调度详情", " 碳排放对比"])

    # ===== 路线地图 =====
    with tab_map:
        st.subheader(" 物流路线地图")
        if nodes_list:
            center_lat = sum(nd["lat"] for nd in nodes_list) / len(nodes_list)
            center_lng = sum(nd["lng"] for nd in nodes_list) / len(nodes_list)
            m = folium.Map(location=[center_lat, center_lng], zoom_start=12)

            colors = ["red", "blue", "green", "purple", "orange", "darkred",
                       "cadetblue", "pink", "darkblue", "darkgreen"]

            # 标记总仓库
            wh_node = nodes_list[0]
            folium.Marker(
                [wh_node["lat"], wh_node["lng"]],
                popup=f"<b> {wh_node['name']}</b><br>{wh_node.get('address', '')}",
                tooltip="总仓库",
                icon=folium.Icon(color="darkred", icon="star"),
            ).add_to(m)

            # 标记中转仓
            for depot in depot_results_list:
                d_lat = depot.get("纬度", 0)
                d_lng = depot.get("经度", 0)
                if d_lat != 0 and d_lng != 0:
                    popup_html = (
                        f"<b> {depot.get('中转仓编号', '')}</b><br>"
                        f"地址：{depot.get('建议地址', '')}<br>"
                        f"坐标：({d_lng:.6f}, {d_lat:.6f})<br>"
                        f"服务场馆：{depot.get('服务场馆数', 0)}个<br>"
                        f"物资总量：{depot.get('物资总量(kg)', 0):,.0f} kg"
                    )
                    folium.Marker(
                        [d_lat, d_lng],
                        popup=folium.Popup(popup_html, max_width=300),
                        tooltip=depot.get("中转仓编号", "中转仓"),
                        icon=folium.Icon(color="red", icon="home", prefix="fa"),
                    ).add_to(m)

            # 标记场馆
            for nd in nodes_list[1:]:
                venue_d = results.get("demands", {}).get(nd["name"], 0)
                total_d = venue_d.get("总需求", sum(v for v in venue_d.values() if isinstance(v, (int, float)))) if isinstance(venue_d, dict) else float(venue_d)
                folium.CircleMarker(
                    [nd["lat"], nd["lng"]],
                    radius=8, color="blue", fill=True, fillOpacity=0.7,
                    popup=f"<b> {nd['name']}</b><br>需求: {total_d:.0f} kg",
                    tooltip=f"{nd['name']} ({total_d:.0f} kg)",
                ).add_to(m)

            # 绘制路线
            for i, rr in enumerate(route_results_list):
                color = colors[i % len(colors)]
                route_coords = rr.get("route_coords", [])
                if len(route_coords) >= 2:
                    folium.PolyLine(
                        route_coords, color=color, weight=4, opacity=0.8,
                        popup=f"{rr['vehicle_name']}: {rr['total_distance_km']:.2f}km",
                    ).add_to(m)

            st_folium(m, width="100%", height=500)
        else:
            st.info("无节点数据")

    # ===== 车辆调度详情 =====
    with tab_table:
        st.subheader(" 车辆调度详情")
        for rr in route_results_list:
            label = f" {rr['vehicle_name']}（{rr['vehicle_type']}）"
            with st.expander(label, expanded=False):
                route_str = "  ".join(["总仓库"] + rr["visits"] + ["总仓库"])
                st.markdown(f"**路线：** {route_str}")
                st.divider()

                load_details = rr.get("load_details", [])
                if load_details:
                    rows = []
                    for stop in load_details:
                        row = {
                            "场馆": stop.get("venue", ""),
                            "通用赛事物资(kg)": stop.get("general_materials_kg", 0),
                            "专项运动器材(kg)": stop.get("sports_equipment_kg", 0),
                            "医疗物资(kg)": stop.get("medical_materials_kg", 0),
                            "IT设备(kg)": stop.get("it_equipment_kg", 0),
                        }
                        row["总需求量(kg)"] = sum(row[k] for k in row if k != "场馆")
                        rows.append(row)
                    detail_df = pd.DataFrame(rows)
                    if not detail_df.empty:
                        total_row = {"场馆": "合计"}
                        for col in detail_df.columns:
                            if col != "场馆":
                                total_row[col] = detail_df[col].sum()
                        detail_df = pd.concat([detail_df, pd.DataFrame([total_row])], ignore_index=True)
                    st.dataframe(detail_df, width="stretch", hide_index=True)

                st.divider()
                col1, col2, col3 = st.columns(3)
                with col1:
                    max_load = results.get("vehicle_capacity_kg", 15000)
                    total_load = rr.get("total_load_kg", 0)
                    util = (total_load / max_load * 100) if max_load > 0 else 0
                    st.metric("总装载量", f"{total_load:.0f} kg", delta=f"利用率 {util:.0f}%")
                with col2:
                    st.metric("行驶距离", f"{rr['total_distance_km']:.2f} km")
                with col3:
                    st.metric("碳排放", f"{rr['total_carbon_kg']:.2f} kg CO₂")

        # 汇总表
        st.markdown("---")
        st.subheader(" 车辆调度汇总")
        summary_rows = [{
            "车辆": rr["vehicle_name"], "车型": rr["vehicle_type"],
            "访问场馆数": len(rr["visits"]), "装载量(kg)": rr["total_load_kg"],
            "距离(km)": rr["total_distance_km"], "碳排放(kg CO₂)": rr["total_carbon_kg"],
        } for rr in route_results_list]
        st.dataframe(pd.DataFrame(summary_rows), hide_index=True, width="stretch")

    # ===== 碳排放对比 =====
    with tab_carbon:
        st.subheader(" 碳排放对比")
        import plotly.express as px

        col_c1, col_c2, col_c3 = st.columns(3)
        baseline = results.get("baseline_emission", 0)
        optimized = results.get("total_emission", 0)
        reduction = baseline - optimized
        pct = results.get("reduction_percent", 0)

        with col_c1:
            st.metric("基线碳排放", f"{baseline:.2f} kg CO₂")
        with col_c2:
            st.metric("优化碳排放", f"{optimized:.2f} kg CO₂")
        with col_c3:
            st.metric("减排量", f"{reduction:.2f} kg CO₂", delta=f"-{pct:.1f}%")

        df_carbon = pd.DataFrame({
            "方案": ["基线方案（单独配送）", "优化方案（VRP调度）"],
            "碳排放(kg CO₂)": [baseline, optimized],
        })
        fig_bar = px.bar(df_carbon, x="方案", y="碳排放(kg CO₂)", color="方案",
                         title="碳排放对比", text_auto=True)
        fig_bar.update_layout(showlegend=False)
        st.plotly_chart(fig_bar, width="stretch")

        # 等效种树（12 kg CO₂/棵年）
        tree_eq = reduction / 12.0
        st.info(f" 减排量相当于种植 **{tree_eq:.1f} 棵树** 一年的吸收量（12 kg CO₂/棵年）")

elif not res:
    st.info(" 完成参数设置后，点击「 开始优化计算」按钮")

st.markdown("---")
if st.button("下一步：碳排放概览 ➡️", type="primary", width="stretch"):
    st.switch_page("pages/6_碳排放概览.py")