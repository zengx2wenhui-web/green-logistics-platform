"""碳排放分析页面"""
import streamlit as st
import pandas as pd
import plotly.express as px
import json

st.set_page_config(page_title="碳排放分析", page_icon="🔬")

st.title("🔬 Step 7：碳排放分析")
st.markdown("基于车型库的碳排放对比分析")

# ===================== 加载车型库 =====================
@st.cache_data
def load_vehicle_types():
    try:
        with open("data/vehicle_types.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "vehicle_types" in data:
                return data["vehicle_types"]
            return data
    except:
        try:
            with open("green-logistics-platform/data/vehicle_types.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "vehicle_types" in data:
                    return data["vehicle_types"]
                return data
        except:
            return []

vehicle_types = load_vehicle_types()

# ===================== 碳排放因子对比表格 =====================
st.subheader("📋 车型碳排放因子对比表")

if vehicle_types:
    table_data = []
    for v in vehicle_types:
        table_data.append({
            "车型名称": v["name"],
            "能源类型": v.get("fuel_type", ""),
            "碳排放因子_min": v.get("emission_factor_min", 0),
            "碳排放因子_max": v.get("emission_factor_max", 0),
            "碳排放因子_default": v.get("emission_factor_default", 0),
            "排放单位": v.get("emission_factor_unit", "kg CO₂/吨·km"),
            "对比柴油减排": v.get("reduction_vs_diesel", "N/A")
        })
    df_factors = pd.DataFrame(table_data)
    st.dataframe(df_factors, hide_index=True, width="stretch")
else:
    st.warning("无法加载车型库数据")

st.markdown("---")

# ===================== 碳排放对比分析 =====================
st.subheader("📊 不同车型碳排放对比")

# 获取session_state中的数据
vehicles = st.session_state.get("vehicles", [])

# 检查物资需求数据是否存在
has_demands = "demands" in st.session_state and st.session_state["demands"] and len(st.session_state["demands"]) > 0

if not has_demands:
    st.warning("⚠️ 请先在【物资需求】页面录入或上传物资需求数据")
    st.stop()
else:
    demands = st.session_state["demands"]
    total_demand_kg = sum(demands.values()) if demands else 0
    st.success(f"已加载 {len(demands)} 个场馆的物资需求数据，总需求 {total_demand_kg:,.1f} kg")

# 假设运输距离（根据总需求估算，每吨每公里碳排放）
# 这里用Haversine估算平均运输距离为50km
avg_distance_km = 50

# 计算各车型的碳排放
emission_data = []
for v in vehicle_types:
    vid = v["id"]
    vname = v["name"]
    ef = v.get("emission_factor_default", 0.060)  # kg CO₂/吨·km
    load_ton = v.get("max_load_ton_default", 15.0)

    # 计算总碳排放 = 总需求吨 × 距离 × 排放因子
    total_ton = total_demand_kg / 1000
    total_carbon_kg = total_ton * avg_distance_km * ef

    # 计算每辆车碳排放（假设车队5辆）
    fleet_carbon_kg = total_carbon_kg * 5

    emission_data.append({
        "车型": vname,
        "能源": v.get("fuel_type", ""),
        "排放因子": ef,
        "载重吨": load_ton,
        "总需求_t": total_ton,
        "总碳排放_kg": fleet_carbon_kg
    })

df_emission = pd.DataFrame(emission_data)

if total_demand_kg > 0:
    col1, col2 = st.columns(2)

    with col1:
        fig_bar = px.bar(
            df_emission,
            x="车型",
            y="总碳排放_kg",
            color="能源",
            title=f"车队碳排放对比（总需求 {total_demand_kg:,.0f} kg，平均运输 {avg_distance_km} km）",
            text_auto=True
        )
        fig_bar.update_layout(yaxis_title="碳排放 (kg CO₂)")
        st.plotly_chart(fig_bar, width="stretch")

    with col2:
        fig_ef = px.bar(
            df_emission,
            x="车型",
            y="排放因子",
            color="能源",
            title="碳排放因子对比 (kg CO₂/吨·km)",
            text_auto=True
        )
        st.plotly_chart(fig_ef, width="stretch")

    # 减排潜力排名
    st.subheader("🌿 减排潜力排名")
    df_sorted = df_emission.sort_values("总碳排放_kg", ascending=True)
    df_sorted["减排空间_%"] = ((df_sorted["总碳排放_kg"].max() - df_sorted["总碳排放_kg"]) / df_sorted["总碳排放_kg"].max() * 100).round(1)

    col_r1, col_r2 = st.columns(2)
    with col_r1:
        st.dataframe(df_sorted[["车型", "总碳排放_kg", "减排空间_%"]], hide_index=True, width="stretch")
    with col_r2:
        best = df_sorted.iloc[0]
        worst = df_sorted.iloc[-1]
        st.metric("最优车型", best["车型"])
        st.metric("减排潜力", f"{best['减排空间_%']:.1f}%")
        st.metric("相比柴油车", f"减少 {worst['总碳排放_kg'] - best['总碳排放_kg']:,.0f} kg CO₂")
else:
    st.info("📦 请先在「物资需求」页面录入物资需求，才能进行碳排放分析")

st.markdown("---")

# ===================== 当前配置碳排放 =====================
st.subheader("🚛 当前车队配置碳排放")

if vehicles:
    config_carbon = []
    for v in vehicles:
        vid = v.get("vehicle_type", "")
        name = v.get("name", vid)
        count = v.get("count", 0)
        ef = v.get("emission_factor", 0.060)
        load_ton = v.get("load_ton", 15.0)

        if count > 0:
            total_ton = total_demand_kg / 1000
            total_carbon_kg = total_ton * avg_distance_km * ef * count

            config_carbon.append({
                "车型": name,
                "数量": count,
                "碳因子": ef,
                "载重吨": load_ton,
                "估算碳排放_kg": total_carbon_kg
            })

    if config_carbon:
        df_config = pd.DataFrame(config_carbon)
        st.dataframe(df_config, hide_index=True, width="stretch")

        total_config_carbon = df_config["估算碳排放_kg"].sum()
        st.metric("当前配置总碳排放", f"{total_config_carbon:,.0f} kg CO₂")
    else:
        st.info("请在「车辆配置」页面添加车辆")
else:
    st.info("请在「车辆配置」页面配置车队")

st.markdown("---")
st.caption("💡 提示: 碳排放计算公式 E = 总需求(t) × 运输距离(km) × 排放因子(kg CO₂/吨·km)")
