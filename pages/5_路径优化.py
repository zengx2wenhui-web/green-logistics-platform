"""路径优化页面 - 执行车队优化计算（FSMVRP）

核心特性：
- 使用 OR-Tools 异构车队求解（FSMVRP，车队规模与组成问题）
- 引入全局环境变量（季节、氢气源）参与双公式核算
- 使用 utils.clustering 进行 K-Medoids 真实中转仓选址
- 碳排放使用双公式精确计算（冷启动 + 逐站载重递减）
"""
import streamlit as st
import pandas as pd
import math
import folium
from streamlit_folium import st_folium
from datetime import datetime

from utils.file_reader import normalize_name
from utils.vehicle_lib import get_vehicle_params, VEHICLE_LIB

st.set_page_config(page_title="路径优化", page_icon="🧠", layout="wide")
st.title("🧠 第五步：路径优化中心")
st.markdown("执行物流网络优化计算（全国候选仓 K-Medoids 选址 + OR-Tools 异构车队 FSMVRP 调度）")

POWER_TYPE_MAPPING = {
    "diesel": "柴油重卡",
    "lng": "LNG天然气重卡",
    "hev": "混合动力 (HEV)",
    "phev": "插电混动 (PHEV)",
    "bev": "纯电动 (BEV)",
    "fcev": "氢燃料电池 (FCEV)",
}

def translate_vehicle_type(vtype: str) -> str:
    clean_vtype = str(vtype).split('_')[0].lower()
    return POWER_TYPE_MAPPING.get(clean_vtype, vtype)

def format_route_with_arrows(stops, start_label="总仓库", end_label="总仓库") -> str:
    return " → ".join([start_label] + list(stops) + [end_label])

# ===================== 数据完整性检查 =====================
st.markdown("### 📊 数据完整性与环境检查")

warehouse = st.session_state.get("warehouse", {})
venues = st.session_state.get("venues", [])
demands = st.session_state.get("demands", {})
vehicles = st.session_state.get("vehicles", [])

g_season = st.session_state.get("global_season", "夏")
g_h2_source = st.session_state.get("global_h2_source", "工业副产氢")

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    if warehouse.get("lng"):
        st.success("✅ 仓库已设")
    else:
        st.error("❌ 仓库未设")
with col2:
    st.info(f"🏟️ {len(venues)} 个场馆")
with col3:
    total_demand = 0.0
    for v in demands.values():
        if isinstance(v, dict):
            total_demand += v.get("总需求", sum(val for val in v.values() if isinstance(val, (int, float))))
        else:
            total_demand += float(v)
    st.metric("总需求", f"{total_demand:,.0f} kg")
with col4:
    total_vehicles = sum(v.get("count_max", 0) for v in vehicles)
    st.metric("车队上限", f"{total_vehicles} 辆")
with col5:
    st.metric("当前环境", f"{g_season} | {g_h2_source}")

# 检查数据是否完整
missing = []
if not warehouse.get("lng"): missing.append("仓库坐标")
if len(venues) == 0: missing.append("场馆")
if not demands: missing.append("物资需求")
if len(vehicles) == 0: missing.append("车辆配置")

if missing:
    st.warning(f"⚠️ 数据不完整：{'、'.join(missing)}")
    st.info("请先通过左侧菜单完成第一步~第四步的数据录入")
    st.stop()

st.success("✅ 数据链完整，求解器已就绪")
st.markdown("---")

# ===================== 优化参数 =====================
st.markdown("### ⚙️ 算法运行参数")

col_p1, col_p2 = st.columns(2)
with col_p1:
    api_key = st.text_input(
        "高德API密钥（可选，用于逆地理编码）",
        value=st.session_state.get("api_key_amap", ""),
        type="password",
        help="不填则中转仓仅显示坐标；填入后可解析出真实省市地址",
        key="api_key_input",
    )
    if api_key:
        st.session_state.api_key_amap = api_key

with col_p2:
    time_limit = st.slider("OR-Tools 求解时间上限（秒）", 5, 120, 30,
                           help="时间越长，启发式算法找到全局最优解的概率越大")

st.markdown("---")

