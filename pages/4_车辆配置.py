"""车辆配置页面"""
import streamlit as st
import pandas as pd
from utils.vehicle_config import load_vehicle_types

st.set_page_config(page_title="车辆配置", page_icon="")

st.title(" 第四步：车辆配置")
st.markdown("从预置车型库选择车辆并配置数量")

# 加载车型库（使用 utils 统一接口）
@st.cache_data
def get_vehicle_types():
    return load_vehicle_types()

vehicle_types = get_vehicle_types()
if not vehicle_types:
    st.error("无法加载车型库数据，请检查 data/vehicle_types.json 文件")
    st.stop()

# 初始化 session_state
if "vehicles" not in st.session_state:
    st.session_state.vehicles = []

# 燃料类型标签
fuel_labels = {
    "electric": " 纯电动", "hybrid": " 混合动力", "phev": " 插电混动",
    "diesel": " 柴油", "lng": " LNG天然气", "hydrogen": " 氢燃料电池",
}

# ===================== 车型库概览 =====================
st.subheader(" 车型库概览")
table_data = [
    {
        "车型名称": v["name"],
        "代表品牌": v.get("representative_models", "N/A"),
        "最大载重范围": f"{v.get('max_load_ton_min', 0):.0f} ~ {v.get('max_load_ton_max', 0):.0f} 吨",
        "续航范围": f"{v.get('range_km_min', 0):.0f} ~ {v.get('range_km_max', 0):.0f} km",
        "碳排放强度": f"{v.get('emission_factor_min', 0):.3f} ~ {v.get('emission_factor_max', 0):.3f}",
        "对比柴油减排": v.get("reduction_vs_diesel", "N/A"),
    }
    for v in vehicle_types
]
st.dataframe(pd.DataFrame(table_data), hide_index=True, use_container_width=True)
st.markdown("---")

# ===================== 车辆参数配置 =====================
st.subheader(" 车辆参数配置")

vehicle_configs = {}
for v in vehicle_types:
    vid = v["id"]
    vname = v["name"]
    fuel_type = v.get("fuel_type", "")
    fuel_label = fuel_labels.get(fuel_type, fuel_type)

    load_min = v.get("max_load_ton_min", 1)
    load_max = v.get("max_load_ton_max", 50)
    load_default = v.get("max_load_ton_default", (load_min + load_max) / 2)
    ef_min = v.get("emission_factor_min", 0.01)
    ef_max = v.get("emission_factor_max", 0.10)
    ef_default = v.get("emission_factor_default", (ef_min + ef_max) / 2)

    # 获取已保存的配置
    existing = next((x for x in st.session_state.vehicles if x.get("vehicle_type") == vid), None)
    current_qty = existing.get("count", 0) if existing else 0
    current_load = existing.get("load_ton", load_default) if existing else load_default
    current_ef = existing.get("emission_factor", ef_default) if existing else ef_default

    with st.container():
        col_header, col_qty = st.columns([4, 1])
        with col_header:
            st.write(f"**{vname}** {fuel_label}")
        with col_qty:
            new_qty = st.number_input(
                "数量", min_value=0, max_value=20, value=current_qty,
                step=1, key=f"qty_{vid}", label_visibility="collapsed",
            )

        if new_qty > 0:
            col_load, col_ef = st.columns(2)
            with col_load:
                actual_load = st.slider(
                    "实际载重（吨）",
                    min_value=float(load_min), max_value=float(load_max),
                    value=float(current_load), step=0.5, key=f"load_{vid}",
                )
            with col_ef:
                actual_ef = st.slider(
                    "碳排放因子 (kg CO₂/吨km)",
                    min_value=float(ef_min), max_value=float(ef_max),
                    value=float(current_ef), step=0.001, key=f"ef_{vid}", format="%.3f",
                )
            vehicle_configs[vid] = {
                "vehicle_type": vid, "name": vname, "fuel_type": fuel_type,
                "count": new_qty, "load_ton": actual_load, "emission_factor": actual_ef,
            }
        st.markdown("---")

# ===================== 车队汇总 =====================
st.subheader(" 车队汇总")

# 实时同步到 session_state
if vehicle_configs:
    st.session_state.vehicles = list(vehicle_configs.values())

total_vehicles = sum(cfg["count"] for cfg in vehicle_configs.values())
total_load = sum(cfg["count"] * cfg["load_ton"] for cfg in vehicle_configs.values())

col_s1, col_s2, col_s3 = st.columns(3)
with col_s1:
    st.metric("已选车型数", len(vehicle_configs))
with col_s2:
    st.metric("车辆总数", total_vehicles)
with col_s3:
    st.metric("总运力", f"{total_load:.1f} 吨")

if vehicle_configs:
    st.markdown("**配置详情：**")
    detail_data = [
        {
            "车型": cfg["name"], "数量": cfg["count"],
            "载重(吨)": cfg["load_ton"], "碳因子": cfg["emission_factor"],
            "小计运力(吨)": cfg["count"] * cfg["load_ton"],
        }
        for cfg in vehicle_configs.values()
    ]
    st.dataframe(pd.DataFrame(detail_data), hide_index=True, use_container_width=True)

st.markdown("---")

if st.button(" 保存配置", type="primary", use_container_width=True):
    st.session_state.vehicles = list(vehicle_configs.values())
    st.success(f"已保存 {len(vehicle_configs)} 种车型，共 {total_vehicles} 辆车")

st.caption(" 提示：车型参数来源于 data/vehicle_types.json，碳因子单位为 kg CO₂/吨km")

st.markdown("---")
if st.button("下一步：路径优化 ➡️", type="primary", use_container_width=True):
    st.switch_page("pages/5_路径优化.py")