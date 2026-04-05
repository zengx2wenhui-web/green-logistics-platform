"""优化结果页面 - 展示优化结果"""
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import plotly.express as px

st.set_page_config(page_title="优化结果", page_icon="📋")

st.title("📋 Step 8：优化结果")
st.markdown("查看物流网络优化详细结果")

# ===================== 检查是否有结果 =====================
results = st.session_state.get("optimization_results") or st.session_state.get("results")

if not results:
    st.warning("⚠️ 暂无优化结果")
    st.info("""
    **请先在 Step 6「路径优化」页面运行优化计算**

    1. 🏭 仓库设置 - 设置总仓库地址和坐标
    2. 🏟️ 场馆录入 - 录入场馆信息
    3. 📦 物资需求 - 录入各场馆物资需求量
    4. 🚛 车辆配置 - 配置配送车辆类型和数量
    5. 🗺️ **Step 6 路径优化** - 运行优化计算
    6. 📋 **Step 8 优化结果** - 查看结果（本页面）
    """)
    st.stop()

# ===================== 结果概览 =====================
st.markdown("### 📊 优化结果概览")

total_distance = results.get("total_distance_km", 0)
total_carbon = results.get("total_emission", 0)
baseline_carbon = results.get("baseline_emission", 0)
reduction_pct = results.get("reduction_percent", 0)
num_vehicles = results.get("num_vehicles_used", 0)
optimization_method = results.get("optimization_method", "未知")
distance_method = results.get("distance_method", "未知")

# 车辆类型名称映射
vehicle_name_map = {
    "diesel_heavy": "柴油重卡",
    "lng": "LNG天然气",
    "hev": "柴电混动",
    "phev": "插电混动",
    "bev": "纯电动",
    "fcev": "氢燃料电池"
}
vehicle_type = results.get("vehicle_type", "diesel_heavy")
vehicle_name = vehicle_name_map.get(vehicle_type, vehicle_type)

col_o1, col_o2, col_o3, col_o4 = st.columns(4)
with col_o1:
    st.metric("总行驶距离", f"{total_distance:.2f} km")
with col_o2:
    st.metric("总碳排放", f"{total_carbon:.2f} kg CO₂")
with col_o3:
    st.metric("使用车辆数", num_vehicles)
with col_o4:
    efficiency = total_carbon / max(total_distance, 0.01)
    st.metric("碳效率", f"{efficiency:.4f} kg/km")

