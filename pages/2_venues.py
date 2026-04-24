"""场馆录入页面。"""
from __future__ import annotations

import sys
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from folium import MacroElement
from jinja2 import Template
from streamlit_folium import st_folium

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

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
from utils.file_reader import LogisticsDataProcessor, read_uploaded_file


VENUE_TYPES = ["比赛场地", "训练场地", "媒体中心", "运动员村", "餐饮中心", "医疗站点", "停车场", "其他"]
VENUE_TYPE_COLORS = {
    "比赛场地": {"folium": "blue", "hex": "#38AADD"},
    "训练场地": {"folium": "cadetblue", "hex": "#5F9EA0"},
    "媒体中心": {"folium": "purple", "hex": "#D252B9"},
    "运动员村": {"folium": "green", "hex": "#72AF26"},
    "餐饮中心": {"folium": "orange", "hex": "#F69730"},
    "医疗站点": {"folium": "red", "hex": "#CB2B3E"},
    "停车场": {"folium": "gray", "hex": "#575757"},
    "其他": {"folium": "lightgray", "hex": "#A3A3A3"},
}
TYPE_COMPAT = {"比赛场馆": "比赛场地", "训练场馆": "训练场地"}


def normalize_venue_type(raw_type: object) -> str:
    venue_type = str(raw_type or "").strip()
    if not venue_type:
        return "比赛场地"
    return TYPE_COMPAT.get(venue_type, venue_type if venue_type in VENUE_TYPES else "其他")


def detect_columns(df: pd.DataFrame) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    columns = [str(col) for col in df.columns]
    name_col = addr_col = type_col = cap_col = demand_col = None
    for col in columns:
        col_lower = col.lower()
        if name_col is None and ("名称" in col or "场馆" in col or "name" in col_lower):
            name_col = col
        if addr_col is None and ("地址" in col or "address" in col_lower):
            addr_col = col
        if type_col is None and ("类型" in col or "type" in col_lower):
            type_col = col
        if cap_col is None and ("容量" in col or "capacity" in col_lower):
            cap_col = col
        if demand_col is None and ("需求" in col or "demand" in col_lower or "kg" in col_lower or "量" in col):
            demand_col = col
    return name_col, addr_col, type_col, cap_col, demand_col


def read_venue_file(uploaded_file) -> tuple[pd.DataFrame | None, str | None]:
    processor = LogisticsDataProcessor(required_columns=["场馆名称", "地址"])
    df, error = processor.process(uploaded_file)
    if error:
        uploaded_file.seek(0)
        df, error = read_uploaded_file(uploaded_file)
    return df, error


def build_venue_dataframe(venues: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "编号": venue["id"],
                "名称": venue["name"],
                "地址": venue["address"],
                "类型": venue["type"],
                "容量": venue["capacity"],
                "需求量(kg)": venue["demand_kg"],
                "坐标": (
                    f"({float(venue['lng']):.4f}, {float(venue['lat']):.4f})"
                    if venue.get("lng") is not None and venue.get("lat") is not None
                    else "未定位"
                ),
                "状态": "已定位" if venue.get("geocoded") else "未定位",
            }
            for venue in venues
        ]
    )


def add_map_legend(map_obj: folium.Map) -> None:
    legend_items = "".join(
        (
            f'<li><span style="background:{info["hex"]};width:14px;height:14px;'
            f'display:inline-block;margin-right:6px;border:1px solid #999;'
            f'border-radius:2px;vertical-align:middle;"></span>{venue_type}</li>'
        )
        for venue_type, info in VENUE_TYPE_COLORS.items()
    )
    legend_html = f"""
    {{% macro html(this, kwargs) %}}
    <div style="
        position: fixed; bottom: 30px; left: 30px; z-index: 1000;
        background: white; padding: 10px 14px; border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.25); font-size: 13px;
        line-height: 1.8; max-width: 180px;">
        <b style="font-size:14px;">场馆类型</b>
        <ul style="list-style:none;padding:4px 0 0 0;margin:0;">
            {legend_items}
        </ul>
    </div>
    {{% endmacro %}}
    """
    legend_element = MacroElement()
    legend_element._template = Template(legend_html)
    map_obj.get_root().add_child(legend_element)


