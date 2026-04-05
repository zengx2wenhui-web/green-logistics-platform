"""场馆录入页面"""
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from utils.amap_api import geocode
from utils.file_reader import read_uploaded_file

st.set_page_config(page_title="场馆录入", page_icon="🏟️")

st.title("🏟️ Step 2：场馆录入")
st.markdown("批量导入或逐条添加赛事场馆信息")

# 初始化session_state
if "venues" not in st.session_state:
    st.session_state.venues = []

if "demands" not in st.session_state:
    st.session_state.demands = {}

if "venue_form_data" not in st.session_state:
    st.session_state.venue_form_data = {
        "name": "",
        "address": "",
        "venue_type": "比赛场馆",
        "capacity": 0,
        "demand_kg": 0
    }

# 预置场馆类型
VENUE_TYPES = ["比赛场馆", "训练场馆", "媒体中心", "运动员村", "餐饮中心", "医疗站点", "停车场", "其他"]

tab1, tab2 = st.tabs(["📁 批量导入(CVS)", "✏️ 在线表单"])

with tab1:
    st.subheader("文件批量导入")

    st.info("""
    **支持文件格式：**
    - CSV (.csv)、Excel (.xlsx, .xls)、TXT (.txt)、JSON (.json)
    - 编码：自动识别（UTF-8/GBK/GB2312）
    """)
    st.caption("支持格式：CSV、Excel(.xlsx/.xls)、TXT、JSON")

    uploaded_file = st.file_uploader(
        "上传场馆数据文件",
        type=["csv", "xlsx", "xls", "txt", "json"],
        help="支持 CSV、Excel、TXT、JSON 格式"
    )

    api_key_batch = st.text_input(
        "高德API密钥 (批量地理编码)",
        type="password",
        placeholder="输入API密钥进行批量地理编码"
    )

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        process_btn = st.button("🚀 开始批量处理", type="primary", use_container_width=True)
    with col_btn2:
        clear_btn = st.button("🗑️ 清空场馆", use_container_width=True)

    if clear_btn:
        st.session_state.venues = []
        st.session_state.demands = {}
        st.rerun()

    if uploaded_file and process_btn:
        if not api_key_batch:
            st.error("请输入API密钥")
        else:
            df, error = read_uploaded_file(uploaded_file)
            if error:
                st.error(f"❌ {error}")
            elif df is not None and len(df) > 0:
                st.success(f"✅ 成功读取 {len(df)} 条数据")
                st.dataframe(df, width="stretch")
                st.info(f"共读取 {len(df)} 条场馆记录")

                # 智能匹配列名
                columns = df.columns.tolist()
                name_col = None
                addr_col = None
                demand_col = None
                type_col = None
                capacity_col = None

                for col in columns:
                    col_lower = str(col).lower()
                    if '名称' in str(col) or 'name' in col_lower:
                        name_col = col
                    if '地址' in str(col) or 'address' in col_lower or 'location' in col_lower:
                        addr_col = col
                    if '需求' in str(col) or 'demand' in col_lower or '量' in str(col):
                        demand_col = col
                    if '类型' in str(col) or 'type' in col_lower or 'category' in col_lower:
                        type_col = col
                    if '容量' in str(col) or 'capacity' in col_lower or 'cap' in col_lower:
                        capacity_col = col

                # 如果找不到匹配的列，显示已识别的列名，让用户手动选择
                if name_col is None or addr_col is None:
                    st.warning("未能自动识别列名，请手动选择：")
                    name_col = st.selectbox("选择【场馆名称】列", columns, index=columns.index(name_col) if name_col in columns else 0)
                    addr_col = st.selectbox("选择【地址】列", columns, index=columns.index(addr_col) if addr_col in columns else 1)
                    demand_col = st.selectbox("选择【日均需求量_kg】列（可选）", [None] + columns)
                    type_col = st.selectbox("选择【类型】列（可选）", [None] + columns)
                    capacity_col = st.selectbox("选择【容量】列（可选）", [None] + columns)
                else:
                    st.info(f"已识别：名称列=`{name_col}`, 地址列=`{addr_col}`")
                    # 让用户确认或修改
                    with st.expander("🔧 手动调整列映射"):
                        name_col = st.selectbox("场馆名称列", columns, index=columns.index(name_col))
                        addr_col = st.selectbox("地址列", columns, index=columns.index(addr_col))
                        demand_col = st.selectbox("日均需求量_kg列（可选）", [None] + columns, index=0)
                        type_col = st.selectbox("类型列（可选）", [None] + columns, index=0)
                        capacity_col = st.selectbox("容量列（可选）", [None] + columns, index=0)

                # 开始处理
                with st.spinner(f"正在处理 {len(df)} 个场馆..."):
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    for idx, row in df.iterrows():
                        venue_name = str(row.get(name_col, ""))
                        venue_address = str(row.get(addr_col, ""))

                        if not venue_name or venue_name == 'nan':
                            continue

                        venue_demand = float(row.get(demand_col, 0)) if demand_col and pd.notna(row.get(demand_col)) else 0.0
                        venue_type = str(row.get(type_col, "比赛场馆")) if type_col and pd.notna(row.get(type_col)) else "比赛场馆"
                        venue_capacity = int(row.get(capacity_col, 0)) if capacity_col and pd.notna(row.get(capacity_col)) else 0

                        venue = {
                            "id": idx + 1,
                            "name": venue_name,
                            "address": venue_address,
                            "type": venue_type,
                            "capacity": venue_capacity,
                            "demand_kg": venue_demand,
                            "lng": None,
                            "lat": None,
                            "geocoded": False
                        }

                        # 地理编码
                        result = geocode(venue_address, api_key_batch)
                        if result:
                            venue["lng"], venue["lat"] = result
                            venue["geocoded"] = True

                        st.session_state.venues.append(venue)
                        # 同步更新 demands
                        st.session_state.demands[venue_name] = venue_demand

                        progress_bar.progress((idx + 1) / len(df))
                        status_text.text(f"处理中: {venue_name} ({idx + 1}/{len(df)})")

                    progress_bar.empty()
                    status_text.empty()

                    success_count = sum(1 for v in st.session_state.venues if v.get("geocoded"))
                    st.success(f"批量导入完成！成功: {success_count}/{len(df)} 个场馆")

