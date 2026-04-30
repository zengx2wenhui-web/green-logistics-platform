"""车辆配置页面。"""
from __future__ import annotations

import base64
import sys
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from pages._bottom_nav import render_page_nav
from ._ui_shared import (
    anchor,
    get_data_status,
    inject_base_style,
    inject_sidebar_navigation_label,
    is_data_saved,
    render_pending_step_state,
    render_sidebar_navigation,
    set_data_status,
    render_title,
    render_top_nav,
)
from utils.vehicle_lib import VEHICLE_LIB
from utils.vehicle_environment import (
    DEFAULT_H2_SOURCE,
    DEFAULT_SEASON,
    build_vehicle_environment_config,
    resolve_vehicle_environment_config,
)


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


def get_current_vehicle_id(vehicle_ids: list[str]) -> str:
    fallback_id = vehicle_ids[0]
    current_vehicle_id = st.session_state.get("current_vehicle_id")

    if current_vehicle_id not in vehicle_ids:
        legacy_idx = st.session_state.get("current_vehicle_idx", 0)
        if isinstance(legacy_idx, int):
            current_vehicle_id = vehicle_ids[legacy_idx % len(vehicle_ids)]
        else:
            current_vehicle_id = fallback_id
        st.session_state.current_vehicle_id = current_vehicle_id

    st.session_state.pop("current_vehicle_idx", None)
    st.session_state.pop("vehicle_selectbox", None)
    return st.session_state.current_vehicle_id


def sync_vehicle_selectbox(vehicle_ids: list[str]) -> str:
    current_vehicle_id = get_current_vehicle_id(vehicle_ids)
    if st.session_state.get("current_vehicle_selectbox") != current_vehicle_id:
        st.session_state.current_vehicle_selectbox = current_vehicle_id
    return current_vehicle_id


def handle_vehicle_selectbox_change() -> None:
    selected_vehicle_id = st.session_state.get("current_vehicle_selectbox")
    if selected_vehicle_id:
        st.session_state.current_vehicle_id = selected_vehicle_id


def update_current_vehicle(step: int, vehicle_ids: list[str]) -> None:
    current_vehicle_id = get_current_vehicle_id(vehicle_ids)
    current_idx = vehicle_ids.index(current_vehicle_id)
    st.session_state.current_vehicle_id = vehicle_ids[(current_idx + step) % len(vehicle_ids)]


def render_global_season_radio() -> None:
    st.session_state.global_season = st.radio(
        "季节选择",
        options=["春", "夏", "秋", "冬"],
        index=["春", "夏", "秋", "冬"].index(st.session_state.global_season),
        key="global_season_radio",
        help="季节会影响新能源车辆的热管理能耗。",
        horizontal=True,
    )


def render_global_h2_source_radio() -> None:
    st.session_state.global_h2_source = st.radio(
        "FCEV 氢气来源",
        options=["灰氢", "工业副产氢", "绿氢"],
        index=["灰氢", "工业副产氢", "绿氢"].index(st.session_state.global_h2_source),
        key="global_h2_source_radio",
        help="氢气来源会影响氢燃料电池车辆的全生命周期碳排强度。",
        horizontal=True,
    )


def get_saved_vehicle_environment_config() -> dict[str, object]:
    return resolve_vehicle_environment_config(
        st.session_state.get("vehicles", []),
        st.session_state.get("vehicle_environment_config"),
        fallback_season=st.session_state.get("global_season", DEFAULT_SEASON),
        fallback_h2_source=st.session_state.get("global_h2_source", DEFAULT_H2_SOURCE),
    )


def build_vehicle_signature(
    vehicle_configs: dict[str, dict],
    *,
    environment_config: dict[str, object],
) -> tuple[tuple[str, object, float], ...]:
    configs = tuple(
        sorted(
            (
                vehicle_id,
                int(config.get("count_max", 0) or 0),
                round(float(config.get("load_ton", 0) or 0.0), 4),
            )
            for vehicle_id, config in vehicle_configs.items()
            if int(config.get("count_max", 0) or 0) > 0
        )
    )
    signature_parts = list(configs)
    if environment_config.get("has_new_energy"):
        signature_parts.append(("__season__", str(environment_config.get("season") or ""), 0.0))
    if environment_config.get("has_fcev"):
        signature_parts.append(("__h2_source__", str(environment_config.get("h2_source") or ""), 0.0))
    return tuple(signature_parts)


def build_saved_vehicle_signature() -> tuple[tuple[str, object, float], ...]:
    saved_configs = {
        str(item.get("vehicle_type")): item
        for item in st.session_state.get("vehicles", [])
        if item.get("vehicle_type")
    }
    return build_vehicle_signature(
        saved_configs,
        environment_config=get_saved_vehicle_environment_config(),
    )


