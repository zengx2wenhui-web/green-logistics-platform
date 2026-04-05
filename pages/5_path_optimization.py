"""路径优化页面 - 执行VRP优化计算"""
import streamlit as st
import pandas as pd
import math
import folium
from streamlit_folium import st_folium
from datetime import datetime

st.set_page_config(page_title="路径优化", page_icon="🗺️")

st.title("🗺️ Step 5：路径优化")
st.markdown("执行物流网络优化计算")

# ===================== 工具函数 =====================

def haversine_distance(coord1, coord2):
    """计算两点间Haversine距离（公里）"""
    R = 6371.0
    lon1, lat1 = math.radians(coord1[0]), math.radians(coord1[1])
    lon2, lat2 = math.radians(coord2[0]), math.radians(coord2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def build_distance_matrix_haversine(coords):
    """使用Haversine公式构建距离矩阵（道路系数1.3）"""
    n = len(coords)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                matrix[i][j] = haversine_distance(coords[i], coords[j]) * 1.3
    return matrix


def greedy_vrp(distance_matrix, demands_list, vehicle_capacity):
    """贪心最近邻算法"""
    n = len(distance_matrix)
    remaining = demands_list.copy()
    routes = []

    while sum(remaining) > 0:
        route = [0]
        current_load = 0
        current_pos = 0

        while True:
            min_dist = float('inf')
            next_node = -1
            for j in range(1, n):
                if remaining[j] > 0 and distance_matrix[current_pos][j] < min_dist:
                    min_dist = distance_matrix[current_pos][j]
                    next_node = j
            if next_node == -1:
                break
            if current_load + remaining[next_node] <= vehicle_capacity:
                route.append(next_node)
                current_load += remaining[next_node]
                remaining[next_node] = 0
                current_pos = next_node
            else:
                break

        route.append(0)
        if len(route) > 2:
            routes.append(route)

    return routes


# ===================== 数据检查 =====================
st.markdown("### 📊 数据完整性检查")

warehouse = st.session_state.get("warehouse", {})
venues = st.session_state.get("venues", [])
demands = st.session_state.get("demands", {})
vehicles = st.session_state.get("vehicles", [])

col1, col2, col3, col4 = st.columns(4)
with col1:
    if warehouse.get("lng"):
        st.success(f"✅ 仓库已设置")
    else:
        st.error("❌ 仓库未设置")
with col2:
    st.success(f"✅ {len(venues)} 个场馆")
with col3:
    total_demand = sum(demands.values()) if isinstance(demands, dict) else 0
    st.metric("总需求", f"{total_demand:,.0f} kg")
with col4:
    total_vehicles = sum(v.get("count", 0) for v in vehicles) if vehicles else 0
    st.metric("车辆数", f"{total_vehicles} 辆")

# 检查缺失项
missing = []
if not warehouse.get("lng"):
    missing.append("仓库坐标")
if len(venues) == 0:
    missing.append("场馆")
if not demands or len(demands) == 0:
    missing.append("物资需求")
if len(vehicles) == 0:
    missing.append("车辆配置")

if missing:
    st.markdown("---")
    st.warning("⚠️ 数据不完整：" + "、".join(missing))
    st.info("""
    **数据录入流程：**
    1. 🏭 **Step 1 仓库设置** - 设置总仓库地址和坐标
    2. 🏟️ **Step 2 场馆录入** - 录入场馆信息
    3. 📦 **Step 3 物资需求** - 录入各场馆物资需求量
    4. 🚛 **Step 4 车辆配置** - 配置配送车辆类型和数量
    """)
    st.stop()

# ======== 数据完整，显示摘要 ========
st.markdown("---")
st.markdown("### ✅ 数据完整，可以开始优化")

# 显示数据摘要
col_s1, col_s2, col_s3, col_s4 = st.columns(4)
with col_s1:
    st.metric("总仓库地址", warehouse.get("address", "未设置")[:15] + "..." if len(warehouse.get("address", "")) > 15 else warehouse.get("address", "未设置"))
with col_s2:
    st.metric("场馆数量", len(venues))
with col_s3:
    # 各车型车辆数
    vehicle_summary = ", ".join([f"{v.get('name', v.get('vehicle_type', '未知'))}:{v.get('count', 0)}辆" for v in vehicles]) if vehicles else "未配置"
    st.metric("车辆配置", vehicle_summary[:20] + "..." if len(vehicle_summary) > 20 else vehicle_summary)
with col_s4:
    st.metric("总物资需求", f"{total_demand:,.0f} kg")

# ======== 侧边栏参数 ========
st.sidebar.header("优化参数设置")
api_key = st.sidebar.text_input(
    "高德API密钥（可选）",
    type="password",
    help="用于路径规划，不填则使用Haversine距离"
)

# ======== 开始优化按钮 ========
st.markdown("---")
st.markdown("### 🚀 执行优化计算")

if st.button("🚀 开始优化计算", type="primary", use_container_width=True):
    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        # ======== Step A: 构建节点和需求 ========
        status_text.text("📍 Step A: 构建节点和需求...")
        progress_bar.progress(0.05)

        # 节点列表：[仓库, 场馆1, 场馆2, ...]
        # 只添加有坐标的场馆
        nodes = [{"name": warehouse["name"], "lng": warehouse["lng"], "lat": warehouse["lat"]}]
        node_demands = [0]  # 仓库需求为0

        venues_with_coords = []
        for v in venues:
            if v.get("lng") is not None and v.get("lat") is not None:
                venues_with_coords.append(v)
                nodes.append({"name": v["name"], "lng": v["lng"], "lat": v["lat"]})
                venue_demand = demands.get(v["name"], {})
                if isinstance(venue_demand, dict):
                    total = venue_demand.get("总需求", sum(venue_demand.values()))
                else:
                    total = float(venue_demand)
                node_demands.append(total)

        n = len(nodes)

        # 检查仓库坐标
        if nodes[0]["lng"] is None or nodes[0]["lat"] is None:
            st.error("❌ 仓库坐标未设置，请先在【仓库设置】页面设置仓库坐标")
            st.stop()

        if n < 2:
            st.error("❌ 需要至少1个有坐标的场馆，请先在【场馆录入】页面为场馆获取坐标")
            st.stop()

        coords = [(node["lng"], node["lat"]) for node in nodes]
        st.success(f"✅ 节点构建完成：1个仓库 + {n-1}个有坐标的场馆（已跳过{len(venues)-len(venues_with_coords)}个无坐标场馆）")
        progress_bar.progress(0.1)

        # ======== Step B: 计算距离矩阵 ========
        status_text.text("📏 Step B: 计算距离矩阵...")
        progress_bar.progress(0.15)

        # 使用本地Haversine公式计算距离矩阵（快速且稳定）
        from utils.distance_matrix import build_distance_matrix_from_coords
        def progress_callback(prog, msg):
            progress_bar.progress(0.15 + 0.25 * prog)
            status_text.text(msg)

        distance_matrix = build_distance_matrix_from_coords(coords, road_factor=1.3, progress_callback=progress_callback)
        distance_method = "Haversine×1.3"
        st.success("✅ 距离矩阵计算完成（本地Haversine×1.3）")

        progress_bar.progress(0.4)

        # ======== Step C: K-Means中转仓选址 ========
        status_text.text("🏭 Step C: K-Means中转仓选址...")
        progress_bar.progress(0.45)

        venue_nodes_list = [n for n in nodes if not n.get("is_warehouse", False)]

        if len(venue_nodes_list) <= 5:
            optimal_k = 1
            clustering_result = {
                "optimal_k": 1,
                "clusters": [{"cluster_id": 0, "centroid": None, "venues": venue_nodes_list}],
                "labels": [0] * len(venue_nodes_list)
            }
            st.info(f"ℹ️ 场馆数量≤5，不设中转仓，直接从仓库配送")
            clustering_method = "无中转仓"
            depot_results = []
        else:
            try:
                from utils.clustering import select_warehouse_locations

                venue_coords = [(v["lng"], v["lat"]) for v in venue_nodes_list]
                venue_weights = [v.get("demand", 0) for v in venue_nodes_list]

                clustering_result = select_warehouse_locations(
                    venue_coords,
                    venue_weights,
                    max_warehouses=6
                )

                optimal_k = clustering_result.get("optimal_k", 1)
                st.success(f"✅ K-Means选址完成，最优中转仓数量: {optimal_k}")
                clustering_method = f"K-Means (K={optimal_k})"

                # 显示中转仓位置（带地址逆地理编码）
                if optimal_k > 1 and clustering_result.get("warehouses"):
                    st.markdown("**📦 中转仓选址结果：**")
                    depot_results = []
                    labels = clustering_result.get("labels", [])
                    for i, wh in enumerate(clustering_result.get("warehouses", [])[:optimal_k]):
                        wh_lng = wh.get('lng', 0)
                        wh_lat = wh.get('lat', 0)
                        # 逆地理编码获取地址
                        if api_key:
                            from utils.amap_api import reverse_geocode
                            address = reverse_geocode(wh_lng, wh_lat, api_key)
                        else:
                            address = f"({wh_lng:.4f}, {wh_lat:.4f}) 附近"
                        # 获取该中转仓服务的场馆列表
                        served_venue_indices = [j for j, label in enumerate(labels) if label == i]
                        served_venue_names = [venue_nodes_list[j]["name"] for j in served_venue_indices] if venue_nodes_list else []
                        served_venue_list = "、".join(served_venue_names[:5])
                        if len(served_venue_names) > 5:
                            served_venue_list += f" 等{len(served_venue_names)}个"
                        depot_results.append({
                            "中转仓编号": f"中转仓{i+1}",
                            "建议地址": address,
                            "经度": round(wh_lng, 6),
                            "纬度": round(wh_lat, 6),
                            "服务场馆数": len(served_venue_names),
                            "服务场馆列表": served_venue_list
                        })

                    # 展示中转仓表格
                    df_depots = pd.DataFrame(depot_results)
                    st.dataframe(df_depots, use_container_width=True, hide_index=True)

            except Exception as e:
                st.warning(f"K-Means选址失败: {e}，不使用中转仓")
                optimal_k = 1
                clustering_result = {
                    "optimal_k": 1,
                    "clusters": [{"cluster_id": 0, "centroid": None, "venues": venue_nodes_list}],
                    "labels": [0] * len(venue_nodes_list)
                }
                clustering_method = "选址失败，无中转仓"
                depot_results = []

        # 为节点分配聚类ID
        for node in nodes:
            if not node.get("is_warehouse", False):
                for i, v in enumerate(venue_nodes_list):
                    if node["name"] == v["name"]:
                        node["cluster_id"] = clustering_result.get("labels", [0] * len(venue_nodes_list))[i] if "labels" in clustering_result else 0
                        break

        progress_bar.progress(0.5)

        # ======== Step D: VRP求解 ========
        status_text.text("🚚 Step D: VRP求解...")
        progress_bar.progress(0.55)

        # 获取车辆配置
        if vehicles:
            v = vehicles[0]
            vehicle_type = v.get("vehicle_type", "diesel_heavy")
            vehicle_name = v.get("name", vehicle_type)
            emission_factor = v.get("emission_factor", 0.060)
            load_ton = v.get("load_ton", v.get("max_load_ton_default", 15.0))
            vehicle_capacity = int(load_ton * 1000)
            num_vehicles = sum(vv.get("count", 0) for vv in vehicles)
        else:
            vehicle_type = "diesel_heavy"
            vehicle_name = "柴油重卡"
            emission_factor = 0.060
            load_ton = 15.0
            vehicle_capacity = 15000
            num_vehicles = 3

        # 确保参数有效
        if num_vehicles <= 0:
            num_vehicles = 3
        if vehicle_capacity <= 0:
            vehicle_capacity = 15000

        demands_list = node_demands

        # 使用贪心最近邻算法（稳定可靠）
        routes = greedy_vrp(distance_matrix, demands_list, vehicle_capacity)
        optimization_method = "贪心算法"
        st.success(f"✅ VRP求解完成（贪心算法），生成 {len(routes)} 条路线")

        progress_bar.progress(0.6)

        # ======== Step D: 生成调度方案 ========
        status_text.text("📋 Step E: 生成调度方案...")
        progress_bar.progress(0.65)

        route_results = []

        for vehicle_idx, route in enumerate(routes):
            route_info = {
                "vehicle_id": vehicle_idx + 1,
                "vehicle_name": f"车辆{vehicle_idx + 1}",
                "vehicle_type": vehicle_name,
                "emission_factor": emission_factor,
                "route": route,
                "visits": [],  # 访问的场馆名称列表
                "load_details": [],  # 各场馆装载明细
                "total_load_kg": 0,
                "total_distance_km": 0,
                "total_carbon_kg": 0,
                "route_coords": []
            }

            current_load_ton = 0

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
                    total_venue_demand = venue_demand.get("总需求", sum(venue_demand.values()))
                else:
                    total_venue_demand = float(venue_demand)
                    detail = {
                        "venue": venue_name,
                        "general_materials_kg": total_venue_demand,
                        "sports_equipment_kg": 0,
                        "medical_materials_kg": 0,
                        "it_equipment_kg": 0,
                    }

                route_info["visits"].append(venue_name)
                route_info["load_details"].append(detail)
                route_info["total_load_kg"] += total_venue_demand

            # 计算路线距离和碳排放
            total_distance = 0.0
            total_carbon = 0.0
            current_load_ton = route_info["total_load_kg"] / 1000

            for i in range(len(route) - 1):
                from_idx = route[i]
                to_idx = route[i + 1]
                dist = distance_matrix[from_idx][to_idx]
                total_distance += dist
                carbon = dist * emission_factor * current_load_ton
                total_carbon += carbon
                current_load_ton -= demands_list[to_idx] / 1000

            route_info["total_distance_km"] = total_distance
            route_info["total_carbon_kg"] = total_carbon
            route_results.append(route_info)

        progress_bar.progress(0.75)

        # ======== 计算碳排放对比 ========
        status_text.text("🌿 Step F: 计算碳排放对比...")
        progress_bar.progress(0.8)

        # 基线碳排放（每场馆单独跑一趟）
        baseline_ef = 0.080  # 柴油车排放因子
        baseline_distance = sum(distance_matrix[0][i] + distance_matrix[i][0] for i in range(1, n))
        baseline_carbon = sum(demands_list) / 1000 * baseline_distance * baseline_ef

        # 优化后碳排放
        optimized_carbon = sum(r["total_carbon_kg"] for r in route_results)
        carbon_reduction = baseline_carbon - optimized_carbon
        reduction_pct = (carbon_reduction / baseline_carbon * 100) if baseline_carbon > 0 else 0

        # ======== 保存结果 ========
        status_text.text("💾 保存结果...")
        progress_bar.progress(0.9)

        # 保存到 st.session_state["optimization_results"]
        st.session_state["optimization_results"] = {
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
            "timestamp": datetime.now().isoformat()
        }

        # 兼容旧格式
        st.session_state["results"] = st.session_state["optimization_results"]
        progress_bar.progress(1.0)
        status_text.text("✅ 优化完成！")

        st.markdown("---")
        st.success("🎉 **优化计算完成！**")

        # 简要结果卡片
        col_r1, col_r2, col_r3, col_r4 = st.columns(4)
        opt_results = st.session_state["optimization_results"]
        with col_r1:
            st.metric("总距离", f"{opt_results['total_distance_km']:.2f} km")
        with col_r2:
            st.metric("总碳排放", f"{opt_results['total_emission']:.2f} kg CO₂")
        with col_r3:
            st.metric("使用车辆", f"{opt_results['num_vehicles_used']} 辆")
        with col_r4:
            st.metric("减排比例", f"{opt_results['reduction_percent']:.1f}%")

        # ===== 导出功能 =====
        st.markdown("---")
        st.subheader("📥 导出结果")

        # 车辆调度表CSV
        csv_data = []
        for rr in route_results:
            route_str = "总仓库 → " + " → ".join(rr["visits"]) + " → 总仓库"
            csv_data.append({
                "车辆编号": rr["vehicle_name"],
                "车型": rr["vehicle_type"],
                "路线": route_str,
                "访问场馆数": len(rr["visits"]),
                "总装载量_kg": rr["total_load_kg"],
                "总距离_km": round(rr["total_distance_km"], 2),
                "总碳排放_kgCO2": round(rr["total_carbon_kg"], 2)
            })
        df_csv = pd.DataFrame(csv_data)
        csv_str = df_csv.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="📥 下载车辆调度表(CSV)",
            data=csv_str,
            file_name="vehicle_dispatch_schedule.csv",
            mime="text/csv"
        )

        # 完整优化报告
        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append("物流路径优化报告")
        report_lines.append("=" * 60)
        report_lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"优化方法: {optimization_method}")
        report_lines.append(f"距离计算: {distance_method}")
        report_lines.append("")
        report_lines.append("【数据摘要】")
        report_lines.append(f"  总仓库: {warehouse.get('name', '总仓库')} ({warehouse.get('address', '')})")
        report_lines.append(f"  场馆数量: {len(venues)}")
        report_lines.append(f"  总物资需求: {sum(demands.values()) if isinstance(demands, dict) else 0:.0f} kg")
        report_lines.append(f"  使用车辆: {len(routes)} 辆 ({vehicle_name})")
        report_lines.append("")
        report_lines.append("【优化结果】")
        report_lines.append(f"  总行驶距离: {opt_results['total_distance_km']:.2f} km")
        report_lines.append(f"  总碳排放: {opt_results['total_emission']:.2f} kg CO₂")
        report_lines.append(f"  基线碳排放: {opt_results['baseline_emission']:.2f} kg CO₂")
        report_lines.append(f"  减排比例: {opt_results['reduction_percent']:.1f}%")
        report_lines.append("")
        report_lines.append("【车辆调度详情】")
        for rr in route_results:
            route_str = " → ".join(rr["visits"]) if rr["visits"] else "无"
            report_lines.append(f"  {rr['vehicle_name']} ({rr['vehicle_type']}):")
            report_lines.append(f"    路线: 总仓库 → {route_str} → 总仓库")
            report_lines.append(f"    装载量: {rr['total_load_kg']:.0f} kg | 距离: {rr['total_distance_km']:.2f} km | 碳排放: {rr['total_carbon_kg']:.2f} kg CO₂")
        report_lines.append("")
        report_lines.append("=" * 60)

        report_str = "\n".join(report_lines)
        st.download_button(
            label="📥 下载完整优化报告(TXT)",
            data=report_str,
            file_name="optimization_report.txt",
            mime="text/plain"
        )

    except Exception as e:
        st.error(f"优化过程出错: {e}")
        import traceback
        st.code(traceback.format_exc())