# 优化效果
carbon_reduction = baseline_carbon - total_carbon
if carbon_reduction > 0:
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #27ae60, #2ecc71);
                padding: 20px; border-radius: 10px; text-align: center; color: white; margin: 10px 0;">
        <h3>🌿 优化效果</h3>
        <p>相比基线（柴油车）减少碳排放 <strong style="font-size: 24px;">{carbon_reduction:.1f} kg CO₂</strong>
        ({reduction_pct:.1f}%)</p>
        <p>相当于种植 <strong style="font-size: 20px;">{carbon_reduction / 21.7:.1f} 棵</strong> 树木一年吸收量</p>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div style="background: linear-gradient(135deg, #f39c12, #e67e22);
                padding: 20px; border-radius: 10px; text-align: center; color: white; margin: 10px 0;">
        <h3>⚠️ 优化效果</h3>
        <p>当前方案碳排放略高于基线，请尝试调整车辆配置</p>
    </div>
    """, unsafe_allow_html=True)

# 方法说明
method_col1, method_col2, method_col3 = st.columns(3)
with method_col1:
    st.caption(f"📏 距离计算: {distance_method}")
with method_col2:
    st.caption(f"🏭 选址方法: {results.get('clustering_method', '无中转仓')}")
with method_col3:
    st.caption(f"🚚 路径优化: {optimization_method}")

st.markdown("---")

# ===================== Tab展示 =====================
route_results = results.get("route_results", [])
nodes = results.get("nodes", [])
routes = results.get("routes", [])

tab1, tab2, tab3 = st.tabs(["🗺️ 物流网络地图", "📊 碳排放对比", "📋 调度详情"])

# ======== Tab 1: 物流网络地图 ========
with tab1:
    st.subheader("🗺️ 物流网络地图")

    if nodes:
        center_lat = sum(n["lat"] for n in nodes) / len(nodes)
        center_lng = sum(n["lng"] for n in nodes) / len(nodes)

        m = folium.Map(location=[center_lat, center_lng], zoom_start=13, tiles="cartodbpositron")

        route_colors = ["red", "blue", "green", "purple", "orange", "darkred", "cadetblue", "pink"]

        # 绘制路线
        for i, rr in enumerate(route_results):
            color = route_colors[i % len(route_colors)]
            coords = rr.get("route_coords", [])
            if len(coords) >= 2:
                folium.PolyLine(
                    locations=coords,
                    color=color,
                    weight=4,
                    opacity=0.8,
                    popup=f"{rr.get('vehicle_name', f'路线 {i+1}')}: {rr.get('total_distance_km', 0):.2f}km"
                ).add_to(m)

        # 绘制节点
        demands_dict = results.get("demands", {})
        for i, node in enumerate(nodes):
            if i == 0:
                # 仓库
                folium.Marker(
                    [node["lat"], node["lng"]],
                    popup=f"<b>🏭 {node['name']}</b><br>地址: {node.get('address', '')}",
                    tooltip=node["name"],
                    icon=folium.Icon(color="red", icon="star")
                ).add_to(m)
            else:
                # 场馆
                venue_name = node.get("name", "")
                venue_demand = demands_dict.get(venue_name, 0)
                if isinstance(venue_demand, dict):
                    total = venue_demand.get("总需求", sum(venue_demand.values()))
                else:
                    total = float(venue_demand)

                folium.CircleMarker(
                    [node["lat"], node["lng"]],
                    radius=10,
                    popup=f"<b>🏟️ {venue_name}</b><br>需求: {total:.0f} kg",
                    tooltip=f"{venue_name} ({total:.0f} kg)",
                    color="blue",
                    fill=True,
                    fillColor="blue",
                    fillOpacity=0.7
                ).add_to(m)

        # 图例
        legend_html = '''
        <div style="position:fixed; bottom:50px; left:50px; z-index:1000;
                    background:white; padding:10px; border-radius:5px; border:1px solid gray;">
            <h4 style="margin:0 0 5px 0;">📍 图例</h4>
            <p style="margin:3px 0;"><span style="color:red;">⭐</span> 总仓库（配送起点）</p>
            <p style="margin:3px 0;"><span style="color:blue;">●</span> 场馆（配送终点）</p>
            <p style="margin:3px 0;">— 配送路线</p>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))

        st_folium(m, width="100%", height=500)
    else:
        st.info("无节点数据")

# ======== Tab 2: 碳排放对比 ========
with tab2:
    st.subheader("📊 碳排放对比分析")

    comparison_data = pd.DataFrame({
        "方案": ["基线（柴油车）", f"优化方案（{vehicle_name}）"],
        "碳排放_kg": [baseline_carbon, total_carbon]
    })

    fig_bar = px.bar(
        comparison_data,
        x="方案",
        y="碳排放_kg",
        color="方案",
        title="碳排放对比",
        text_auto=True
    )
    fig_bar.update_layout(yaxis_title="碳排放 (kg CO₂)")
    st.plotly_chart(fig_bar, width="stretch")

    # 减排构成
    if carbon_reduction > 0:
        reduction_data = pd.DataFrame({
            "指标": ["碳减排量", "剩余排放"],
            "数值_kg": [carbon_reduction, total_carbon]
        })

        fig_pie = px.pie(
            reduction_data,
            values="数值_kg",
            names="指标",
            title="碳排放构成",
            hole=0.4
        )
        st.plotly_chart(fig_pie, width="stretch")

    # 各车辆碳排放
    if route_results:
        st.markdown("#### 各车辆碳排放详情")

        route_carbon_data = []
        for i, rr in enumerate(route_results):
            route_carbon_data.append({
                "车辆": rr.get("vehicle_name", f"车辆 {i+1}"),
                "距离_km": rr.get("total_distance_km", 0),
                "碳排放_kg": rr.get("total_carbon_kg", 0),
                "碳效率": rr.get("total_carbon_kg", 0) / max(rr.get("total_distance_km", 1), 0.01)
            })

        df_route_carbon = pd.DataFrame(route_carbon_data)

        fig_route = px.bar(
            df_route_carbon,
            x="车辆",
            y="碳排放_kg",
            color="距离_km",
            title="各车辆碳排放分布",
            text_auto=True
        )
        st.plotly_chart(fig_route, width="stretch")

        st.dataframe(df_route_carbon, hide_index=True, width="stretch")

# ======== Tab 3: 调度详情 ========
with tab3:
    st.subheader("📋 调度详情")

    if route_results:
        # 构建调度详情表
        dispatch_data = []
        for i, rr in enumerate(route_results):
            route_str = " → ".join(rr.get("visits", [])) if rr.get("visits") else "无"
            dispatch_data.append({
                "车辆编号": rr.get("vehicle_name", f"车辆 {i+1}"),
                "车型": rr.get("vehicle_type", vehicle_name),
                "访问顺序": route_str,
                "访问场馆数": len(rr.get("visits", [])),
                "行驶距离_km": f"{rr.get('total_distance_km', 0):.2f}",
                "装载量_kg": f"{rr.get('total_load_kg', 0):.0f}",
                "碳排放_kg": f"{rr.get('total_carbon_kg', 0):.2f}"
            })

        df_dispatch = pd.DataFrame(dispatch_data)
        st.dataframe(df_dispatch, hide_index=True, width="stretch")

        # CSV导出
        csv_data = []
        for i, rr in enumerate(route_results):
            route_str = " → ".join(rr.get("visits", [])) if rr.get("visits") else "无"
            csv_data.append({
                "车辆编号": rr.get("vehicle_name", f"车辆 {i+1}"),
                "车型": rr.get("vehicle_type", vehicle_name),
                "路线": f"总仓库 → {route_str} → 总仓库",
                "访问场馆数": len(rr.get("visits", [])),
                "行驶距离_km": rr.get('total_distance_km', 0),
                "装载量_kg": rr.get('total_load_kg', 0),
                "碳排放_kg": rr.get('total_carbon_kg', 0)
            })

        df_csv = pd.DataFrame(csv_data)
        csv_string = df_csv.to_csv(index=False, encoding="utf-8-sig")

        st.download_button(
            label="📥 下载调度详情CSV",
            data=csv_string,
            file_name="dispatch_details.csv",
            mime="text/csv"
        )

        # 装载明细表
        st.markdown("#### 各车辆装载明细")

        for i, rr in enumerate(route_results):
            with st.expander(f"🚛 {rr.get('vehicle_name', f'车辆 {i+1}')} 装载明细"):
                load_details = rr.get("load_details", [])
                if load_details:
                    df_load = pd.DataFrame(load_details)
                    st.dataframe(df_load, hide_index=True, use_container_width=True)
                else:
                    st.info("无装载明细")

    else:
        st.info("无路线数据")

st.markdown("---")
st.caption(f"💡 优化完成时间: {results.get('timestamp', '未知')}")
