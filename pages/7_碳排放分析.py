"""碳排放分析页面 - 详细碳排放分析与车型对比"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# 引入核心车辆库字典
from utils.vehicle_lib import VEHICLE_LIB

st.set_page_config(page_title="碳排放分析", page_icon="📈", layout="wide")
st.title("📈 第七步：碳排放深度分析")
st.markdown("多动力类型碳足迹横向对比与减排敏感性评估")

# 统一动力类型显示名称
POWER_TYPE_MAPPING = {
    "diesel": "柴油重卡",
    "lng": "LNG天然气重卡",
    "hev": "混合动力 (HEV)",
    "phev": "插电混动 (PHEV)",
    "bev": "纯电动 (BEV)",
    "fcev": "氢燃料电池 (FCEV)",
}

# ===================== 加载数据 =====================
results = st.session_state.get("optimization_results") or st.session_state.get("results")

if not results or not isinstance(results, dict):
    st.warning("⚠️ 尚未执行路径优化，请先完成第五步「路径优化」")
    st.info("请在左侧导航选择第五步，完成优化计算后再查看碳排放概览。")
    st.stop()

route_results = results.get("route_results", [])
nodes = results.get("nodes", [])
fleet_used_by_type = results.get("fleet_used_by_type", {}) or {}
fleet_max_by_type = results.get("fleet_max_by_type", {}) or {}

# 实际优化距离和载重
actual_total_distance = results.get("total_distance_km", 0)
actual_total_emission = results.get("total_emission", 0)
total_demand_kg = sum(rr.get("total_load_kg", 0) for rr in route_results)

# ===================== 路径碳排明细 =====================
st.markdown("### 🔍 路径碳排明细")
st.markdown("本页展示的总碳排已包含**冷启动基数**，以下路径明细按每段**实际载重与距离**通过双公式精准核算。")

if route_results:
    for idx, rr in enumerate(route_results, start=1):
        vname = POWER_TYPE_MAPPING.get(rr.get("vehicle_type", "").split('_')[0].lower(), rr.get("vehicle_type", "未知"))
        with st.expander(f"🚛 车辆{idx}：{rr.get('vehicle_name', '-')} [{vname}]", expanded=False):
            total_load = rr.get("initial_load_kg", rr.get("total_load_kg", 0))
            st.markdown(
                f"**路线总载重**：{total_load/1000:.2f} 吨 &nbsp;|&nbsp; "
                f"**总距离**：{rr.get('total_distance_km', 0):.2f} km &nbsp;|&nbsp; "
                f"**总碳排**：{rr.get('total_carbon_kg', 0):.2f} kg CO₂"
            )
            segments = rr.get("segments", [])
            if segments and nodes:
                segment_rows = []
                for seg_idx, seg in enumerate(segments):
                    from_idx = rr.get("route", [0])[seg_idx]
                    to_idx = rr.get("route", [0, 0])[seg_idx + 1]
                    from_name = nodes[from_idx].get("name", f"节点{from_idx}") if from_idx < len(nodes) else f"节点{from_idx}"
                    to_name = nodes[to_idx].get("name", f"节点{to_idx}") if to_idx < len(nodes) else f"节点{to_idx}"
                    segment_rows.append({
                        "行驶区间": f"{from_name} ➡️ {to_name}",
                        "区间距离 (km)": seg.get("distance_km", 0),
                        "当前实际载重 (吨)": round(seg.get("load_kg", 0) / 1000.0, 3),
                        "区间碳排 (kg CO₂)": round(seg.get("carbon_kg", 0), 4),
                    })
                st.dataframe(pd.DataFrame(segment_rows), hide_index=True, width="stretch")
            elif segments:
                st.dataframe(pd.DataFrame(segments), hide_index=True, width="stretch")
            else:
                st.info("当前路线未包含分段碳排明细。")
else:
    st.info("尚无路线明细数据，请先完成第五步路径优化。")

st.markdown("---")

# ===================== 核心动力类型碳因子横评 =====================
st.markdown("### 🧬 核心动力类型碳因子横评")

vt_data = []
for vid, v_info in VEHICLE_LIB.items():
    ef_g = v_info.get("intensity_g_per_tkm", 60)
    ef_kg = ef_g / 1000.0
    label = "🟢 低碳" if ef_kg < 0.04 else ("🟡 中碳" if ef_kg < 0.06 else "🔴 高碳")
    
    vt_data.append({
        "车型名称": POWER_TYPE_MAPPING.get(vid, vid),
        "有载碳因子 (kg/吨km)": ef_kg,
        "空跑碳因子 (kg/km)": v_info.get("empty_g_per_km", 0) / 1000.0,
        "冷启动 (kg)": v_info.get("cold_start_g", 0) / 1000.0,
        "碳排放评级": label,  # <--- 注意这里叫 "碳排放评级"
    })

df_vt = pd.DataFrame(vt_data)

col1, col2 = st.columns([2, 1])
with col1:
    fig_ef = px.bar(
        df_vt, x="车型名称", y="有载碳因子 (kg/吨km)", color="碳排放评级",  # <--- 对齐列名
        title="各车型主碳因子对比 (越低越好)",
        color_discrete_map={"🟢 低碳": "#00CC96", "🟡 中碳": "#FFA15A", "🔴 高碳": "#EF553B"},
        text_auto=".3f",
    )
    fig_ef.update_layout(height=400)
    st.plotly_chart(fig_ef, width="stretch")

with col2:
    st.dataframe(df_vt[["车型名称", "有载碳因子 (kg/吨km)", "碳排放评级"]], hide_index=True, width="stretch")

st.markdown("---")

# ===================== 实际派车情况 =====================
if fleet_used_by_type or fleet_max_by_type:
    st.markdown("### 🚛 本次方案派车组成（实际 / 上限）")
    all_types = sorted(set(list(fleet_max_by_type.keys()) + list(fleet_used_by_type.keys())))
    rows = []
    for vtype in all_types:
        clean_vtype = vtype.split('_')[0].lower()
        used = int(fleet_used_by_type.get(vtype, 0) or 0)
        cap = int(fleet_max_by_type.get(vtype, 0) or 0)
        rows.append({
            "动力类型": POWER_TYPE_MAPPING.get(clean_vtype, vtype),
            "实际派车数": used,
            "可用上限": cap,
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

# ===================== 模拟各车型碳排放 =====================
st.markdown("### 🧪 车型换算模拟推演")
st.markdown(f"基于本次最优路径（总距离 **{actual_total_distance:.2f} km**，"
            f"总货物量 **{total_demand_kg:,.0f} kg**），推演如果**全部**使用某种车型，碳排表现如何：")

simulation_data = []

# 基准线设定为系统的普通柴油重卡
baseline_ef = VEHICLE_LIB.get("diesel", {}).get("intensity_g_per_tkm", 60) / 1000.0
baseline_emission = (total_demand_kg / 1000.0) * actual_total_distance * baseline_ef

for vid, v_info in VEHICLE_LIB.items():
    ef_kg = v_info.get("intensity_g_per_tkm", 60) / 1000.0
    simulated_emission = (total_demand_kg / 1000.0) * actual_total_distance * ef_kg
    reduction = baseline_emission - simulated_emission
    reduction_pct = (reduction / baseline_emission * 100) if baseline_emission > 0 else 0

    simulation_data.append({
        "车型": POWER_TYPE_MAPPING.get(vid, vid),
        "模拟碳排放(kg CO₂)": round(simulated_emission, 2), # <--- 严格对齐画图所需的列名
        "基线碳排放(kg CO₂)": round(baseline_emission, 2),  # <--- 加入基准线用于画红线
        "减排量 (kg CO₂)": round(reduction, 2),
        "减排比例(%)": round(reduction_pct, 1),           # <--- 严格对齐雷达图的列名
        "等效种树 (棵/年)": round(simulated_emission / 12.0, 1),
    })

df_sim = pd.DataFrame(simulation_data)

fig_sim = px.bar(
    df_sim, x="车型", y="模拟碳排放(kg CO₂)", color="车型", # 换成按"车型"分色，因为我们没存能源类型
    title="单一车型全包换算模拟",
    text_auto=".1f",
    color_discrete_sequence=px.colors.qualitative.Set2,
)
# 画红色虚线（利用刚刚补全的 基线碳排放 列）
fig_sim.add_hline(y=df_sim["基线碳排放(kg CO₂)"].max(),
                  line_dash="dash", line_color="red",
                  annotation_text=" 基线碳排放（柴油单独配送）")
fig_sim.update_layout(height=450, showlegend=False)
st.plotly_chart(fig_sim, width="stretch")

with st.expander("📊 查看详细模拟数据"):
    st.dataframe(df_sim, width="stretch", hide_index=True)

st.markdown("---")

# ===================== 减排比例雷达图 =====================
st.markdown("### 🕸️ 车型减排潜力雷达图")

fig_radar = go.Figure()
categories = df_sim["车型"].tolist()
fig_radar.add_trace(go.Scatterpolar(
    r=df_sim["减排比例(%)"].tolist(),  # <--- 对齐
    theta=categories,
    fill="toself",
    name="减排比例(%)",
    marker=dict(color="#00CC96")
))
fig_radar.update_layout(
    polar=dict(radialaxis=dict(visible=True, ticksuffix="%")),
    title="相比传统柴油直发的减排百分比",
    height=450,
)
st.plotly_chart(fig_radar, width="stretch")

st.markdown("---")

# ===================== 最优车型推荐 =====================
st.markdown("### 🏆 减排冠军揭晓")

if not df_sim.empty:
    best = df_sim.loc[df_sim["模拟碳排放(kg CO₂)"].idxmin()] # <--- 对齐
    worst = df_sim.loc[df_sim["模拟碳排放(kg CO₂)"].idxmax()] # <--- 对齐

    col_best, col_worst = st.columns(2)
    with col_best:
        st.success(f"""
        **🥇 绿色先锋推荐：{best['车型']}**
        - 模拟碳排放：{best['模拟碳排放(kg CO₂)']:.2f} kg CO₂
        - 减排比例：**{best['减排比例(%)']:.1f}%**
        - 等效自然界种树：{best['等效种树 (棵/年)']:.1f} 棵/年
        """)
    with col_worst:
        st.error(f"""
        **⚠️ 高碳排放警示：{worst['车型']}**
        - 模拟碳排放：{worst['模拟碳排放(kg CO₂)']:.2f} kg CO₂
        - 减排比例：{worst['减排比例(%)']:.1f}%
        """)

st.markdown("---")

# ===================== 碳排放敏感性分析 =====================
st.markdown("### 📉 里程-碳排敏感性分析")
st.markdown("分析当距离变化时，不同车型的碳排放变化趋势")

sensitivity_data = []
for mult in [0.5, 0.75, 1.0, 1.25, 1.5]:
    for vid, v_info in VEHICLE_LIB.items():
        ef_kg = v_info.get("intensity_g_per_tkm", 60) / 1000.0
        dist = actual_total_distance * mult
        emission = dist * ef_kg * (total_demand_kg / 1000.0)
        sensitivity_data.append({
            "距离缩放倍数": f"{mult}x",
            "距离(km)": round(dist, 1), # <--- 对齐
            "车型": POWER_TYPE_MAPPING.get(vid, vid), # <--- 对齐
            "碳排放(kg CO₂)": round(emission, 2),
        })

df_sens = pd.DataFrame(sensitivity_data)
fig_sens = px.line(df_sens, x="距离(km)", y="碳排放(kg CO₂)", color="车型", # <--- 对齐
                   title="碳排放敏感性分析（距离变化）", markers=True)
fig_sens.update_layout(height=450)
st.plotly_chart(fig_sens, width="stretch")

st.markdown("---")
st.caption(f"数据来源：第五步路径优化结果 | 计算时间：{results.get('timestamp', '未知')}")

st.markdown("---")
if st.button("最终步：导出优化报告 ➡️", type="primary", width="stretch"):
    st.switch_page("pages/8_优化结果.py")