def build_vehicle_save_payload(
    vehicle_types: list[dict],
    vehicle_configs: dict[str, dict],
) -> list[dict]:
    payload: list[dict] = []
    for vehicle in vehicle_types:
        vehicle_id = vehicle["id"]
        config = vehicle_configs.get(vehicle_id)
        if not config:
            continue

        count_max = int(config.get("count_max", 0) or 0)
        load_ton = float(config.get("load_ton", 0) or 0.0)
        if count_max <= 0 or load_ton <= 0:
            continue

        payload.append(
            {
                "vehicle_type": vehicle_id,
                "name": vehicle["name"],
                "fuel_type": vehicle["fuel_type"],
                "count_max": count_max,
                "load_ton": load_ton,
            }
        )
    return payload


def set_vehicle_save_notice(message: str, level: str = "success") -> None:
    st.session_state.vehicle_save_notice = {
        "message": message,
        "level": level,
    }


def render_vehicle_save_notice():
    placeholder = st.empty()
    notice = st.session_state.get("vehicle_save_notice")
    if not isinstance(notice, dict):
        return placeholder

    message = str(notice.get("message", "") or "").strip()
    level = str(notice.get("level", "info") or "info").strip().lower()
    if message:
        if level == "success":
            placeholder.success(message)
        elif level == "warning":
            placeholder.warning(message)
        else:
            placeholder.info(message)

    st.session_state.vehicle_save_notice = None
    return placeholder


st.set_page_config(page_title="车辆配置", page_icon="🚛", layout="wide", initial_sidebar_state="expanded")
if "vehicles" not in st.session_state:
    st.session_state.vehicles = []
if "vehicle_environment_config" not in st.session_state and st.session_state.get("vehicles"):
    st.session_state.vehicle_environment_config = resolve_vehicle_environment_config(
        st.session_state.get("vehicles", []),
        None,
        fallback_season=st.session_state.get("global_season", DEFAULT_SEASON),
        fallback_h2_source=st.session_state.get("global_h2_source", DEFAULT_H2_SOURCE),
    )
saved_vehicle_environment_config = get_saved_vehicle_environment_config()
if st.session_state.get("vehicles"):
    st.session_state.vehicle_environment_config = saved_vehicle_environment_config
if "global_season" not in st.session_state:
    st.session_state.global_season = str(saved_vehicle_environment_config.get("season") or DEFAULT_SEASON)
if "global_h2_source" not in st.session_state:
    st.session_state.global_h2_source = str(saved_vehicle_environment_config.get("h2_source") or DEFAULT_H2_SOURCE)
if "vehicle_save_notice" not in st.session_state:
    st.session_state.vehicle_save_notice = None

vehicle_types = build_vehicle_catalog()
vehicle_ids = [vehicle["id"] for vehicle in vehicle_types]
vehicle_name_by_id = {vehicle["id"]: vehicle["name"] for vehicle in vehicle_types}
vehicle_by_id = {vehicle["id"]: vehicle for vehicle in vehicle_types}
vehicle_index_by_id = {vehicle_id: idx for idx, vehicle_id in enumerate(vehicle_ids)}

if "vehicle_saved_signature" not in st.session_state:
    st.session_state.vehicle_saved_signature = (
        build_saved_vehicle_signature()
        if get_data_status("vehicles") == "saved"
        else None
    )

current_vehicle_draft_configs: dict[str, dict] = {}
for vehicle in vehicle_types:
    vehicle_id = vehicle["id"]
    existing = get_saved_vehicle_entry(vehicle_id)
    qty_key = f"qty_{vehicle_id}"
    load_key = f"load_{vehicle_id}"
    if qty_key not in st.session_state:
        st.session_state[qty_key] = int(
            (existing or {}).get("count_max", (existing or {}).get("count", 0)) or 0
        )
    if load_key not in st.session_state:
        st.session_state[load_key] = float(
            (existing or {}).get("load_ton", vehicle["max_load_ton_default"])
            or vehicle["max_load_ton_default"]
        )

    qty_value = int(st.session_state[qty_key] or 0)
    load_value = float(st.session_state[load_key] or 0.0)
    if qty_value > 0 and load_value > 0:
        current_vehicle_draft_configs[vehicle_id] = {
            "vehicle_type": vehicle_id,
            "count_max": qty_value,
            "load_ton": load_value,
        }

current_vehicle_signature = build_vehicle_signature(
    current_vehicle_draft_configs,
    environment_config=build_vehicle_environment_config(
        current_vehicle_draft_configs.values(),
        season=st.session_state.global_season,
        h2_source=st.session_state.global_h2_source,
    ),
)
saved_vehicle_signature = st.session_state.get("vehicle_saved_signature")
if saved_vehicle_signature:
    if current_vehicle_signature == saved_vehicle_signature:
        set_data_status("vehicles", "saved")
    else:
        set_data_status("vehicles", "dirty")
elif current_vehicle_draft_configs:
    set_data_status("vehicles", "dirty")
else:
    set_data_status("vehicles", "empty")

inject_sidebar_navigation_label()
inject_base_style()
render_sidebar_navigation()
render_top_nav(
    tabs=[("车型库概览", "sec-overview"), ("在线配置", "sec-online"), ("环境参数", "sec-environment")],
    active_idx=0,
)

