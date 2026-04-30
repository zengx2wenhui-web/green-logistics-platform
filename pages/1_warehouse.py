"""仓库设置页面。"""
from __future__ import annotations

import base64
import html
import json
import sys
from pathlib import Path

import folium
from folium import Icon
import streamlit as st
from streamlit_folium import st_folium

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from pages._bottom_nav import render_page_nav
from pages._ui_shared import (
    anchor,
    get_data_status,
    get_data_status_label,
    inject_base_style,
    inject_sidebar_navigation_label,
    is_data_saved,
    render_download_button,
    render_sidebar_navigation,
    set_data_status,
    render_title,
    render_top_nav,
)
from utils.amap_api import DEFAULT_AMAP_API_KEY, geocode


BOX_IMAGE = Path(__file__).resolve().parents[1] / "assets" / "icons" / "step" / "箱子.png"
DEFAULT_WAREHOUSE = {
    "name": "",
    "address": "",
    "lng": None,
    "lat": None,
    "capacity_kg": 50000,
    "capacity_m3": 500.0,
}


def clear_validation_state() -> None:
    st.session_state.missing_field = None
    st.session_state.warehouse_validation_error = None


def set_validation_error(field: str, message: str) -> None:
    st.session_state.missing_field = field
    st.session_state.warehouse_validation_error = message


def has_matching_coordinates(current_address: str, warehouse_data: dict) -> bool:
    saved_address = str(warehouse_data.get("address", "") or "").strip()
    return (
        bool(current_address)
        and warehouse_data.get("lng") is not None
        and warehouse_data.get("lat") is not None
        and saved_address == current_address
    )


def build_missing_field_style(missing_field: str | None) -> str:
    field_selectors = {
        "name": 'input[aria-label="仓库名称"]',
        "address": 'input[aria-label="仓库地址"]',
        "coords": 'input[aria-label="仓库地址"]',
    }
    selector = field_selectors.get(missing_field)
    if not selector:
        return ""

    return f"""
    <style>
    .st-key-warehouse-left-panel div[data-baseweb="input"]:has({selector}),
    .st-key-warehouse-left-panel div[data-baseweb="base-input"]:has({selector}) {{
        border-color: #d94b4b !important;
        box-shadow: 0 0 0 2px rgba(217, 75, 75, 0.18) !important;
        background: #fff3f3 !important;
    }}
    .st-key-warehouse-left-panel {selector} {{
        background: #fff3f3 !important;
        border-color: #d94b4b !important;
    }}
    </style>
    """


def build_form_alert_html(kind: str, message: str) -> str:
    palette = {
        "error": {
            "bg": "#fdeceb",
            "border": "#efb7b2",
            "text": "#8c2f27",
            "icon_bg": "#f7d1cd",
            "icon_text": "#aa3e33",
            "icon": "!",
        },
        "success": {
            "bg": "#e9f6e6",
            "border": "#bddfb8",
            "text": "#2d6f35",
            "icon_bg": "#d5ecd1",
            "icon_text": "#2d7a37",
            "icon": "OK",
        },
        "info": {
            "bg": "#e7f1fb",
            "border": "#bfd7f1",
            "text": "#2f5f8c",
            "icon_bg": "#d6e7f8",
            "icon_text": "#356c9d",
            "icon": "i",
        },
    }
    colors = palette.get(kind, palette["error"])
    safe_message = html.escape(message)
    return f"""
    <div class="warehouse-form-alert warehouse-form-alert--{kind}">
      <div class="warehouse-form-alert__icon" aria-hidden="true">{colors["icon"]}</div>
      <div class="warehouse-form-alert__text">{safe_message}</div>
    </div>
    <style>
    .warehouse-form-alert {{
        width: 100%;
        min-height: 56px;
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.8rem 1rem;
        border-radius: 14px;
        box-sizing: border-box;
        border: 1px solid transparent;
    }}
    .warehouse-form-alert__icon {{
        width: 1.7rem;
        height: 1.7rem;
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 700;
        line-height: 1;
    }}
    .warehouse-form-alert__text {{
        flex: 1;
        min-height: 100%;
        display: flex;
        align-items: center;
        margin: 0;
        line-height: 1.45;
    }}
    .warehouse-form-alert--error {{
        background: {palette["error"]["bg"]};
        border-color: {palette["error"]["border"]};
        color: {palette["error"]["text"]};
    }}
    .warehouse-form-alert--error .warehouse-form-alert__icon {{
        background: {palette["error"]["icon_bg"]};
        color: {palette["error"]["icon_text"]};
    }}
    .warehouse-form-alert--success {{
        background: {palette["success"]["bg"]};
        border-color: {palette["success"]["border"]};
        color: {palette["success"]["text"]};
    }}
    .warehouse-form-alert--success .warehouse-form-alert__icon {{
        background: {palette["success"]["icon_bg"]};
        color: {palette["success"]["icon_text"]};
    }}
    .warehouse-form-alert--info {{
        background: {palette["info"]["bg"]};
        border-color: {palette["info"]["border"]};
        color: {palette["info"]["text"]};
    }}
    .warehouse-form-alert--info .warehouse-form-alert__icon {{
        background: {palette["info"]["icon_bg"]};
        color: {palette["info"]["icon_text"]};
    }}
    </style>
    """


