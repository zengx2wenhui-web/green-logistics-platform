"""Shared UI helpers for page layout and navigation."""
from __future__ import annotations

import base64
from pathlib import Path
import sys

import streamlit as st

from pages._bottom_nav import render_page_nav


_APP_ROOT = Path(__file__).resolve().parents[1]
_SIDEBAR_ICON_DIR = _APP_ROOT / "assets" / "icons" / "首页"
_DATA_STATUS_SESSION_KEYS = {
    "warehouse": "warehouse_data_status",
    "venues": "venues_data_status",
    "materials": "materials_data_status",
    "vehicles": "vehicles_data_status",
}
_DATA_STATUS_LABELS = {
    "empty": "未设置",
    "dirty": "未保存",
    "saved": "已设置",
}
_DATA_STATUS_DISPLAY_NAMES = {
    "warehouse": "仓库设置",
    "venues": "场馆录入",
    "materials": "物资需求",
    "vehicles": "车辆配置",
}


def inject_sidebar_navigation_label() -> None:
    """Hide Streamlit's default page navigation block."""
    st.markdown(
        """
        <style>
        [data-testid="stSidebarNav"] {
            display: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _image_to_data_uri(path: Path) -> str:
    if not path.exists():
        return ""

    suffix = path.suffix.lower()
    mime = "image/png"
    if suffix in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    elif suffix == ".svg":
        mime = "image/svg+xml"

    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def _sum_material_demands_kg(material_demands: dict) -> float:
    total_demand_kg = 0.0
    for venue in material_demands.values():
        if not isinstance(venue, dict):
            continue
        for items in venue.values():
            if not isinstance(items, dict):
                continue
            for material in items.values():
                if isinstance(material, dict):
                    total_demand_kg += float(material.get("weight_kg", 0) or 0)
    return total_demand_kg


def _sum_demands_kg(demands: dict) -> float:
    total_demand_kg = 0.0
    for demand in demands.values():
        if isinstance(demand, dict):
            total_demand_kg += float(
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
            continue
        try:
            total_demand_kg += float(demand or 0)
        except (TypeError, ValueError):
            continue
    return total_demand_kg


def _infer_data_status(data_key: str) -> str:
    warehouse = st.session_state.get("warehouse", {})
    venues = st.session_state.get("venues", [])
    demands = st.session_state.get("demands", {})
    vehicles = st.session_state.get("vehicles", [])
    material_demands = st.session_state.get("material_demands", {})

    if data_key == "warehouse":
        if warehouse.get("lng") is not None and warehouse.get("lat") is not None:
            return "saved"
        if any(
            warehouse.get(field)
            for field in ("name", "address")
        ):
            return "dirty"
        return "empty"

    if data_key == "venues":
        return "saved" if venues else "empty"

    if data_key == "materials":
        total_demand_kg = _sum_material_demands_kg(material_demands)
        if total_demand_kg <= 0:
            total_demand_kg = _sum_demands_kg(demands)
        return "saved" if total_demand_kg > 0 else "empty"

    if data_key == "vehicles":
        fleet_vehicles = sum(
            int(item.get("count_max", item.get("count", 0)) or 0) for item in vehicles
        )
        return "saved" if fleet_vehicles > 0 else "empty"

    return "empty"


def init_data_status_state() -> None:
    for data_key, session_key in _DATA_STATUS_SESSION_KEYS.items():
        if session_key not in st.session_state:
            st.session_state[session_key] = _infer_data_status(data_key)


def get_data_status(data_key: str) -> str:
    init_data_status_state()
    return st.session_state.get(_DATA_STATUS_SESSION_KEYS[data_key], "empty")


def set_data_status(data_key: str, status: str) -> None:
    init_data_status_state()
    st.session_state[_DATA_STATUS_SESSION_KEYS[data_key]] = status


def is_data_saved(data_key: str) -> bool:
    return get_data_status(data_key) == "saved"


def get_data_status_label(data_key: str) -> str:
    return _DATA_STATUS_LABELS.get(get_data_status(data_key), "未设置")


def _normalize_page_path(page: str | None) -> str:
    return str(page or "").strip().replace("\\", "/").lower()


def _infer_current_page_path() -> str:
    main_module = sys.modules.get("__main__")
    main_file = getattr(main_module, "__file__", "") if main_module else ""
    if not main_file:
        return ""

    try:
        resolved_path = Path(main_file).resolve()
        return str(resolved_path.relative_to(_APP_ROOT)).replace("\\", "/")
    except Exception:
        return str(main_file).replace("\\", "/")


def _get_sidebar_nav_item_key(page: str) -> str:
    normalized = _normalize_page_path(page)
    slug_parts: list[str] = []
    last_was_dash = False

    for char in normalized:
        if char.isalnum():
            slug_parts.append(char)
            last_was_dash = False
        elif not last_was_dash:
            slug_parts.append("-")
            last_was_dash = True

    slug = "".join(slug_parts).strip("-") or "home"
    return f"glp-sidebar-nav-{slug}"


def _format_sidebar_status_value(
    data_key: str,
    *,
    status: str,
    warehouse_name: str,
    venues_count: int,
    fleet_vehicles: int,
    total_demand_kg: float,
) -> str:
    if data_key == "warehouse":
        detail = warehouse_name or "未命名仓库"
    elif data_key == "venues":
        detail = f"{venues_count}个场馆"
    elif data_key == "materials":
        detail = f"{total_demand_kg:.0f} kg"
    elif data_key == "vehicles":
        detail = f"{fleet_vehicles}辆"
    else:
        detail = ""

    if status == "saved":
        return detail or "已设置"
    if status == "dirty":
        return f"未保存（{detail}）" if detail else "未保存"
    return "未设置"


def require_saved_data(
    required_keys: list[str],
    *,
    page_label: str,
    back_page: str | None = None,
    back_label: str = "返回上一步",
    key_prefix: str = "data-guard",
) -> None:
    pending = [data_key for data_key in required_keys if not is_data_saved(data_key)]
    if not pending:
        return

    pending_labels = "、".join(_DATA_STATUS_DISPLAY_NAMES[data_key] for data_key in pending)
    
    st.markdown("<div style='margin-top: 300px;'></div>", unsafe_allow_html=True)
    
    st.warning(f"当前无法进入{page_label}，请先完成并保存：{pending_labels}。")

    st.markdown("<div style='margin-top: 50px;'></div>", unsafe_allow_html=True)
    if back_page:
        _, center_col, _ = st.columns([2.2, 1.6, 2.2])
        with center_col:
            if st.button(back_label, key=f"{key_prefix}-back", width="stretch"):
                st.switch_page(back_page)
    st.stop()


def render_pending_step_state(
    *,
    anchor_name: str,
    container_key: str,
    warning_message: str,
    info_message: str,
    prev_page: str | None,
    next_page: str | None,
    key_prefix: str,
    next_block_message: str,
) -> None:
    anchor(anchor_name)
    with st.container(key=container_key):
        st.warning(warning_message)
        st.info(info_message)
    render_page_nav(
        prev_page,
        next_page,
        key_prefix=key_prefix,
        can_go_next=False,
        next_block_message=next_block_message,
    )
    st.stop()
    raise SystemExit


def render_download_button(
    label: str,
    data: object,
    file_name: str | None = None,
    mime: str | None = None,
    *,
    key: str,
    width: str = "stretch",
    disabled: bool = False,
) -> None:
    """Render download buttons in a fragment to keep media URLs stable across reruns."""
    payload = data.encode("utf-8") if isinstance(data, str) else data

    @st.fragment
    def _render() -> None:
        st.download_button(
            label=label,
            data=payload,
            file_name=file_name,
            mime=mime,
            key=key,
            on_click="ignore",
            disabled=disabled,
            width=width,
        )

    _render()


def _get_sidebar_summary() -> dict[str, int | float | bool]:
    init_data_status_state()
    warehouse = st.session_state.get("warehouse", {})
    venues = st.session_state.get("venues", [])
    vehicles = st.session_state.get("vehicles", [])
    fleet_config = st.session_state.get("fleet_config", {})
    demands = st.session_state.get("demands", {})
    material_demands = st.session_state.get("material_demands", {})

    fleet_vehicles = sum(
        int(item.get("count_max", item.get("count", 0)) or 0) for item in vehicles
    )
    if fleet_vehicles <= 0:
        fleet_vehicles = sum(int(value or 0) for value in fleet_config.values())

    total_demand_kg = sum(
        float(material.get("weight_kg", 0) or 0)
        for venue in material_demands.values()
        for items in venue.values()
        for material in items.values()
        if isinstance(material, dict)
    )
    if total_demand_kg <= 0:
        for demand in demands.values():
            if isinstance(demand, dict):
                total_demand_kg += float(
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
                    total_demand_kg += float(demand or 0)
                except (TypeError, ValueError):
                    continue

    warehouse_status = get_data_status("warehouse")
    venues_status = get_data_status("venues")
    materials_status = get_data_status("materials")
    vehicles_status = get_data_status("vehicles")
    warehouse_name = str(warehouse.get("name", "") or "").strip()

    return {
        "warehouse_status": _format_sidebar_status_value(
            "warehouse",
            status=warehouse_status,
            warehouse_name=warehouse_name,
            venues_count=len(venues),
            fleet_vehicles=fleet_vehicles,
            total_demand_kg=total_demand_kg,
        ),
        "venues_status": _format_sidebar_status_value(
            "venues",
            status=venues_status,
            warehouse_name=warehouse_name,
            venues_count=len(venues),
            fleet_vehicles=fleet_vehicles,
            total_demand_kg=total_demand_kg,
        ),
        "materials_status": _format_sidebar_status_value(
            "materials",
            status=materials_status,
            warehouse_name=warehouse_name,
            venues_count=len(venues),
            fleet_vehicles=fleet_vehicles,
            total_demand_kg=total_demand_kg,
        ),
        "vehicles_status": _format_sidebar_status_value(
            "vehicles",
            status=vehicles_status,
            warehouse_name=warehouse_name,
            venues_count=len(venues),
            fleet_vehicles=fleet_vehicles,
            total_demand_kg=total_demand_kg,
        ),
        "venues_geocoded": sum(1 for venue in venues if venue.get("geocoded")),
        "fleet_vehicles": fleet_vehicles,
        "total_demand_kg": total_demand_kg,
    }


def render_sidebar_navigation(current_page: str | None = None) -> None:
    """Render the app-style sidebar for Streamlit pages."""
    nav_pages = [
        ("首页", "app.py", _SIDEBAR_ICON_DIR / "首页.png"),
        ("仓库设置", "pages/1_warehouse.py", _SIDEBAR_ICON_DIR / "仓库设置.png"),
        ("场馆录入", "pages/2_venues.py", _SIDEBAR_ICON_DIR / "场馆录入.png"),
        ("物资需求", "pages/3_materials.py", _SIDEBAR_ICON_DIR / "物资需求导入.png"),
        ("车辆配置", "pages/4_vehicles.py", _SIDEBAR_ICON_DIR / "车辆配置.png"),
        ("路径优化", "pages/7_path_optimization.py", _SIDEBAR_ICON_DIR / "路径优化.png"),
        ("碳排放概览", "pages/6_carbon_overview.py", _SIDEBAR_ICON_DIR / "碳排放概览.png"),
        ("碳排放分析", "pages/5_carbon_analysis.py", _SIDEBAR_ICON_DIR / "碳排放分析.png"),
        ("优化结果", "pages/8_results.py", _SIDEBAR_ICON_DIR / "优化结果.png"),
    ]
    summary = _get_sidebar_summary()
    current_page_normalized = _normalize_page_path(current_page or _infer_current_page_path())
    active_nav_key = ""

    with st.sidebar:
        logo_uri = _image_to_data_uri(_SIDEBAR_ICON_DIR / "logo.png")
        if logo_uri:
            st.markdown(
                f'<div class="sidebar-logo-wrap"><img src="{logo_uri}" alt="logo"/></div>',
                unsafe_allow_html=True,
            )

        menu_uri = _image_to_data_uri(_SIDEBAR_ICON_DIR / "三杠.png")
        if menu_uri:
            st.markdown(
                f'<div class="sidebar-menu-strip"><img src="{menu_uri}" alt="menu"/></div>',
                unsafe_allow_html=True,
            )

        for label, page, icon_path in nav_pages:
            nav_item_key = _get_sidebar_nav_item_key(page)
            if _normalize_page_path(page) == current_page_normalized:
                active_nav_key = nav_item_key

            with st.container(key=nav_item_key):
                row_icon, row_link = st.columns([0.22, 6.78], gap="small")
                with row_icon:
                    if icon_path.exists():
                        st.image(str(icon_path), width=17)
                with row_link:
                    st.page_link(page, label=label)

        st.markdown('<div class="sidebar-status-title">数据状态</div>', unsafe_allow_html=True)

        status_icon_map = {
            "仓库": _SIDEBAR_ICON_DIR / "仓库.png",
            "场馆": _SIDEBAR_ICON_DIR / "场馆.png",
            "车辆": _SIDEBAR_ICON_DIR / "车辆.png",
            "物资": _SIDEBAR_ICON_DIR / "物资.png",
        }
        status_rows = [
            ("仓库", summary["warehouse_status"]),
            ("场馆", summary["venues_status"]),
            ("物资", summary["materials_status"]),
            ("车辆", summary["vehicles_status"]),
        ]

        for label, value in status_rows:
            icon_uri = _image_to_data_uri(status_icon_map[label])
            icon_html = (
                f'<img class="status-icon-img" src="{icon_uri}" alt="{label}"/>'
                if icon_uri
                else ""
            )
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

    if active_nav_key:
        st.markdown(
            f"""
            <style>
            [data-testid="stSidebar"] .st-key-{active_nav_key} a {{
                background: rgba(255, 255, 255, 0.13) !important;
                border-left-color: #d7e8bf !important;
            }}

            [data-testid="stSidebar"] .st-key-{active_nav_key} a p,
            [data-testid="stSidebar"] .st-key-{active_nav_key} a span {{
                font-weight: 600 !important;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )

    st.html(
        r"""
        <script>
        (() => {
          const routeAliases = {
            "首页": ["/", "/app", "/app.py"],
            "仓库设置": ["/warehouse", "/1_warehouse", "/pages/1_warehouse.py"],
            "场馆录入": ["/venues", "/2_venues", "/pages/2_venues.py"],
            "物资需求": ["/materials", "/3_materials", "/pages/3_materials.py"],
            "车辆配置": ["/vehicles", "/4_vehicles", "/pages/4_vehicles.py"],
            "路径优化": ["/path_optimization", "/7_path_optimization", "/pages/7_path_optimization.py"],
            "碳排放概览": ["/carbon_overview", "/6_carbon_overview", "/pages/6_carbon_overview.py"],
            "碳排放分析": ["/carbon_analysis", "/5_carbon_analysis", "/pages/5_carbon_analysis.py"],
            "优化结果": ["/results", "/8_results", "/pages/8_results.py"],
          };

          const normalize = (value) => {
            const text = `${value || ""}`.toLowerCase().replace(/\\\\/g, "/").trim();
            if (!text) {
              return "/";
            }
            return text === "/" ? "/" : text.replace(/\/+$/, "") || "/";
          };

          const isAliasMatched = (currentPath, currentHref, alias, isHome = false) => {
            const normalizedAlias = normalize(alias);
            if (normalizedAlias === "/") {
              return currentHref === "/";
            }
            if (currentHref === normalizedAlias || currentPath === normalizedAlias) {
              return true;
            }
            if (!isHome && (currentPath.endsWith(normalizedAlias) || currentHref.includes(normalizedAlias))) {
              return true;
            }
            return false;
          };

          const getLinkMatchScore = (link, currentPath, currentHref, isHome) => {
            const label = (link.querySelector("p, span")?.textContent || link.textContent || "").trim();
            const aliases = routeAliases[label] || [];
            let score = 0;

            aliases.forEach((alias) => {
              if (isAliasMatched(currentPath, currentHref, alias, isHome)) {
                score = Math.max(score, normalize(alias) === "/" ? 2 : 4);
              }
            });

            try {
              const linkUrl = new URL(link.href, window.parent.location.origin);
              const linkPath = normalize(linkUrl.pathname);
              const linkHref = normalize(`${linkUrl.pathname}${linkUrl.search}`);

              if (currentHref === linkHref) {
                score = Math.max(score, 6);
              } else if (!isHome && currentPath === linkPath) {
                score = Math.max(score, 5);
              } else if (!isHome && linkPath !== "/" && currentPath.endsWith(linkPath)) {
                score = Math.max(score, 3);
              }
            } catch (error) {
            }

            return score;
          };

          const syncSidebarActiveState = () => {
            const parentDoc = window.parent.document;
            const parentWin = parentDoc.defaultView;
            const sidebar = parentDoc.querySelector('[data-testid="stSidebar"]');
            if (!sidebar) {
              return false;
            }

            const links = Array.from(
              sidebar.querySelectorAll('[class*="st-key-glp-sidebar-nav-"] a[href]')
            );
            if (!links.length) {
              return false;
            }

            const currentPath = normalize(parentWin.location.pathname);
            const currentHref = normalize(
              `${parentWin.location.pathname}${parentWin.location.search}`
            );

            const linkStates = links.map((link, index) => ({
              link,
              isHome: index === 0,
              score: getLinkMatchScore(link, currentPath, currentHref, index === 0),
            }));

            const nonHomeMatch = linkStates
              .filter(({ isHome, score }) => !isHome && score > 0)
              .sort((a, b) => b.score - a.score)[0];
            const homeMatch = linkStates
              .filter(({ isHome, score }) => isHome && score > 0)
              .sort((a, b) => b.score - a.score)[0];
            const activeLink = nonHomeMatch?.link || homeMatch?.link || null;

            links.forEach((link) => {
              if (link === activeLink) {
                link.setAttribute("data-glp-active", "true");
                link.setAttribute("aria-current", "page");
              } else {
                link.removeAttribute("data-glp-active");
                link.removeAttribute("aria-current");
              }
            });

            return true;
          };

          const initSidebarActiveState = () => {
            if (!syncSidebarActiveState()) {
              return false;
            }

            const parentWin = window.parent;
            if (parentWin.__glpSidebarActiveCleanup) {
              parentWin.__glpSidebarActiveCleanup();
            }

            const onChange = () => syncSidebarActiveState();
            parentWin.addEventListener("popstate", onChange);
            parentWin.addEventListener("hashchange", onChange);
            parentWin.addEventListener("pageshow", onChange);

            const timer = parentWin.setInterval(onChange, 400);
            parentWin.__glpSidebarActiveCleanup = () => {
              parentWin.clearInterval(timer);
              parentWin.removeEventListener("popstate", onChange);
              parentWin.removeEventListener("hashchange", onChange);
              parentWin.removeEventListener("pageshow", onChange);
            };

            return true;
          };

          if (!initSidebarActiveState()) {
            let attempts = 0;
            const retryTimer = window.setInterval(() => {
              attempts += 1;
              if (initSidebarActiveState() || attempts > 30) {
                window.clearInterval(retryTimer);
              }
            }, 200);
          }
        })();
        </script>
        """,
        width="content",
        unsafe_allow_javascript=True,
    )


def inject_base_style() -> None:
    st.markdown(
        """
        <style>
        :root {
            --glp-sidebar-width: 214px;
            --glp-top-nav-height: 52px;
            --glp-top-nav-title-gap: -50px;
        }

        header[data-testid="stHeader"] {
            background: transparent !important;
            z-index: 10001 !important;
        }

        [data-testid="stHeader"] {
            background: transparent !important;
            z-index: 10001 !important;
        }

        .stAppToolbar,
        [data-testid="stToolbar"],
        [data-testid="stToolbarActions"],
        [data-testid="stMainMenu"],
        [data-testid="stDecoration"] {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
        }

        .stApp {
            background: #dfe7d6;
            color: #111;
        }

        [data-testid="stAppViewContainer"] > .main {
            padding-top: 0 !important;
            margin-top: 0 !important;
        }

        .block-container {
            max-width: 1240px;
            padding-top: calc(var(--glp-top-nav-height) + var(--glp-top-nav-title-gap));
            padding-left: 3rem;
            padding-right: 3rem;
            padding-bottom: 3rem;
        }

        .glp-page-title {
            margin: 0 0 0;
            display: block;
            --glp-title-size: 3rem;
            --glp-title-weight: 700;
            --glp-title-line-height: 1.08;
            --glp-title-color: #000000;
            --glp-subtitle-gap: 0.55rem;
            --glp-subtitle-size: 1.05rem;
            --glp-subtitle-weight: 500;
            --glp-subtitle-line-height: 1.45;
            --glp-subtitle-color: #4d5f3b;
        }

        [data-testid="stSidebar"] {
            border-right: 0 !important;
        }

        [data-testid="stSidebar"][aria-expanded="true"] {
            min-width: var(--glp-sidebar-width) !important;
            max-width: var(--glp-sidebar-width) !important;
        }

        [data-testid="stSidebarResizer"] {
            display: none !important;
            pointer-events: none !important;
        }

        [data-testid="stSidebar"] > div:first-child {
            background: #365f10;
            padding: 0;
        }

        div[data-testid="stSidebarContent"],
        div[data-testid="stSidebarUserContent"] {
            padding-top: 0;
            padding-left: 0;
            padding-right: 0;
        }

        div[data-testid="stSidebarUserContent"] > div:first-child,
        div[data-testid="stSidebarContent"] > div:first-child {
            height: 0 !important;
            min-height: 0 !important;
            margin-bottom: 0 !important;
            padding: 0 !important;
        }

        [data-testid="collapsedControl"],
        button[kind="header"][aria-label*="sidebar"],
        [data-testid="stSidebarCollapseButton"] {
            display: flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            pointer-events: auto !important;
            z-index: 10002 !important;
        }

        [data-testid="stSidebarNav"] {
            display: none !important;
        }

        [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {
            margin: 0;
            border-radius: 0;
            padding: 0.1rem 0.6rem 0.1rem 0.4rem;
            border-left: 3px solid transparent;
            background: transparent;
            transition: background-color 0.2s ease;
            min-height: 2rem;
        }

        [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] p {
            color: #f0f4ec;
            font-size: 0.99rem;
            font-weight: 500;
            line-height: 1.22;
            letter-spacing: 0.01em;
        }

        [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {
            background: rgba(255, 255, 255, 0.08);
        }

        [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][aria-current="page"],
        [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][data-glp-active="true"] {
            background: rgba(255, 255, 255, 0.13);
            border-left-color: #d7e8bf;
        }

        .sidebar-logo-wrap {
            background: #365f10;
            padding: 0.7rem 0.4rem;
            display: flex;
            justify-content: center;
            align-items: center;
        }

        .sidebar-logo-wrap img {
            max-width: 90px;
            height: auto;
        }

        .sidebar-menu-strip {
            height: 30px;
            background: #6a8d34;
            display: flex;
            align-items: center;
            padding-left: 8px;
            margin-bottom: 0.5rem;
        }

        .sidebar-menu-strip img {
            width: 18px;
            height: 18px;
            object-fit: contain;
        }

        .sidebar-status-title {
            margin-top: 0.62rem;
            background: #6a8d34;
            color: #f2f6ee;
            font-size: 1.1rem;
            font-weight: 700;
            padding: 0.4rem 0.36rem;
            line-height: 1;
        }

        .sidebar-status-item {
            display: flex;
            align-items: center;
            background: rgba(38, 73, 11, 0.48);
            color: #eef3e8;
            padding: 0.55rem 0.5rem;
            border-top: 1px solid rgba(255, 255, 255, 0.09);
            font-size: 0.95rem;
            line-height: 1.2;
        }

        .sidebar-status-item .status-icon-img {
            width: 1rem;
            height: 1rem;
            object-fit: contain;
            margin-right: 0.35rem;
            flex-shrink: 0;
        }

        .sidebar-status-item .label {
            margin-right: 0.16rem;
        }

        .sidebar-status-item .value {
            font-weight: 500;
        }

        .glp-top-nav {
            position: fixed !important;
            top: 0 !important;
            left: 0;
            width: 100vw;
            min-height: var(--glp-top-nav-height);
            display: grid;
            grid-template-columns: 148px 1fr 48px;
            align-items: center;
            gap: 0.8rem;
            padding: 0 16px;
            margin: 0;
            box-sizing: border-box;
            background: #b6c59d;
            z-index: 9999;
            box-shadow: 0 4px 14px rgba(30, 50, 20, 0.12);
            border-bottom: none !important;
        }

        .glp-left-controls {
            display: flex;
            align-items: center;
            gap: 0.35rem;
            min-width: 0;
        }

        .glp-nav-toggle,
        .glp-icons a.glp-icon,
        .glp-icons a.glp-icon:hover,
        .glp-icons a.glp-icon:focus,
        .glp-icons a.glp-icon:active,
        .glp-icons a.glp-icon:visited {
            color: #1b1b1b !important;
            text-decoration: none !important;
            border: 0 !important;
            border-bottom: 0 !important;
            box-shadow: none !important;
            outline: none !important;
            background: transparent !important;
            background-image: none !important;
        }

        .glp-nav-toggle {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 34px;
            height: 34px;
            padding: 0;
            cursor: pointer;
        }

        .glp-nav-toggle .glp-nav-toggle-text {
            font-size: 1.1rem;
            line-height: 1;
            font-weight: 700;
            color: rgba(44, 62, 80, 0.6);
        }

        .glp-icons {
            display: flex;
            gap: 0.2rem;
            align-items: center;
            font-size: 1.8rem;
        }

        .glp-icons a.glp-icon-back {
            font-size: 2.2rem;
            line-height: 1;
        }

        .glp-icons a.glp-icon {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 34px;
            text-align: center;
            cursor: pointer !important;
            pointer-events: auto !important;
        }

        .glp-top-nav .glp-icons a.glp-icon::before,
        .glp-top-nav .glp-icons a.glp-icon::after {
            content: none !important;
            border: 0 !important;
            text-decoration: none !important;
        }

        .glp-tabs {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 5rem;
            font-size: 1.25rem;
            min-width: 0;
        }

        .glp-tabs a {
            position: relative;
            display: inline-block;
            color: #121212;
            text-decoration: none;
            font-weight: 500;
            padding-bottom: 1px;
            transition: color 0.18s ease;
            white-space: nowrap;
        }

        .glp-tabs a::after {
            content: "";
            position: absolute;
            left: 0;
            bottom: 0;
            width: 100%;
            height: 3px;
            background: transparent;
            transition: background-color 0.18s ease;
        }

        .glp-tabs a.active,
        .glp-tabs a.active:hover,
        .glp-tabs a.active:focus,
        .glp-tabs a.active:active,
        .glp-tabs a.active:visited {
            color: #4e6e24 !important;
            font-weight: 700 !important;
        }

        .glp-tabs a:hover,
        .glp-tabs a:focus {
            color: #4e6e24 !important;
            font-weight: 700 !important;
        }

        .glp-tabs a,
        .glp-tabs a:hover,
        .glp-tabs a:focus,
        .glp-tabs a:active,
        .glp-tabs a:visited {
            text-decoration: none !important;
        }

        .glp-tabs a.active::after,
        .glp-tabs a:hover::after,
        .glp-tabs a:focus::after {
            background: #4e6e24 !important;
        }

        .glp-right {
            min-width: 0;
        }

        .glp-card {
            background: #cfe0ba;
            border: 1px solid #c4d3b2;
            border-radius: 26px;
            padding: 1.2rem;
            box-shadow: 0 6px 16px rgba(30, 50, 20, 0.14);
        }

        .glp-card-title {
            font-size: 2rem;
            font-weight: 500;
            margin-bottom: 0.7rem;
        }

        .glp-anchor {
            position: relative;
            top: calc(var(--glp-top-nav-height) * -1 - 16px);
            height: 0;
        }

        .glp-bottom-nav {
            margin-top: 1.6rem;
            display: flex;
            justify-content: center;
            gap: 3rem;
            font-size: 1.5rem;
        }

        .glp-bottom-nav a {
            color: #111;
            text-decoration: none;
            border-bottom: 1px solid #333;
            padding: 0 1.2rem 0.2rem;
        }

        .stButton > button,
        .stDownloadButton > button {
            border-radius: 10px;
            height: 3rem;
            font-size: 1.55rem;
            border: 0;
            box-shadow: 0 3px 8px rgba(0, 0, 0, 0.16);
        }

        .stButton > button[kind="primary"] {
            background: #2cb46d;
            color: #fff;
        }

        @media (max-width: 1280px) {
            .glp-tabs {
                gap: 2rem;
                font-size: 1.08rem;
            }
        }

            @media (max-width: 960px) {
            .block-container {
                padding-left: 1.25rem;
                padding-right: 1.25rem;
            }

            .glp-page-title {
                margin-top: 0;
                --glp-title-size: 2.55rem;
            }

            .glp-top-nav {
                grid-template-columns: 132px 1fr 16px;
                padding: 0 10px;
            }

            .glp-tabs {
                justify-content: flex-start;
                gap: 1rem;
                overflow-x: auto;
                scrollbar-width: none;
            }

            .glp-tabs::-webkit-scrollbar {
                display: none;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_top_nav(
    tabs: list[tuple[str, str]], active_idx: int, home_href: str = "/"
) -> None:
    tab_html = []
    for idx, (label, anchor_name) in enumerate(tabs):
        cls = "active" if idx == active_idx else ""
        tab_html.append(
            f'<a class="{cls}" data-anchor="{anchor_name}" href="#{anchor_name}">{label}</a>'
        )
    st.markdown(
        f"""
        <div class="glp-top-nav">
          <div class="glp-left-controls">
            <button type="button" class="glp-nav-toggle" aria-label="切换左侧边栏">
              <span class="glp-nav-toggle-text" translate="no">&lt;&lt;</span>
            </button>
            <div class="glp-icons">
              <a class="glp-icon glp-icon-back" href="{home_href}" target="_top">&#9664;</a>
              <a class="glp-icon glp-icon-refresh" href="#">&#10227;</a>
            </div>
          </div>
          <div class="glp-tabs">
            {''.join(tab_html)}
          </div>
          <div class="glp-right"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.html(
        """
        <script>
        (() => {
          const initNav = () => {
            const parentDoc = window.parent.document;
            const parentWin = parentDoc.defaultView;
            const navs = Array.from(parentDoc.querySelectorAll('.glp-top-nav'));
            const nav = navs[navs.length - 1] || null;
            if (!nav) return false;

            navs.slice(0, -1).forEach((node) => node.remove());

            const toggleButton = nav.querySelector('.glp-nav-toggle');
            const toggleIcon = toggleButton?.querySelector('.glp-nav-toggle-text');
            const refreshIcon = nav.querySelector('.glp-icon-refresh');
            const links = Array.from(nav.querySelectorAll('.glp-tabs a[data-anchor]'));
            const defaultActiveLink = links.find((link) => link.classList.contains('active')) || links[0] || null;
            const sections = links
              .map((link) => {
                const anchorId = link.getAttribute('data-anchor');
                return [link, parentDoc.getElementById(anchorId)];
              })
              .filter(([, section]) => section);

            const getSidebar = () => parentDoc.querySelector('[data-testid="stSidebar"]');

            const sidebarExpanded = () => {
              const sidebar = getSidebar();
              if (!sidebar) {
                return false;
              }
              const expanded = sidebar.getAttribute('aria-expanded');
              if (expanded === 'false') {
                return false;
              }
              if (expanded === 'true') {
                return true;
              }
              return sidebar.getBoundingClientRect().width >= 160;
            };

            const getSidebarToggleControl = () => {
              const candidates = [
                parentDoc.querySelector('[data-testid="collapsedControl"]'),
                parentDoc.querySelector('[data-testid="stSidebarCollapseButton"]'),
                parentDoc.querySelector('button[kind="header"][aria-label*="sidebar"]'),
                parentDoc.querySelector('button[aria-label*="sidebar"]'),
              ];
              return candidates.find((candidate) => candidate && typeof candidate.click === 'function') || null;
            };

            const triggerNativeSidebarToggle = () => {
              const nativeToggle = getSidebarToggleControl();
              if (!nativeToggle) {
                return false;
              }
              nativeToggle.click();
              return true;
            };

            const pinNav = () => {
              nav.style.position = 'fixed';
              nav.style.top = '0px';
              nav.style.zIndex = '9999';

              const sidebar = getSidebar();
              const sidebarWidth = sidebar
                ? Math.max(sidebar.getBoundingClientRect().width, 0)
                : 0;
              const navLeft = sidebarWidth;
              const navWidth = Math.max(parentWin.innerWidth - navLeft, 320);

              nav.style.left = `${navLeft}px`;
              nav.style.width = `${navWidth}px`;
              nav.style.transform = 'none';

              const mainBlock =
                parentDoc.querySelector('.main .block-container') ||
                parentDoc.querySelector('.block-container');
              if (mainBlock) {
                const rootStyle = parentWin.getComputedStyle(parentDoc.documentElement);
                const gapValue = parseFloat(rootStyle.getPropertyValue('--glp-top-nav-title-gap')) || 0;
                const topSpace = (nav.offsetHeight || 52) + gapValue;
                mainBlock.style.paddingTop = `${topSpace}px`;
                mainBlock.style.scrollPaddingTop = `${topSpace}px`;
              }
            };

            const clearIconUnderline = () => {
              nav.querySelectorAll('.glp-icons a.glp-icon').forEach((icon) => {
                icon.style.textDecoration = 'none';
                icon.style.borderBottom = 'none';
                icon.style.boxShadow = 'none';
                icon.style.backgroundImage = 'none';
                icon.style.outline = 'none';
                icon.classList.remove('active');
              });
            };

            const setToggleIcon = () => {
              if (!toggleIcon) return;
              toggleIcon.textContent = sidebarExpanded() ? '<<' : '>>';
            };

            const setActive = (activeLink) => {
              links.forEach((link) => link.classList.toggle('active', link === activeLink));
            };

            const scrollToSection = (section) => {
              if (!section) return;
              section.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
              });

              const anchorId = section.id;
              if (anchorId) {
                parentWin.history.replaceState(null, '', `#${anchorId}`);
              }
            };

            const syncNavState = () => {
              pinNav();
              clearIconUnderline();
              setToggleIcon();

              if (!sections.length) {
                setActive(null);
                return;
              }

              const navHeight = nav.offsetHeight || 56;
              const focusLine = navHeight + 28;
              let current = null;

              for (const [link, section] of sections) {
                const rect = section.getBoundingClientRect();
                if (rect.top <= focusLine && rect.bottom > focusLine) {
                  current = link;
                  break;
                }
              }

              if (!current) {
                const firstRect = sections[0][1].getBoundingClientRect();
                current = firstRect.top > focusLine ? defaultActiveLink : sections[sections.length - 1][0];
              }

              setActive(current);
            };

            if (parentWin.__glpTopNavController) {
              parentWin.__glpTopNavController.abort();
            }
            const controller = new AbortController();
            const { signal } = controller;
            parentWin.__glpTopNavController = controller;

            links.forEach((link, index) => {
              link.addEventListener('click', (event) => {
                event.preventDefault();
                const anchorId = link.getAttribute('data-anchor');
                const section = anchorId ? parentDoc.getElementById(anchorId) : null;
                setActive(link);
                scrollToSection(section);
              }, { signal });

              link.addEventListener('mouseenter', () => {
                setActive(link);
              }, { signal });

              link.addEventListener('mouseleave', () => {
                syncNavState();
              }, { signal });
            });

            if (toggleButton) {
              toggleButton.addEventListener('click', (event) => {
                event.preventDefault();
                event.stopPropagation();
                if (!triggerNativeSidebarToggle()) {
                  return;
                }
                window.setTimeout(syncNavState, 0);
                window.setTimeout(syncNavState, 120);
                window.setTimeout(syncNavState, 260);
              }, { signal });
            }

            if (refreshIcon) {
              refreshIcon.addEventListener('click', (event) => {
                event.preventDefault();
                parentWin.location.reload();
              }, { signal });
            }

            parentWin.addEventListener('scroll', syncNavState, { passive: true, signal });
            parentWin.addEventListener('resize', syncNavState, { passive: true, signal });

            const sidebar = getSidebar();
            if (sidebar && typeof MutationObserver !== 'undefined') {
              const observer = new MutationObserver(() => syncNavState());
              observer.observe(sidebar, {
                attributes: true,
                attributeFilter: ['aria-expanded', 'style', 'class'],
              });
              signal.addEventListener('abort', () => observer.disconnect(), { once: true });
            }

            syncNavState();
            return true;
          };

          if (!initNav()) {
            let attempts = 0;
            const timer = window.setInterval(() => {
              attempts += 1;
              if (initNav() || attempts > 40) {
                window.clearInterval(timer);
              }
            }, 150);
          }
        })();
        </script>
        """,
        width="content",
        unsafe_allow_javascript=True,
    )


def render_title(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="glp-page-title">
          <div class="glp-page-title-main" style="font-size:var(--glp-title-size, 3.4rem);font-weight:var(--glp-title-weight, 700);line-height:var(--glp-title-line-height, 1.08);margin:0;color:var(--glp-title-color, #1f2d16);">{title}</div>
          <div class="glp-page-title-sub" style="display:block;margin-top:var(--glp-subtitle-gap, 0.55rem);font-size:var(--glp-subtitle-size, 1.4rem);font-weight:var(--glp-subtitle-weight, 500);line-height:var(--glp-subtitle-line-height, 1.45);color:var(--glp-subtitle-color, #4d5f3b);">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def anchor(name: str) -> None:
    st.markdown(f'<div id="{name}" class="glp-anchor"></div>', unsafe_allow_html=True)

def render_prev_next(prev_href: str, next_href: str) -> None:
    st.markdown(
        f"""
        <div class="glp-bottom-nav">
          <a href="{prev_href}">上一步</a>
          <a href="{next_href}">下一步</a>
        </div>
        """,
        unsafe_allow_html=True,
    )