st.set_page_config(page_title="场馆录入", page_icon="🏟️", layout="wide", initial_sidebar_state="expanded")
inject_sidebar_navigation_label()
inject_base_style()
render_sidebar_navigation()
render_top_nav(
    tabs=[
        ("场馆录入", "sec-entry"),
        ("场馆列表", "sec-list"),
        ("分布地图", "sec-map"),
    ],
    active_idx=0,
)

st.markdown(
    """
    <style>
    .glp-venue-card,
    .st-key-venues-entry-card,
    .st-key-venues-batch-card,
    .st-key-venues-form-card,
    .st-key-venues-list-card,
    .st-key-venues-map-card {
        background: linear-gradient(135deg, #DFEFC8 0%, #DFEFC8 100%);
        border: 1px solid #d0e2b4;
        border-radius: 28px;
        padding: 1.45rem 1.65rem 1.55rem;
        box-shadow: 0 8px 24px rgba(123, 145, 91, 0.22);
        margin-top: 1.2rem;
        overflow: hidden;
    }
    .glp-venue-card-title {
        font-size: 1.9rem;
        font-weight: 700;
        color: #111;
        margin-bottom: 1rem;
    }
    .glp-field-label {
        font-size: 0.95rem;
        font-weight: 500;
        color: #18220f;
        margin: 0 0 0.45rem 0;
    }
    .glp-upload-tip {
        margin-top: 0.55rem;
        color: #707070;
        font-size: 0.95rem;
    }
    .st-key-venues-batch-upload-panel,
    .st-key-venues-batch-api-panel {
        background: rgba(255, 255, 255, 0.24);
        border: 1px solid rgba(255, 255, 255, 0.5);
        border-radius: 22px;
        padding: 1.2rem 1.2rem 1.1rem;
        min-height: 240px;
        box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.14);
    }
    .st-key-venues-batch-upload-panel > div,
    .st-key-venues-batch-api-panel > div {
        height: 100%;
    }
    .glp-batch-panel-note {
        margin-top: 0.65rem;
        color: #4d5f3b;
        font-size: 0.95rem;
        line-height: 1.7;
    }
    .glp-empty-list {
        min-height: 160px;
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        color: #767676;
        font-size: 1.15rem;
        line-height: 1.7;
    }
    .glp-map-empty {
        height: 420px;
        background: #dbe7f7;
        border-radius: 28px;
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        color: #5b8ac2;
        font-size: 1.55rem;
        line-height: 1.7;
        box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.45);
        padding: 1.5rem 2rem;
    }
    .glp-export-wrap {
        margin: 1.5rem auto 0;
        max-width: 400px;
    }
    div[data-testid="stFileUploader"] > label,
    div[data-testid="stTextInput"] > label,
    div[data-testid="stNumberInput"] > label,
    div[data-testid="stSelectbox"] > label {
        color: #1d2812 !important;
        font-weight: 600 !important;
    }
    div[data-testid="stFileUploaderDropzone"] {
        background: rgba(255, 255, 255, 0.14) !important;
        border: 3px dashed #111 !important;
        border-radius: 18px !important;
        min-height: 120px !important;
    }
    div[data-testid="stFileUploaderDropzoneInstructions"] > div:first-child,
    div[data-testid="stFileUploaderDropzoneInstructions"] > small {
        display: none !important;
    }
    div[data-testid="stFileUploaderDropzone"] button {
        background: #ffffff !important;
        color: #1b1b1b !important;
        border: 0 !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2) !important;
        font-size: 1rem !important;
        padding: 0.55rem 1.25rem !important;
    }
    [data-baseweb="input"] input,
    [data-baseweb="base-input"] input,
    [data-baseweb="select"] > div,
    textarea {
        background: rgba(255, 255, 255, 0.92) !important;
        border-radius: 10px !important;
    }
    .stButton > button,
    .stDownloadButton > button,
    .stFormSubmitButton > button {
        height: 3rem !important;
        border-radius: 14px !important;
        font-size: 1.08rem !important;
        border: 0 !important;
        box-shadow: 0 5px 13px rgba(0, 0, 0, 0.2) !important;
    }
    .stButton > button[kind="primary"],
    .stFormSubmitButton > button[kind="primary"] {
        background: #2db567 !important;
        color: #fff !important;
    }
    .stButton > button:not([kind="primary"]),
    .stDownloadButton > button {
        background: #ffffff !important;
        color: #111 !important;
    }
    div[data-testid="stAlert"] {
        border-radius: 18px !important;
    }
    div[data-testid="stDataFrame"] {
        background: #ffffff;
        border-radius: 18px !important;
        overflow: hidden;
    }
    .glp-bottom-nav {
        margin-top: 2.3rem !important;
        gap: 4rem !important;
        font-size: 1.65rem !important;
    }
    @media (max-width: 900px) {
        .st-key-venues-batch-card,
        .st-key-venues-entry-card,
        .st-key-venues-form-card,
        .st-key-venues-list-card,
        .st-key-venues-map-card {
            padding: 1.2rem 1rem 1.3rem;
        }
        .st-key-venues-batch-upload-panel,
        .st-key-venues-batch-api-panel {
            min-height: auto;
            padding: 1rem;
        }
        .glp-map-empty {
            height: 320px;
            font-size: 1.2rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)
render_title("场馆录入", "批量导入或逐条添加赛事场馆信息")

if "venues" not in st.session_state:
    st.session_state.venues = []
if "demands" not in st.session_state:
    st.session_state.demands = {}

for venue in st.session_state.venues:
    venue["type"] = normalize_venue_type(venue.get("type"))

uploaded_df: pd.DataFrame | None = None
uploaded_error: str | None = None
detected_name = detected_addr = detected_type = detected_cap = detected_demand = None

anchor("sec-entry")
with st.container(key="venues-entry-card"):
    st.markdown('<div class="glp-venue-card-title">场馆录入</div>', unsafe_allow_html=True)
    tab_online, tab_batch = st.tabs(["在线添加", "文件批量导入"])

    with tab_online:
        with st.form("venue_form"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("场馆名称 *", placeholder="如：主体育场")
            with col2:
                venue_type = st.selectbox("场馆类型", VENUE_TYPES)

            address = st.text_input("场馆地址 *", placeholder="如：广州市天河区体育东路")

            col_a, col_b = st.columns(2)
            with col_a:
                capacity = st.number_input("场馆容量（人数）", min_value=0, step=1000)
            with col_b:
                demand_kg = st.number_input("日均物资需求量 (kg)", min_value=0.0, step=100.0)

            col_m1, col_m2 = st.columns(2)
            with col_m1:
                manual_lng = st.number_input("手动输入经度（可选）", value=113.0, format="%.6f")
            with col_m2:
                manual_lat = st.number_input("手动输入纬度（可选）", value=23.0, format="%.6f")

            api_key_single = st.text_input(
                "高德API密钥",
                value=st.session_state.get("api_key_amap", ""),
                type="password",
                placeholder="不填则只保存场馆信息",
            )
            submitted = st.form_submit_button("添加场馆", type="primary", width='stretch')

        if submitted:
            if not name or not address:
                st.error("请填写必填字段（名称、地址）")
            else:
                lng = lat = None
                geocoded = False
                if api_key_single:
                    st.session_state.api_key_amap = api_key_single
                if 22.0 <= manual_lat <= 25.0 and 112.0 <= manual_lng <= 115.0:
                    lng, lat, geocoded = float(manual_lng), float(manual_lat), True
                elif api_key_single:
                    result = geocode(address, api_key_single)
                    if result:
                        lng, lat, geocoded = float(result[0]), float(result[1]), True
                    else:
                        st.warning("地理编码失败，场馆已保存但不包含坐标")

                venue = {
                    "id": len(st.session_state.venues) + 1,
                    "name": name.strip(),
                    "address": address.strip(),
                    "type": normalize_venue_type(venue_type),
                    "capacity": int(capacity),
                    "demand_kg": float(demand_kg),
                    "lng": lng,
                    "lat": lat,
                    "geocoded": geocoded,
                }
                st.session_state.venues.append(venue)
                st.session_state.demands[name.strip()] = float(demand_kg)
                st.success(f"场馆「{name.strip()}」已添加！")

    with tab_batch:
        left, right = st.columns([1, 1], gap="large")

        with left:
            with st.container(key="venues-batch-upload-panel"):
                st.markdown('<div class="glp-field-label">上传场馆数据文件</div>', unsafe_allow_html=True)
                uploaded_file = st.file_uploader(
                    "上传场馆数据文件",
                    type=["csv", "xlsx", "xls", "txt", "json"],
                    label_visibility="collapsed",
                )
                st.markdown('<div class="glp-upload-tip">支持格式：CSV/Excel/TXT/JSON</div>', unsafe_allow_html=True)

                if uploaded_file is not None:
                    uploaded_df, uploaded_error = read_venue_file(uploaded_file)
                    if uploaded_error:
                        st.error(uploaded_error)
                    elif uploaded_df is not None and not uploaded_df.empty:
                        detected_name, detected_addr, detected_type, detected_cap, detected_demand = detect_columns(uploaded_df)
                        st.success("文件读取成功，可开始批量处理。")
                        st.markdown(
                            '<div class="glp-batch-panel-note">系统已完成文件解析，并自动识别场馆名称、地址等关键列。</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.warning("文件中没有可读取的数据")

        with right:
            with st.container(key="venues-batch-api-panel"):
                st.markdown('<div class="glp-field-label">高德API密钥</div>', unsafe_allow_html=True)
                api_key_batch = st.text_input(
                    "高德API密钥",
                    value=st.session_state.get("api_key_amap", ""),
                    type="password",
                    key="venues_batch_api_key",
                    label_visibility="collapsed",
                )
                st.markdown(
                    '<div class="glp-batch-panel-note">用于批量地理编码场馆地址，未填写时无法执行批量定位。</div>',
                    unsafe_allow_html=True,
                )
                if api_key_batch:
                    st.session_state.api_key_amap = api_key_batch

        b1, b2 = st.columns(2)
        with b1:
            process_btn = st.button("开始批量处理", type="primary", width='stretch')
        with b2:
            clear_all = st.button("清空场馆", width='stretch')

        if clear_all:
            st.session_state.venues = []
            st.session_state.demands = {}
            st.success("已清空场馆数据")

        if process_btn:
            if uploaded_file is None:
                st.error("请先上传文件")
            elif uploaded_df is None or uploaded_df.empty:
                st.error("上传文件暂无可读取数据")
            elif not api_key_batch.strip():
                st.error("请输入高德API密钥")
            elif not detected_name or not detected_addr:
                st.error("未能自动识别场馆名称列和地址列，请检查表头命名")
            else:
                st.session_state.venues = []
                st.session_state.demands = {}
                progress_bar = st.progress(0.0)
                status_text = st.empty()

                for idx, (_, row) in enumerate(uploaded_df.iterrows(), start=1):
                    venue_name = str(row.get(detected_name, "")).strip()
                    venue_address = str(row.get(detected_addr, "")).strip()
                    if not venue_name or venue_name.lower() == "nan":
                        continue

                    venue_demand = (
                        float(pd.to_numeric(row.get(detected_demand, 0), errors="coerce") or 0)
                        if detected_demand
                        else 0.0
                    )
                    venue_capacity = (
                        int(pd.to_numeric(row.get(detected_cap, 0), errors="coerce") or 0)
                        if detected_cap
                        else 0
                    )
                    venue_type = (
                        normalize_venue_type(row.get(detected_type, "比赛场地"))
                        if detected_type
                        else "比赛场地"
                    )
                    lng = lat = None
                    geocoded = False

                    result = geocode(venue_address, api_key_batch.strip())
                    if result:
                        lng, lat = float(result[0]), float(result[1])
                        geocoded = True

                    venue = {
                        "id": len(st.session_state.venues) + 1,
                        "name": venue_name,
                        "address": venue_address,
                        "type": venue_type,
                        "capacity": venue_capacity,
                        "demand_kg": venue_demand,
                        "lng": lng,
                        "lat": lat,
                        "geocoded": geocoded,
                    }
                    st.session_state.venues.append(venue)
                    st.session_state.demands[venue_name] = venue_demand
                    progress_bar.progress(idx / len(uploaded_df))
                    status_text.text(f"处理中：{venue_name} ({idx}/{len(uploaded_df)})")

                progress_bar.empty()
                status_text.empty()
                geo_ok = sum(1 for venue in st.session_state.venues if venue.get("geocoded"))
                st.success(f"批量导入完成！成功定位 {geo_ok}/{len(st.session_state.venues)} 个场馆")

anchor("sec-list")
with st.container(key="venues-list-card"):
    st.markdown('<div class="glp-venue-card-title">场馆列表</div>', unsafe_allow_html=True)
    if st.session_state.venues:
        df_venues = build_venue_dataframe(st.session_state.venues)
        col_l1, col_l2 = st.columns([3, 1])
        with col_l1:
            st.dataframe(df_venues, hide_index=True, width='stretch', height=300)
        with col_l2:
            total_demand = sum(float(venue.get("demand_kg", 0) or 0) for venue in st.session_state.venues)
            geo_count = sum(1 for venue in st.session_state.venues if venue.get("geocoded"))
            st.metric("场馆总数", len(st.session_state.venues))
            st.metric("已定位", geo_count)
            st.metric("总需求量", f"{total_demand:,.0f} kg")

        venue_names = [venue["name"] for venue in st.session_state.venues]
        selected_name = st.selectbox("选择要删除的场馆", [""] + venue_names)
        if selected_name and st.button("确认删除"):
            st.session_state.venues = [venue for venue in st.session_state.venues if venue["name"] != selected_name]
            st.session_state.demands.pop(selected_name, None)
            st.success(f"已删除场馆：{selected_name}")
            st.rerun()
    else:
        st.markdown('<div class="glp-empty-list">暂无场馆数据，请通过上方方式添加场馆</div>', unsafe_allow_html=True)

anchor("sec-map")
with st.container(key="venues-map-card"):
    st.markdown('<div class="glp-venue-card-title">场馆分布地图</div>', unsafe_allow_html=True)
    geocoded_venues = [
        venue
        for venue in st.session_state.venues
        if venue.get("lng") is not None and venue.get("lat") is not None
    ]
    if geocoded_venues:
        center_lat = sum(float(venue["lat"]) for venue in geocoded_venues) / len(geocoded_venues)
        center_lng = sum(float(venue["lng"]) for venue in geocoded_venues) / len(geocoded_venues)
        venue_map = folium.Map(location=[center_lat, center_lng], zoom_start=13)

        for venue in geocoded_venues:
            venue_type = normalize_venue_type(venue.get("type"))
            color_info = VENUE_TYPE_COLORS.get(venue_type, VENUE_TYPE_COLORS["其他"])
            popup_html = (
                f"<b>{venue['name']}</b><br>"
                f"类型: {venue_type}<br>"
                f"地址: {venue['address']}<br>"
                f"需求: {float(venue.get('demand_kg', 0) or 0):,.0f} kg"
            )
            folium.Marker(
                [float(venue["lat"]), float(venue["lng"])],
                popup=popup_html,
                tooltip=venue["name"],
                icon=folium.Icon(color=color_info["folium"], icon="star"),
            ).add_to(venue_map)

        add_map_legend(venue_map)
        st_folium(venue_map, width=None, height=500)
    else:
        st.markdown(
            '<div class="glp-map-empty">添加并定位场馆后，地图将自动显示所有场馆位置</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="glp-export-wrap">', unsafe_allow_html=True)
    if st.session_state.venues:
        export_df = pd.DataFrame(
            [
                {
                    "名称": venue["name"],
                    "地址": venue["address"],
                    "类型": venue["type"],
                    "容量": venue["capacity"],
                    "日均需求量(kg)": venue["demand_kg"],
                    "经度": venue.get("lng", ""),
                    "纬度": venue.get("lat", ""),
                    "已定位": "是" if venue.get("geocoded") else "否",
                }
                for venue in st.session_state.venues
            ]
        )
        render_download_button(
            label="导出场馆CSV",
            data=export_df.to_csv(index=False).encode("utf-8-sig"),
            key="venues-export-csv",
            file_name="venues_export.csv",
            mime="text/csv",
            width='stretch',
        )
    else:
        st.button("导出场馆CSV", disabled=True, width='stretch')
    st.markdown("</div>", unsafe_allow_html=True)

render_page_nav("pages/1_warehouse.py", "pages/3_materials.py", key_prefix="venues-nav")
