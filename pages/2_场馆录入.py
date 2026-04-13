"""场馆录入页面"""
import streamlit as st
import pandas as pd
import folium
from folium import MacroElement
from jinja2 import Template
from streamlit_folium import st_folium
from utils.amap_api import geocode
from utils.file_reader import read_uploaded_file, LogisticsDataProcessor

st.set_page_config(page_title="场馆录入", page_icon="")

st.title(" 第二步：场馆录入")
st.markdown("批量导入或逐条添加赛事场馆信息")

# 初始化 session_state
if "venues" not in st.session_state:
    st.session_state.venues = []
if "demands" not in st.session_state:
    st.session_state.demands = {}

# ===================== 全局颜色映射 =====================
# Folium Icon 颜色名 -> 场馆类型
VENUE_TYPES = ["比赛场地", "训练场地", "媒体中心", "运动员村", "餐饮中心", "医疗站点", "停车场", "其他"]

# Folium Icon color name 到 CSS hex 的映射，用于图注一致性
VENUE_TYPE_COLORS = {
    "比赛场地": {"folium": "blue",      "hex": "#38AADD"},
    "训练场地": {"folium": "cadetblue", "hex": "#5F9EA0"},
    "媒体中心": {"folium": "purple",    "hex": "#D252B9"},
    "运动员村": {"folium": "green",     "hex": "#72AF26"},
    "餐饮中心": {"folium": "orange",    "hex": "#F69730"},
    "医疗站点": {"folium": "red",       "hex": "#CB2B3E"},
    "停车场":   {"folium": "gray",      "hex": "#575757"},
    "其他":     {"folium": "lightgray", "hex": "#A3A3A3"},
}

tab1, tab2 = st.tabs([" 批量导入", " 在线表单"])

# ===================== 批量导入标签页 =====================
with tab1:
    st.subheader("文件批量导入")
    st.info("**支持格式：** CSV / Excel (.xlsx/.xls) / TXT / JSON | **编码：** 自动识别")

    uploaded_file = st.file_uploader(
        "上传场馆数据文件",
        type=["csv", "xlsx", "xls", "txt", "json"],
        help="文件需包含「场馆名称」和「地址」列"
    )

    api_key_batch = st.text_input(
        "高德API密钥（批量地理编码）",
        value=st.session_state.get("api_key_amap", ""),
        type="password",
        placeholder="输入API密钥进行批量地理编码"
    )
    if api_key_batch:
        st.session_state.api_key_amap = api_key_batch

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        process_btn = st.button(" 开始批量处理", type="primary", use_container_width=True)
    with col_btn2:
        if st.button(" 清空场馆", use_container_width=True):
            st.session_state.venues = []
            st.session_state.demands = {}
            st.rerun()

    if uploaded_file and process_btn:
        if not api_key_batch:
            st.error("请输入API密钥")
        else:
            # 使用 LogisticsDataProcessor 处理上传文件
            processor = LogisticsDataProcessor(
                required_columns=["场馆名称", "地址"],
            )
            df, error = processor.process(uploaded_file)
            if error:
                # 降级到基础读取
                uploaded_file.seek(0)
                df, error = read_uploaded_file(uploaded_file)
                if error:
                    st.error(f" {error}")
                    st.stop()

            if df is not None and len(df) > 0:
                st.success(f" 成功读取 {len(df)} 条数据")
                st.dataframe(df, use_container_width=True)

                # 智能列名匹配
                columns = df.columns.tolist()
                name_col, addr_col, demand_col = None, None, None
                for col in columns:
                    cl = str(col).lower()
                    if "名称" in str(col) or "name" in cl or "场馆" in str(col):
                        name_col = name_col or col
                    if "地址" in str(col) or "address" in cl:
                        addr_col = addr_col or col
                    if "需求" in str(col) or "demand" in cl or "量" in str(col):
                        demand_col = demand_col or col

                if name_col is None or addr_col is None:
                    st.warning("未能自动识别列名，请手动选择：")
                    name_col = st.selectbox("选择【场馆名称】列", columns)
                    addr_col = st.selectbox("选择【地址】列", columns)
                    demand_col = st.selectbox("选择【需求量】列（可选）", [None] + columns)
                else:
                    st.info(f"已识别  名称列: `{name_col}`, 地址列: `{addr_col}`")
                    with st.expander(" 手动调整列映射"):
                        name_col = st.selectbox("场馆名称列", columns, index=columns.index(name_col))
                        addr_col = st.selectbox("地址列", columns, index=columns.index(addr_col))
                        demand_col = st.selectbox("需求量列（可选）", [None] + columns)

                # 执行批量处理
                with st.spinner(f"正在处理 {len(df)} 个场馆..."):
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    for idx, row in df.iterrows():
                        venue_name = str(row.get(name_col, "")).strip()
                        venue_address = str(row.get(addr_col, "")).strip()
                        if not venue_name or venue_name == "nan":
                            continue

                        venue_demand = 0.0
                        if demand_col and pd.notna(row.get(demand_col)):
                            try:
                                venue_demand = float(row[demand_col])
                            except (ValueError, TypeError):
                                pass

                        venue = {
                            "id": len(st.session_state.venues) + 1,
                            "name": venue_name,
                            "address": venue_address,
                            "type": "比赛场地",
                            "capacity": 0,
                            "demand_kg": venue_demand,
                            "lng": None, "lat": None,
                            "geocoded": False,
                        }

                        # 地理编码
                        result = geocode(venue_address, api_key_batch)
                        if result:
                            venue["lng"], venue["lat"] = result
                            venue["geocoded"] = True

                        st.session_state.venues.append(venue)
                        st.session_state.demands[venue_name] = venue_demand

                        progress_bar.progress((idx + 1) / len(df))
                        status_text.text(f"处理中: {venue_name} ({idx + 1}/{len(df)})")

                    progress_bar.empty()
                    status_text.empty()
                    ok = sum(1 for v in st.session_state.venues if v.get("geocoded"))
                    st.success(f"批量导入完成！成功定位: {ok}/{len(df)} 个场馆")