with tab2:
    st.subheader("在线表单逐条添加")

    with st.form("venue_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input(
                "场馆名称 *",
                value=st.session_state.venue_form_data.get("name", ""),
                placeholder="如：主体育场"
            )
        with col2:
            venue_type = st.selectbox(
                "场馆类型",
                VENUE_TYPES,
                index=VENUE_TYPES.index(st.session_state.venue_form_data.get("venue_type", "比赛场馆")) if st.session_state.venue_form_data.get("venue_type", "比赛场馆") in VENUE_TYPES else 0
            )

        address = st.text_input(
            "场馆地址 *",
            value=st.session_state.venue_form_data.get("address", ""),
            placeholder="如：广州市天河区体育东路"
        )

        col_a, col_b = st.columns(2)
        with col_a:
            capacity = st.number_input(
                "场馆容量（人数）",
                min_value=0,
                value=int(st.session_state.venue_form_data.get("capacity", 0)),
                step=1000
            )
        with col_b:
            demand_kg = st.number_input(
                "日均物资需求量 (kg)",
                min_value=0.0,
                value=float(st.session_state.venue_form_data.get("demand_kg", 0)),
                step=100.0
            )

        col_manual1, col_manual2 = st.columns(2)
        with col_manual1:
            manual_lat = st.number_input(
                "手动输入纬度（可选）",
                min_value=-90.0,
                max_value=90.0,
                value=23.0,
                format="%.6f",
                help="如果已知精确坐标可手动输入"
            )
        with col_manual2:
            manual_lng = st.number_input(
                "手动输入经度（可选）",
                min_value=-180.0,
                max_value=180.0,
                value=113.0,
                format="%.6f"
            )

        # API密钥输入（放在表单内，提交前获取）
        api_key_single = st.text_input(
            "高德API密钥（地理编码）",
            type="password",
            placeholder="输入API密钥进行地理编码（可选）",
            help="不填则只保存场馆信息，不获取坐标"
        )

        submitted = st.form_submit_button("➕ 添加场馆", type="primary", use_container_width=True)

        if submitted:
            if not name or not address:
                st.error("请填写必填字段（名称、地址）")
            else:
                lng, lat = None, None
                geocoded = False

                # 优先使用手动坐标
                if manual_lat >= 22.0 and manual_lng >= 112.0:
                    lng, lat = manual_lng, manual_lat
                    geocoded = True
                    st.info(f"使用手动坐标: ({lng}, {lat})")
                elif api_key_single:
                    with st.spinner("正在获取坐标..."):
                        result = geocode(address, api_key_single)
                        if result:
                            lng, lat = result
                            geocoded = True
                            st.success(f"坐标获取成功: ({lng:.6f}, {lat:.6f})")
                        else:
                            st.warning("地理编码失败，场馆将保存但不包含坐标")

                venue = {
                    "id": len(st.session_state.venues) + 1,
                    "name": name,
                    "address": address,
                    "type": venue_type,
                    "capacity": capacity,
                    "demand_kg": demand_kg,
                    "lng": lng,
                    "lat": lat,
                    "geocoded": geocoded
                }

                st.session_state.venues.append(venue)

                # 同步更新 demands
                st.session_state.demands[name] = demand_kg

                st.session_state.venue_form_data = {
                    "name": "",
                    "address": "",
                    "venue_type": "比赛场馆",
                    "capacity": 0,
                    "demand_kg": 0
                }
                st.success(f"✅ 场馆「{name}」已添加！")

    # 快捷预置场馆
    st.markdown("---")
    st.subheader("⚡ 快速添加预置场馆")

    preset_venues = [
        {"name": "主体育场", "address": "广州市天河区体育西路", "type": "比赛场馆", "capacity": 80000},
        {"name": "游泳中心", "address": "广州市天河区体育西路", "type": "比赛场馆", "capacity": 4000},
        {"name": "体育馆A", "address": "广州市天河区体育东路", "type": "比赛场馆", "capacity": 12000},
        {"name": "运动员村", "address": "广州市天河区奥体中心", "type": "运动员村", "capacity": 15000},
    ]

    cols = st.columns(len(preset_venues))
    for idx, (col, preset) in enumerate(zip(cols, preset_venues)):
        with col:
            if st.button(f"➕ {preset['name']}", use_container_width=True):
                preset_demand = preset["capacity"] * 0.05
                st.session_state.venues.append({
                    "id": len(st.session_state.venues) + 1,
                    "name": preset["name"],
                    "address": preset["address"],
                    "type": preset["type"],
                    "capacity": preset["capacity"],
                    "demand_kg": preset_demand,
                    "lng": None,
                    "lat": None,
                    "geocoded": False
                })
                # 同步更新 demands
                st.session_state.demands[preset["name"]] = preset_demand
                st.success(f"已添加{preset['name']}")
                st.rerun()