# ======== 结果展示 ========
res = st.session_state.get("optimization_results") or st.session_state.get("results")

if res:
    results = res
    st.markdown("---")
    st.markdown("### 📊 优化结果")

    route_results_list = results.get("route_results", [])
    nodes = results.get("nodes", [])
    depot_results_list = results.get("depot_results", [])

    # ===== 一、中转仓选址结果表格（展示在最前面）=====
    if depot_results_list and len(depot_results_list) > 0:
        st.subheader("🏭 中转仓选址结果")
        st.dataframe(pd.DataFrame(depot_results_list), use_container_width=True, hide_index=True)
        st.markdown("")

    # ===== 结果Tabs =====
    tab_map, tab_table, tab_carbon = st.tabs(["🗺️ 路线地图", "🚛 车辆调度详情", "📊 碳排放对比"])

    # ===== Tab: 路线地图 =====
    with tab_map:
        st.subheader("🗺️ 物流路线地图")

        # 构建Folium地图
        nodes = results.get("nodes", [])
        center_lat = sum(n["lat"] for n in nodes) / len(nodes) if nodes else 0
        center_lng = sum(n["lng"] for n in nodes) / len(nodes) if nodes else 0
        m = folium.Map(location=[center_lat, center_lng], zoom_start=12)

        # 颜色列表
        colors = ["red", "blue", "green", "purple", "orange", "darkred", "lightred", "beige", "darkblue", "darkgreen"]

        # 标记仓库
        if nodes:
            warehouse_node = nodes[0]
            folium.Marker(
                [warehouse_node["lat"], warehouse_node["lng"]],
                popup=f"<b>🏭 总仓库</b><br>{warehouse_node['name']}<br>{warehouse.get('address', '')}",
                tooltip="总仓库",
                icon=folium.Icon(color="darkred", icon="star")
            ).add_to(m)

            # 标记中转仓（红色方块）
            depot_results_map = results.get("depot_results", [])
            for depot in depot_results_map:
                popup_html = f"<b>🏭 {depot.get('中转仓编号', depot.get('编号', ''))}</b><br>建议地址：{depot.get('建议地址', '未知')}<br>坐标：({depot.get('经度', 0)}, {depot.get('纬度', 0)})<br>服务场馆数：{depot.get('服务场馆数', 0)}个"
                folium.Marker(
                    [depot.get("纬度", 0), depot.get("经度", 0)],
                    popup=folium.Popup(popup_html, max_width=300),
                    tooltip=depot.get("中转仓编号", depot.get("编号", "")),
                    icon=folium.Icon(color="red", icon="home", prefix="fa")
                ).add_to(m)

            # 标记场馆
            for node in nodes[1:]:
                venue_demand = demands.get(node["name"], {})
                if isinstance(venue_demand, dict):
                    total = venue_demand.get("总需求", sum(venue_demand.values()))
                else:
                    total = float(venue_demand)

                popup_html = f"<b>{node['name']}</b><br>总需求: {total:.0f} kg<br>地址: {node.get('address', '')}"
                folium.Marker(
                    [node["lat"], node["lng"]],
                    popup=popup_html,
                    tooltip=node["name"],
                    icon=folium.Icon(color="blue", icon="info-sign")
                ).add_to(m)

        # 绘制路线
        route_results_list = results.get("route_results", [])
        for i, route_result in enumerate(route_results_list):
            color = colors[i % len(colors)]
            coords = route_result.get("route_coords", [])

            if len(coords) > 1:
                folium.PolyLine(
                    coords,
                    color=color,
                    weight=4,
                    opacity=0.8,
                    popup=f"{route_result['vehicle_name']} ({route_result['vehicle_type']})"
                ).add_to(m)

                # 中点箭头
                mid_idx = len(coords) // 2
                mid_point = coords[mid_idx]
                folium.Marker(
                    mid_point,
                    icon=folium.DivIcon(
                        icon_size=(20, 20),
                        icon_anchor=(10, 10),
                        html=f'<div style="font-size:10pt;color:{color};font-weight:bold;">→</div>'
                    )
                ).add_to(m)

        # 添加图例
        legend_html = '<div style="position:fixed;bottom:50px;left:50px;z-index:1000;background:white;padding:10px;border-radius:5px;border:1px solid gray;font-size:11pt;">'
        legend_html += '<b>📍 图例</b><br>'
        legend_html += '<i style="background:darkred;width:12px;height:12px;display:inline-block;margin-right:5px;">⭐</i> 总仓库<br>'
        if depot_results_map:
            legend_html += '<i style="background:red;width:12px;height:12px;display:inline-block;margin-right:5px;">■</i> 中转仓<br>'
        legend_html += '<i style="background:blue;width:12px;height:12px;display:inline-block;margin-right:5px;">●</i> 场馆<br>'
        for i, rr in enumerate(route_results_list):
            color = colors[i % len(colors)]
            legend_html += f'<i style="background:{color};width:12px;height:12px;display:inline-block;margin-right:5px;"></i>{rr["vehicle_name"]}<br>'
        legend_html += '</div>'
        m.get_root().html.add_child(folium.Element(legend_html))

        st_folium(m, width=800, height=500)

    # ===== Tab: 车辆调度详情 =====
    with tab_table:
        st.subheader("🚛 车辆调度详情")

        for route_result in route_results_list:
            vehicle_label = f"{route_result['vehicle_name']}（{route_result['vehicle_type']}）"

            with st.expander(f"🚛 {vehicle_label}", expanded=False):
                # 路线信息
                route_str = " → ".join(["总仓库"] + route_result["visits"] + ["总仓库"])
                st.markdown(f"**路线：** {route_str}")
                st.divider()

                # 构建物资明细表格（6列）
                load_details = route_result.get("load_details", [])
                if load_details:
                    table_rows = []
                    for stop in load_details:
                        row = {
                            "场馆": stop.get("venue", ""),
                            "通用赛事物资(kg)": stop.get("general_materials_kg", 0),
                            "专项运动器材(kg)": stop.get("sports_equipment_kg", 0),
                            "医疗物资(kg)": stop.get("medical_materials_kg", 0),
                            "IT设备(kg)": stop.get("it_equipment_kg", 0),
                        }
                        row["总需求量(kg)"] = (
                            row["通用赛事物资(kg)"]
                            + row["专项运动器材(kg)"]
                            + row["医疗物资(kg)"]
                            + row["IT设备(kg)"]
                        )
                        table_rows.append(row)

                    detail_df = pd.DataFrame(table_rows)

                    # 添加合计行
                    if len(detail_df) > 0:
                        total_row = {
                            "场馆": "**合计**",
                            "通用赛事物资(kg)": detail_df["通用赛事物资(kg)"].sum(),
                            "专项运动器材(kg)": detail_df["专项运动器材(kg)"].sum(),
                            "医疗物资(kg)": detail_df["医疗物资(kg)"].sum(),
                            "IT设备(kg)": detail_df["IT设备(kg)"].sum(),
                            "总需求量(kg)": detail_df["总需求量(kg)"].sum(),
                        }
                        detail_df = pd.concat([detail_df, pd.DataFrame([total_row])], ignore_index=True)

                    st.dataframe(detail_df, use_container_width=True, hide_index=True)
                else:
                    st.info("无装载明细数据")

                st.divider()

                # 汇总指标
                col1, col2, col3 = st.columns(3)
                with col1:
                    max_load = results.get("vehicle_capacity_kg", 15000)
                    total_load = route_result.get("total_load_kg", 0)
                    utilization = (total_load / max_load * 100) if max_load > 0 else 0
                    st.metric("总装载量", f"{total_load:.0f} kg", delta=f"利用率 {utilization:.0f}%")
                with col2:
                    st.metric("总行驶距离", f"{route_result.get('total_distance_km', 0):.2f} km")
                with col3:
                    st.metric("碳排放", f"{route_result.get('total_carbon_kg', 0):.2f} kg CO₂")

        # 汇总表格
        st.markdown("---")
        st.subheader("📊 车辆调度汇总")
        summary_rows = []
        for rr in route_results_list:
            summary_rows.append({
                "车辆编号": rr["vehicle_name"],
                "车型": rr["vehicle_type"],
                "访问场馆数": len(rr["visits"]),
                "装载量(kg)": rr["total_load_kg"],
                "距离(km)": round(rr["total_distance_km"], 2),
                "碳排放(kgCO₂)": round(rr["total_carbon_kg"], 2)
            })
        df_summary = pd.DataFrame(summary_rows)
        st.dataframe(df_summary, hide_index=True, use_container_width=True)

    # ===== Tab: 碳排放对比 =====
    with tab_carbon:
        st.subheader("📊 碳排放对比")

        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            st.metric("基线碳排放", f"{results.get('baseline_emission', 0):.2f} kg CO₂")
        with col_c2:
            st.metric("优化后碳排放", f"{results.get('total_emission', 0):.2f} kg CO₂")
        with col_c3:
            reduction = results.get('baseline_emission', 0) - results.get('total_emission', 0)
            pct = results.get('reduction_percent', 0)
            st.metric("减排量", f"{reduction:.2f} kg CO₂", delta=f"-{pct:.1f}%")

        # 碳排放对比柱状图
        import plotly.express as px
        df_carbon = pd.DataFrame({
            "方案": ["基线方案\n(单独配送)", "优化方案\n(VRP调度)"],
            "碳排放(kg CO₂)": [results.get('baseline_emission', 0), results.get('total_emission', 0)]
        })
        fig_bar = px.bar(
            df_carbon,
            x="方案",
            y="碳排放(kg CO₂)",
            color="方案",
            title="碳排放对比",
            text_auto=True
        )
        fig_bar.update_layout(showlegend=False)
        st.plotly_chart(fig_bar, use_container_width=True)

        # 等效种树
        tree_equivalent = reduction / 21.7
        st.info(f"🌳 减排量相当于种植 **{tree_equivalent:.1f} 棵树**（每棵树年吸收21.7kg CO₂）")

else:
    st.info("👆 点击上方「🚀 开始优化计算」按钮执行优化计算")