# ===================== 在线表单标签页 =====================
with tab2:
    st.subheader("在线表单逐条添加")

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
            placeholder="不填则只保存场馆信息"
        )

        submitted = st.form_submit_button(" 添加场馆", type="primary", use_container_width=True)

        if submitted:
            if not name or not address:
                st.error("请填写必填字段（名称、地址）")
            else:
                lng, lat, geocoded = None, None, False
                if api_key_single:
                    st.session_state.api_key_amap = api_key_single

                # 手动坐标优先
                if 22.0 <= manual_lat <= 25.0 and 112.0 <= manual_lng <= 115.0:
                    lng, lat, geocoded = manual_lng, manual_lat, True
                elif api_key_single:
                    result = geocode(address, api_key_single)
                    if result:
                        lng, lat, geocoded = result[0], result[1], True
                    else:
                        st.warning("地理编码失败，场馆已保存但不包含坐标")

                venue = {
                    "id": len(st.session_state.venues) + 1,
                    "name": name, "address": address,
                    "type": venue_type, "capacity": capacity,
                    "demand_kg": demand_kg,
                    "lng": lng, "lat": lat, "geocoded": geocoded,
                }
                st.session_state.venues.append(venue)
                st.session_state.demands[name] = demand_kg
                st.success(f" 场馆「{name}」已添加！")

    # 快速添加预置场馆
    st.markdown("---")
    st.subheader(" 快速添加预置场馆")
    preset_venues = [
        {"name": "主体育场", "address": "广州市天河区体育西路", "type": "比赛场地", "capacity": 80000},
        {"name": "游泳中心", "address": "广州市天河区体育西路", "type": "比赛场地", "capacity": 4000},
        {"name": "体育馆A", "address": "广州市天河区体育东路", "type": "比赛场地", "capacity": 12000},
        {"name": "运动员村", "address": "广州市天河区奥体中心", "type": "运动员村", "capacity": 15000},
    ]
    cols = st.columns(len(preset_venues))
    for idx, (col, preset) in enumerate(zip(cols, preset_venues)):
        with col:
            if st.button(f" {preset['name']}", use_container_width=True):
                demand = preset["capacity"] * 0.05
                st.session_state.venues.append({
                    "id": len(st.session_state.venues) + 1,
                    "name": preset["name"], "address": preset["address"],
                    "type": preset["type"], "capacity": preset["capacity"],
                    "demand_kg": demand,
                    "lng": None, "lat": None, "geocoded": False,
                })
                st.session_state.demands[preset["name"]] = demand
                st.toast(f"已添加 {preset['name']}")
                st.rerun()

# 向下兼容：旧数据中“比赛场馆”自动映射为“比赛场地”
_TYPE_COMPAT = {"比赛场馆": "比赛场地", "训练场馆": "训练场地"}
for v in st.session_state.venues:
    if v.get("type") in _TYPE_COMPAT:
        v["type"] = _TYPE_COMPAT[v["type"]]

st.markdown("---")