# ===================== 开始优化 =====================
if st.button("🚀 启动智能物流引擎", type="primary", width="stretch"):
    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        # ======== Step A: 构建节点列表 ========
        status_text.text("🔄 步骤A: 构建空间节点拓扑...")
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
                venue_key = normalize_name(v.get("name", ""))
                venue_demand = demands.get(venue_key) or demands.get(v.get("name", ""), {})

                if isinstance(venue_demand, dict):
                    total = venue_demand.get("总需求", sum(
                        val for key, val in venue_demand.items() if isinstance(val, (int, float)) and key != "总需求"
                    ))
                else:
                    try: total = float(venue_demand)
                    except: total = 0.0
                node_demands.append(total)

        n = len(nodes)
        if n < 2:
            st.error("❌ 需要至少1个有坐标的场馆才能规划路径")
            st.stop()

        coords = [(nd["lng"], nd["lat"]) for nd in nodes]
        progress_bar.progress(0.10)

        # ======== Step B: 构建距离矩阵 ========
        status_text.text("📏 步骤B: 构建 Haversine 距离矩阵...")
        from utils.distance_matrix import build_distance_matrix_from_coords
        
        def dm_progress(prog, msg):
            progress_bar.progress(0.10 + 0.15 * prog)
            status_text.text(f"📏 {msg}")

        distance_matrix = build_distance_matrix_from_coords(
            coords, road_factor=1.3, progress_callback=dm_progress,
        )
        distance_method = "Haversine × 1.3"
        st.session_state.distance_matrix = distance_matrix
        progress_bar.progress(0.25)

        # ======== Step C0: 车队运力可行性前置阻断 ========
        status_text.text("🛡️ 步骤C0: 运力约束可行性校验...")
        demands_list = node_demands
        max_cap_kg, total_cap_kg = 0, 0
        for v in vehicles:
            try:
                single_cap = int(round(float(v.get("load_ton", 0.0)) * 1000))
                cap_kg = single_cap * int(v.get("count_max", 0))
                max_cap_kg = max(max_cap_kg, single_cap)
                total_cap_kg += cap_kg
            except Exception:
                continue

        max_demand_kg = max(demands_list) if demands_list else 0
        total_demand_kg = sum(demands_list) if demands_list else 0
        
        if max_cap_kg <= 0:
            st.error("❌ 车队无有效载重，请回到第四步填写实际载重（吨）")
            st.stop()
        if max_demand_kg > max_cap_kg:
            st.error(f"❌ 运力瓶颈：单个场馆最大需求 {max_demand_kg:,.0f} kg，超过了当前车队单车最大载荷 {max_cap_kg:,.0f} kg。无法一车送达！")
            st.stop()
        if total_demand_kg > total_cap_kg:
            st.error(f"❌ 运力不足：总需求 {total_demand_kg:,.0f} kg 超过车队满载总运力 {total_cap_kg:,.0f} kg。")
            st.stop()
        progress_bar.progress(0.30)

        # ======== Step C: K-Medoids 中转仓选址 ========
        status_text.text("📍 步骤C: 触发 K-Medoids 全国候选物流园选址...")
        venue_nodes = [nd for nd in nodes if not nd.get("is_warehouse")]
        depot_results = [] 

        if len(venue_nodes) <= 5:
            optimal_k = 1
            clustering_method = "场馆数≤5，直达配送"
        else:
            try:
                from utils.clustering import select_warehouse_from_national_candidates
                venue_coords = [(v["lng"], v["lat"]) for v in venue_nodes]
                venue_weights = [node_demands[i + 1] for i in range(len(venue_nodes))]

                clustering_result, err = select_warehouse_from_national_candidates(
                    venue_coords, venue_weights, max_warehouses=6
                )
                if err: raise Exception(err)
                st.session_state.clustering_result = clustering_result
                optimal_k = clustering_result.get("optimal_k", 1)
                clustering_method = f"K-Medoids选址 (K={optimal_k})"

                # 提取选址详情
                if optimal_k >= 1 and clustering_result.get("warehouses"):
                    for i, wh in enumerate(clustering_result["warehouses"]):
                        wh_lng, wh_lat = wh.get("lng", 0), wh.get("lat", 0)
                        wh_name = wh.get("nearest_candidate_name", f"真实枢纽{i + 1}")
                        province, city = wh.get("province", ""), wh.get("city", "")
                        
                        if not province or not city:
                            # 1. 优先从仓库名字中智能提取（免API配额）
                            if "广州" in wh_name: province, city = "广东省", "广州市"
                            elif "东莞" in wh_name: province, city = "广东省", "东莞市"
                            elif "深圳" in wh_name: province, city = "广东省", "深圳市"
                            elif "佛山" in wh_name: province, city = "广东省", "佛山市"
                            elif "肇庆" in wh_name: province, city = "广东省", "肇庆市"
                            # 2. 如果没匹配上，且填了高德Key，使用正则解析高德地址
                            elif api_key:
                                try:
                                    from utils.amap_api import reverse_geocode
                                    addr = reverse_geocode(wh_lng, wh_lat, api_key)
                                    if addr and "未知" not in addr:
                                        import re
                                        match = re.match(r'^([^省]+省|[^自治区]+自治区|[^市]+市)([^市]+市|[^自治州]+自治州|[^区]+区)', addr)
                                        if match:
                                            province, city = match.group(1), match.group(2)
                                        else:
                                            province, city = addr[:3], addr[3:6]
                                except: pass
                        served_indices = wh.get("venues", [])
                        served_names = [venue_nodes[j]["name"] for j in served_indices if j < len(venue_nodes)]
                        
                        avg_dist = 0
                        if served_indices:
                            from utils.clustering import haversine_distance
                            total_dist = sum(haversine_distance(wh_lng, wh_lat, venue_nodes[j]["lng"], venue_nodes[j]["lat"]) for j in served_indices)
                            avg_dist = total_dist / len(served_indices)

                        depot_results.append({
                            "仓库名称": wh_name, "省": province, "市": city,
                            "经度": round(wh_lng, 6), "纬度": round(wh_lat, 6),
                            "服务场馆数": len(served_names), "物资总量(kg)": round(wh.get("weight", 0), 1),
                            "平均距离(km)": round(avg_dist, 2) if avg_dist > 0 else "N/A",
                        })
            except Exception as e:
                optimal_k = 1
                clustering_method = "选址降级: 无中转仓"
        progress_bar.progress(0.45)

        # ======== Step D: OR-Tools FSMVRP ========
        status_text.text("🚛 步骤D: OR-Tools 异构车队 FSMVRP 求解中 (过程较长请耐心等待)...")
        from utils.fsmvrp_ortools import solve_fsmvrp_ortools

        result = solve_fsmvrp_ortools(
            distance_matrix_km=distance_matrix,
            demands_kg=demands_list,
            fleet=vehicles,
            depot=0,
            time_limit_seconds=time_limit,
            season=g_season,      
            h2_source=g_h2_source, 
        )
        if not result or not result.get("success"):
            st.error("❌ FSMVRP 求解未找到可行解，可能因时间限制过短或装载搭配不合理")
            st.stop()
            
        routes = result["routes"]
        route_vehicle_ids = result.get("route_vehicle_ids", [])
        vehicle_types_pool = result.get("vehicle_types", [])
        vehicle_capacities_pool = result.get("vehicle_capacities_kg", [])
        progress_bar.progress(0.70)

        # ======== Step E: 碳排放双公式精算 ========
        status_text.text("🍃 步骤E: 动态载重碳排双公式精算...")
        route_results = []
        from utils.carbon_calc import compute_route_emission
        material_columns = st.session_state.get("material_columns", ["通用赛事物资", "专项运动器材", "医疗物资", "IT设备"]) 

        for vehicle_idx, route in enumerate(routes):
            v_id = route_vehicle_ids[vehicle_idx]
            vtype_id = vehicle_types_pool[v_id].split('_')[0].lower() # 清洗命名
            vehicle_capacity = int(vehicle_capacities_pool[v_id])

            route_info = {
                "vehicle_name": f"派车{vehicle_idx + 1}",
                "vehicle_type": vtype_id,
                "route": route,
                "visits": [], "load_details": [], "route_coords": [],
                "total_load_kg": 0, "total_distance_km": 0, "total_carbon_kg": 0,
            }

            for stop_idx in route:
                node = nodes[stop_idx]
                route_info["route_coords"].append([node["lat"], node["lng"]])
                if stop_idx == 0: continue
                venue_name = node["name"]

                venue_key = normalize_name(venue_name)
                venue_demand = demands.get(venue_key) or demands.get(venue_name, {})

                detail = {"venue": venue_name}
                if isinstance(venue_demand, dict):
                    for cat in material_columns: detail[cat] = float(venue_demand.get(cat, 0) or 0)
                    total_venue = venue_demand.get("总需求", sum(detail.get(cat, 0) for cat in material_columns))
                else:
                    try: total_venue = float(venue_demand)
                    except: total_venue = 0.0
                    for i, cat in enumerate(material_columns): detail[cat] = float(total_venue) if i == 0 else 0.0

                route_info["visits"].append(venue_name)
                route_info["load_details"].append(detail)
                route_info["total_load_kg"] += total_venue

            # 分段距离与需求
            segment_distances, segment_demands = [], []
            for i in range(len(route) - 1):
                from_idx, to_idx = route[i], route[i + 1]
                segment_distances.append(distance_matrix[from_idx][to_idx])
                if to_idx != 0: segment_demands.append(demands_list[to_idx])

            emission_summary = compute_route_emission(
                distances=segment_distances,
                demands_kg=segment_demands,
                vehicle_type=vtype_id,
                season=g_season,
                h2_source=g_h2_source,
                include_cold_start=True,
            )

            route_info["total_distance_km"] = emission_summary["total_distance_km"]
            route_info["total_carbon_kg"] = emission_summary["total_carbon_kg"]
            route_info["vehicle_capacity_kg"] = vehicle_capacity
            route_info["cold_start_g"] = get_vehicle_params(vtype_id).get("cold_start_g", 0)
            route_info["segments"] = emission_summary.get("segments", [])
            route_results.append(route_info)

        progress_bar.progress(0.85)

        # ======== Step F: 基线对比与保存 ========
        status_text.text("💾 步骤F: 生成对比报告并持久化...")
        baseline_ef = 0.060 # 假设传统的柴油基准
        baseline_distance = sum(distance_matrix[0][i] + distance_matrix[i][0] for i in range(1, n))
        baseline_carbon = sum(demands_list) / 1000 * baseline_distance * baseline_ef

        optimized_carbon = sum(r["total_carbon_kg"] for r in route_results)
        reduction_pct = ((baseline_carbon - optimized_carbon) / baseline_carbon * 100) if baseline_carbon > 0 else 0

        opt_result = {
            "route_results": route_results, "total_emission": optimized_carbon,
            "baseline_emission": baseline_carbon, "reduction_percent": reduction_pct,
            "total_distance_km": sum(r["total_distance_km"] for r in route_results),
            "num_vehicles_used": len(routes), "clustering_method": clustering_method,

            "optimization_method": "OR-Tools FSMVRP",
            "distance_method": distance_method,

            "nodes": nodes, "demands": demands, "depot_results": depot_results,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        st.session_state["optimization_results"] = opt_result
        st.session_state["results"] = opt_result

        progress_bar.progress(1.0)
        status_text.text("✅ 优化求解全部完成！")
        st.balloons()

    except Exception as e:
        st.error(f"❌ 优化过程出错: {e}")
        import traceback
        with st.expander("点击查看底层报错栈"): st.code(traceback.format_exc())


# ===================== 结果展示 =====================
res = st.session_state.get("optimization_results")
if res and isinstance(res, dict) and res.get("route_results"):
    st.markdown("---")
    st.markdown("### 🏆 智能调度与减排结果分析")

    route_results_list = res.get("route_results", [])
    nodes_list = res.get("nodes", [])
    depot_results_list = res.get("depot_results", [])

    # 简要结果 KPI
    col_r1, col_r2, col_r3, col_r4 = st.columns(4)
    col_r1.metric("总行驶距离", f"{res['total_distance_km']:.2f} km")
    col_r2.metric("实际派车", f"{res['num_vehicles_used']} 辆")
    col_r3.metric("系统总碳足迹", f"{res['total_emission']:.2f} kg", delta="包含冷启动与空跑", delta_color="normal")
    col_r4.metric("测算减排率", f"{res['reduction_percent']:.1f}%", delta="VS 传统单点直发")

    if depot_results_list:
        st.subheader("🏢 K-Medoids 真实中转枢纽选址结果")
        st.dataframe(pd.DataFrame(depot_results_list), width="stretch", hide_index=True)

    tab_map, tab_table, tab_carbon = st.tabs(["🗺️ 配送路线地图", "📋 车队派发清单", "🍃 碳减排效益"])

    # ===== Tab 1: 路线地图 =====
    with tab_map:
        if nodes_list:
            c_lat = sum(nd["lat"] for nd in nodes_list) / len(nodes_list)
            c_lng = sum(nd["lng"] for nd in nodes_list) / len(nodes_list)
            m = folium.Map(location=[c_lat, c_lng], zoom_start=11)
            colors = ["blue", "purple", "orange", "darkred", "cadetblue", "darkgreen"]

            # 总仓库
            folium.Marker(
                [nodes_list[0]["lat"], nodes_list[0]["lng"]],
                popup="总发货仓", icon=folium.Icon(color="darkred", icon="star")
            ).add_to(m)

            # 场馆
            for nd in nodes_list[1:]:
                folium.CircleMarker(
                    [nd["lat"], nd["lng"]], radius=6, color="cadetblue", fill=True,
                    tooltip=nd['name']
                ).add_to(m)

            # 路线
            for i, rr in enumerate(route_results_list):
                folium.PolyLine(
                    rr["route_coords"], color=colors[i % len(colors)], weight=4, opacity=0.7,
                    tooltip=f"{rr['vehicle_name']} ({translate_vehicle_type(rr['vehicle_type'])})"
                ).add_to(m)
            st_folium(m, width="100%", height=500)

    # ===== Tab 2: 车辆调度详情 =====
    with tab_table:
        for rr in route_results_list:
            v_name = translate_vehicle_type(rr['vehicle_type'])
            with st.expander(f"🚛 {rr['vehicle_name']} [{v_name}] - 负责 {len(rr['visits'])} 个场馆", expanded=False):
                st.markdown(f"配送路线: {format_route_with_arrows(rr['visits'])}")
                c_c1, c_c2, c_c3 = st.columns(3)
                util = (rr['total_load_kg'] / rr['vehicle_capacity_kg'] * 100) if rr['vehicle_capacity_kg'] > 0 else 0
                c_c1.metric("实际装载率", f"{util:.1f} %", help=f"装载 {rr['total_load_kg']:.0f} kg / 设定上限 {rr['vehicle_capacity_kg']:.0f} kg")
                c_c2.metric("该车总碳排", f"{rr['total_carbon_kg']:.2f} kg")
                c_c3.metric("内含冷启动基数", f"{rr['cold_start_g']/1000:.2f} kg", help="发动引擎产生的固定碳排基数")

                if rr.get("load_details"):
                    st.markdown("👇 **逐站卸货清单**")
                    st.dataframe(pd.DataFrame(rr["load_details"]), width="stretch")

    # ===== Tab 3: 碳排放对比 =====
    with tab_carbon:
        import plotly.express as px
        df_carbon = pd.DataFrame({
            "方案对标": ["传统直发模式", "当前 AI 统筹调度"],
            "系统总碳排 (kg CO₂)": [res.get("baseline_emission", 0), res.get("total_emission", 0)],
        })
        fig = px.bar(df_carbon, x="方案对标", y="系统总碳排 (kg CO₂)", color="方案对标", text_auto=".2f")
        st.plotly_chart(fig, width="stretch")

        tree_eq = (res.get("baseline_emission", 0) - res.get("total_emission", 0)) / 12.0
        st.info(f"🌳 此次优化减少的碳排放，相当于替大自然额外种下了 **{tree_eq:.1f} 棵树** (按每棵树年吸收12kg测算)！")

st.markdown("---")
if st.button("查看最终报告 ➡️", type="secondary", width="stretch"):
    st.switch_page("pages/6_碳排放概览.py")