st.set_page_config(
    page_title="仓库设置",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)


def build_warehouse_signature(
    *,
    name: str,
    address: str,
    capacity_kg: int,
    capacity_m3: float,
    lng: float | None,
    lat: float | None,
) -> tuple[str, str, int, float, float | None, float | None]:
    return (
        str(name or "").strip(),
        str(address or "").strip(),
        int(capacity_kg or 0),
        round(float(capacity_m3 or 0.0), 4),
        None if lng is None else round(float(lng), 6),
        None if lat is None else round(float(lat), 6),
    )


def build_warehouse_signature_from_state(
    warehouse_data: dict,
) -> tuple[str, str, int, float, float | None, float | None]:
    return build_warehouse_signature(
        name=str(warehouse_data.get("name", "") or "").strip(),
        address=str(warehouse_data.get("address", "") or "").strip(),
        capacity_kg=int(
            warehouse_data.get("capacity_kg", DEFAULT_WAREHOUSE["capacity_kg"]) or 0
        ),
        capacity_m3=float(
            warehouse_data.get("capacity_m3", DEFAULT_WAREHOUSE["capacity_m3"]) or 0.0
        ),
        lng=warehouse_data.get("lng"),
        lat=warehouse_data.get("lat"),
    )


if "warehouse" not in st.session_state:
    st.session_state.warehouse = DEFAULT_WAREHOUSE.copy()
if "api_key_amap" not in st.session_state:
    st.session_state.api_key_amap = DEFAULT_AMAP_API_KEY
if "missing_field" not in st.session_state:
    st.session_state.missing_field = None
if "warehouse_validation_error" not in st.session_state:
    st.session_state.warehouse_validation_error = None
if "warehouse_flash_message" not in st.session_state:
    st.session_state.warehouse_flash_message = None
if "warehouse_flash_kind" not in st.session_state:
    st.session_state.warehouse_flash_kind = "success"
if "warehouse_flash_target" not in st.session_state:
    st.session_state.warehouse_flash_target = "save"
if "warehouse_name_input" not in st.session_state:
    st.session_state.warehouse_name_input = str(st.session_state.warehouse.get("name", "") or "")
if "warehouse_address_input" not in st.session_state:
    st.session_state.warehouse_address_input = str(st.session_state.warehouse.get("address", "") or "")
if "warehouse_capacity_kg_input" not in st.session_state:
    st.session_state.warehouse_capacity_kg_input = int(
        st.session_state.warehouse.get("capacity_kg", DEFAULT_WAREHOUSE["capacity_kg"])
        or DEFAULT_WAREHOUSE["capacity_kg"]
    )
if "warehouse_capacity_m3_input" not in st.session_state:
    st.session_state.warehouse_capacity_m3_input = float(
        st.session_state.warehouse.get("capacity_m3", DEFAULT_WAREHOUSE["capacity_m3"])
        or DEFAULT_WAREHOUSE["capacity_m3"]
    )
if "warehouse_saved_signature" not in st.session_state:
    st.session_state.warehouse_saved_signature = (
        build_warehouse_signature_from_state(st.session_state.warehouse)
        if get_data_status("warehouse") == "saved"
        else None
    )