st.markdown("---")

# 场馆列表展示
st.subheader("📋 场馆列表")

if st.session_state.venues:
    df_venues = pd.DataFrame([
        {
            "ID": v["id"],
            "名称": v["name"],
            "地址": v["address"],
            "类型": v["type"],
            "容量": v["capacity"],
            "需求量_kg": v["demand_kg"],
            "坐标": f"({v['lng']:.4f}, {v['lat']:.4f})" if v.get("lng") else "❌ 未定位",
            "状态": "✅" if v.get("geocoded") else "⚠️"
        }
        for v in st.session_state.venues
    ])

    col_list1, col_list2 = st.columns([3, 1])
    with col_list1:
        st.dataframe(df_venues, hide_index=True, width="stretch")
    with col_list2:
        total_demand = sum(v.get("demand_kg", 0) for v in st.session_state.venues)
        geocoded_count = sum(1 for v in st.session_state.venues if v.get("geocoded"))
        st.metric("场馆总数", len(st.session_state.venues))
        st.metric("已定位", geocoded_count)
        st.metric("总需求量", f"{total_demand:,.0f} kg")

    # 删除场馆功能
    st.markdown("**🗑️ 删除场馆**")
    venue_names = [v["name"] for v in st.session_state.venues]
    selected_venue = st.selectbox("选择要删除的场馆", [""] + venue_names)
    if selected_venue and st.button("确认删除"):
        st.session_state.venues = [v for v in st.session_state.venues if v["name"] != selected_venue]
        # 同时删除 demands 中的记录
        if selected_venue in st.session_state.demands:
            del st.session_state.demands[selected_venue]
        st.success(f"已删除场馆: {selected_venue}")
        st.rerun()

