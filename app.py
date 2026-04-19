"""
大型赛事绿色物流碳足迹优化平台 - 主入口
十五运会赛事物流碳排放智能分析与路径优化系统
"""
import streamlit as st

from utils.vehicle_lib import VEHICLE_LIB

# ===================== 页面配置 =====================
st.set_page_config(
    page_title="赛事碳足迹优化平台",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": """
        ## 赛事碳足迹优化平台 v2.0

        基于AI的物流碳排放优化系统，为大型赛事提供绿色物流解决方案。

        **核心功能：**
        - 碳排放实时监控与预测 (基于动态双公式)
        - VRP路径优化（异构车队最小化碳排放）
        - K-Medoids 全国真实物流枢纽选址
        - 新能源车队配置优化
        """
    }
)

# ===================== 模块级初始化 =====================
if "demands" not in st.session_state:
    st.session_state.demands = {}
if "venues" not in st.session_state:
    st.session_state.venues = []
if "material_demands" not in st.session_state:
    st.session_state.material_demands = {}

# ===================== 工具函数 =====================

def init_session_state():
    """初始化所有 session_state 数据"""
    defaults = {
        "warehouse": {
            "name": "", "address": "", "lng": None, "lat": None,
            "capacity_kg": 50000, "capacity_m3": 500
        },
        "venues": [],
        "demands": {},
        "vehicles": [],
        "material_demands": {},
        "vrp_result": None,
        "results": None,
        "optimization_results": None,
        "clustering_result": None,
        "distance_matrix": None,
        "api_key_amap": "",
        "global_season": "夏",
        "global_h2_source": "工业副产氢",
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

    if "fleet_config" not in st.session_state:
        st.session_state.fleet_config = {v_id: 0 for v_id in VEHICLE_LIB.keys()}


def get_data_summary():
    """获取数据汇总信息"""
    wh = st.session_state.get("warehouse", {})
    venues = st.session_state.get("venues", [])
    demands = st.session_state.get("demands", {})
    vehicles = st.session_state.get("vehicles", [])

    total_demand = 0.0
    for v in demands.values():
        if isinstance(v, dict):
            total_demand += v.get("总需求", sum(
                val for key, val in v.items()
                if isinstance(val, (int, float)) and key != "总需求"
            ))
        else:
            total_demand += float(v)

    return {
        "warehouse_set": bool(wh.get("lng")),
        "venues_count": len(venues),
        "venues_geocoded": sum(1 for v in venues if v.get("geocoded")),
        "fleet_vehicles": sum(v.get("count_max", 0) for v in vehicles),
        "total_demand_kg": total_demand,
        "has_results": (st.session_state.get("optimization_results") is not None
                        or st.session_state.get("results") is not None),
    }


# ===================== 主页面 =====================
def main():
    init_session_state()
    summary = get_data_summary()

    # ===== 侧边栏 =====
    with st.sidebar:
        # 数据状态
        st.markdown("### 📊 数据状态")
        status_items = [
            ("🏢 仓库", summary["warehouse_set"],
             "已设置" if summary["warehouse_set"] else "未设置"),
            ("🏟️ 场馆", summary["venues_count"] > 0,
             f"{summary['venues_geocoded']}/{summary['venues_count']} 已定位"),
            ("🚛 车辆", summary["fleet_vehicles"] > 0,
             f"{summary['fleet_vehicles']} 辆已配置"),
            ("📦 物资", summary["total_demand_kg"] > 0,
             f"{summary['total_demand_kg']:,.0f} kg"),
        ]
        for name, ok, detail in status_items:
            if ok:
                st.success(f"{name}: {detail}")
            else:
                st.warning(f"{name}: {detail}")

        st.divider()

        # 快速操作
        st.markdown("### ⚡ 快速操作")
        if st.button("🔄 重置所有数据", width="stretch"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # ===== 主内容区 =====
    st.title("🚛 大型赛事绿色物流碳足迹优化平台")
    st.caption("十五运会赛事物流碳排放智能分析与路径优化系统 v2.0")
    st.markdown("---")

    # 平台简介
    st.markdown("""
    ### 📖 平台简介

    本平台旨在为大型体育赛事提供 **绿色物流碳足迹优化** 解决方案。

    | 功能模块 | 技术方案 | 优化目标 |
    |---------|---------|---------|
    | 地理编码 | 高德地图API | 场馆坐标精确定位 |
    | 中转仓选址 | **K-Medoids 真实物流园选址** | 最小化全局加权距离 |
    | 路径优化 | OR-Tools FSMVRP（异构车队） | 规划最低碳排放配送路线 |
    | 碳排核算 | **双公式核算模型** | 精确还原有载/空驶实际碳排 |
    """)

    # 进度指示器
    st.markdown("### 🗺️ 流程进度")
    step_status = [
        ("第一步 仓库", summary["warehouse_set"]),
        ("第二步 场馆", summary["venues_count"] > 0),
        ("第三步 物资", summary["total_demand_kg"] > 0),
        ("第四步 车辆", summary["fleet_vehicles"] > 0),
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

    col_opt, col_res = st.columns(2)
    with col_opt:
        if summary["has_results"]:
            st.success("✅ 路径优化已完成")
        else:
            st.info("⏳ 第五步~第八步 待运行")
    with col_res:
        if summary["has_results"]:
            st.success("✅ 可查看分析结果")
        else:
            st.info("⏳ 等待优化计算")

    st.markdown("---")

    # 功能卡片
    st.markdown("### 🧩 核心功能模块")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""
        #### 🏢 第一步：仓库设置
        - 设置总仓库地址
        - 高德API地理编码
        - 地图标记定位
        """)
    with col2:
        st.markdown("""
        #### 🏟️ 第二步：场馆录入
        - 批量文件导入
        - 在线表单录入
        - 批量地理编码
        """)
    with col3:
        st.markdown("""
        #### 📦 第三步：物资需求
        - 四类物资录入
        - 可编辑数据表
        - 文件批量导入
        """)

    col4, col5, col6 = st.columns(3)
    with col4:
        st.markdown("""
        #### 🚛 第四步：车辆配置
        - 全局季节与氢气源设定
        - 自定义实际载重与可用上限
        - 算法自动决定实际派车搭配
        """)
    with col5:
        st.markdown("""
        #### 🧠 第五步：路径优化
        - **全国 120 个真实物流枢纽选址**
        - OR-Tools异构车队自动求解
        - 碳排放最小化（含冷启动成本）
        """)
    with col6:
        st.markdown("""
        #### 📊 第六~八步：分析与结果
        - 基于实际载重的真实碳排分析
        - 减排效益与环保等价物测算
        - 精细化调度方案导出
        """)

    st.markdown("---")

    # 技术架构
    with st.expander("🛠️ 技术架构说明"):
        st.markdown("""
        | 层级 | 技术 | 用途 |
        |-----|------|-----|
        | 前端 | Streamlit | 响应式交互应用框架 |
        | 地图 | Folium | 赛事场馆与路线地理可视化 |
        | 求解器 | OR-Tools | FSMVRP路径优化（解决复杂约束条件） |
        | 聚类 | Scikit-learn (自研K-Medoids) | 全国尺度物流园真实节点选址 |
        | 地图API | 高德地图 | 批量距离矩阵与球面距离降级测算 |

        **最新碳排放计算模型：** - 有载段：`E = 距离(km) × 碳因子(kg CO₂/吨km) × 实际载重(吨) × 季节因子`
        - 空驶段：`E = 距离(km) × 空跑碳排(kg CO₂/km) × 季节因子`
        *(每车额外叠加一次冷启动碳排放基数)*
        """)

    # 页脚
    st.markdown("---")
    if st.button("下一步：进入仓库设置 ➡️", type="primary", width="stretch"):
        st.switch_page("pages/1_仓库设置.py")
    st.caption("© 2026 赛事碳足迹优化平台 | 十五运会绿色物流解决方案")


if __name__ == "__main__":
    main()