warehouse = st.session_state.warehouse
current_warehouse_signature = build_warehouse_signature(
    name=st.session_state.get("warehouse_name_input", ""),
    address=st.session_state.get("warehouse_address_input", ""),
    capacity_kg=int(
        st.session_state.get("warehouse_capacity_kg_input", DEFAULT_WAREHOUSE["capacity_kg"])
        or 0
    ),
    capacity_m3=float(
        st.session_state.get("warehouse_capacity_m3_input", DEFAULT_WAREHOUSE["capacity_m3"])
        or 0.0
    ),
    lng=warehouse.get("lng"),
    lat=warehouse.get("lat"),
)
saved_warehouse_signature = st.session_state.get("warehouse_saved_signature")
has_warehouse_draft = any(
    [
        current_warehouse_signature[0],
        current_warehouse_signature[1],
        current_warehouse_signature[4] is not None,
        current_warehouse_signature[5] is not None,
    ]
)
if saved_warehouse_signature and current_warehouse_signature == saved_warehouse_signature:
    set_data_status("warehouse", "saved")
elif has_warehouse_draft:
    set_data_status("warehouse", "dirty")
else:
    set_data_status("warehouse", "empty")

inject_sidebar_navigation_label()
inject_base_style()
render_sidebar_navigation()
render_top_nav(
    tabs=[("仓库信息录入", "sec-form"), ("仓库地图位置", "sec-map"), ("快捷操作", "sec-actions")],
    active_idx=0,
)
render_title("仓库设置", "设置赛事物流配送的中心仓库位置")
st.markdown(
    """
    <style>
    .glp-page-title {
        margin-top: 0 !important;
        margin-bottom: -0.35rem;
        --glp-subtitle-gap: 0.32rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
warehouse_flash_message = st.session_state.pop("warehouse_flash_message", None)
warehouse_flash_kind = st.session_state.pop("warehouse_flash_kind", "success")
warehouse_flash_target = st.session_state.pop("warehouse_flash_target", "save")

missing_field_style_slot = st.empty()

anchor("sec-form")
st.markdown(
    """
    <style>
    .st-key-warehouse-left-panel,
    .st-key-warehouse-right-panel {
        height: 100%;
        border-radius: 28px;
        box-shadow: 0 12px 26px rgba(84, 108, 52, 0.18);
    }
    .st-key-warehouse-left-panel {
        background: linear-gradient(135deg, #dcebbf 0%, #cfe3ab 100%);
        border: 1px solid #c9daa6;
        padding: 1.2rem 1.2rem 1.3rem;
        margin-top: 0.2rem;
    }
    .st-key-warehouse-right-panel {
        background: #adc486;
        border: 1px solid #9eb577;
        padding: 1.95rem 1.35rem 1.35rem;
        margin-top: 0.8rem;
        position: relative;
        min-height: 100%;
    }
    .st-key-warehouse-right-panel > [data-testid="stVerticalBlock"] {
        min-height: 100%;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    }
    .st-key-warehouse-left-panel [data-testid="stMarkdownContainer"] p,
    .st-key-warehouse-right-panel [data-testid="stMarkdownContainer"] p {
        margin: 0;
    }
    .warehouse-section-label {
        font-size: 1rem;
        font-weight: 450;
        color: #26351b;
        margin: 0 0 0.45rem;
    }
    .st-key-warehouse-left-panel label,
    .st-key-warehouse-right-panel label {
        color: #26351b !important;
        font-weight: 600 !important;
    }
    .st-key-warehouse-left-panel [data-baseweb="input"] input,
    .st-key-warehouse-left-panel [data-baseweb="base-input"] input {
        background: rgba(255, 255, 255, 0.9);
        border-radius: 8px;
    }
    .warehouse-box-image {
        width: 100%;
        display: flex;
        justify-content: center;
        margin: 0.1rem 0 0.7rem;
    }
    .warehouse-box-image img {
        display: block;
        width: 210px;
        max-width: 100%;
        height: auto;
    }
    .warehouse-status-pill {
        width: 100%;
        background: #f5f0cf;
        color: #c68f53;
        border-radius: 18px;
        padding: 0.9rem 1.25rem;
        text-align: center;
        font-size: 1.25rem;
        font-weight: 650;
        margin: 0.55rem 0 1rem;
    }
    .warehouse-info-box {
        width: 100%;
        background: #d6e3f2;
        border-radius: 18px;
        padding: 1.35rem 1.5rem;
        color: #5d8bbd;
        font-size: 1.05rem;
        line-height: 1.6;
        box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.35);
    }
    .warehouse-info-box b {
        color: #4f87c2;
    }
    .warehouse-empty-tip {
        text-align: center;
        font-size: 1.2rem;
        font-weight: 600;
        color: #6a98ca;
    }
    .warehouse-map-address {
        margin: 1rem 0 0.85rem;
        background: rgba(245, 240, 207, 0.96);
        border: 1px solid #e3d9a5;
        border-radius: 18px;
        padding: 0.95rem 1.25rem;
        color: #7a6636;
        font-size: 1.05rem;
        line-height: 1.55;
    }
    .warehouse-map-empty {
        height: 430px;
        background: #cedbec;
        border-radius: 28px;
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        color: #5a87b9;
        font-size: 1.65rem;
        line-height: 1.6;
        box-shadow: 0 6px 16px rgba(30, 50, 20, 0.14);
        padding: 1.5rem 2rem;
    }
    @media (max-width: 991px) {
        .st-key-warehouse-left-panel {
            margin-top: 0;
        }
        .st-key-warehouse-right-panel {
            margin-top: 0.18rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)
missing_field_style_slot.markdown(
    build_missing_field_style(st.session_state.get("missing_field")),
    unsafe_allow_html=True,
)
col_left, col_right = st.columns([1.05, 0.95], gap="large")

with col_left:
    with st.container(key="warehouse-left-panel"):
        st.markdown('<div class="warehouse-section-label">仓库名称</div>', unsafe_allow_html=True)
        name = st.text_input(
            "仓库名称",
            key="warehouse_name_input",
            placeholder="请输入仓库名称",
            label_visibility="collapsed",
        )

        st.markdown('<div class="warehouse-section-label">仓库地址</div>', unsafe_allow_html=True)
        address = st.text_input(
            "仓库地址",
            key="warehouse_address_input",
            placeholder="请输入仓库地址",
            label_visibility="collapsed",
        )

        c1, c2 = st.columns(2)
        with c1:
            capacity_kg = st.number_input(
                "仓库容量(kg)",
                min_value=0,
                step=1000,
                key="warehouse_capacity_kg_input",
            )
        with c2:
            capacity_m3 = st.number_input(
                "仓库容量(m³)",
                min_value=0.0,
                step=10.0,
                key="warehouse_capacity_m3_input",
            )

        api_key = st.text_input(
            "高德API密钥",
            value=st.session_state.get("api_key_amap", DEFAULT_AMAP_API_KEY),
            type="password",
            help="默认已填入系统密钥；如需排查或替换，可临时显示并修改。",
        )
        if api_key != st.session_state.get("api_key_amap", DEFAULT_AMAP_API_KEY):
            st.session_state.api_key_amap = api_key or DEFAULT_AMAP_API_KEY

        b1, b2 = st.columns(2)
        with b1:
            get_coord = st.button("获取坐标", type="primary", width='stretch')
        with b2:
            save_info = st.button("保存仓库", width='stretch')
        flash_alert_slot = st.empty()
        form_alert_slot = st.empty()

        current_name = name.strip()
        current_address = address.strip()

        if st.session_state.get("missing_field") == "name" and current_name:
            clear_validation_state()
        elif st.session_state.get("missing_field") == "address" and current_address:
            clear_validation_state()
        elif st.session_state.get("missing_field") == "coords" and has_matching_coordinates(current_address, warehouse):
            clear_validation_state()

        missing_field_style_slot.markdown(
            build_missing_field_style(st.session_state.get("missing_field")),
            unsafe_allow_html=True,
        )

        validation_error = st.session_state.get("warehouse_validation_error")
        form_alert_kind = "error" if validation_error else None
        form_alert_message = validation_error

        if get_coord:
            if not address.strip():
                form_alert_kind = "error"
                form_alert_message = "请先输入仓库地址"
            else:
                result = geocode(address.strip(), st.session_state.get("api_key_amap", DEFAULT_AMAP_API_KEY))
                if result:
                    warehouse["lng"], warehouse["lat"] = float(result[0]), float(result[1])
                    warehouse["name"] = name.strip()
                    warehouse["address"] = address.strip()
                    warehouse["capacity_kg"] = int(capacity_kg)
                    warehouse["capacity_m3"] = float(capacity_m3)
                    set_data_status("warehouse", "dirty")
                    st.session_state.warehouse_flash_kind = "info"
                    st.session_state.warehouse_flash_target = "coord"
                    st.session_state.warehouse_flash_message = (
                        f"坐标已获取：({warehouse['lng']:.6f}, {warehouse['lat']:.6f})，当前为未保存状态。"
                    )
                    clear_validation_state()
                    missing_field_style_slot.markdown("", unsafe_allow_html=True)
                    st.rerun()
                else:
                    form_alert_kind = "error"
                    form_alert_message = "坐标获取失败，请检查地址信息"

        if save_info:
            if not current_name:
                set_validation_error("name", "请填写仓库名称")
                st.rerun()
            if not current_address:
                set_validation_error("address", "请填写仓库地址")
                st.rerun()
            if not has_matching_coordinates(current_address, warehouse):
                set_validation_error("coords", "请先获取当前仓库地址的坐标")
                st.rerun()

            warehouse["name"] = current_name
            warehouse["address"] = current_address
            warehouse["capacity_kg"] = int(capacity_kg)
            warehouse["capacity_m3"] = float(capacity_m3)
            st.session_state.warehouse_saved_signature = build_warehouse_signature_from_state(warehouse)
            set_data_status("warehouse", "saved")
            st.session_state.warehouse_flash_kind = "success"
            st.session_state.warehouse_flash_target = "save"
            st.session_state.warehouse_flash_message = "仓库信息已保存"
            clear_validation_state()
            missing_field_style_slot.markdown("", unsafe_allow_html=True)
            st.rerun()

        if form_alert_message:
            form_alert_slot.markdown(build_form_alert_html(form_alert_kind or "error", form_alert_message), unsafe_allow_html=True)
        elif warehouse_flash_message:
            flash_alert_slot.markdown(
                build_form_alert_html(warehouse_flash_kind or "success", warehouse_flash_message),
                unsafe_allow_html=True,
            )

display_name = current_name or warehouse.get("name", "")
display_address = current_address or warehouse.get("address", "")
display_capacity_kg = int(capacity_kg)
display_capacity_m3 = float(capacity_m3)
has_address = bool(display_address)
has_coords = (
    warehouse.get("lng") is not None
    and warehouse.get("lat") is not None
    and (not current_address or str(warehouse.get("address", "") or "").strip() == current_address)
)
warehouse_status_label = get_data_status_label("warehouse")

with col_right:
    with st.container(key="warehouse-right-panel"):
        if not has_address and BOX_IMAGE.exists():
            box_image_base64 = base64.b64encode(BOX_IMAGE.read_bytes()).decode("ascii")
            st.markdown(
                f'<div class="warehouse-box-image"><img src="data:image/png;base64,{box_image_base64}" alt="仓库箱子图标"></div>',
                unsafe_allow_html=True,
            )

        if has_coords:
            st.markdown(
                f"""
                <div class="warehouse-status-pill">仓库状态：{warehouse_status_label}</div>
                <div class="warehouse-info-box">
                  <b>名称:</b> {display_name or "未填写"}<br/>
                  <b>地址:</b> {display_address or "未填写"}<br/>
                  <b>坐标:</b> ({warehouse.get("lng"):.6f}, {warehouse.get("lat"):.6f})<br/>
                  <b>容量:</b> {display_capacity_kg:,} kg / {display_capacity_m3:,.1f} m³
                </div>
                """,
                unsafe_allow_html=True,
            )
        elif has_address:
            st.markdown(
                f"""
                <div class="warehouse-status-pill">仓库状态：{warehouse_status_label}</div>
                <div class="warehouse-info-box">
                  <b>名称:</b> {display_name or "未填写"}<br/>
                  <b>地址:</b> {display_address}<br/>
                  <b>坐标:</b> 请点击【获取坐标】<br/>
                  <b>容量:</b> {display_capacity_kg:,} kg / {display_capacity_m3:,.1f} m³
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div class="warehouse-status-pill">仓库状态：未设置</div>
                <div class="warehouse-info-box warehouse-empty-tip">
                  请输入地址并点击【获取坐标】
                </div>
                """,
                unsafe_allow_html=True,
            )

anchor("sec-map")
st.markdown('<div class="glp-card-title" style="margin-top:1rem;">仓库地图位置</div>', unsafe_allow_html=True)
if has_coords:
    st.markdown(
        f'<div class="warehouse-map-address"><b>地址：</b>{display_address}</div>',
        unsafe_allow_html=True,
    )
    m = folium.Map(location=[warehouse["lat"], warehouse["lng"]], zoom_start=13)
    folium.Marker(
        [warehouse["lat"], warehouse["lng"]],
        tooltip=display_name or "仓库",
        popup=display_address,
        icon=Icon(color="red", icon="map-marker", prefix="fa"),
    ).add_to(m)
    st_folium(m, height=430, width=None)
elif has_address:
    st.markdown(
        f"""
        <div class="warehouse-map-empty">
          已填写地址：{display_address}<br/>
          点击【获取坐标】后，这里会展示真实地址位置。
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        """
        <div class="warehouse-map-empty">
          请输入地址并点击【获取坐标】<br/>
          这里会展示仓库的真实地址位置。
        </div>
        """,
        unsafe_allow_html=True,
    )

anchor("sec-actions")
st.markdown(
    """
    <style>
    .st-key-warehouse-actions {
        margin-top: 1.5rem;
    }
    .st-key-warehouse-actions .stButton > button,
    .st-key-warehouse-actions .stDownloadButton > button {
        min-height: 54px;
        height: 54px;
        padding: 0.45rem 1rem;
        border-radius: 12px;
    }
    .st-key-warehouse-actions .stButton > button p,
    .st-key-warehouse-actions .stButton > button span,
    .st-key-warehouse-actions .stButton > button div,
    .st-key-warehouse-actions .stDownloadButton > button p,
    .st-key-warehouse-actions .stDownloadButton > button span,
    .st-key-warehouse-actions .stDownloadButton > button div {
        font-size: 1.05rem !important;
        font-weight: 500 !important;
        line-height: 1.15;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.container(key="warehouse-actions"):
    a1, a2 = st.columns([1, 1], gap="large")
    with a1:
        if st.button("清空仓库数据", width='stretch'):
            st.session_state.warehouse = DEFAULT_WAREHOUSE.copy()
            st.session_state.warehouse_name_input = DEFAULT_WAREHOUSE["name"]
            st.session_state.warehouse_address_input = DEFAULT_WAREHOUSE["address"]
            st.session_state.warehouse_capacity_kg_input = DEFAULT_WAREHOUSE["capacity_kg"]
            st.session_state.warehouse_capacity_m3_input = DEFAULT_WAREHOUSE["capacity_m3"]
            st.session_state.warehouse_saved_signature = None
            set_data_status("warehouse", "empty")
            clear_validation_state()
            st.rerun()
    with a2:
        payload = json.dumps(st.session_state.warehouse, ensure_ascii=False, indent=2)
        render_download_button(
            label="导出仓库数据",
            data=payload,
            file_name="warehouse.json",
            mime="application/json",
            key="warehouse-export-json",
            width='stretch',
        )

st.markdown(
    '<div style="margin-top:0.4rem;color:#8a8a8a;font-size:1rem;">提示：总仓库是 VRP 路径优化的起点，所有配送路线将从这里出发。</div>',
    unsafe_allow_html=True,
)
render_page_nav(
    "app.py",
    "pages/2_venues.py",
    prev_label="返回首页",
    key_prefix="warehouse-nav",
    can_go_next=is_data_saved("warehouse"),
    next_block_message="仓库信息尚未保存，请先点击【保存仓库】后再进入下一步。",
)
