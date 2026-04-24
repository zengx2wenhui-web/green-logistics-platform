"""车辆配置页面。"""
from __future__ import annotations

import base64
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from pages._bottom_nav import render_page_nav
from pages._ui_shared import (
    anchor,
    inject_base_style,
    inject_sidebar_navigation_label,
    render_sidebar_navigation,
    render_title,
    render_top_nav,
)
from utils.vehicle_lib import VEHICLE_LIB


VEHICLE_META = {
    "diesel": {
        "name": "柴油重卡",
        "fuel_type": "diesel",
        "representative_models": "解放 JH6 / 东风天龙 KX",
        "load_min": 10.0,
        "load_max": 49.0,
        "range_min": 600.0,
        "range_max": 1200.0,
        "image": "柴油重卡.png",
    },
    "lng": {
        "name": "LNG天然气重卡",
        "fuel_type": "lng",
        "representative_models": "陕汽德龙 LNG / 欧曼EST LNG",
        "load_min": 10.0,
        "load_max": 49.0,
        "range_min": 450.0,
        "range_max": 900.0,
        "image": "lng天然气.png",
    },
    "hev": {
        "name": "混合动力 (HEV)",
        "fuel_type": "hybrid",
        "representative_models": "混动干线重卡",
        "load_min": 10.0,
        "load_max": 49.0,
        "range_min": 500.0,
        "range_max": 1000.0,
        "image": "柴电混动.png",
    },
    "phev": {
        "name": "插电混动 (PHEV)",
        "fuel_type": "phev",
        "representative_models": "插混物流重卡",
        "load_min": 10.0,
        "load_max": 49.0,
        "range_min": 450.0,
        "range_max": 950.0,
        "image": "插电混动.png",
    },
    "bev": {
        "name": "纯电动 (BEV)",
        "fuel_type": "electric",
        "representative_models": "换电重卡 / 纯电城配重卡",
        "load_min": 5.0,
        "load_max": 30.0,
        "range_min": 180.0,
        "range_max": 420.0,
        "image": "纯电动.png",
    },
    "fcev": {
        "name": "氢燃料电池 (FCEV)",
        "fuel_type": "hydrogen",
        "representative_models": "氢燃料重卡",
        "load_min": 15.0,
        "load_max": 35.0,
        "range_min": 350.0,
        "range_max": 700.0,
        "image": "氢燃料电池.png",
    },
}

FUEL_LABELS = {
    "electric": "纯电动",
    "hybrid": "混合动力",
    "phev": "插电混动",
    "diesel": "柴油",
    "lng": "LNG天然气",
    "hydrogen": "氢燃料电池",
}

IMAGE_DIR = Path(__file__).resolve().parents[1] / "assets" / "icons" / "车辆配置"


def build_vehicle_catalog() -> list[dict]:
    catalog = []
    for vehicle_id, params in VEHICLE_LIB.items():
        meta = VEHICLE_META[vehicle_id]
        factor = float(params.get("intensity_g_per_tkm", 0) or 0) / 1000.0
        catalog.append(
            {
                "id": vehicle_id,
                "name": meta["name"],
                "fuel_type": meta["fuel_type"],
                "representative_models": meta["representative_models"],
                "max_load_ton_min": meta["load_min"],
                "max_load_ton_max": meta["load_max"],
                "max_load_ton_default": round((meta["load_min"] + meta["load_max"]) / 2, 1),
                "range_km_min": meta["range_min"],
                "range_km_max": meta["range_max"],
                "emission_factor_min": factor,
                "emission_factor_max": factor,
                "reduction_vs_diesel": (
                    f"{(1 - factor / (VEHICLE_LIB['diesel']['intensity_g_per_tkm'] / 1000.0)) * 100:.0f}%"
                    if vehicle_id != "diesel"
                    else "0%"
                ),
                "image": meta["image"],
            }
        )
    return catalog


def encode_vehicle_image(image_name: str) -> str:
    image_path = IMAGE_DIR / image_name
    if not image_path.exists():
        return ""
    return base64.b64encode(image_path.read_bytes()).decode("utf-8")


def get_saved_vehicle_entry(vehicle_id: str) -> dict | None:
    for item in st.session_state.vehicles:
        if item.get("vehicle_type") == vehicle_id:
            return item
    return None


def update_idx(step: int, total: int) -> None:
    st.session_state.current_vehicle_idx = (st.session_state.current_vehicle_idx + step) % total
    st.session_state.pop("vehicle_selectbox", None)


