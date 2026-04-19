"""车辆配置页面"""
import streamlit as st
import pandas as pd

from utils.vehicle_lib import VEHICLE_LIB

st.set_page_config(page_title="车辆配置", page_icon="🚛")

st.title("🚛 第四步：车辆配置")
st.markdown("选择可用动力类型，并填写每类车的**实际载重**与**可用上限**（算法将自动寻优，决定最终派车组合与数量）")

if "vehicles" not in st.session_state:
    st.session_state.vehicles = []
if "global_season" not in st.session_state:
    st.session_state.global_season = "夏"
if "global_h2_source" not in st.session_state:
    st.session_state.global_h2_source = "工业副产氢"

# 动力类型映射（用于前端美观显示）
POWER_TYPE_MAPPING = {
    "diesel": "柴油重卡", 
    "lng": "LNG天然气重卡",
    "hev": "混合动力 (HEV)",
    "phev": "插电混动 (PHEV)",
    "bev": "纯电动 (BEV)",
    "fcev": "氢燃料电池 (FCEV)",
}

# 兜底的推荐载重区间（吨），供前端提示使用
LOAD_RANGE_HINTS = {
    "diesel": (10, 49),
    "lng": (10, 49),
    "hev": (10, 49),
    "phev": (10, 49),
    "bev": (5, 30),
    "fcev": (15, 35),
}

# ===================== 车型库概览 =====================
with st.expander("📚 车型基础碳排参数概览（读取自系统核心库）", expanded=False):
    table_data = []
    # 【修改3】适配 VEHICLE_LIB 的字典遍历
    for vid, v_info in VEHICLE_LIB.items():
        table_data.append({
            "动力类型": POWER_TYPE_MAPPING.get(vid, vid),
            "有载碳排强度 (g CO₂/吨·km)": v_info.get("intensity_g_per_tkm", "N/A"),
            "空跑碳排 (g CO₂/km)": v_info.get("empty_g_per_km", "N/A"),
            "冷启动碳排 (g CO₂)": v_info.get("cold_start_g", "N/A"),
            "新能源类型": "✅ 是" if v_info.get("is_new_energy") else "❌ 否",
        })
    st.dataframe(pd.DataFrame(table_data), hide_index=True, width="stretch")
st.markdown("---")

# ===================== 全局环境参数配置 =====================
st.subheader("🌍 全局环境参数配置")
st.markdown("设置影响碳排放双公式计算的环境倍率因子（将全局生效）")

col_env1, col_env2 = st.columns(2)
with col_env1:
    season = st.radio(
        "🌡️ 季节选择",
        options=["春", "夏", "秋", "冬"],
        index=["春", "夏", "秋", "冬"].index(st.session_state.global_season),
        help="季节将影响新能源车辆的热管理能耗（夏季制冷/冬季制热），从而改变实际碳排放",
        key="season_radio"
    )
    st.session_state.global_season = season

with col_env2:
    h2_source = st.radio(
        "🧪 FCEV 氢气来源",
        options=["灰氢", "工业副产氢", "绿氢"],
        index=["灰氢", "工业副产氢", "绿氢"].index(st.session_state.global_h2_source),
        help="氢气的制取方式将决定氢燃料电池车全生命周期（Well-to-Wheel）的碳排放强度",
        key="h2_source_radio"
    )
    st.session_state.global_h2_source = h2_source

st.markdown("---")

# ===================== 车辆参数配置 =====================
st.subheader("⚙️ 车辆参数配置")
hdr_sel, hdr_type, hdr_load, hdr_cap, hdr_spacer = st.columns([0.5, 1.5, 1.2, 1.2, 1.5])
with hdr_sel:
    st.caption("勾选")
with hdr_type:
    st.caption("动力类型")
with hdr_load:
    st.caption("实际载重(吨)")
with hdr_cap:
    st.caption("可用上限(辆)")
with hdr_spacer:
    st.empty()

vehicle_configs = {}

