"""路径优化页面 - 执行VRP优化计算"""
import streamlit as st
import pandas as pd
import math
import folium
from streamlit_folium import st_folium
from datetime import datetime

st.set_page_config(page_title="路径优化", page_icon="🗺️")

st.title("🗺️ Step 7：路径优化")
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
        nodes = [{"name": warehouse["name"], "lng": warehouse["lng"], "lat": warehouse["lat"]}]
        node_demands = [0]  # 仓库需求为0

        for v in venues:
            nodes.append({"name": v["name"], "lng": v["lng"], "lat": v["lat"]})
            venue_demand = demands.get(v["name"], {})
            if isinstance(venue_demand, dict):
                total = venue_demand.get("总需求", sum(venue_demand.values()))
            else:
                total = float(venue_demand)
            node_demands.append(total)

        n = len(nodes)
        coords = [(node["lng"], node["lat"]) for node in nodes]
        st.success(f"✅ 节点构建完成：1个仓库 + {n-1}个场馆")
        progress_bar.progress(0.1)

        # ======== Step B: 计算距离矩阵 ========
        status_text.text("📏 Step B: 计算距离矩阵...")
        progress_bar.progress(0.15)

        if api_key:
            try:
                from utils.amap_api import get_driving_distance
                distance_matrix = [[0.0] * n for _ in range(n)]
                total_pairs = n * (n - 1) // 2
                completed = 0

                for i in range(n):
                    for j in range(i + 1, n):
                        result = get_driving_distance(
                            (coords[i][0], coords[i][1]),
                            (coords[j][0], coords[j][1]),
                            api_key
                        )
                        if result:
                            distance_matrix[i][j] = result[0]
                            distance_matrix[j][i] = result[0]
                        else:
                            dist = haversine_distance(coords[i], coords[j]) * 1.3
                            distance_matrix[i][j] = dist
                            distance_matrix[j][i] = dist
                        completed += 1
                        if completed % 3 == 0:
                            progress_bar.progress(0.15 + 0.25 * completed / total_pairs)

                distance_method = "高德API"
                st.success("✅ 距离矩阵计算完成（高德API）")
            except Exception as e:
                distance_matrix = build_distance_matrix_haversine(coords)
                distance_method = f"Haversine(API失败:{str(e)[:20]})"
                st.warning(f"高德API失败，使用Haversine: {e}")
        else:
            distance_matrix = build_distance_matrix_haversine(coords)
            distance_method = "Haversine×1.3"
            st.info("ℹ️ 未提供API密钥，使用Haversine距离×1.3估算")

        progress_bar.progress(0.4)

        # ======== Step C: VRP求解 ========
        status_text.text("🚚 Step C: VRP求解...")
        progress_bar.progress(0.45)

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

        demands_list = node_demands
        routes = []

        try:
            from ortools.constraint_solver import routing_enums_pb2
            from ortools.constraint_solver import pywrapcp

            manager = pywrapcp.RoutingIndexManager(n, num_vehicles, 0)
            routing = pywrapcp.RoutingModel(manager)

            def distance_callback(from_index, to_index):
                from_node = manager.IndexToNode(from_index)
                to_node = manager.IndexToNode(to_index)
                return int(distance_matrix[from_node][to_node] * 1000)

            transit_callback_index = routing.RegisterTransitCallback(distance_callback)
            routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

            def demand_callback(from_index):
                from_node = manager.IndexToNode(from_index)
                return demands_list[from_node]

            demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
            routing.AddDimensionWithVehicleCapacity(
                demand_callback_index, 0, [vehicle_capacity] * num_vehicles, True, "Capacity"
            )

            search_parameters = pywrapcp.DefaultRoutingSearchParameters()
            search_parameters.first_solution_strategy = (
                routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
            )
            search_parameters.time_limit.seconds = 30

            solution = routing.SolveWithParameters(search_parameters)

            if solution:
                route = []
                vehicle_id = 0
                while vehicle_id < num_vehicles:
                    index = routing.Start(vehicle_id)
                    if not routing.IsEnd(solution.Value(routing.NextVar(index))):
                        single_route = [manager.IndexToNode(index)]
                        while not routing.IsEnd(index):
                            index = solution.Value(routing.NextVar(index))
                            single_route.append(manager.IndexToNode(index))
                        if len(single_route) > 2:
                            routes.append(single_route)
                    vehicle_id += 1
                optimization_method = "OR-Tools"
                st.success(f"✅ VRP求解完成（OR-Tools），使用 {len(routes)} 辆车")
            else:
                raise Exception("OR-Tools无解")

        except Exception as e:
            st.warning(f"OR-Tools求解失败: {e}，使用贪心算法")
            routes = greedy_vrp(distance_matrix, demands_list, vehicle_capacity)
            optimization_method = "贪心算法"
            st.success(f"✅ VRP求解完成（贪心算法），生成 {len(routes)} 条路线")

        progress_bar.progress(0.6)

        # ======== Step D: 生成调度方案 ========
        status_text.text("📋 Step D: 生成调度方案...")
        progress_bar.progress(0.65)

        route_results = []

        for vehicle_idx, route in enumerate(routes):
            route_info = {
                "车辆编号": f"车辆{vehicle_idx + 1}",
                "车型": vehicle_name,
                "碳因子": emission_factor,
                "访问场馆": [],
                "各场馆装载明细": [],
                "总装载量(kg)": 0,
                "总行驶距离(km)": 0,
                "总碳排放(kgCO2)": 0,
                "路线坐标": []
            }

            current_load = 0

            for stop_idx in route:
                node = nodes[stop_idx]
                route_info["路线坐标"].append([node["lat"], node["lng"]])

                if stop_idx == 0:  # 仓库
                    continue

                venue_name = node["name"]
                venue_demand = demands.get(venue_name, {})
                if isinstance(venue_demand, dict):
                    detail = {
                        "场馆": venue_name,
                        "通用赛事物资(kg)": venue_demand.get("通用赛事物资", 0),
                        "专项运动器材(kg)": venue_demand.get("专项运动器材", 0),
                        "医疗物资(kg)": venue_demand.get("医疗物资", 0),
                        "IT设备(kg)": venue_demand.get("IT设备", 0),
                    }
                    total_venue_demand = venue_demand.get("总需求", sum(venue_demand.values()))
                else:
                    total_venue_demand = float(venue_demand)
                    detail = {
                        "场馆": venue_name,
                        "通用赛事物资(kg)": total_venue_demand,
                        "专项运动器材(kg)": 0,
                        "医疗物资(kg)": 0,
                        "IT设备(kg)": 0,
                    }

                route_info["访问场馆"].append(venue_name)
                route_info["各场馆装载明细"].append(detail)
                route_info["总装载量(kg)"] += total_venue_demand

            # 计算路线距离和碳排放
            total_distance = 0.0
            total_carbon = 0.0
            current_load_ton = route_info["总装载量(kg)"] / 1000

            for i in range(len(route) - 1):
                from_idx = route[i]
                to_idx = route[i + 1]
                dist = distance_matrix[from_idx][to_idx]
                total_distance += dist
                carbon = dist * emission_factor * current_load_ton
                total_carbon += carbon
                current_load_ton -= demands_list[to_idx] / 1000

            route_info["总行驶距离(km)"] = total_distance
            route_info["总碳排放(kgCO2)"] = total_carbon
            route_results.append(route_info)

        progress_bar.progress(0.75)

        # ======== 计算碳排放对比 ========
        status_text.text("🌿 Step D: 计算碳排放对比...")
        progress_bar.progress(0.8)

        # 基线碳排放（每场馆单独跑一趟）
        baseline_ef = 0.080  # 柴油车排放因子
        baseline_distance = sum(distance_matrix[0][i] + distance_matrix[i][0] for i in range(1, n))
        baseline_carbon = sum(demands_list) / 1000 * baseline_distance * baseline_ef

        # 优化后碳排放
        optimized_carbon = sum(r["总碳排放(kgCO2)"] for r in route_results)
        carbon_reduction = baseline_carbon - optimized_carbon
        reduction_pct = (carbon_reduction / baseline_carbon * 100) if baseline_carbon > 0 else 0

        # 保存结果到session_state
        results = {
            "nodes": nodes,
            "routes": routes,
            "route_results": route_results,
            "distance_matrix": distance_matrix,
            "total_distance_km": sum(r["总行驶距离(km)"] for r in route_results),
            "total_carbon_kg": optimized_carbon,
            "baseline_carbon_kg": baseline_carbon,
            "carbon_reduction_kg": carbon_reduction,
            "reduction_pct": reduction_pct,
            "optimization_method": optimization_method,
            "distance_method": distance_method,
            "vehicle_name": vehicle_name,
            "vehicle_capacity": vehicle_capacity,
            "emission_factor": emission_factor,
            "num_vehicles_used": len(routes),
            "timestamp": datetime.now().isoformat()
        }

        st.session_state["results"] = results
        progress_bar.progress(1.0)
        status_text.text("✅ 优化完成！")

        st.markdown("---")
        st.success("🎉 **优化计算完成！**")

        # 简要结果卡片
        col_r1, col_r2, col_r3, col_r4 = st.columns(4)
        with col_r1:
            st.metric("总距离", f"{results['total_distance_km']:.2f} km")
        with col_r2:
            st.metric("总碳排放", f"{results['total_carbon_kg']:.2f} kg CO₂")
        with col_r3:
            st.metric("使用车辆", f"{results['num_vehicles_used']} 辆")
        with col_r4:
            st.metric("减排比例", f"{results['reduction_pct']:.1f}%")

    except Exception as e:
        st.error(f"优化过程出错: {e}")
        import traceback
        st.code(traceback.format_exc())

