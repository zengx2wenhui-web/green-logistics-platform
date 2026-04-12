"""
大型赛事绿色物流碳足迹优化平台 - 主入口
十五运会赛事物流碳排放智能分析与路径优化系统
"""
import streamlit as st
from utils.vehicle_config import load_vehicle_types


# ===================== 页面配置 =====================
st.set_page_config(
    page_title="赛事碳足迹优化平台",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": """
        ## 赛事碳足迹优化平台 v1.0

        基于AI的物流碳排放优化系统，为大型赛事提供绿色物流解决方案。

        **核心功能：**
        - 碳排放实时监控与预测
        - VRP路径优化（最小化碳排放）
        - 加权K-Means中转仓选址
        - 新能源车队配置优化

        **技术栈：** Streamlit + Folium + Scikit-learn + 高德API
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

def load_vehicle_library():
    """加载车型库数据（委托 vehicle_config 统一接口）。"""
    return load_vehicle_types()


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
        "vehicle_type": "diesel_heavy",
        "vehicle_capacity": 10000,
        "num_vehicles": 3,
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

    # 车队配置需要车型库
    if "fleet_config" not in st.session_state:
        vehicle_lib = load_vehicle_library()
        st.session_state.fleet_config = {v["id"]: 0 for v in vehicle_lib}


def get_data_summary():
    """获取数据汇总信息"""
    wh = st.session_state.get("warehouse", {})
    venues = st.session_state.get("venues", [])
    demands = st.session_state.get("demands", {})
    vehicles = st.session_state.get("vehicles", [])
    mat = st.session_state.get("material_demands", {})

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
        "fleet_vehicles": sum(v.get("count", 0) for v in vehicles),
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
        st.markdown("###  数据状态")
        status_items = [
            (" 仓库", summary["warehouse_set"],
             "已设置" if summary["warehouse_set"] else "未设置"),
            (" 场馆", summary["venues_count"] > 0,
             f"{summary['venues_geocoded']}/{summary['venues_count']} 已定位"),
            (" 车辆", summary["fleet_vehicles"] > 0,
             f"{summary['fleet_vehicles']} 辆已配置"),
            (" 物资", summary["total_demand_kg"] > 0,
             f"{summary['total_demand_kg']:,.0f} kg"),
        ]
        for name, ok, detail in status_items:
            if ok:
                st.success(f"{name}: {detail}")
            else:
                st.warning(f"{name}: {detail}")

        st.divider()

        # 快速操作
        st.markdown("###  快速操作")
        if st.button(" 重置所有数据", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # ===== 主内容区 =====
    st.title(" 大型赛事绿色物流碳足迹优化平台")
    st.caption("十五运会赛事物流碳排放智能分析与路径优化系统 v1.0")
    st.markdown("---")

    # 平台简介
    st.markdown("""
    ###  平台简介

    本平台旨在为大型体育赛事提供 **绿色物流碳足迹优化** 解决方案。

    | 功能模块 | 技术方案 | 优化目标 |
    |---------|---------|---------|
    | 地理编码 | 高德地图API | 场馆坐标精确定位 |
    | 中转仓选址 | 加权K-Means（UTM投影） | 最小化加权距离 |
    | 路径优化 | 贪心最近邻 VRP | 最小化碳排放 |
    | 碳排放核算 | 标准公式 E = d × ef × L | 精确逐段计算 |
    """)

    # 进度指示器
    st.markdown("###  流程进度")
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
                st.success(f" {name}")
                st.progress(1.0)
            else:
                st.warning(f" {name}")
                st.progress(0.0)

    col_opt, col_res = st.columns(2)
    with col_opt:
        if summary["has_results"]:
            st.success(" 路径优化已完成")
        else:
            st.info(" 第五步~第八步 待运行")
    with col_res:
        if summary["has_results"]:
            st.success(" 可查看分析结果")
        else:
            st.info(" 等待优化计算")

    st.markdown("---")

    # 功能卡片
    st.markdown("###  核心功能模块")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""
        ####  第一步：仓库设置
        - 设置总仓库地址
        - 高德API地理编码
        - 地图标记定位
        """)
    with col2:
        st.markdown("""
        ####  第二步：场馆录入
        - 批量文件导入
        - 在线表单录入
        - 批量地理编码
        """)
    with col3:
        st.markdown("""
        ####  第三步：物资需求
        - 四类物资录入
        - 可编辑数据表
        - 文件批量导入
        """)

    col4, col5, col6 = st.columns(3)
    with col4:
        st.markdown("""
        ####  第四步：车辆配置
        - 6种重型货车车型
        - 自定义载重与碳因子
        - 车队规模配置
        """)
    with col5:
        st.markdown("""
        ####  第五步：路径优化
        - K-Means中转仓选址
        - 贪心最近邻VRP求解
        - 碳排放最小化
        """)
    with col6:
        st.markdown("""
        ####  第六~八步：分析与结果
        - 碳排放概览与对比
        - 车型碳因子分析
        - 调度方案导出
        """)

    st.markdown("---")

    # 技术架构
    with st.expander(" 技术架构说明"):
        st.markdown("""
        | 层级 | 技术 | 用途 |
        |-----|------|-----|
        | 前端 | Streamlit | 应用框架 |
        | 地图 | Folium | 地理可视化 |
        | 图表 | Plotly | 数据可视化 |
        | 求解器 | 贪心最近邻 | VRP路径优化 |
        | 聚类 | Scikit-learn | K-Means选址 |
        | 地图API | 高德地图 | 地理编码 / 路径规划 |

        **碳排放计算公式：** `E = 距离(km) × 碳因子(kg CO₂/吨km) × 载重(吨)`

        **Green CVRP目标：** 最小化总碳排放，同时满足容量约束和需求约束

        **加权K-Means选址：** 最小化 Σ 需求权重 × 距离(中心, 节点)，支持UTM投影与质心吸附
        """)

    # 页脚
    st.markdown("---")
    st.caption(" 2024 赛事碳足迹优化平台 | 十五运会绿色物流解决方案")


if __name__ == "__main__":
    main()