# 遍历系统核心库中的车型
for vid in VEHICLE_LIB.keys():
    vname = POWER_TYPE_MAPPING.get(vid, vid.upper())
    
    # 获取兜底的载重范围提示
    load_min, load_max = LOAD_RANGE_HINTS.get(vid, (10, 50))
    load_default = (load_min + load_max) / 2

    # 获取已保存的配置回显
    existing = next((x for x in st.session_state.vehicles if x.get("vehicle_type") == vid), None)
    current_qty = existing.get("count_max", 0) if existing else 0
    current_load = existing.get("load_ton", load_default) if existing else load_default
    current_enabled = bool(existing) and current_qty > 0

    with st.container():
        col_sel, col_type, col_load, col_cap, col_spacer = st.columns([0.5, 1.5, 1.2, 1.2, 1.5])
        with col_sel:
            enabled = st.checkbox(
                "勾选",
                value=current_enabled,
                key=f"enable_{vid}",
                label_visibility="collapsed",
            )
        with col_type:
            st.write(f"**{vname}**")

        with col_load:
            actual_load = st.number_input(
                "实际载重(吨)",
                min_value=0.0,
                value=float(current_load) if enabled else 0.0,
                step=0.5,
                key=f"load_{vid}",
                disabled=not enabled,
                help="实际载重 = 车辆实际装载的物资重量（不是最大总质量GVW）",
                label_visibility="collapsed",
            )
            hint = f"建议 {load_min}~{load_max} 吨"
            if enabled and (actual_load < load_min or actual_load > load_max):
                st.caption(f"⚠️ {hint} (已超典型区间)")
            else:
                st.caption(hint)

        with col_cap:
            new_qty = st.number_input(
                "可用上限(辆)",
                min_value=0,
                max_value=999,
                value=int(current_qty) if enabled else 0,
                step=1,
                key=f"qty_{vid}",
                label_visibility="collapsed",
                disabled=not enabled,
            )

        with col_spacer:
            st.empty()

        if enabled and new_qty > 0 and actual_load > 0:
            vehicle_configs[vid] = {
                "vehicle_type": vid,
                "name": vname,
                "count_max": int(new_qty),
                "load_ton": float(actual_load),
            }
        st.markdown("---")

# ===================== 车队汇总 =====================
st.subheader("📋 车队配置汇总")

# 实时同步到 session_state
if vehicle_configs:
    st.session_state.vehicles = list(vehicle_configs.values())

total_vehicles_max = sum(cfg["count_max"] for cfg in vehicle_configs.values())
total_capacity_max = sum(cfg["count_max"] * cfg["load_ton"] for cfg in vehicle_configs.values())

col_s1, col_s2, col_s3 = st.columns(3)
with col_s1:
    st.metric("已启用的动力类型", len(vehicle_configs))
with col_s2:
    st.metric("全局车辆上限", total_vehicles_max)
with col_s3:
    st.metric("单次发车总运力上限", f"{total_capacity_max:.1f} 吨")

if vehicle_configs:
    detail_data = [
        {
            "动力类型": cfg["name"],
            "可用上限(辆)": cfg["count_max"],
            "设定的实际载重(吨/辆)": cfg["load_ton"],
            "该车型运力上限(吨)": cfg["count_max"] * cfg["load_ton"],
        }
        for cfg in vehicle_configs.values()
    ]
    st.dataframe(pd.DataFrame(detail_data), hide_index=True, width="stretch")

st.markdown("---")

# 建议阈值提示，过多车辆会显著增加 OR-Tools 求解时间
if total_vehicles_max > 100:
    st.warning(f"⚠️ 检测到车辆上限达到 {total_vehicles_max} 辆。建议总上限控制在 100 辆以内，以确保路径优化算法的求解速度。")

if st.button("💾 保存配置", type="primary", width="stretch"):
    st.session_state.vehicles = list(vehicle_configs.values())
    st.success(f"已保存 {len(vehicle_configs)} 种动力类型！全局季节设为【{st.session_state.global_season}】，FCEV氢气来源设为【{st.session_state.global_h2_source}】。")

st.caption("ℹ️ 提示：基础碳排参数（冷启动、空跑系数等）已自动从后台引擎读取，您只需关注派车约束条件即可。")

st.markdown("---")
if st.button("下一步：进入路径优化中心 ➡️", type="secondary", width="stretch"):
    st.switch_page("pages/5_路径优化.py")