"""
大型赛事绿色物流碳足迹优化平台 - 主入口
15运会赛事物流碳排放智能分析与路径优化系统
"""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from pages._ui_shared import inject_sidebar_navigation_label, render_sidebar_navigation
from utils.vehicle_lib import VEHICLE_LIB


# ===================== 页面配置 =====================
st.set_page_config(
    page_title="“碳智运”—面向多点分布式活动的物流碳足迹智能优化平台",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_sidebar_navigation_label()


# ===================== 立即初始化 Session State =====================
if "demands" not in st.session_state:
    st.session_state.demands = {}
if "venues" not in st.session_state:
    st.session_state.venues = []
if "material_demands" not in st.session_state:
    st.session_state.material_demands = {}


# ===================== Session State 初始化函数 =====================
def init_session_state() -> None:
    """初始化所有 session_state 数据（用于手动调用）。"""
    if "warehouse" not in st.session_state:
        st.session_state.warehouse = {
            "name": "",
            "address": "",
            "lng": None,
            "lat": None,
            "capacity_kg": 50000,
            "capacity_m3": 500,
        }

    if "venues" not in st.session_state:
        st.session_state.venues = []

    if "demands" not in st.session_state:
        st.session_state.demands = {}

    if "vehicles" not in st.session_state:
        st.session_state.vehicles = []

    if "fleet_config" not in st.session_state:
        st.session_state.fleet_config = {
            vehicle_id: 0 for vehicle_id in VEHICLE_LIB.keys()
        }

    if "material_demands" not in st.session_state:
        st.session_state.material_demands = {}

    if "vrp_result" not in st.session_state:
        st.session_state.vrp_result = None

    if "results" not in st.session_state:
        st.session_state.results = None

    if "clustering_result" not in st.session_state:
        st.session_state.clustering_result = None

    if "distance_matrix" not in st.session_state:
        st.session_state.distance_matrix = None

    if "api_key_amap" not in st.session_state:
        st.session_state.api_key_amap = ""

    if "vehicle_type" not in st.session_state:
        st.session_state.vehicle_type = "diesel_heavy"

    if "vehicle_capacity" not in st.session_state:
        st.session_state.vehicle_capacity = 10000

    if "num_vehicles" not in st.session_state:
        st.session_state.num_vehicles = 3

    if "global_season" not in st.session_state:
        st.session_state.global_season = "夏"

    if "global_h2_source" not in st.session_state:
        st.session_state.global_h2_source = "工业副产氢"


def _sum_demands_kg(demands: dict) -> float:
    total_demand = 0.0
    for demand in demands.values():
        if isinstance(demand, dict):
            total_demand += float(
                demand.get(
                    "总需求",
                    sum(
                        value
                        for key, value in demand.items()
                        if isinstance(value, (int, float)) and key != "总需求"
                    ),
                )
                or 0
            )
        else:
            try:
                total_demand += float(demand or 0)
            except (TypeError, ValueError):
                continue
    return total_demand


def _sum_material_demands_kg(material_demands: dict) -> float:
    total_demand = 0.0
    for venue in material_demands.values():
        for items in venue.values():
            for material in items.values():
                if isinstance(material, dict):
                    total_demand += float(material.get("weight_kg", 0) or 0)
    return total_demand


def get_data_summary() -> dict:
    """获取数据汇总信息。"""
    warehouse = st.session_state.get("warehouse", {})
    venues = st.session_state.get("venues", [])
    demands = st.session_state.get("demands", {})
    vehicles = st.session_state.get("vehicles", [])
    material_demands = st.session_state.get("material_demands", {})
    fleet_vehicles = sum(
        int(vehicle.get("count_max", vehicle.get("count", 0)) or 0)
        for vehicle in vehicles
    )
    if fleet_vehicles <= 0:
        fleet_vehicles = sum(st.session_state.fleet_config.values())

    total_demand_kg = _sum_material_demands_kg(material_demands)
    if total_demand_kg <= 0:
        total_demand_kg = _sum_demands_kg(demands)

    return {
        "warehouse_set": bool(warehouse.get("lng")),
        "venues_count": len(venues),
        "venues_geocoded": sum(1 for venue in venues if venue.get("geocoded")),
        "fleet_vehicles": fleet_vehicles,
        "material_items": sum(
            len(items)
            for venue in material_demands.values()
            for items in venue.values()
        ),
        "total_demand_kg": total_demand_kg,
    }


def image_to_base64(path: Path) -> str:
    """读取图片并转为 base64；图片不存在时返回空字符串。"""
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def image_to_data_uri(path: Path) -> str:
    """读取图片并转为 data URI；图片不存在时返回空字符串。"""
    if not path.exists():
        return ""
    suffix = path.suffix.lower()
    mime = "image/png"
    if suffix in [".jpg", ".jpeg"]:
        mime = "image/jpeg"
    elif suffix == ".svg":
        mime = "image/svg+xml"
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def resolve_hero_image() -> str:
    """优先使用可视化封面图，缺失时退化为纯色背景。"""
    icon_root = Path(__file__).resolve().parent / "assets" / "icons"
    candidates = [
        icon_root / "首页" / "封面.jpg",
        Path(__file__).resolve().parent / "assets" / "home_cover.jpg",
    ]
    for image_path in candidates:
        if image_path.exists():
            return image_to_base64(image_path)
    return ""


def inject_home_style(hero_b64: str) -> None:
    """注入首页样式。"""
    background_css = (
        f'background-image: linear-gradient(rgba(217, 229, 205, 0.52), rgba(116, 164, 66, 0.62)),'
        f' url("data:image/jpeg;base64,{hero_b64}");'
        if hero_b64
        else "background: linear-gradient(135deg, #d7e5c9 0%, #a8c982 100%);"
    )

    st.markdown(
        f"""
        <style>
        .stApp {{
            background: #cfdcbc;
            color: #111;
            font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif;
        }}
        header[data-testid="stHeader"],
        .stAppToolbar,
        [data-testid="stToolbar"],
        [data-testid="stToolbarActions"],
        [data-testid="stMainMenu"],
        [data-testid="stDecoration"] {{
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
        }}
        [data-testid="stAppViewContainer"] > .main {{
            padding-top: 0 !important;
            margin-top: 0 !important;
        }}
        [data-testid="stSidebar"] {{
            min-width: 214px;
            max-width: 214px;
            border-right: 0;
        }}
        [data-testid="stSidebar"][aria-expanded="false"] {{
            min-width: 214px !important;
            max-width: 214px !important;
            transform: translateX(0) !important;
            margin-left: 0 !important;
        }}
        [data-testid="collapsedControl"],
        button[kind="header"][aria-label*="sidebar"],
        [data-testid="stSidebarCollapseButton"] {{
            display: none !important;
        }}
        [data-testid="stSidebar"] > div:first-child {{
            background: #365f10;
            padding: 0;
        }}
        div[data-testid="stSidebarContent"],
        div[data-testid="stSidebarUserContent"] {{
            padding-top: 0;
            padding-left: 0;
            padding-right: 0;
        }}
        div[data-testid="stSidebarUserContent"] > div:first-child,
        div[data-testid="stSidebarContent"] > div:first-child {{
            height: 0 !important;
            min-height: 0 !important;
            margin-bottom: 0 !important;
            padding: 0 !important;
        }}

        div[data-testid="stVerticalBlock"] > div:has(> div > .hero-wrap) {{
            margin-top: 0 !important;
            padding-top: 0 !important;
        }}

        div[data-testid="stVerticalBlock"] > div:has(.hero-wrap) {{
            margin-top: 0 !important;
            padding-top: 0 !important;
        }}

        div[data-testid="stMarkdown"] {{
            margin-top: 0 !important;
            padding-top: 0 !important;
        }}

        div[data-testid="stMarkdownContainer"] {{
            margin-top: 0 !important;
            padding-top: 0 !important;
        }}

        div[data-testid="stCode"] {{
            display: none !important;
        }}


        [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {{
            margin: 0;
            border-radius: 0;
            padding: 0.1rem 0.6rem 0.1rem 0.4rem;
            border-left: 3px solid transparent;
            background: transparent;
            transition: background-color 0.2s ease;
            min-height: 2rem;
        }}
        [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] p {{
            color: #f0f4ec;
            font-size: 0.99rem;
            font-weight: 500;
            line-height: 1.22;
            letter-spacing: 0.01em;
        }}
        .sidebar-logo-wrap {{
            background: #365F10;
            padding: 0.7rem 0.4rem;
            display: flex;
            justify-content: center;
            align-items: center;
        }}
        .sidebar-logo-wrap img {{
            max-width: 90px;
            height: auto;
        }}
        .sidebar-menu-strip {{
            height: 30px;
            background: #6a8d34;
            display: flex;
            align-items: center;
            padding-left: 8px;
            margin-bottom: 0.5rem;
        }}
        .sidebar-menu-strip img {{
            width: 18px;
            height: 18px;
            object-fit: contain;
        }}
        .sidebar-nav-row {{
            display: flex;
            align-items: center;
            gap: 0.28rem;
            width: 100%;
        }}
        .sidebar-nav-icon {{
            width: 0.95rem;
            height: 0.95rem;
            object-fit: contain;
            flex-shrink: 0;
        }}
        [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {{
            background: rgba(255, 255, 255, 0.08);
        }}
        [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][aria-current="page"],
        [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][data-glp-active="true"] {{
            background: rgba(255, 255, 255, 0.13);
            border-left-color: #d7e8bf;
        }}
        .sidebar-status-title {{
            margin-top: 0.62rem;
            background: #6a8d34;
            color: #f2f6ee;
            font-size: 1.1rem;
            font-weight: 700;
            padding: 0.40rem 0.36rem 0.40rem 0.36rem;
            line-height: 1;
        }}
        .sidebar-status-item {{
            display: flex;
            align-items: center;
            background: rgba(38, 73, 11, 0.48);
            color: #eef3e8;
            padding: 0.55rem 0.5rem;
            border-top: 1px solid rgba(255, 255, 255, 0.09);
            font-size: 0.95rem;
            line-height: 1.2;
        }}
        .sidebar-status-item .icon {{
            width: 1.35rem;
            text-align: center;
            margin-right: 0.3rem;
        }}
        .sidebar-status-item .status-icon-img {{
            width: 1rem;
            height: 1rem;
            object-fit: contain;
            margin-right: 0.35rem;
            flex-shrink: 0;
        }}
        .sidebar-status-item .label {{
            margin-right: 0.16rem;
        }}
        .sidebar-status-item .value {{
            font-weight: 500;
        }}
        .block-container {{
            max-width: 100%;
            padding-top: 0;
            padding-left: 0;
            padding-right: 0;
            padding-bottom: 0;
        }}
        .hero-wrap {{
            min-height: 690px;
            border-radius: 0;
            padding: 0.75rem 2.6rem 1.25rem 2.6rem;
            {background_css}
            background-size: cover;
            background-position: center;
            box-shadow: none;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }}
        .hero-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 2rem;
            color: #111;
        }}
        .hero-title {{
            margin-top: 0.7rem;
            margin-left: 0.8rem;
        }}
        .hero-title h1 {{
            margin: 0;
            font-size: clamp(1.8rem, 2.8vw, 3.6rem);
            line-height: 1.15;
            font-weight: 780;
            letter-spacing: 0.01em;
        }}
        .hero-title p {{
            margin: 0.7rem 0 0 0;
            font-size: clamp(0.95rem, 1.2vw, 1.32rem);
            color: rgba(0, 0, 0, 0.84);
        }}
        .hero-desc {{
            margin-left: 0.8rem;
            margin-top: auto;
            margin-bottom: 0.45rem;
        }}
        .hero-desc h2 {{
            margin: 0;
            font-size: clamp(2rem, 2.7vw, 2.95rem);
            line-height: 1.2;
            color: #f2f5f0;
            font-weight: 500;
        }}
        .hero-desc p {{
            margin: 0.3rem 0 0 0;
            font-size: clamp(1.3rem, 1.95vw, 2.25rem);
            color: #f4f6f3;
            line-height: 1.22;
            font-weight: 450;
        }}
        .hero-feature-grid {{
            margin-top: 0.95rem;
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 1rem;
        }}
        .hero-feature-card {{
            background: rgba(244, 245, 240, 0.91);
            border-radius: 18px;
            padding: 1rem 1.05rem;
            min-height: 100px;
            font-size: clamp(0.97rem, 1.08vw, 1.24rem);
            line-height: 1.43;
            color: #121212;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.12);
        }}
        .section-block {{
            margin-top: 0;
            background: #d7e3c5;
            border-radius: 0;
            padding: 2.9rem 2.5rem 2.9rem 2.5rem;
        }}
        .section-flow {{
            background: #EEF5E3 !important;
        }}
        .flow-card {{
            background: linear-gradient(180deg, rgba(250, 252, 244, 0.98), rgba(238, 245, 227, 0.96));
            border: 1px solid rgba(130, 155, 104, 0.28);
            border-radius: 24px;
            padding: 1.6rem 1.5rem 1.3rem 1.5rem;
            box-shadow: 0 12px 24px rgba(72, 98, 43, 0.08);
            overflow: visible;
        }}
        .section-module {{
            background: #DFEFC8 !important;
        }}
        .section-tech {{
            margin-top: 0;
            background: #EEF5E3;
            border-radius: 0;
            padding: 2.5rem 2.5rem 2.5rem 2.5rem;
        }}
        .section-tech-empty {{
            margin-top: 0;
            background: #DFEFC8;
            border-radius: 0;
            min-height: 280px;
        }}
        .section-title {{
            text-align: center;
            margin: 0 0 1.5rem 0;
            font-size: clamp(1.8rem, 2.6vw, 2.85rem);
            font-weight: 500;
            letter-spacing: 0.01em;
        }}
        .flow-row {{
            display: flex;
            flex-wrap: nowrap;
            align-items: stretch;
            gap: 0.1rem;
            overflow: visible;
            padding: 1rem 0 0.75rem 0;
        }}
        .flow-item {{
            position: relative;
            min-width: 136px;
            flex: 1 1 136px;
        }}
        .flow-link {{
            text-decoration: none !important;
            color: inherit !important;
            display: block;
            position: relative;
            outline: none;
        }}
        .flow-arrow {{
            width: 100%;
            min-height: 80px;
            padding: 0.78rem 0.82rem;
            box-sizing: border-box;
            background: linear-gradient(135deg, #f7fbef 0%, #e8f1d8 100%);
            clip-path: polygon(0 0, calc(100% - 22px) 0, 100% 50%, calc(100% - 22px) 100%, 0 100%, 14px 50%);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            box-shadow: 0 8px 18px rgba(55, 76, 34, 0.12);
            border: 1px solid rgba(119, 145, 86, 0.22);
            font-size: clamp(1.02rem, 1.06vw, 1.28rem);
            font-weight: 680;
            color: #18200f;
            position: relative;
            transition: background 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
        }}
        .flow-item:first-child .flow-arrow {{
            clip-path: polygon(0 0, calc(100% - 22px) 0, 100% 50%, calc(100% - 22px) 100%, 0 100%);
        }}
        .flow-item:last-child .flow-arrow {{
            clip-path: polygon(0 0, 100% 0, 100% 100%, 0 100%);
        }}
        .flow-link:hover .flow-arrow,
        .flow-link:focus-visible .flow-arrow {{
            background: linear-gradient(135deg, #eef9e8 0%, #d8efc7 100%);
            box-shadow: 0 12px 24px rgba(89, 141, 65, 0.24);
            transform: translateY(-2px);
        }}
        .flow-step {{
            font-size: clamp(0.95rem, 0.98vw, 1.12rem);
            font-weight: 700;
            line-height: 1.1;
        }}
        .flow-tooltip {{
            position: absolute;
            left: 50%;
            bottom: calc(100% + 12px);
            transform: translateX(-50%) translateY(8px);
            opacity: 0;
            visibility: hidden;
            pointer-events: none;
            white-space: nowrap;
            background: rgba(43, 67, 24, 0.95);
            color: #f7fbef;
            border-radius: 12px;
            padding: 0.5rem 0.8rem;
            font-size: 0.92rem;
            line-height: 1.2;
            box-shadow: 0 10px 20px rgba(28, 40, 15, 0.2);
            transition: opacity 0.18s ease, transform 0.18s ease, visibility 0.18s ease;
            z-index: 20;
        }}
        .flow-tooltip::after {{
            content: "";
            position: absolute;
            top: 100%;
            left: 50%;
            transform: translateX(-50%);
            border-width: 7px 6px 0 6px;
            border-style: solid;
            border-color: rgba(43, 67, 24, 0.95) transparent transparent transparent;
        }}
        .flow-link:hover .flow-tooltip,
        .flow-link:focus-visible .flow-tooltip {{
            opacity: 1;
            visibility: visible;
            transform: translateX(-50%) translateY(0);
        }}
        .module-grid {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 1.2rem;
            margin-top:1.5rem;
        }}
        .module-card {{
            background: rgba(244, 244, 244, 0.92);
            border-radius: 18px;
            min-height: 270px;
            padding: 1.15rem 1.14rem;
            box-shadow: 0 5px 14px rgba(0, 0, 0, 0.12);
        }}
        .module-card h4 {{
            margin: 0 0 0.72rem 0;
            text-align: center;
            font-size: clamp(1.38rem, 1.52vw, 1.8rem);
            font-weight: 700;
            color: #121212;
        }}
        .module-card ul {{
            margin: 0;
            padding-left: 1.2rem;
            font-size: clamp(0.96rem, 0.98vw, 1.1rem);
            line-height: 1.48;
            color: #1e1e1e;
        }}
        .module-card p {{
            margin: 0.3rem 0 0 0;
            font-size: clamp(0.96rem, 0.98vw, 1.1rem);
            line-height: 1.45;
            color: #1e1e1e;
        }}
        .module-streamlit-card {{
            background: rgba(244, 244, 244, 0.92);
            border-radius: 18px;
            min-height: 270px;
            padding: 1.15rem 1.14rem;
            box-shadow: 0 5px 14px rgba(0, 0, 0, 0.12);
            margin-bottom: 1rem;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}
        .module-streamlit-card:hover {{
            transform: translateY(-9px) scale(1.015);
            box-shadow: 0 14px 22px rgba(0, 0, 0, 0.2);
        }}
        .module-step {{
            text-align: center;
            margin: 0 0 0.72rem 0;
            font-size: clamp(1.38rem, 1.52vw, 1.8rem);
            font-weight: 700;
            color: #121212;
        }}
        .module-title {{
            margin: 0.1rem 0 0.4rem 0;
            font-size: clamp(0.96rem, 0.98vw, 1.1rem);
            line-height: 1.45;
            color: #1e1e1e;
        }}
        .module-list {{
            margin: 0;
            padding-left: 1.2rem;
            font-size: clamp(0.96rem, 0.98vw, 1.1rem);
            line-height: 1.48;
            color: #1e1e1e;
        }}
        .module-list li {{
            margin: 0.2rem 0;
        }}
        .quick-link-title {{
            margin: 2rem 0 0.8rem 0;
            text-align: center;
            font-size: clamp(1.15rem, 1.25vw, 1.35rem);
            color: #3a4a2b;
            font-weight: 600;
        }}
        .tech-wrap {{
            margin-top: 1.4rem;
            margin-bottom: 0.5rem;
        }}
        .architecture-shell {{
            display: flex;
            justify-content: center;
            align-items: center;
            width: 100%;
            padding: 1.4rem 2.5rem 2.5rem 2.5rem;
            box-sizing: border-box;
        }}
        .architecture-card {{
            width: min(100%, 760px);
            background: #eef5e3;
            border-radius: 12px;
            padding: 1.35rem 1.5rem 1.45rem 1.5rem;
            box-sizing: border-box;
        }}
        .architecture-title {{
            margin: 0 0 0.9rem 0;
            text-align: center;
            font-size: clamp(1.2rem, 1.6vw, 1.55rem);
            font-weight: 600;
            color: #3a4a2b;
        }}
        .architecture-expander {{
            width: min(100%, 820px);
            margin: 0 auto;
        }}
        .architecture-toggle {{
            background: #fbfcf8;
            border: 1px solid rgba(112, 140, 74, 0.14);
            border-radius: 4px;
            box-shadow: 0 1px 4px rgba(40, 56, 24, 0.14);
            overflow: hidden;
        }}
        .architecture-toggle summary {{
            list-style: none;
            cursor: pointer;
            min-height: 34px;
            padding: 0.35rem 0.8rem;
            display: flex;
            align-items: center;
            gap: 0.45rem;
            color: #4a523f;
            font-size: 1.10rem;
            font-weight: 500;
        }}
        .architecture-toggle summary::-webkit-details-marker {{
            display: none;
        }}
        .architecture-toggle summary::before {{
            content: "›";
            font-size: 0.95rem;
            color: #6d775f;
            transform: rotate(0deg);
            transition: transform 0.2s ease;
            line-height: 1;
        }}
        .architecture-toggle[open] summary::before {{
            transform: rotate(90deg);
        }}
        .architecture-content {{
            padding: 0 0.9rem 0.9rem 1.9rem;
            color: #2f3527;
            font-size: 0.92rem;
        }}
        .architecture-content table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 0.4rem;
        }}
        .architecture-content th,
        .architecture-content td {{
            border-bottom: 1px solid rgba(112, 140, 74, 0.16);
            padding: 0.48rem 0.4rem;
            text-align: left;
        }}
        .architecture-content p {{
            margin: 0.7rem 0 0;
        }}
        @media (max-width: 1300px) {{
            .hero-feature-grid {{
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }}
            .flow-row {{
                flex-wrap: wrap;
                row-gap: 0.8rem;
            }}
            .flow-item {{
                min-width: calc(25% - 0.45rem);
            }}
            .flow-arrow {{
                min-height: 72px;
            }}
            .module-grid {{
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }}
        }}
        @media (max-width: 900px) {{
            .block-container {{
                padding-top: 0 !important;
                padding-left: 0.5rem;
                padding-right: 0.5rem;
            }}
        .hero-wrap {{
            height: 760px;
            box-sizing: border-box;
            overflow: hidden;
            padding: 0 2.6rem 1.25rem 2.6rem;
            display: flex;
            flex-direction: column;
            justify-content: flex-start;
        }}

        .hero-title {{
            margin-top: 0;
            margin-left: 0.8rem;
        }}

        .hero-desc {{
            margin-left: 0.8rem;
            margin-top: 18rem;   /* 按效果再微调，比如 15rem / 16rem / 17rem */
            margin-bottom: 0.35rem;
        }}

        .hero-feature-grid {{
            margin-top: 0.6rem;
            margin-bottom: 0;
        }}


        .hero-top {{
            font-size: 1.5rem;
        }}
        .hero-title, .hero-desc {{
            margin-left: 0.2rem;
        }}

        .section-block {{
            padding: 2rem 1rem;
        }}
        .module-grid {{
            grid-template-columns: 1fr;
        }}
        .flow-row {{
            gap: 0.6rem;
            overflow-x: visible;
        }}
        .flow-item {{
            min-width: calc(50% - 0.35rem);
            flex: 1 1 calc(50% - 0.35rem);
        }}
        .flow-arrow {{
            width: 100%;
            min-width: 0;
        }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar(summary: dict) -> None:
    """渲染左侧栏。"""
    icon_dir = Path(__file__).resolve().parent / "assets" / "icons" / "首页"
    logo_path = icon_dir / "logo.png"
    menu_icon_path = icon_dir / "三杠.png"
    sidebar_icon_size = 17

    nav_pages = [
        ("首页", "app.py", icon_dir / "首页.png"),
        ("仓库设置", "pages/1_warehouse.py", icon_dir / "仓库设置.png"),
        ("场馆录入", "pages/2_venues.py", icon_dir / "场馆录入.png"),
        ("物资需求", "pages/3_materials.py", icon_dir / "物资需求导入.png"),
        ("车辆配置", "pages/4_vehicles.py", icon_dir / "车辆配置.png"),
        ("路径优化", "pages/7_path_optimization.py", icon_dir / "路径优化.png"),
        ("碳排放概览", "pages/6_carbon_overview.py", icon_dir / "碳排放概览.png"),
        ("碳排放分析", "pages/5_carbon_analysis.py", icon_dir / "碳排放分析.png"),
        ("优化结果", "pages/8_results.py", icon_dir / "优化结果.png"),
    ]

    with st.sidebar:
        if logo_path.exists():
            logo_uri = image_to_data_uri(logo_path)
            st.markdown(
                f'<div class="sidebar-logo-wrap"><img src="{logo_uri}" alt="logo"/></div>',
                unsafe_allow_html=True,
            )

        menu_uri = image_to_data_uri(menu_icon_path)
        if menu_uri:
            st.markdown(
                f'<div class="sidebar-menu-strip"><img src="{menu_uri}" alt="menu"/></div>',
                unsafe_allow_html=True,
            )

        for label, page, icon_path in nav_pages:
            row_icon, row_link = st.columns([0.2, 6.8], gap="small")
            if icon_path.name == "首页.png":
                icon_width = 100
            elif icon_path.name == "物资需求导入.png":
                icon_width = 200
            else:
                icon_width = sidebar_icon_size   
            with row_icon:
                if icon_path.exists():
                    st.image(str(icon_path), width=icon_width)
            with row_link:
                st.page_link(page, label=label)

        st.markdown('<div class="sidebar-status-title">数据状态</div>', unsafe_allow_html=True)

        status_icon_map = {
            "仓库": icon_dir / "仓库.png",
            "场馆": icon_dir / "场馆.png",
            "车辆": icon_dir / "车辆.png",
            "物资": icon_dir / "物资.png",
        }
        status_rows = [
            ("仓库", "已设置" if summary["warehouse_set"] else "未设置"),
            ("场馆", f"{summary['venues_geocoded']}个已定位"),
            ("车辆", f"{summary['fleet_vehicles']}辆已配置"),
            ("物资", f"{summary['total_demand_kg']:.0f}kg"),
        ]
        for label, value in status_rows:
            icon_uri = image_to_data_uri(status_icon_map[label])
            icon_html = ""
            if icon_uri:
                icon_html = f'<img class="status-icon-img" src="{icon_uri}" alt="{label}"/>'
            st.markdown(
                f"""
                <div class="sidebar-status-item">
                  {icon_html}
                  <span class="label">{label}:</span>
                  <span class="value">{value}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_hero() -> None:
    """渲染头部视觉区。"""
    st.markdown(
        """
        <section class="hero-wrap">
          <div class="hero-title">
            <h1>“碳智运”—面向多点分布式活动的物流碳足迹智能优化平台</h1>
            <p>多点分布式活动物流碳排放智能分析与路径优化系统</p>
          </div>
          <div class="hero-desc">
            <h2>本平台旨在</h2>
            <p>提供绿色物流碳足迹优化解决方案</p>
          </div>
          <div class="hero-feature-grid">
            <div class="hero-feature-card">采用高德地图 API 实现地理编码，完成场馆坐标的精确定位。</div>
            <div class="hero-feature-card">基于 K-Medoids 算法进行中转仓选址，实现加权距离最小化。</div>
            <div class="hero-feature-card">运用 异构车队OR-Tools FSMVRP 算法优化配送路径，达成碳排放最小化目标。</div>
            <div class="hero-feature-card">依据 双公式核算模型 进行碳排放核算，实现精确逐段计算。</div>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_module_section() -> None:
    """渲染核心功能模块"""
    modules = [
        (
            "Step 1",
            "仓库设置",
            [
                "配置总仓地址、容量与坐标",
                "支持高德地理编码与手动坐标录入",
                "仓库信息写入全局调度上下文",
                "为后续路径优化提供统一起点",
            ],
        ),
        (
            "Step 2",
            "场馆录入",
            [
                "在线添加与文件批量导入双模式",
                "自动识别场馆名称/地址等核心字段",
                "高德编码补全场馆坐标",
                "列表管理、删除与地图联动展示",
            ],
        ),
        (
            "Step 3",
            "物资需求",
            [
                "智能清洗 Excel/CSV/TXT/JSON 物资文件",
                "动态识别物资列并统一换算为 kg",
                "在线编辑多品类物资需求表",
                "自动汇总总需求并写入调度数据",
            ],
        ),
        (
            "Step 4",
            "车辆配置",
            [
                "基于车型库配置异构运输车队",
                "支持柴油、LNG、混动、纯电、氢燃料等车型",
                "维护车辆数、载重与碳排参数",
                "为求解器提供车队规模与运力约束",
            ],
        ),
        (
            "Step 5",
            "路径优化",
            [
                "基于坐标构建距离矩阵",
                "真实候选仓 K-Medoids 中转枢纽选址",
                "OR-Tools FSMVRP 异构车队求解",
                "执行运力可行性检查与异常拦截",
            ],
        ),
        (
            "Step 6",
            "碳排放概览",
            [
                "展示基线与优化后总碳排",
                "输出减排率、运输距离与等效指标",
                "汇总多条路线的整体表现",
            ],
        ),
        (
            "Step 7",
            "碳排放分析",
            [
                "按车型与路线分段分析碳排放",
                "结合季节与氢气来源修正排放因子",
                "输出对比图表与减排潜力分析",
            ],
        ),
        (
            "Step 8",
            "优化结果",
            [
                "Folium 物流网络与调度路径地图",
                "逐车调度详情与卸货清单展示",
                "优化结果、路线明细与汇总导出",
            ],
        ),
    ]

    cards_html = []
    for step, title, details in modules:
        detail_html = "".join(f"<li>{item}</li>" for item in details)
        cards_html.append(
            f"""
<div class="module-streamlit-card">
  <div class="module-step">{step}</div>
  <p class="module-title"><strong>{title}</strong></p>
  <ul class="module-list">{detail_html}</ul>
</div>
"""
        )

    st.markdown(
        f"""
<section class="section-block section-module" style="margin-top:0;">
  <h3 class="section-title">核心功能模块</h3>
  <div class="module-grid">
    {''.join(cards_html)}
  </div>
</section>
""",
        unsafe_allow_html=True,
    )


def main() -> None:
    init_session_state()

    inject_home_style(resolve_hero_image())
    render_sidebar_navigation()
    render_hero()
    render_module_section()
    render_architecture_html_card()
    if st.button("下一步：进入仓库设置 ➡️", type="primary", width="stretch"):
        st.switch_page("pages/1_warehouse.py")



def render_architecture_html_card() -> None:
    """Render architecture as a single HTML card with inline collapsible content."""
    st.markdown(
        """
        <section class="section-block section-flow" style="margin-top:0; min-height:auto; padding:0;">
          <div class="architecture-shell">
            <div class="architecture-card">
              <h3 class="architecture-title">技术架构说明</h3>
              <div class="architecture-expander">
                <details class="architecture-toggle">
                  <summary>技术架构说明</summary>
                  <div class="architecture-content">
                    <table>
                      <thead>
                        <tr>
                          <th>层级</th>
                          <th>技术</th>
                          <th>用途</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr><td>页面层</td><td>Streamlit + 自定义共享 UI</td><td>多页面交互、侧边栏导航、表单与数据编辑</td></tr>
                        <tr><td>数据处理</td><td>Pandas</td><td>文件读取、字段清洗、动态列提取与汇总统计</td></tr>
                        <tr><td>地图展示</td><td>Folium + Streamlit-Folium</td><td>仓库/场馆分布、物流路径与中转枢纽可视化</td></tr>
                        <tr><td>图表分析</td><td>Plotly Express</td><td>碳排放对比与结果分析图表</td></tr>
                        <tr><td>优化求解</td><td>OR-Tools FSMVRP</td><td>异构车队车辆路径与车队规模优化</td></tr>
                        <tr><td>选址算法</td><td>自定义 K-Medoids + 全国候选仓库数据</td><td>中转仓候选点筛选与聚类选址</td></tr>
                        <tr><td>地理服务</td><td>高德地图 API</td><td>地理编码、逆地理编码与地址补全</td></tr>
                      </tbody>
                    </table>
                    <p>当前项目以 Streamlit 为前端载体，串联仓库设置、场馆录入、物资需求、车队配置、OR-Tools 调度求解与碳排放分析全流程。</p>
                    <p>碳排放核算按路线分段执行，综合运输距离、车辆类型、载重、季节与氢气来源等参数计算优化结果。</p>
                  </div>
                </details>
              </div>
            </div>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
