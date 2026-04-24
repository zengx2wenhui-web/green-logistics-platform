"""仓库设置页面。"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import folium
from folium import Icon
import streamlit as st
from streamlit_folium import st_folium

from pages._bottom_nav import render_page_nav
from pages._ui_shared import (
    anchor,
    inject_base_style,
    inject_sidebar_navigation_label,
    render_download_button,
    render_sidebar_navigation,
    render_title,
    render_top_nav,
)
from utils.amap_api import geocode


BOX_IMAGE = Path(__file__).resolve().parents[1] / "assets" / "icons" / "step" / "箱子.png"


st.set_page_config(
    page_title="仓库设置",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)
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
        margin-top: 6px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "warehouse" not in st.session_state:
    st.session_state.warehouse = {
        "name": "",
        "address": "",
        "lng": None,
        "lat": None,
        "capacity_kg": 50000,
        "capacity_m3": 500.0,
    }
if "api_key_amap" not in st.session_state:
    st.session_state.api_key_amap = ""

warehouse = st.session_state.warehouse

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
    }
    .st-key-warehouse-right-panel {
        background: #adc486;
        border: 1px solid #9eb577;
        padding: 1.95rem 1.35rem 1.35rem;
        margin-top: 1.6rem;
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
        margin-bottom: 0;
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
        .st-key-warehouse-right-panel {
            margin-top: 0.35rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)
col_left, col_right = st.columns([1.05, 0.95], gap="large")

with col_left:
    with st.container(key="warehouse-left-panel"):
        st.markdown('<div class="warehouse-section-label">仓库名称</div>', unsafe_allow_html=True)
        name = st.text_input("仓库名称", value=warehouse.get("name", ""), label_visibility="collapsed")

        st.markdown('<div class="warehouse-section-label">仓库地址</div>', unsafe_allow_html=True)
        address = st.text_input("仓库地址", value=warehouse.get("address", ""), label_visibility="collapsed")

        c1, c2 = st.columns(2)
        with c1:
            capacity_kg = st.number_input(
                "仓库容量(kg)",
                min_value=0,
                step=1000,
                value=int(warehouse.get("capacity_kg", 50000)),
            )
        with c2:
            capacity_m3 = st.number_input(
                "仓库容量(m³)",
                min_value=0.0,
                step=10.0,
                value=float(warehouse.get("capacity_m3", 500.0)),
            )

        api_key = st.text_input(
            "高德API密钥",
            value=st.session_state.get("api_key_amap", ""),
            type="password",
        )
        if api_key != st.session_state.get("api_key_amap", ""):
            st.session_state.api_key_amap = api_key

        b1, b2 = st.columns(2)
        with b1:
            get_coord = st.button("获取坐标", type="primary", width='stretch')
        with b2:
            save_info = st.button("保存仓库", width='stretch')

        if get_coord:
            key = api_key.strip() or st.session_state.get("api_key_amap", "").strip()
            if not address.strip():
                st.error("请先输入仓库地址")
            elif not key:
                st.error("请先输入高德API密钥")
            else:
                result = geocode(address.strip(), key)
                if result:
                    st.session_state.api_key_amap = key
                    warehouse["lng"], warehouse["lat"] = float(result[0]), float(result[1])
                    warehouse["name"] = name.strip()
                    warehouse["address"] = address.strip()
                    warehouse["capacity_kg"] = int(capacity_kg)
                    warehouse["capacity_m3"] = float(capacity_m3)
                    st.success(f"坐标已获取：({warehouse['lng']:.6f}, {warehouse['lat']:.6f})")
                else:
                    st.error("坐标获取失败，请检查地址或 API 密钥")

        if save_info:
            warehouse["name"] = name.strip()
            warehouse["address"] = address.strip()
            warehouse["capacity_kg"] = int(capacity_kg)
            warehouse["capacity_m3"] = float(capacity_m3)
            st.success("仓库信息已保存")

display_name = name.strip() or warehouse.get("name", "")
display_address = address.strip() or warehouse.get("address", "")
display_capacity_kg = int(capacity_kg)
display_capacity_m3 = float(capacity_m3)
has_address = bool(display_address)
has_coords = warehouse.get("lng") is not None and warehouse.get("lat") is not None

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
                <div class="warehouse-status-pill">坐标已设置</div>
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
                <div class="warehouse-status-pill">坐标未设置</div>
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
                <div class="warehouse-status-pill">坐标未设置</div>
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
        f'<div class="warehouse-map-address"><b>真实地址：</b>{display_address}</div>',
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
        margin-top: 4rem;
    }
    .st-key-warehouse-actions .stButton > button,
    .st-key-warehouse-actions .stDownloadButton > button {
        height: 80px;
        border-radius: 14px;
    }
    .st-key-warehouse-actions .stButton > button p,
    .st-key-warehouse-actions .stButton > button span,
    .st-key-warehouse-actions .stButton > button div,
    .st-key-warehouse-actions .stDownloadButton > button p,
    .st-key-warehouse-actions .stDownloadButton > button span,
    .st-key-warehouse-actions .stDownloadButton > button div {
        font-size: 1.2rem !important;
        font-weight: 500 !important;
        line-height: 1.1;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.container(key="warehouse-actions"):
    a1, a2 = st.columns([1, 1], gap="large")
    with a1:
        if st.button("清空仓库数据", width='stretch'):
            st.session_state.warehouse = {
                "name": "",
                "address": "",
                "lng": None,
                "lat": None,
                "capacity_kg": 50000,
                "capacity_m3": 500.0,
            }
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
render_page_nav("app.py", "pages/2_venues.py", prev_label="返回首页", key_prefix="warehouse-nav")