# ===================== 场馆列表 =====================
st.subheader(" 场馆列表")
if st.session_state.venues:
    df_venues = pd.DataFrame([{
        "编号": v["id"],
        "名称": v["name"],
        "地址": v["address"],
        "类型": v["type"],
        "容量": v["capacity"],
        "需求量(kg)": v["demand_kg"],
        "坐标": f"({v['lng']:.4f}, {v['lat']:.4f})" if v.get("lng") else " 未定位",
        "状态": "" if v.get("geocoded") else "",
    } for v in st.session_state.venues])

    col_l1, col_l2 = st.columns([3, 1])
    with col_l1:
        st.dataframe(df_venues, hide_index=True, use_container_width=True)
    with col_l2:
        total_demand = sum(v.get("demand_kg", 0) for v in st.session_state.venues)
        geo_count = sum(1 for v in st.session_state.venues if v.get("geocoded"))
        st.metric("场馆总数", len(st.session_state.venues))
        st.metric("已定位", geo_count)
        st.metric("总需求量", f"{total_demand:,.0f} kg")

    # 删除场馆
    st.markdown("删除场馆")
    venue_names = [v["name"] for v in st.session_state.venues]
    sel = st.selectbox("选择要删除的场馆", [""] + venue_names)
    if sel and st.button("确认删除"):
        st.session_state.venues = [v for v in st.session_state.venues if v["name"] != sel]
        st.session_state.demands.pop(sel, None)
        st.success(f"已删除场馆: {sel}")
        st.rerun()
else:
    st.info("暂无场馆数据，请通过上方方式添加场馆")

st.markdown("---")

# ===================== 场馆地图 =====================
st.subheader(" 场馆分布地图")
if st.session_state.venues:
    geocoded_venues = [v for v in st.session_state.venues if v.get("lat") and v.get("lng")]
    if geocoded_venues:
        center_lat = sum(v["lat"] for v in geocoded_venues) / len(geocoded_venues)
        center_lng = sum(v["lng"] for v in geocoded_venues) / len(geocoded_venues)
        m = folium.Map(location=[center_lat, center_lng], zoom_start=13)

        for venue in st.session_state.venues:
            if venue.get("lat") and venue.get("lng"):
                vtype = venue.get("type", "其他")
                color_info = VENUE_TYPE_COLORS.get(vtype, VENUE_TYPE_COLORS["其他"])
                color = color_info["folium"]
                popup_html = (
                    f"<b>{venue['name']}</b><br>"
                    f"类型: {vtype}<br>"
                    f"地址: {venue['address']}<br>"
                    f"需求: {venue['demand_kg']:,.0f} kg"
                )
                folium.Marker(
                    [venue["lat"], venue["lng"]],
                    popup=popup_html, tooltip=venue["name"],
                    icon=folium.Icon(color=color, icon="star")
                ).add_to(m)

        # 添加悬浮图注（Legend）
        legend_items = "".join(
            f'<li><span style="background:{info["hex"]};width:14px;height:14px;'
            f'display:inline-block;margin-right:6px;border:1px solid #999;'
            f'border-radius:2px;vertical-align:middle;"></span>{vtype}</li>'
            for vtype, info in VENUE_TYPE_COLORS.items()
        )
        legend_html = f"""
        {{% macro html(this, kwargs) %}}
        <div style="
            position: fixed; bottom: 30px; left: 30px; z-index: 1000;
            background: white; padding: 10px 14px; border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.25); font-size: 13px;
            line-height: 1.8; max-width: 180px;
        ">
            <b style="font-size:14px;">场馆类型</b>
            <ul style="list-style:none;padding:4px 0 0 0;margin:0;">
                {legend_items}
            </ul>
        </div>
        {{% endmacro %}}
        """
        legend_element = MacroElement()
        legend_element._template = Template(legend_html)
        m.get_root().add_child(legend_element)

        st_folium(m, width=800, height=500)
    else:
        st.warning("暂无已定位的场馆，请先进行地理编码")
else:
    st.info("添加场馆后，地图将自动显示所有场馆位置")

st.markdown("---")

# 导出功能
if st.button(" 导出场馆CSV", use_container_width=True) and st.session_state.venues:
    df_export = pd.DataFrame([{
        "名称": v["name"], "地址": v["address"], "类型": v["type"],
        "容量": v["capacity"], "日均需求量(kg)": v["demand_kg"],
        "经度": v.get("lng", ""), "纬度": v.get("lat", ""),
        "已定位": "是" if v.get("geocoded") else "否",
    } for v in st.session_state.venues])
    csv = df_export.to_csv(index=False)
    st.download_button("下载CSV", data=csv, file_name="venues_export.csv", mime="text/csv")

st.markdown("---")
if st.button("下一步：物资需求 ➡️", type="primary", use_container_width=True):
    st.switch_page("pages/3_物资需求.py")