st.set_page_config(page_title="车辆配置", page_icon="🚛", layout="wide", initial_sidebar_state="expanded")
inject_sidebar_navigation_label()
inject_base_style()
render_sidebar_navigation()
render_top_nav(
    tabs=[("车型库概览", "sec-overview"), ("环境参数", "sec-environment"), ("在线配置", "sec-online")],
    active_idx=0,
)

st.markdown(
    """
    <style>
    .st-key-materials-upload-card,
    .st-key-vehicle-environment-card,
    .st-key-materials-online-card {
        background: linear-gradient(135deg, #DFEFC8 0%, #DFEFC8 100%);
        border: 1px solid #d0e2b4;
        border-radius: 28px;
        padding: 1.45rem 1.65rem 1.55rem;
        box-shadow: 0 8px 24px rgba(123, 145, 91, 0.22);
        margin-top: 1.2rem;
    }
    .glp-vehicle-card-title {
        font-size: 1.5rem;
        font-weight: 700;
        color: #111;
        margin-bottom: 1rem;
        display: inline-block;
        margin-right: 1rem;
    }
    .glp-carousel-img-side {
        width: 100%;
        max-width: 180px;
        opacity: 0.4;
        transform: scale(0.85);
        transition: all 0.3s ease;
        display: block;
        margin: 0 auto;
    }
    .glp-carousel-main {
        position: relative;
        display: flex;
        justify-content: center;
        align-items: center;
    }
    .glp-carousel-img-main {
        width: 100%;
        max-width: 400px;
        transition: transform 0.3s ease;
        display: block;
        margin: 0 auto;
    }
    .glp-carousel-main:hover .glp-carousel-img-main {
        transform: scale(1.02);
    }
    .glp-vehicle-info-box {
        position: absolute;
        top: 50%;
        right: -40px;
        transform: translateY(-50%);
        background: rgba(255, 255, 255, 0.95);
        padding: 1rem;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        opacity: 0;
        transition: opacity 0.3s ease;
        pointer-events: none;
        font-size: 0.9rem;
        line-height: 1.6;
        color: #333;
        width: 240px;
        z-index: 10;
        border: 1px solid #e0e0e0;
    }
    .glp-carousel-main:hover .glp-vehicle-info-box {
        opacity: 1;
    }
    .glp-vehicle-name {
        text-align: center;
        font-size: 1.2rem;
        color: #666;
        margin-top: 1rem;
    }
    .glp-online-item-name {
        font-size: 0.98rem;
        font-weight: 500;
        color: #111;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    .glp-environment-note {
        color: #495057;
        font-size: 0.95rem;
        margin-bottom: 1rem;
    }
    div[data-testid="stMetric"] {
        text-align: center !important;
        align-items: center !important;
    }
    div[data-testid="stMetric"] label {
        color: #333 !important;
        font-size: 1rem !important;
        font-weight: 500 !important;
        display: flex !important;
        justify-content: center !important;
    }
    div[data-testid="stMetricValue"] {
        color: #111 !important;
        font-size: 1.5rem !important;
        font-weight: 700 !important;
        display: flex !important;
        justify-content: center !important;
    }
    .stButton > button,
    .stDownloadButton > button {
        height: 2.8rem !important;
        border-radius: 10px !important;
        font-size: 1rem !important;
        border: none !important;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.14) !important;
    }
    .stButton > button[kind="primary"] {
        background: #2db567 !important;
        color: #ffffff !important;
    }
    .stButton > button:not([kind="primary"]) {
        background: #ffffff !important;
        color: #111 !important;
    }
    .glp-bottom-nav {
        margin-top: 2.3rem !important;
        gap: 4rem !important;
        font-size: 1.65rem !important;
    }
    @media (max-width: 900px) {
        .st-key-materials-upload-card,
        .st-key-vehicle-environment-card,
        .st-key-materials-online-card {
            padding: 1.2rem 1rem 1.3rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

render_title("车辆配置", "从预置车型库中选择车辆，并补充全局环境参数。")

if "vehicles" not in st.session_state:
    st.session_state.vehicles = []
if "current_vehicle_idx" not in st.session_state:
    st.session_state.current_vehicle_idx = 0
if "global_season" not in st.session_state:
    st.session_state.global_season = "夏"
if "global_h2_source" not in st.session_state:
    st.session_state.global_h2_source = "工业副产氢"
if "vehicle_save_success" not in st.session_state:
    st.session_state.vehicle_save_success = False

vehicle_types = build_vehicle_catalog()
vehicle_names = [vehicle["name"] for vehicle in vehicle_types]

if st.session_state.get("vehicle_save_success", False):
    st.success("车辆与环境参数已保存")
    st.session_state.vehicle_save_success = False

with st.container(key="materials-upload-card"):
    anchor("sec-overview")
    c_title, c_sel, _ = st.columns([1.5, 2, 6], vertical_alignment="center")
    with c_title:
        st.markdown('<div class="glp-vehicle-card-title">车型库概览</div>', unsafe_allow_html=True)
    with c_sel:
        selected_name = st.selectbox(
            "车型",
            vehicle_names,
            index=st.session_state.current_vehicle_idx,
            key="vehicle_selectbox",
            label_visibility="collapsed",
        )
        if vehicle_names.index(selected_name) != st.session_state.current_vehicle_idx:
            st.session_state.current_vehicle_idx = vehicle_names.index(selected_name)
            st.rerun()

    current_idx = st.session_state.current_vehicle_idx
    vehicle = vehicle_types[current_idx]
    prev_vehicle = vehicle_types[(current_idx - 1) % len(vehicle_types)]
    next_vehicle = vehicle_types[(current_idx + 1) % len(vehicle_types)]

    st.markdown("<br>", unsafe_allow_html=True)
    col_prev_btn, col_prev_img, col_main_img, col_next_img, col_next_btn = st.columns(
        [0.5, 2, 4, 2, 0.5],
        vertical_alignment="center",
    )

    with col_prev_btn:
        if st.button("❮", key="btn_prev", width='stretch'):
            update_idx(-1, len(vehicle_types))
            st.rerun()

    with col_prev_img:
        prev_img_data = encode_vehicle_image(prev_vehicle["image"])
        if prev_img_data:
            st.markdown(f'<img src="data:image/png;base64,{prev_img_data}" class="glp-carousel-img-side">', unsafe_allow_html=True)

    with col_main_img:
        img_data = encode_vehicle_image(vehicle["image"])
        load_text = f"{vehicle['max_load_ton_min']:.0f}~{vehicle['max_load_ton_max']:.0f} 吨"
        range_text = f"{vehicle['range_km_min']:.0f}~{vehicle['range_km_max']:.0f} km"
        emission_text = f"{vehicle['emission_factor_min']:.3f}"
        if img_data:
            st.markdown(
                f"""
                <div class="glp-carousel-main">
                    <img src="data:image/png;base64,{img_data}" class="glp-carousel-img-main">
                    <div class="glp-vehicle-info-box">
                        <div><b>代表车型:</b> {escape(str(vehicle['representative_models']))}</div>
                        <div><b>典型载重范围:</b> {escape(load_text)}</div>
                        <div><b>续航范围:</b> {escape(range_text)}</div>
                        <div><b>碳排因子:</b> {escape(emission_text)} kg CO₂/吨km</div>
                        <div><b>相对柴油减排:</b> {escape(str(vehicle['reduction_vs_diesel']))}</div>
                    </div>
                </div>
                <div class="glp-vehicle-name">{escape(vehicle['name'])}</div>
                """,
                unsafe_allow_html=True,
            )

    with col_next_img:
        next_img_data = encode_vehicle_image(next_vehicle["image"])
        if next_img_data:
            st.markdown(f'<img src="data:image/png;base64,{next_img_data}" class="glp-carousel-img-side">', unsafe_allow_html=True)

    with col_next_btn:
        if st.button("❯", key="btn_next", width='stretch'):
            update_idx(1, len(vehicle_types))
            st.rerun()

with st.container(key="vehicle-environment-card"):
    anchor("sec-environment")
    st.markdown('<div class="glp-vehicle-card-title">全局环境参数配置</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="glp-environment-note">这些参数会在路径优化与碳排放核算中全局生效。</div>',
        unsafe_allow_html=True,
    )
    col_env1, col_env2 = st.columns(2, gap="large")
    with col_env1:
        st.session_state.global_season = st.radio(
            "季节选择",
            options=["春", "夏", "秋", "冬"],
            index=["春", "夏", "秋", "冬"].index(st.session_state.global_season),
            key="global_season_radio",
            help="季节会影响新能源车辆的热管理能耗。",
            horizontal=True,
        )
    with col_env2:
        st.session_state.global_h2_source = st.radio(
            "FCEV 氢气来源",
            options=["灰氢", "工业副产氢", "绿氢"],
            index=["灰氢", "工业副产氢", "绿氢"].index(st.session_state.global_h2_source),
            key="global_h2_source_radio",
            help="氢气来源会影响氢燃料电池车辆的全生命周期碳排强度。",
            horizontal=True,
        )

vehicle_configs: dict[str, dict] = {}

with st.container(key="materials-online-card"):
    anchor("sec-online")
    st.markdown('<div class="glp-vehicle-card-title" style="margin-bottom: 1.5rem;">在线配置</div>', unsafe_allow_html=True)
    cols = st.columns(2, gap="large")

    for index, vehicle in enumerate(vehicle_types):
        col = cols[index % 2]
        vehicle_id = vehicle["id"]
        fuel_label = FUEL_LABELS.get(vehicle["fuel_type"], vehicle["fuel_type"])
        existing = get_saved_vehicle_entry(vehicle_id)

        qty_key = f"qty_{vehicle_id}"
        load_key = f"load_{vehicle_id}"
        if qty_key not in st.session_state:
            st.session_state[qty_key] = int((existing or {}).get("count_max", (existing or {}).get("count", 0)) or 0)
        if load_key not in st.session_state:
            st.session_state[load_key] = float((existing or {}).get("load_ton", vehicle["max_load_ton_default"]) or vehicle["max_load_ton_default"])

        def decrement_qty(k: str = qty_key) -> None:
            if st.session_state[k] > 0:
                st.session_state[k] -= 1

        def increment_qty(k: str = qty_key) -> None:
            if st.session_state[k] < 99:
                st.session_state[k] += 1

        with col:
            with st.container(border=True):
                title_col, minus_col, num_col, plus_col = st.columns([4.8, 0.8, 1.2, 0.8], vertical_alignment="center")
                with title_col:
                    st.markdown(
                        f"<div class='glp-online-item-name'>{escape(vehicle['name'])}"
                        f"<span style='color:#a0a0a0;font-size:0.85rem;margin-left:0.5rem;'>{escape(fuel_label)}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    st.caption(
                        f"建议载重 {vehicle['max_load_ton_min']:.0f}~{vehicle['max_load_ton_max']:.0f} 吨/辆"
                    )
                with minus_col:
                    st.button("－", key=f"btn_minus_{vehicle_id}", width='stretch', on_click=decrement_qty)
                with num_col:
                    st.number_input(
                        "数量",
                        min_value=0,
                        max_value=99,
                        key=qty_key,
                        label_visibility="collapsed",
                    )
                with plus_col:
                    st.button("＋", key=f"btn_plus_{vehicle_id}", width='stretch', on_click=increment_qty)

                load_col1, load_col2 = st.columns([1.3, 1])
                with load_col1:
                    st.number_input(
                        "实际载重(吨/辆)",
                        min_value=0.0,
                        step=0.5,
                        key=load_key,
                        help="实际载重 = 车辆真实可投入配送的装载重量，不是法定总质量。",
                    )
                with load_col2:
                    st.caption(f"有载碳因子 {vehicle['emission_factor_min']:.3f} kg CO₂/吨km")

                qty_value = int(st.session_state[qty_key])
                load_value = float(st.session_state[load_key])
                if qty_value > 0 and load_value > 0:
                    vehicle_configs[vehicle_id] = {
                        "vehicle_type": vehicle_id,
                        "name": vehicle["name"],
                        "fuel_type": vehicle["fuel_type"],
                        "count_max": qty_value,
                        "load_ton": load_value,
                    }

    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown('<div class="glp-vehicle-card-title">车队汇总</div>', unsafe_allow_html=True)

    total_vehicles = sum(config["count_max"] for config in vehicle_configs.values())
    total_capacity = sum(config["count_max"] * config["load_ton"] for config in vehicle_configs.values())

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("已选车型数", len(vehicle_configs))
    with m2:
        st.metric("车辆总上限", total_vehicles)
    with m3:
        st.metric("单次总运力", f"{total_capacity:.1f} 吨" if total_capacity > 0 else "0")

    if vehicle_configs:
        summary_df = pd.DataFrame(
            [
                {
                    "车型": config["name"],
                    "数量上限(辆)": config["count_max"],
                    "实际载重(吨/辆)": round(config["load_ton"], 2),
                    "总运力上限(吨)": round(config["count_max"] * config["load_ton"], 1),
                }
                for config in vehicle_configs.values()
            ]
        )
        st.dataframe(summary_df, hide_index=True, width='stretch')

    if total_vehicles > 100:
        st.warning(f"检测到车辆上限达到 {total_vehicles} 辆，建议控制在 100 辆以内以保证求解速度。")

    left_spacer, btn_col, right_spacer = st.columns([2, 3, 2])
    with btn_col:
        if st.button("保存车辆与环境配置", type="primary", width='stretch'):
            st.session_state.vehicles = list(vehicle_configs.values())
            st.session_state.vehicle_save_success = True
            st.rerun()

render_page_nav("pages/3_materials.py", "pages/7_path_optimization.py", key_prefix="vehicles-nav")
