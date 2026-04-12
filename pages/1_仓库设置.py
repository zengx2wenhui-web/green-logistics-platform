"""总仓库设置页面"""
import streamlit as st
import folium
from streamlit_folium import st_folium
from utils.amap_api import geocode

st.set_page_config(page_title="仓库设置", page_icon="")

st.title(" 第一步：仓库设置")
st.markdown("设置赛事物流配送的中心仓库位置")

# 初始化 session_state
if "warehouse" not in st.session_state:
    st.session_state.warehouse = {
        "name": "", "address": "", "lng": None, "lat": None,
        "capacity_kg": 50000, "capacity_m3": 500
    }

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("仓库信息录入")

    warehouse_name = st.text_input(
        "仓库名称",
        value=st.session_state.warehouse.get("name", ""),
        placeholder="如：十五运会物流中心仓库"
    )

    warehouse_address = st.text_input(
        "仓库地址",
        value=st.session_state.warehouse.get("address", ""),
        placeholder="如：广州市天河区奥体路88号",
        help="输入完整地址，系统将自动获取经纬度坐标"
    )

    col_a, col_b = st.columns(2)
    with col_a:
        capacity_kg = st.number_input(
            "仓库容量 (kg)",
            min_value=0,
            value=int(st.session_state.warehouse.get("capacity_kg", 50000)),
            step=1000
        )
    with col_b:
        capacity_m3 = st.number_input(
            "仓库容积 (m)",
            min_value=0.0,
            value=float(st.session_state.warehouse.get("capacity_m3", 500)),
            step=10.0
        )

    # API 密钥输入，同时保存到全局 session_state
    api_key = st.text_input(
        "高德API密钥",
        value=st.session_state.get("api_key_amap", ""),
        type="password",
        placeholder="输入您的高德API密钥",
        help="请到高德开放平台申请API密钥，此密钥将在后续页面中复用"
    )
    if api_key:
        st.session_state.api_key_amap = api_key

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        geocode_btn = st.button(" 获取坐标", type="primary", use_container_width=True)
    with col_btn2:
        save_btn = st.button(" 保存仓库", use_container_width=True)

    # 执行地理编码
    if geocode_btn and warehouse_address:
        key = api_key or st.session_state.get("api_key_amap", "")
        if not key:
            st.error("请先输入高德API密钥")
        else:
            with st.spinner("正在获取坐标..."):
                result = geocode(warehouse_address, key)
                if result:
                    lng, lat = result
                    st.session_state.warehouse.update({
                        "lng": lng, "lat": lat,
                        "address": warehouse_address,
                        "name": warehouse_name,
                        "capacity_kg": capacity_kg,
                        "capacity_m3": capacity_m3,
                    })
                    st.success(f"坐标获取成功！经度: {lng:.6f}, 纬度: {lat:.6f}")
                else:
                    st.error("地址解析失败，请检查地址是否正确或API密钥是否有效")

    # 保存仓库信息
    if save_btn:
        st.session_state.warehouse.update({
            "name": warehouse_name,
            "address": warehouse_address,
            "capacity_kg": capacity_kg,
            "capacity_m3": capacity_m3,
        })
        st.success("仓库信息已保存！")

with col2:
    st.subheader("仓库状态")
    wh = st.session_state.warehouse

    if wh.get("lng") and wh.get("lat"):
        st.success(" 坐标已设置")
        st.markdown(f"**名称：** {wh.get('name') or '未命名'}")
        st.markdown(f"**地址：** {wh.get('address') or '未填写'}")
        st.markdown(f"**坐标：** ({wh['lng']:.6f}, {wh['lat']:.6f})")
        st.markdown(f"**容量：** {wh.get('capacity_kg', 0):,} kg / {wh.get('capacity_m3', 0):,} m")
    else:
        st.warning(" 坐标未设置")
        st.info("请输入地址并点击「获取坐标」")

st.markdown("---")

# 地图显示
st.subheader(" 仓库位置地图")

if st.session_state.warehouse.get("lng") and st.session_state.warehouse.get("lat"):
    center_lat = st.session_state.warehouse["lat"]
    center_lng = st.session_state.warehouse["lng"]

    m = folium.Map(location=[center_lat, center_lng], zoom_start=15)
    folium.Marker(
        [center_lat, center_lng],
        popup=f"<b>{st.session_state.warehouse.get('name', '仓库')}</b><br>"
              f"地址: {st.session_state.warehouse.get('address', '')}<br>"
              f"容量: {st.session_state.warehouse.get('capacity_kg', 0):,} kg",
        tooltip=st.session_state.warehouse.get("name", "仓库"),
        icon=folium.Icon(color="red", icon="industry")
    ).add_to(m)

    folium.Circle(
        [center_lat, center_lng],
        radius=1000, color="red", fill=True, fillOpacity=0.1
    ).add_to(m)

    st_folium(m, width=800, height=400)
else:
    st.info(" 设置仓库地址后，地图将自动显示位置")

st.markdown("---")

# 快捷操作
st.subheader("快捷操作")
col1, col2, col3 = st.columns(3)
with col1:
    if st.button(" 清除仓库数据", use_container_width=True):
        st.session_state.warehouse = {
            "name": "", "address": "", "lng": None, "lat": None,
            "capacity_kg": 0, "capacity_m3": 0
        }
        st.rerun()
with col2:
    if st.button(" 导出仓库信息", use_container_width=True):
        st.json(st.session_state.warehouse)
with col3:
    st.write("")

st.caption(" 提示：总仓库是VRP路径优化的起点，所有配送路线将从这里出发")