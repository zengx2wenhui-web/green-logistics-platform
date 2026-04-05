"""
大型赛事绿色物流碳足迹优化平台 - 主入口
15运会赛事物流碳排放智能分析与路径优化系统
"""
import streamlit as st
import json
from pathlib import Path

# ===================== 页面配置 =====================
st.set_page_config(
    page_title="赛事碳足迹优化平台",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===================== 定义页面导航 =====================
pages = {
    "首页": st.Page("app.py", title="🏠 首页", default=True),
    "Step 1 - 仓库设置": st.Page("pages/1_warehouse.py", title="📍 Step 1: 仓库设置"),
    "Step 2 - 场馆录入": st.Page("pages/2_venues.py", title="🏟️ Step 2: 场馆录入"),
    "Step 3 - 物资需求": st.Page("pages/3_materials.py", title="📦 Step 3: 物资需求"),
    "Step 4 - 车辆配置": st.Page("pages/4_vehicles.py", title="🚛 Step 4: 车辆配置"),
    "Step 5 - 路径优化": st.Page("pages/5_path_optimization.py", title="🗺️ Step 5: 路径优化"),
    "Step 6 - 碳排放概览": st.Page("pages/6_carbon_overview.py", title="📊 Step 6: 碳排放概览"),
    "Step 7 - 碳排放分析": st.Page("pages/7_carbon_analysis.py", title="🔬 Step 7: 碳排放分析"),
    "Step 8 - 优化结果": st.Page("pages/8_results.py", title="📋 Step 8: 优化结果"),
}

pg = st.navigation(pages)
pg.run()


# ===================== 立即初始化 Session State =====================
# 直接在模块级别初始化，确保session_state在任何函数被调用前就存在
if "demands" not in st.session_state:
    st.session_state.demands = {}
if "venues" not in st.session_state:
    st.session_state.venues = []
if "material_demands" not in st.session_state:
    st.session_state.material_demands = {}


# ===================== Session State 初始化函数 =====================
def init_session_state():
    """初始化所有session_state数据（用于手动调用）"""

    # ----- 仓库数据 -----
    if "warehouse" not in st.session_state:
        st.session_state.warehouse = {
            "name": "",
            "address": "",
            "lng": None,
            "lat": None,
            "capacity_kg": 50000,
            "capacity_m3": 500
        }

    # ----- 场馆数据 -----
    # 格式: [{"name": "场馆名", "address": "地址", "lng": 113.x, "lat": 23.x}, ...]
    if "venues" not in st.session_state:
        st.session_state.venues = []

    # ----- 物资需求 -----
    # 格式: {"场馆名": 总重量_kg, ...}
    if "demands" not in st.session_state:
        st.session_state.demands = {}

    # ----- 车辆配置 -----
    # 格式: [{"vehicle_type": "diesel_heavy", "count": 2, "emission_factor": 0.060, "load_ton": 15.0}, ...]
    if "vehicles" not in st.session_state:
        st.session_state.vehicles = []

    # ----- 车队配置 (fleet_config) -----
    # 格式: {"diesel_heavy": 0, "bev": 0, "lng": 0, ...}
    if "fleet_config" not in st.session_state:
        vehicle_lib = load_vehicle_library()
        st.session_state.fleet_config = {
            vehicle["id"]: 0 for vehicle in vehicle_lib
        }

    # ----- 物资需求详情 -----
    # 格式: {"场馆名": {"类别": {"物资名": {"weight_kg": 100, "volume_m3": 1, "urgency": "中"}}}}
    if "material_demands" not in st.session_state:
        st.session_state.material_demands = {}

    # ----- VRP求解结果 -----
    if "vrp_result" not in st.session_state:
        st.session_state.vrp_result = None

    # ----- 优化结果（Step 7保存，Step 8读取）-----
    if "results" not in st.session_state:
        st.session_state.results = None

    # ----- 聚类选址结果 -----
    if "clustering_result" not in st.session_state:
        st.session_state.clustering_result = None

    # ----- 距离矩阵 -----
    if "distance_matrix" not in st.session_state:
        st.session_state.distance_matrix = None

    # ----- 用户配置 -----
    if "api_key_amap" not in st.session_state:
        st.session_state.api_key_amap = ""

    if "vehicle_type" not in st.session_state:
        st.session_state.vehicle_type = "diesel_heavy"

    if "vehicle_capacity" not in st.session_state:
        st.session_state.vehicle_capacity = 10000

    if "num_vehicles" not in st.session_state:
        st.session_state.num_vehicles = 3


def load_vehicle_library():
    """加载车型库数据"""
    try:
        with open("data/vehicle_types.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            # 新格式: {"vehicle_types": [...]} 旧格式: [...]
            if isinstance(data, dict) and "vehicle_types" in data:
                return data["vehicle_types"]
            return data
    except FileNotFoundError:
        try:
            with open("green-logistics-platform/data/vehicle_types.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "vehicle_types" in data:
                    return data["vehicle_types"]
                return data
        except:
            return []


def get_data_summary():
    """获取数据汇总信息"""
    summary = {
        "warehouse_set": bool(st.session_state.warehouse.get("lng")),
        "venues_count": len(st.session_state.venues),
        "venues_geocoded": sum(1 for v in st.session_state.venues if v.get("geocoded")),
        "fleet_vehicles": sum(st.session_state.fleet_config.values()),
        "material_items": sum(
            len(items)
            for venue in st.session_state.material_demands.values()
            for items in venue.values()
        ),
        "total_demand_kg": sum(
            mat["weight_kg"]
            for venue in st.session_state.material_demands.values()
            for items in venue.values()
            for mat in items.values()
        )
    }
    return summary


# ===================== 主页面 =====================
def main():
    init_session_state()

    # ===== 侧边栏 =====
    with st.sidebar:
        st.title("🌿 导航菜单")

        # 状态指示器
        st.markdown("### 📊 数据状态")

        summary = get_data_summary()

        status_items = [
            ("🏭 仓库", summary["warehouse_set"], "未设置" if not summary["warehouse_set"] else "已设置"),
            ("🏟️ 场馆", summary["venues_count"], f"{summary['venues_geocoded']}个已定位"),
            ("🚛 车辆", summary["fleet_vehicles"], "辆已配置"),
            ("📦 物资", summary["material_items"], f"{summary['total_demand_kg']:.0f}kg"),
        ]

        for name, status, detail in status_items:
            if status:
                st.success(f"{name}: {detail}")
            else:
                st.warning(f"{name}: {detail}")

        st.divider()

        # 快速操作
        st.markdown("### ⚡ 快速操作")

        if st.button("🔄 重置所有数据", use_container_width=True):
            for key in list(st.session_state.keys()):
                if key not in ["api_key_amap", "vehicle_type"]:
                    del st.session_state[key]
            st.rerun()

        st.divider()

        # 配置面板
        st.markdown("### ⚙️ 全局配置")

        st.text_input(
            "高德API密钥",
            value=st.session_state.api_key_amap,
            type="password",
            key="api_key_input",
            help="用于地理编码和路径规划"
        )

        st.selectbox(
            "默认车辆类型",
            options=["diesel_heavy", "lng", "hev", "phev", "bev", "fcev"],
            index=0,
            key="vehicle_type_input",
            help="默认使用的车辆类型"
        )

        st.number_input(
            "车辆容量 (kg)",
            min_value=1000,
            max_value=50000,
            value=st.session_state.vehicle_capacity,
            step=1000,
            key="capacity_input",
            help="车辆最大载重"
        )

    # ===== 主内容区 =====

    with col_title:
        st.title("🌿 大型赛事绿色物流碳足迹优化平台")

    with col_breadcrumb:
        st.markdown("")
        st.caption("v1.0 | 2024")

    st.markdown("---")

    # ===== 平台介绍 =====
    st.markdown("""
    ### 🎯 平台简介

    本平台旨在为大型体育赛事提供 **绿色物流碳足迹优化** 解决方案。通过集成以下核心算法：

    | 功能模块 | 技术方案 | 优化目标 |
    |---------|---------|---------|
    | 地理编码 | 高德地图API | 场馆坐标精确定位 |
    | 中转仓选址 | 加权K-Means | 最小化加权距离 |
    | 路径优化 | OR-Tools CVRP | 最小化碳排放 |
    | 车队配置 | 整数规划 | 成本与碳排放平衡 |

    ### 📋 8步使用流程

    请按以下顺序完成操作：

    ```mermaid
    graph LR
    A[📍 Step1: 仓库设置] --> B[🏟️ Step2: 场馆录入]
    B --> C[📦 Step3: 物资需求]
    C --> D[🚛 Step4: 车辆配置]
    D --> E[🔬 Step5: 碳排放分析]
    E --> F[📊 Step6: 碳排放概览]
    F --> G[🗺️ Step7: 路径优化]
    G --> H[📋 Step8: 优化结果]
    ```
    """)

    # ===== 进度指示器 =====
    st.markdown("### 📊 8步流程进度")

    # 检查各步骤完成状态
    step_status = [
        ("Step 1 仓库", summary["warehouse_set"]),
        ("Step 2 场馆", summary["venues_count"] > 0),
        ("Step 3 物资", summary["material_items"] > 0),
        ("Step 4 车辆", summary["fleet_vehicles"] > 0),
    ]

    cols = st.columns(4)
    for i, (name, is_set) in enumerate(step_status):
        with cols[i]:
            if is_set:
                st.success(f"✅ {name}")
                st.progress(1.0)
            else:
                st.warning(f"⏳ {name}")
                st.progress(0.0)

    # 优化结果状态
    has_results = st.session_state.get("results") is not None
    col_opt, col_overview, col_analysis = st.columns(3)
    with col_opt:
        if has_results:
            st.success("✅ Step 7-8 已完成")
            st.progress(1.0)
        else:
            st.info("⏳ Step 7-8 待运行")
            st.progress(0.0)
    with col_overview:
        st.info("📊 Step 6 碳排放概览")
    with col_analysis:
        st.info("🔬 Step 5 碳排放分析")

    st.markdown("---")

    # ===== 功能卡片 =====
    st.markdown("### 🛠️ 核心功能模块（按8步流程排列）")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
        #### 📍 Step 1: 仓库设置
        配置总仓库地址和坐标：
        - 高德API地理编码
        - Folium地图标记
        - 仓库容量配置

        **[打开页面 →](pages/1_仓库设置.py)**
        """)

    with col2:
        st.markdown("""
        #### 🏟️ Step 2: 场馆录入
        批量导入或逐条添加赛事场馆：
        - CSV批量导入
        - 在线表单录入
        - 预置场馆快速添加

        **[打开页面 →](pages/2_场馆录入.py)**
        """)

    with col3:
        st.markdown("""
        #### 📦 Step 3: 物资需求
        为各场馆录入物资配送需求：
        - CSV批量导入
        - 在线表单录入
        - 按场馆汇总统计

        **[打开页面 →](pages/3_物资需求.py)**
        """)

    col4, col5, col6 = st.columns(3)

    with col4:
        st.markdown("""
        #### 🚛 Step 4: 车辆配置
        从车型库选择车辆并配置参数：
        - 6种重型货车车型
        - 自定义载重和碳因子
        - 快捷配置模板

        **[打开页面 →](pages/4_车辆配置.py)**
        """)

    with col5:
        st.markdown("""
        #### 🔬 Step 5: 碳排放分析
        基于车型库的碳排放对比分析：
        - 车型碳因子对比表
        - 不同方案碳排放柱状图
        - 减排潜力排名

        **[打开页面 →](pages/5_碳排放分析.py)**
        """)

    with col6:
        st.markdown("""
        #### 📊 Step 6: 碳排放概览
        赛事物流碳足迹实时监控：
        - 总碳排放量与减排百分比
        - 干线vs终端碳排放饼图
        - 种树等效指标

        **[打开页面 →](pages/6_碳排放概览.py)**
        """)

    col7, col8 = st.columns(2)

    with col7:
        st.markdown("""
        #### 🗺️ Step 7: 路径优化
        执行物流网络优化计算：
        - 构建距离矩阵
        - K-Means中转仓选址
        - VRP路径优化（OR-Tools）

        **[打开页面 →](pages/7_路径优化.py)**
        """)

    with col8:
        st.markdown("""
        #### 📋 Step 8: 优化结果
        查看优化详细结果：
        - Folium物流网络地图
        - 基线vs优化碳排放对比
        - 调度详情CSV导出

        **[打开页面 →](pages/8_优化结果.py)**
        """)

    st.markdown("---")

    # ===== 核心技术栈 =====
    with st.expander("🔧 技术架构说明"):
        st.markdown("""
        ### 技术栈

        | 层级 | 技术 | 用途 |
        |-----|------|-----|
        | 前端 | Streamlit | Web应用框架 |
        | 地图 | Folium + Streamlit-Folium | 地理信息可视化 |
        | 图表 | Plotly | 数据可视化 |
        | 求解器 | OR-Tools | CVRP求解 |
        | 聚类 | Scikit-learn | K-Means选址 |
        | 地图API | 高德地图 | 地理编码/路径规划 |

        ### 算法说明

        #### 碳排放计算公式
        ```
        E = distance_km × emission_factor × load_ton
        emission_factor: kg CO₂/吨·km（来自车型库）
        load_ton: 当前载重（吨）
        ```

        #### Green CVRP目标函数
        ```
        minimize: Σ carbon(i,j) × x(i,j)
        subject to: 容量约束、需求约束
        ```

        #### 加权K-Means
        ```
        minimize: Σ weight(i) × distance(center, point_i)
        ```
        """)

    # ===== 页脚 =====
    st.markdown("---")
    st.caption("""
    © 2024 赛事碳足迹优化平台 | 技术支持 | 部署文档

    **提示：** 使用前请确保已填写高德API密钥（侧边栏配置）
    """)


if __name__ == "__main__":
    main()
