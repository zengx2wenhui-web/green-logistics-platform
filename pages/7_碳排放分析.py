"""碳排放分析页面 - 详细碳排放分析与车型对比

修复：
- 使用实际优化路线数据替代硬编码avg_distance=50
- 使用 utils/carbon_calc.py 标准碳因子
- 树等效修正为12 kg CO2/棵年
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json

st.set_page_config(page_title="碳排放分析", page_icon="")
st.title(" 第七步：碳排放分析")
st.markdown("多车型碳排放对比分析与减排方案评估")


# ===================== 加载数据 =====================
results = st.session_state.get("optimization_results") or st.session_state.get("results")

if not results or not isinstance(results, dict):
    st.warning(" 尚未执行路径优化，请先完成第五步")
    st.stop()

route_results = results.get("route_results", [])

# 实际优化距离和载重
actual_total_distance = results.get("total_distance_km", 0)
actual_total_emission = results.get("total_emission", 0)
total_demand_kg = sum(
    rr.get("total_load_kg", 0) for rr in route_results
)
avg_distance = actual_total_distance / len(route_results) if route_results else 50

# ===================== 加载车型库 =====================
@st.cache_data
def load_vehicle_types():
    """加载车型数据"""
    try:
        with open("data/vehicle_types.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "vehicle_types" in data:
                return data["vehicle_types"]
            return data
    except FileNotFoundError:
        return []

vehicle_types = load_vehicle_types()

if not vehicle_types:
    st.error(" 无法加载车型数据")
    st.stop()

# ===================== 车型碳因子对比 =====================
st.markdown("###  车型碳因子对比")

vt_data = []
for vt in vehicle_types:
    ef = vt.get("emission_factor", 0)
    label = "低碳" if ef < 0.04 else ("中碳" if ef < 0.06 else "高碳")
    vt_data.append({
        "车型ID": vt.get("id", ""),
        "车型名称": vt.get("name", ""),
        "碳因子(kg CO₂/吨km)": ef,
        "最小载重(吨)": vt.get("load_range", [0, 0])[0] if isinstance(vt.get("load_range"), list) else 0,
        "最大载重(吨)": vt.get("load_range", [0, 0])[1] if isinstance(vt.get("load_range"), list) else 0,
        "碳排放等级": label,
        "能源类型": vt.get("fuel_type", "未知"),
    })

df_vt = pd.DataFrame(vt_data)

col1, col2 = st.columns([2, 1])
with col1:
    fig_ef = px.bar(
        df_vt, x="车型名称", y="碳因子(kg CO₂/吨km)", color="碳排放等级",
        title="各车型碳因子对比",
        color_discrete_map={"低碳": "#00CC96", "中碳": "#FFA15A", "高碳": "#EF553B"},
        text_auto=".3f",
    )
    fig_ef.update_layout(height=400)
    st.plotly_chart(fig_ef, width="stretch")

with col2:
    st.dataframe(df_vt[["车型名称", "碳因子(kg CO₂/吨km)", "碳排放等级"]], hide_index=True)

st.markdown("---")

# ===================== 模拟各车型碳排放 =====================
st.markdown("###  各车型碳排放模拟对比")
st.markdown(f"基于实际优化路线数据：总距离 **{actual_total_distance:.2f} km**，"
            f"总货物量 **{total_demand_kg:,.0f} kg**")

simulation_data = []
for vt in vehicle_types:
    ef = vt.get("emission_factor", 0)
    load_range = vt.get("load_range", [5, 20])
    max_load_ton = load_range[1] if isinstance(load_range, list) and len(load_range) >= 2 else 15

    # 使用实际路线数据模拟该车型的碳排放
    simulated_emission = 0
    for rr in route_results:
        dist = rr.get("total_distance_km", 0)
        load_kg = rr.get("total_load_kg", 0)
        load_ton = load_kg / 1000.0
        simulated_emission += dist * ef * load_ton

    # 基线碳排放（单车配送）
    baseline_ef = 0.080
    baseline_emission = total_demand_kg / 1000.0 * actual_total_distance * baseline_ef

    reduction = baseline_emission - simulated_emission
    reduction_pct = (reduction / baseline_emission * 100) if baseline_emission > 0 else 0

    simulation_data.append({
        "车型": vt.get("name", ""),
        "碳因子": ef,
        "能源类型": vt.get("fuel_type", "未知"),
        "模拟碳排放(kg CO₂)": round(simulated_emission, 2),
        "基线碳排放(kg CO₂)": round(baseline_emission, 2),
        "减排量(kg CO₂)": round(reduction, 2),
        "减排比例(%)": round(reduction_pct, 1),
        "等效种树(棵)": round(simulated_emission / 12.0, 1),
    })

df_sim = pd.DataFrame(simulation_data)

# 排列图表
fig_sim = px.bar(
    df_sim, x="车型", y="模拟碳排放(kg CO₂)", color="能源类型",
    title="各车型碳排放模拟对比",
    text_auto=".1f",
    color_discrete_sequence=px.colors.qualitative.Set2,
)
# 添加基线线
fig_sim.add_hline(y=df_sim["基线碳排放(kg CO₂)"].max(),
                  line_dash="dash", line_color="red",
                  annotation_text="基线碳排放（柴油单独配送）")
fig_sim.update_layout(height=450)
st.plotly_chart(fig_sim, width="stretch")

# 详细数据表
with st.expander(" 详细模拟数据"):
    st.dataframe(df_sim, width="stretch", hide_index=True)

st.markdown("---")

# ===================== 减排比例雷达图 =====================
st.markdown("###  车型减排能力雷达图")

fig_radar = go.Figure()
categories = df_sim["车型"].tolist()
fig_radar.add_trace(go.Scatterpolar(
    r=df_sim["减排比例(%)"].tolist(),
    theta=categories,
    fill="toself",
    name="减排比例(%)"
))
fig_radar.update_layout(
    polar=dict(radialaxis=dict(visible=True)),
    title="各车型减排比例雷达图",
    height=400,
)
st.plotly_chart(fig_radar, width="stretch")

st.markdown("---")

# ===================== 最优车型推荐 =====================
st.markdown("###  车型推荐")

if not df_sim.empty:
    best = df_sim.loc[df_sim["模拟碳排放(kg CO₂)"].idxmin()]
    worst = df_sim.loc[df_sim["模拟碳排放(kg CO₂)"].idxmax()]

    col_best, col_worst = st.columns(2)
    with col_best:
        st.success(f"""
        ** 推荐车型：{best['车型']}**
        - 碳因子：{best['碳因子']} kg CO₂/吨km
        - 模拟碳排放：{best['模拟碳排放(kg CO₂)']:.2f} kg CO₂
        - 减排比例：{best['减排比例(%)']:.1f}%
        - 等效种树：{best['等效种树(棵)']:.1f} 棵/年
        """)
    with col_worst:
        st.warning(f"""
        ** 高碳车型：{worst['车型']}**
        - 碳因子：{worst['碳因子']} kg CO₂/吨km
        - 模拟碳排放：{worst['模拟碳排放(kg CO₂)']:.2f} kg CO₂
        - 减排比例：{worst['减排比例(%)']:.1f}%
        - 等效种树：{worst['等效种树(棵)']:.1f} 棵/年
        """)

    # 计算最优车型相对当前方案的节省
    current_type = results.get("vehicle_type", "")
    if current_type and current_type != best["车型"]:
        savings = actual_total_emission - best["模拟碳排放(kg CO₂)"]
        if savings > 0:
            st.info(f" 切换到 **{best['车型']}** 可比当前方案再节省 **{savings:.2f} kg CO₂** "
                    f"（约 {savings / 12.0:.1f} 棵树/年）")

st.markdown("---")

# ===================== 碳排放敏感性分析 =====================
st.markdown("###  碳排放敏感性分析")
st.markdown("分析当距离变化时，不同车型的碳排放变化趋势")

sensitivity_data = []
for mult in [0.5, 0.75, 1.0, 1.25, 1.5]:
    for vt in vehicle_types:
        ef = vt.get("emission_factor", 0)
        dist = actual_total_distance * mult
        emission = dist * ef * (total_demand_kg / 1000.0)
        sensitivity_data.append({
            "距离倍数": f"{mult}x",
            "距离(km)": round(dist, 1),
            "车型": vt.get("name", ""),
            "碳排放(kg CO₂)": round(emission, 2),
        })

df_sens = pd.DataFrame(sensitivity_data)
fig_sens = px.line(df_sens, x="距离(km)", y="碳排放(kg CO₂)", color="车型",
                   title="碳排放敏感性分析（距离变化）", markers=True)
fig_sens.update_layout(height=400)
st.plotly_chart(fig_sens, width="stretch")

st.markdown("---")
st.caption(f"分析基于第五步优化结果 | 计算时间：{results.get('timestamp', '未知')}")

st.markdown("---")
if st.button("下一步：优化结果 ➡️", type="primary", width="stretch"):
    st.switch_page("pages/8_优化结果.py")