st.markdown(
    """
    <style>
    .st-key-vehicles-empty-card,
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
if not is_data_saved("materials"):
    render_pending_step_state(
        anchor_name="sec-overview",
        container_key="vehicles-empty-card",
        warning_message="尚未完成物资需求，请先完成上一步。",
        info_message="当前页面为车辆与环境配置视图，需要先在“物资需求”页面完成并保存需求数据后，才能继续配置车队。",
        prev_page="pages/3_materials.py",
        next_page="pages/7_path_optimization.py",
        key_prefix="vehicles-guard-nav",
        next_block_message="请先完成并保存物资需求后，再进入下一步。",
    )
current_vehicle_id = sync_vehicle_selectbox(vehicle_ids)

with st.container(key="materials-upload-card"):
    anchor("sec-overview")
    c_title, c_sel, _ = st.columns([1.5, 2, 6], vertical_alignment="center")
    with c_title:
        st.markdown('<div class="glp-vehicle-card-title">车型库概览</div>', unsafe_allow_html=True)
    with c_sel:
        current_vehicle_id = st.selectbox(
            "车型",
            vehicle_ids,
            key="current_vehicle_selectbox",
            format_func=lambda vehicle_id: vehicle_name_by_id[vehicle_id],
            on_change=handle_vehicle_selectbox_change,
            label_visibility="collapsed",
        )
    current_vehicle_id = get_current_vehicle_id(vehicle_ids)
    current_idx = vehicle_index_by_id[current_vehicle_id]
    vehicle = vehicle_by_id[current_vehicle_id]
    prev_vehicle = vehicle_types[(current_idx - 1) % len(vehicle_types)]
    next_vehicle = vehicle_types[(current_idx + 1) % len(vehicle_types)]

    st.markdown("<br>", unsafe_allow_html=True)
    col_prev_btn, col_prev_img, col_main_img, col_next_img, col_next_btn = st.columns(
        [0.5, 2, 4, 2, 0.5],
        vertical_alignment="center",
    )

    with col_prev_btn:
        if st.button("❮", key="btn_prev", width='stretch'):
            update_current_vehicle(-1, vehicle_ids)
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
            update_current_vehicle(1, vehicle_ids)
            st.rerun()

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
                        f"<div class='glp-online-item-name'>{escape(vehicle['name'])}</div>",
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
                    st.markdown(
                        f"<div style='text-align: right; padding-right: 15px; color: rgba(49, 51, 63, 0.6); font-size: 0.875rem;'>有载碳因子 {vehicle['emission_factor_min']:.3f} kg CO₂/吨km</div>",
                        unsafe_allow_html=True
                    )
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

    has_new_energy = any(
        config["count_max"] > 0 and VEHICLE_LIB.get(vehicle_id, {}).get("is_new_energy", False)
        for vehicle_id, config in vehicle_configs.items()
    )
    has_fcev = vehicle_configs.get("fcev", {}).get("count_max", 0) > 0

    anchor("sec-environment")
    if has_new_energy:
        with st.container(key="vehicle-environment-card"):
            st.markdown('<div class="glp-vehicle-card-title">全局环境参数配置</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="glp-environment-note">这些参数会在路径优化与碳排放核算中全局生效。</div>',
                unsafe_allow_html=True,
            )

            if has_fcev:
                col_env1, col_env2 = st.columns(2, gap="large")
                with col_env1:
                    render_global_season_radio()
                with col_env2:
                    render_global_h2_source_radio()
            else:
                render_global_season_radio()         

                    
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
            if not vehicle_configs:
                message = "请至少配置一类车辆后再保存。"
                set_vehicle_save_notice(message, level="warning")
                st.rerun()
            else:
                next_environment_config = build_vehicle_environment_config(
                    vehicle_configs.values(),
                    season=st.session_state.global_season,
                    h2_source=st.session_state.global_h2_source,
                )
                next_signature = build_vehicle_signature(
                    vehicle_configs,
                    environment_config=next_environment_config,
                )
                if saved_vehicle_signature == next_signature and st.session_state.get("vehicles"):
                    st.session_state.vehicle_environment_config = next_environment_config
                    st.session_state.vehicle_saved_signature = next_signature
                    message = "当前车辆与环境配置已保存，无需重复保存。"
                    set_vehicle_save_notice(message, level="info")
                    set_data_status("vehicles", "saved")
                    st.rerun()
                else:
                    st.session_state.vehicles = build_vehicle_save_payload(vehicle_types, vehicle_configs)
                    st.session_state.vehicle_environment_config = next_environment_config
                    st.session_state.vehicle_saved_signature = next_signature
                    set_data_status("vehicles", "saved")
                    message = "车辆与环境配置已保存。"
                    set_vehicle_save_notice(message, level="success")
                    st.rerun()

    left_spacer, notice_col, right_spacer = st.columns([2, 3, 2])
    with notice_col:
        render_vehicle_save_notice()

render_page_nav(
    "pages/3_materials.py",
    "pages/7_path_optimization.py",
    key_prefix="vehicles-nav",
    can_go_next=is_data_saved("vehicles"),
    next_block_message="车辆与环境配置尚未保存，请先点击【保存车辆与环境配置】。",
)
