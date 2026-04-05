"""碳排放概览页面"""
import streamlit as st
import pandas as pd
import plotly.express as px
import json

st.set_page_config(page_title="碳排放概览", page_icon="📊")

st.title("📊 Step 5：碳排放概览")
st.markdown("赛事物流碳足迹实时监控")

# ===================== 检查优化结果 =====================
result = st.session_state.get("optimization_results") or st.session_state.get("results")

vehicles = st.session_state.get("vehicles", [])
demands = st.session_state.get("demands", {})

# ===================== 关键指标展示 =====================
if result and isinstance(result, dict) and result.get("route_results"):
    total_carbon_kg = result.get("total_emission", 0)
    baseline_carbon_kg = result.get("baseline_emission", 0)
    reduction_pct = result.get("reduction_percent", 0)
    tree_equivalent = (baseline_carbon_kg - total_carbon_kg) / 21.7 if total_carbon_kg > 0 else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "总碳排放量",
            f"{total_carbon_kg:,.1f} kg CO₂",
            delta=f"-{reduction_pct:.1f}%" if reduction_pct > 0 else None
        )
    with col2:
        st.metric(
            "对比基线减排",
            f"{reduction_pct:.1f}%",
            delta="相比柴油车" if reduction_pct > 0 else "需优化"
        )
    with col3:
        st.metric(
            "相当于种树",
            f"{tree_equivalent:.0f} 棵/年",
            delta="每棵年吸21.7kg CO₂"
        )

    st.markdown("---")

    # ===================== 碳排放构成分析 =====================
    st.subheader("🥧 碳排放构成分析")

    col_pie1, col_pie2 = st.columns(2)

    with col_pie1:
        # 按路线分类
        route_results = result.get("route_results", [])
        if route_results:
            route_carbon = []
            for i, rr in enumerate(route_results):
                route_carbon.append({
                    "路线": rr.get("vehicle_name", f"车辆 {i+1}"),
                    "碳排放_kg": rr.get("total_carbon_kg", 0),
                    "距离_km": rr.get("total_distance_km", 0)
                })

            df_routes = pd.DataFrame(route_carbon)
            df_routes["类型"] = df_routes["距离_km"].apply(
                lambda x: "干线运输" if x > 30 else "终端配送"
            )

            pie_data = df_routes.groupby("类型")["碳排放_kg"].sum().reset_index()

            fig_pie1 = px.pie(
                pie_data,
                values="碳排放_kg",
                names="类型",
                title="干线运输 vs 终端配送 碳排放构成",
                hole=0.4
            )
            st.plotly_chart(fig_pie1, width="stretch")
        else:
            st.info("无可用路线数据")

    with col_pie2:
        # 车辆类型构成
        vehicle_type_in_result = result.get("vehicle_type", "diesel_heavy")
        vehicle_name_map = {
            "diesel_heavy": "柴油重卡",
            "lng": "LNG天然气",
            "hev": "柴电混动",
            "phev": "插电混动",
            "bev": "纯电动",
            "fcev": "氢燃料电池"
        }
        vehicle_name = vehicle_name_map.get(vehicle_type_in_result, vehicle_type_in_result)

        pie_data2 = pd.DataFrame({
            "类型": [vehicle_name, "其他（假设）"],
            "碳排放_kg": [total_carbon_kg * 0.7, total_carbon_kg * 0.3]
        })

        fig_pie2 = px.pie(
            pie_data2,
            values="碳排放_kg",
            names="类型",
            title="车辆类型碳排放构成",
            hole=0.4
        )
        st.plotly_chart(fig_pie2, width="stretch")

    # ===================== 各车辆碳排放对比 =====================
    st.subheader("📊 各车辆碳排放对比")

    if route_results:
        df_vehicle_carbon = pd.DataFrame([{
            "车辆": rr.get("vehicle_name", f"车辆 {i}"),
            "碳排放(kg CO₂)": rr.get("total_carbon_kg", 0),
            "行驶距离(km)": rr.get("total_distance_km", 0),
            "装载量(kg)": rr.get("total_load_kg", 0)
        } for i, rr in enumerate(route_results)])

        fig_bar = px.bar(
            df_vehicle_carbon,
            x="车辆",
            y="碳排放(kg CO₂)",
            color="车辆",
            title="各车辆碳排放量对比",
            text_auto=True
        )
        fig_bar.update_layout(showlegend=False)
        st.plotly_chart(fig_bar, width="stretch")

    # ===================== 详细数据表 =====================
    st.subheader("📋 路线详情")

    if route_results:
        detail_table = []
        for i, rr in enumerate(route_results):
            detail_table.append({
                "车辆编号": rr.get("vehicle_name", f"车辆 {i+1}"),
                "车型": vehicle_name_map.get(result.get("vehicle_type", ""), result.get("vehicle_type", "")),
                "行驶距离_km": f"{rr.get('total_distance_km', 0):.2f}",
                "碳排放_kg": f"{rr.get('total_carbon_kg', 0):.2f}",
                "装载量_kg": f"{rr.get('total_load_kg', 0):.0f}",
                "访问场馆数": len(rr.get("visits", []))
            })

        df_detail = pd.DataFrame(detail_table)
        st.dataframe(df_detail, hide_index=True, width="stretch")

else:
    # ===================== 无数据提示 =====================
    st.warning("⚠️ 暂无优化计算结果")

    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.info("""
        **请先完成以下步骤：**
        1. 🏭 仓库设置 - 设置总仓库
        2. 🏟️ 场馆录入 - 添加配送场馆
        3. 📦 物资需求 - 录入物资需求
        4. 🚛 车辆配置 - 配置配送车辆
        5. 🗺️ 路径优化 - 运行优化计算
        """)
    with col_info2:
        st.info("""
        **或在「路径优化」页面**
        点击「🚀 开始优化计算」按钮
        运行完整的物流网络优化流程
        """)

    st.markdown("---")

    # 即使没有优化结果，也显示车型库概览
    st.subheader("📊 车型碳排放参考")

    import json
    try:
        with open("data/vehicle_types.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "vehicle_types" in data:
                vehicle_types = data["vehicle_types"]
            else:
                vehicle_types = data
    except:
        try:
            with open("green-logistics-platform/data/vehicle_types.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "vehicle_types" in data:
                    vehicle_types = data["vehicle_types"]
                else:
                    vehicle_types = data
        except:
            vehicle_types = []

    if vehicle_types:
        table_data = []
        for v in vehicle_types:
            table_data.append({
                "车型名称": v.get("name", ""),
                "能源类型": v.get("fuel_type", ""),
                "碳排放因子": v.get("emission_factor_default", 0),
                "单位": v.get("emission_factor_unit", "kg CO₂/吨·km")
            })
        df_ref = pd.DataFrame(table_data)
        st.dataframe(df_ref, hide_index=True, width="stretch")
