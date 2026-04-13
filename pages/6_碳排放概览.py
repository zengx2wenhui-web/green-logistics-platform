"""碳排放概览页面 - 碳排放总览与基本分析

修复：
- 树等效从21.7修正为12 kg CO2/棵年
- 使用 utils/carbon_calc.py 标准函数
- 使用实际优化数据（而非伪造数据）
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="碳排放概览", page_icon="")
st.title(" 第六步：碳排放概览")
st.markdown("物流碳排放总览与分析")


# ===================== 读取优化结果 =====================
results = st.session_state.get("optimization_results") or st.session_state.get("results")

if not results or not isinstance(results, dict):
    st.warning(" 尚未执行路径优化，请先完成第五步「路径优化」")
    st.info("请在左侧导航选择第五步，完成优化计算后再查看碳排放概览。")
    st.stop()

route_results = results.get("route_results", [])
if not route_results:
    st.warning(" 无可用的路线数据")
    st.stop()

# ===================== 基本指标 =====================
st.markdown("###  核心指标")

total_emission = results.get("total_emission", 0)
baseline_emission = results.get("baseline_emission", 0)
reduction_pct = results.get("reduction_percent", 0)
total_distance = results.get("total_distance_km", 0)
num_vehicles = results.get("num_vehicles_used", 0)

# 碳等效换算（12 kg CO2/棵年）
try:
    from utils.carbon_calc import carbon_equivalents
    equiv = carbon_equivalents(total_emission)
    tree_count = equiv.get("trees_per_year", total_emission / 12.0)
    driving_km = total_emission / 0.21  # 普通轿车 0.21 kg CO₂/km
except Exception:
    tree_count = total_emission / 12.0
    driving_km = total_emission / 0.21

carbon_reduction = baseline_emission - total_emission

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(" 总碳排放", f"{total_emission:.2f} kg CO₂",
              delta=f"-{reduction_pct:.1f}%" if reduction_pct > 0 else None,
              delta_color="inverse")
with col2:
    st.metric(" 总行驶距离", f"{total_distance:.2f} km")
with col3:
    st.metric(" 使用车辆", f"{num_vehicles} 辆")
with col4:
    st.metric(" 等效种树", f"{tree_count:.1f} 棵")

st.markdown("---")

# ===================== 碳排放等效分析 =====================
st.markdown("###  碳排放等效换算")
st.markdown(f"""
| 指标 | 数值 | 说明 |
|------|------|------|
| 总碳排放 | **{total_emission:.2f} kg CO₂** | 优化后排放量 |
| 等效种树 | **{tree_count:.1f} 棵** | 每棵树每年吸收12 kg CO₂ |
| 等效驾驶 | **{driving_km:.1f} km** | 普通轿车行驶里程（0.21 kg CO₂/km） |
| 减排量 | **{carbon_reduction:.2f} kg CO₂** | 比基线节省 {reduction_pct:.1f}% |
""")

st.markdown("---")

# ===================== 对比分析 =====================
st.markdown("###  基线 vs 优化 碳排放对比")

col_left, col_right = st.columns(2)
with col_left:
    df_compare = pd.DataFrame({
        "方案": [" 基线方案（单独配送）", " 优化方案（VRP调度）"],
        "碳排放(kg CO₂)": [baseline_emission, total_emission],
    })
    fig_bar = px.bar(df_compare, x="方案", y="碳排放(kg CO₂)", color="方案",
                     title="碳排放对比", text_auto=".2f",
                     color_discrete_sequence=["#EF553B", "#00CC96"])
    fig_bar.update_layout(showlegend=False, height=400)
    st.plotly_chart(fig_bar, use_container_width=True)

with col_right:
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=total_emission,
        delta={"reference": baseline_emission, "decreasing": {"color": "green"}},
        title={"text": "优化碳排放 (kg CO₂)"},
        gauge={
            "axis": {"range": [0, baseline_emission * 1.2] if baseline_emission > 0 else [0, 100]},
            "bar": {"color": "#00CC96"},
            "steps": [
                {"range": [0, baseline_emission * 0.5], "color": "#d4edda"},
                {"range": [baseline_emission * 0.5, baseline_emission], "color": "#fff3cd"},
                {"range": [baseline_emission, baseline_emission * 1.2], "color": "#f8d7da"},
            ],
            "threshold": {
                "line": {"color": "red", "width": 4},
                "thickness": 0.75,
                "value": baseline_emission,
            },
        },
    ))
    fig_gauge.update_layout(height=400)
    st.plotly_chart(fig_gauge, use_container_width=True)

st.markdown("---")

# ===================== 各车辆碳排放分布 =====================
st.markdown("###  各车辆碳排放分布")

vehicle_data = [{
    "车辆": rr.get("vehicle_name", f"车辆{i+1}"),
    "车型": rr.get("vehicle_type", "未知"),
    "距离(km)": rr.get("total_distance_km", 0),
    "装载量(kg)": rr.get("total_load_kg", 0),
    "碳排放(kg CO₂)": rr.get("total_carbon_kg", 0),
    "访问场馆数": len(rr.get("visits", [])),
} for i, rr in enumerate(route_results)]

df_vehicles = pd.DataFrame(vehicle_data)

col_pie, col_table = st.columns([1, 1])
with col_pie:
    fig_pie = px.pie(df_vehicles, values="碳排放(kg CO₂)", names="车辆",
                     title="各车辆碳排放占比", hole=0.4,
                     color_discrete_sequence=px.colors.qualitative.Set3)
    fig_pie.update_traces(textposition="inside", textinfo="percent+label")
    fig_pie.update_layout(height=400)
    st.plotly_chart(fig_pie, use_container_width=True)

with col_table:
    st.dataframe(df_vehicles, use_container_width=True, hide_index=True)

st.markdown("---")

# ===================== 碳排放效率分析 =====================
st.markdown("###  碳排放效率分析")

for rr in vehicle_data:
    dist = rr.get("距离(km)", 0)
    load = rr.get("装载量(kg)", 0)
    carbon = rr.get("碳排放(kg CO₂)", 0)
    rr["碳效率(g CO₂/km)"] = round(carbon * 1000 / dist, 2) if dist > 0 else 0
    rr["碳效率(g CO₂/kg货物)"] = round(carbon * 1000 / load, 2) if load > 0 else 0

df_vehicles = pd.DataFrame(vehicle_data)

fig_eff = px.bar(df_vehicles, x="车辆", y=["碳效率(g CO₂/km)", "碳效率(g CO₂/kg货物)"],
                 barmode="group", title="车辆碳排放效率对比")
fig_eff.update_layout(height=400, yaxis_title="碳效率")
st.plotly_chart(fig_eff, use_container_width=True)

# ===================== 优化建议 =====================
st.markdown("###  优化建议")

try:
    from utils.carbon_calc import generate_optimization_suggestions
    suggestions = generate_optimization_suggestions(
        total_carbon_kg=total_emission,
        vehicle_type=results.get("vehicle_type", "diesel_heavy"),
        total_distance_km=total_distance,
    )
    if suggestions:
        for s in suggestions:
            st.markdown(f"- {s}")
    else:
        st.info("暂无优化建议")
except Exception:
    tips = []
    if reduction_pct < 10:
        tips.append(" 当前减排比例较低，建议考虑切换新能源车型（如纯电动BEV、燃料电池FCEV）")
    if num_vehicles > 1:
        tips.append(" 可尝试优化车队规模，减少空载行驶")
    tips.append(" 合理整合物资需求，提高单车装载率")
    tips.append(" 设置中转仓缩短配送半径，降低运输碳排放")
    for tip in tips:
        st.markdown(f"- {tip}")

st.markdown("---")
st.caption(f"数据来源：第五步路径优化结果 | 计算时间：{results.get('timestamp', '未知')}")

st.markdown("---")
if st.button("下一步：碳排放分析 ➡️", type="primary", use_container_width=True):
    st.switch_page("pages/7_碳排放分析.py")