# ======== 结果展示 ========
if "results" in st.session_state and st.session_state["results"]:
    results = st.session_state["results"]

    st.markdown("---")
    st.markdown("### 📊 优化结果")

    tab_map, tab_table, tab_carbon = st.tabs(["🗺️ 路线地图", "📋 车辆调度表", "📊 碳排放对比"])

    # ===== Tab: 路线地图 =====
    with tab_map:
        st.subheader("🗺️ 物流路线地图")

        # 构建Folium地图
        center_lat = sum(n["lat"] for n in results["nodes"]) / len(results["nodes"])
        center_lng = sum(n["lng"] for n in results["nodes"]) / len(results["nodes"])
        m = folium.Map(location=[center_lat, center_lng], zoom_start=12)

        # 颜色列表
        colors = ["red", "blue", "green", "purple", "orange", "darkred", "lightred", "beige", "darkblue", "darkgreen"]

        # 标记仓库
        warehouse_node = results["nodes"][0]
        folium.Marker(
            [warehouse_node["lat"], warehouse_node["lng"]],
            popup=f"<b>总仓库</b><br>{warehouse_node['name']}",
            tooltip="总仓库",
            icon=folium.Icon(color="red", icon="star")
        ).add_to(m)

        # 标记场馆
        for node in results["nodes"][1:]:
            venue_demand = demands.get(node["name"], {})
            if isinstance(venue_demand, dict):
                total = venue_demand.get("总需求", sum(venue_demand.values()))
            else:
                total = float(venue_demand)

            popup_html = f"""
            <b>{node['name']}</b><br>
            总需求: {total:.0f} kg<br>
            地址: {node.get('address', '')}
            """
            folium.Marker(
                [node["lat"], node["lng"]],
                popup=popup_html,
                tooltip=node["name"],
                icon=folium.Icon(color="blue", icon="info-sign")
            ).add_to(m)

        # 绘制路线
        route_coords = []
        for i, route_result in enumerate(results["route_results"]):
            color = colors[i % len(colors)]
            coords = route_result["路线坐标"]

            # 绘制路线折线
            folium.PolyLine(
                coords,
                color=color,
                weight=4,
                opacity=0.8,
                popup=f"{route_result['车辆编号']} ({route_result['车型']})"
            ).add_to(m)

            # 添加方向箭头（简化为中点标记）
            if len(coords) > 1:
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
        legend_html += '<b>🚛 车辆路线</b><br>'
        for i, rr in enumerate(results["route_results"]):
            color = colors[i % len(colors)]
            legend_html += f'<i style="background:{color};width:12px;height:12px;display:inline-block;margin-right:5px;"></i>{rr["车辆编号"]}<br>'
        legend_html += '</div>'
        m.get_root().html.add_child(folium.Element(legend_html))

        st_folium(m, width=800, height=500)

    # ===== Tab: 车辆调度表 =====
    with tab_table:
        st.subheader("📋 车辆调度详情")

        for i, route_result in enumerate(results["route_results"]):
            with st.expander(f"🚛 {route_result['车辆编号']}（{route_result['车型']}）"):
                # 路线
                route_str = "总仓库 → " + " → ".join(route_result["访问场馆"]) + " → 总仓库"
                st.write(f"**路线：** {route_str}")

                # 装载明细表格
                if route_result["各场馆装载明细"]:
                    df_load = pd.DataFrame(route_result["各场馆装载明细"])
                    st.dataframe(df_load, hide_index=True, use_container_width=True)

                # 统计
                col_v1, col_v2, col_v3 = st.columns(3)
                with col_v1:
                    load_pct = (route_result["总装载量(kg)"] / results["vehicle_capacity"] * 100) if results["vehicle_capacity"] > 0 else 0
                    st.metric("总装载量", f"{route_result['总装载量(kg)']:.0f} kg", delta=f"利用率 {load_pct:.0f}%")
                with col_v2:
                    st.metric("行驶距离", f"{route_result['总行驶距离(km)']:.2f} km")
                with col_v3:
                    st.metric("碳排放", f"{route_result['总碳排放(kgCO2)']:.2f} kg CO₂")

        # 汇总表格
        st.markdown("---")
        st.subheader("📊 车辆调度汇总")
        summary_rows = []
        for rr in results["route_results"]:
            summary_rows.append({
                "车辆编号": rr["车辆编号"],
                "车型": rr["车型"],
                "访问场馆数": len(rr["访问场馆"]),
                "装载量(kg)": rr["总装载量(kg)"],
                "距离(km)": rr["总行驶距离(km)"],
                "碳排放(kgCO₂)": rr["总碳排放(kgCO2)"]
            })
        df_summary = pd.DataFrame(summary_rows)
        st.dataframe(df_summary, hide_index=True, use_container_width=True)

    # ===== Tab: 碳排放对比 =====
    with tab_carbon:
        st.subheader("📊 碳排放对比")

        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            st.metric("基线碳排放", f"{results['baseline_carbon_kg']:.2f} kg CO₂")
        with col_c2:
            st.metric("优化后碳排放", f"{results['total_carbon_kg']:.2f} kg CO₂")
        with col_c3:
            st.metric("减排量", f"{results['carbon_reduction_kg']:.2f} kg CO₂", delta=f"-{results['reduction_pct']:.1f}%")

        # 碳排放对比柱状图
        import plotly.express as px
        df_carbon = pd.DataFrame({
            "方案": ["基线方案\n(单独配送)", "优化方案\n(VRP调度)"],
            "碳排放(kg CO₂)": [results['baseline_carbon_kg'], results['total_carbon_kg']]
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
        tree_equivalent = results['carbon_reduction_kg'] / 21.7
        st.info(f"🌳 减排量相当于种植 **{tree_equivalent:.1f} 棵树**（每棵树年吸收21.7kg CO₂）")

else:
    st.info("👆 点击上方「🚀 开始优化计算」按钮执行优化计算")