else:
    st.info("暂无场馆数据，请通过上方方式添加场馆")

st.markdown("---")

# 地图展示
st.subheader("🗺️ 场馆分布地图")

if st.session_state.venues:
    # 获取地图中心点
    geocoded_venues = [v for v in st.session_state.venues if v.get("lat") and v.get("lng")]

    if geocoded_venues:
        center_lat = sum(v["lat"] for v in geocoded_venues) / len(geocoded_venues)
        center_lng = sum(v["lng"] for v in geocoded_venues) / len(geocoded_venues)

        m = folium.Map(location=[center_lat, center_lng], zoom_start=13)

        # 颜色映射
        type_colors = {
            "比赛场馆": "blue",
            "训练场馆": "cyan",
            "媒体中心": "purple",
            "运动员村": "green",
            "餐饮中心": "orange",
            "医疗站点": "red",
            "停车场": "gray",
            "其他": "lightgray"
        }

        for venue in st.session_state.venues:
            if venue.get("lat") and venue.get("lng"):
                color = type_colors.get(venue.get("type", "其他"), "blue")

                popup_html = f"""
                <b>{venue['name']}</b><br>
                类型: {venue['type']}<br>
                地址: {venue['address']}<br>
                容量: {venue['capacity']:,}人<br>
                日均需求: {venue['demand_kg']:,.0f} kg
                """

                folium.Marker(
                    [venue["lat"], venue["lng"]],
                    popup=popup_html,
                    tooltip=venue["name"],
                    icon=folium.Icon(color=color, icon="star")
                ).add_to(m)

        # 添加图例
        legend_html = '<div style="position:fixed;bottom:50px;left:50px;z-index:1000;background:white;padding:10px;border-radius:5px;border:1px solid gray;">'
        legend_html += '<b>场馆类型</b><br>'
        for t, c in type_colors.items():
            legend_html += f'<i style="background:{c};width:12px;height:12px;display:inline-block;margin-right:5px;"></i>{t}<br>'
        legend_html += '</div>'
        m.get_root().html.add_child(folium.Element(legend_html))

        st_folium(m, width=800, height=500)
    else:
        st.warning("暂无已定位的场馆，无法显示地图。请先为场馆进行地理编码。")
else:
    st.info("添加场馆后，地图将自动显示所有场馆位置")

st.markdown("---")

# 导出功能
col_exp1, col_exp2 = st.columns(2)
with col_exp1:
    if st.button("📥 导出场馆CSV", use_container_width=True) and st.session_state.venues:
        df_export = pd.DataFrame([
            {
                "名称": v["name"],
                "地址": v["address"],
                "类型": v["type"],
                "容量": v["capacity"],
                "日均需求量_kg": v["demand_kg"],
                "经度": v.get("lng", ""),
                "纬度": v.get("lat", ""),
                "已定位": "是" if v.get("geocoded") else "否"
            }
            for v in st.session_state.venues
        ])
        csv = df_export.to_csv(index=False)
        st.download_button(
            label="下载CSV",
            data=csv,
            file_name="venues_export.csv",
            mime="text/csv"
        )

with col_exp2:
    st.write("")
