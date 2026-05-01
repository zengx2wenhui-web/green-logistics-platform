from __future__ import annotations

import folium
import pandas as pd

from utils.file_reader import normalize_name
from utils.route_display import (
    get_ordered_route_names,
    get_ordered_route_nodes,
    get_ordered_route_segments,
    is_warehouse_depot_segment,
)

POWER_TYPE_MAPPING = {
    "diesel": "柴油重卡",
    "lng": "LNG天然气重卡",
    "hev": "混合动力 (HEV)",
    "phev": "插电混动 (PHEV)",
    "bev": "纯电动 (BEV)",
    "fcev": "氢燃料电池 (FCEV)",
    "mixed": "混合车队",
}

ROUTE_COLORS = ["#D94841", "#2F6BFF", "#2E9D52", "#8A46D8", "#F08C2B", "#D6336C", "#0F766E", "#2B8A3E"]
COST_MODEL_DISPLAY_MAP = {
    "fixed cold-start carbon + proxy arc carbon cost (grams CO2 integer)": "固定冷启动碳排 + 代理弧段碳成本（整数克 CO2）",
    "fixed cold-start carbon + proxy arc carbon cost (grams CO2 integer) within per-depot OR-Tools decomposition": "固定冷启动碳排 + 代理弧段碳成本（按中转仓拆分的 OR-Tools 求解）",
}


def get_total_demand_value(demand_data: object) -> float:
    if isinstance(demand_data, dict):
        if "总需求量" in demand_data:
            return float(demand_data.get("总需求量", 0) or 0)
        return float(sum(value for value in demand_data.values() if isinstance(value, (int, float))))
    try:
        return float(demand_data or 0)
    except (TypeError, ValueError):
        return 0.0


def get_vehicle_type_id(route_result: dict) -> str:
    vehicle_type_id = str(route_result.get("vehicle_type_id", "") or "").strip()
    if vehicle_type_id:
        return vehicle_type_id
    return str(route_result.get("vehicle_type", "") or "unknown").strip().lower()


def get_vehicle_display_name(vehicle_type_id: str, fallback: str = "未知") -> str:
    return POWER_TYPE_MAPPING.get(vehicle_type_id, fallback if fallback else vehicle_type_id)


def get_route_vehicle_display_name(route_result: dict, default_name: str | None = None) -> str:
    vehicle_name = str(route_result.get("vehicle_type") or "").strip()
    if vehicle_name:
        return vehicle_name
    vehicle_type_id = get_vehicle_type_id(route_result)
    if vehicle_type_id:
        return get_vehicle_display_name(vehicle_type_id, vehicle_type_id)
    return default_name or "未知"


def add_route_map_legend(map_chart: folium.Map) -> None:
    legend_html = """
        <div style="position: fixed; bottom: 20px; left: 20px; z-index: 1000;
        background: rgba(255, 255, 255, 0.94); padding: 8px 12px; border-radius: 6px;
        border: 1px solid #ccc; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        min-width: 160px; font-family: sans-serif;">
            <div style="margin-bottom: 8px; font-size: 13px; font-weight: bold; color: #000; border-bottom: 1px solid #eee; padding-bottom: 4px;">路线图例</div>
            <div style="display: flex; align-items: center; gap: 8px; margin: 4px 0; min-height: 20px;">
                <span style="width: 24px; min-width: 24px; height: 16px; display: inline-flex; align-items: center; justify-content: center; line-height: 0; flex: 0 0 24px;">
                    <svg style="width: 14px; height: 14px; display: block; filter: drop-shadow(0px 1px 2px rgba(0,0,0,0.4));" viewBox="0 0 24 24">
                        <path fill="#e11d48" d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
                    </svg>
                </span>
                <span style="font-size: 12px; line-height: 1.2; color: #333;">总仓节点</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; margin: 4px 0; min-height: 20px;">
                <span style="width: 24px; min-width: 24px; height: 16px; display: inline-flex; align-items: center; justify-content: center; line-height: 0; flex: 0 0 24px;">
                    <svg style="width: 13px; height: 13px; display: block;" viewBox="0 0 24 24">
                        <path fill="#ef4444" d="M12 3L2 12h3v8h14v-8h3L12 3z"/>
                    </svg>
                </span>
                <span style="font-size: 12px; line-height: 1.2; color: #333;">中转仓节点</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; margin: 4px 0; min-height: 20px;">
                <span style="width: 24px; min-width: 24px; height: 16px; display: inline-flex; align-items: center; justify-content: center; line-height: 0; flex: 0 0 24px;">
                    <span style="width: 10px; height: 10px; background: #ef4444; border-radius: 50%; display: block;"></span>
                </span>
                <span style="font-size: 12px; line-height: 1.2; color: #333;">场馆节点</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; margin: 4px 0; min-height: 20px;">
                <span style="width: 24px; min-width: 24px; height: 16px; display: inline-flex; align-items: center; justify-content: center; line-height: 0; flex: 0 0 24px;">
                    <span style="width: 24px; height: 0; border-top: 2.5px solid #000; display: block;"></span>
                </span>
                <span style="font-size: 12px; line-height: 1.2; color: #333;">配送主路线段</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; margin: 4px 0; min-height: 20px;">
                <span style="width: 24px; min-width: 24px; height: 16px; display: inline-flex; align-items: center; justify-content: center; line-height: 0; flex: 0 0 24px;">
                    <span style="width: 24px; height: 0; border-top: 2px dashed #000; display: block;"></span>
                </span>
                <span style="font-size: 12px; line-height: 1.2; color: #333;">总仓与中转仓补给段</span>
            </div>
        </div>
    """
    map_chart.get_root().html.add_child(folium.Element(legend_html))


def build_route_overview_dataframe(route_results: list[dict], route_context: dict) -> pd.DataFrame:
    rows = []
    for index, route_result in enumerate(route_results, start=1):
        distance_km = float(route_result.get("total_distance_km", 0) or 0)
        load_kg = float(route_result.get("total_load_kg", 0) or 0)
        carbon_kg = float(route_result.get("total_carbon_kg", 0) or 0)
        capacity_kg = float(route_result.get("vehicle_capacity_kg", 0) or 0)
        route_names = get_ordered_route_names(route_result, route_context)
        rows.append(
            {
                "路线编号": f"路线{index}",
                "车辆": route_result.get("vehicle_name", f"车辆{index}"),
                "车型": get_route_vehicle_display_name(route_result),
                "路线": " -> ".join(route_names),
                "场馆数": len(route_result.get("visited_venue_names", route_result.get("visits", []))),
                "装载(kg)": round(load_kg, 2),
                "装载率(%)": round(load_kg / capacity_kg * 100, 1) if capacity_kg > 0 else None,
                "总距离(km)": round(distance_km, 2),
                "总碳排放(kg CO2)": round(carbon_kg, 2),
                "碳排效率(kg/km)": round(carbon_kg / distance_km, 4) if distance_km > 0 else 0.0,
                "碳排强度(g/kg)": round(carbon_kg * 1000 / load_kg, 2) if load_kg > 0 else 0.0,
            }
        )
    return pd.DataFrame(rows)


def build_route_dispatch_dataframe(route_results: list[dict], route_context: dict) -> pd.DataFrame:
    rows = []
    for index, route_result in enumerate(route_results, start=1):
        rows.append(
            {
                "路线编号": f"路线{index}",
                "车辆": route_result.get("vehicle_name", f"车辆{index}"),
                "车型": get_route_vehicle_display_name(route_result),
                "路线": " -> ".join(get_ordered_route_names(route_result, route_context)),
                "场馆数": len(route_result.get("visited_venue_names", route_result.get("visits", []))),
                "总装载(kg)": round(float(route_result.get("total_load_kg", 0) or 0), 2),
                "总距离(km)": round(float(route_result.get("total_distance_km", 0) or 0), 2),
                "总碳排放(kg CO2)": round(float(route_result.get("total_carbon_kg", 0) or 0), 2),
            }
        )
    return pd.DataFrame(rows)


def build_fleet_summary_dataframe(
    summary_rows: list[dict],
    *,
    count_label: str = "车辆数(辆)",
) -> pd.DataFrame:
    rows = []
    for item in summary_rows or []:
        vehicle_count = int(item.get("vehicle_count", 0) or 0)
        vehicle_capacity_ton = float(item.get("vehicle_capacity_ton", 0) or 0)
        total_capacity_ton = float(item.get("total_capacity_ton", vehicle_capacity_ton * vehicle_count) or 0)
        if vehicle_count <= 0:
            continue

        rows.append(
            {
                "车型": str(item.get("vehicle_display_name", "") or item.get("vehicle_type_id", "") or "未知"),
                "单车载重(吨/辆)": round(vehicle_capacity_ton, 2),
                count_label: vehicle_count,
                "总运力(吨)": round(total_capacity_ton, 2),
            }
        )

    return pd.DataFrame(rows)


def build_fleet_composition_dataframe(
    configured_rows: list[dict],
    used_rows: list[dict],
    *,
    configured_count_label: str = "车队配置(辆)",
    used_count_label: str = "实际用车(辆)",
) -> pd.DataFrame:
    rows_by_key: dict[tuple[str, str, float], dict[str, object]] = {}
    ordered_keys: list[tuple[str, str, float]] = []

    def _fleet_key(item: dict) -> tuple[str, str, float]:
        vehicle_display_name = str(item.get("vehicle_display_name", "") or item.get("vehicle_type_id", "") or "未知")
        vehicle_type_id = str(item.get("vehicle_type_id", "") or vehicle_display_name).strip()
        vehicle_capacity_ton = round(float(item.get("vehicle_capacity_ton", 0) or 0), 2)
        return (vehicle_type_id, vehicle_display_name, vehicle_capacity_ton)

    def _ensure_row(item: dict) -> dict[str, object]:
        key = _fleet_key(item)
        if key not in rows_by_key:
            ordered_keys.append(key)
            rows_by_key[key] = {
                "车型": key[1],
                "单车载重(吨/辆)": key[2],
                configured_count_label: 0,
                used_count_label: 0,
                "总运力(吨)": 0.0,
            }
        return rows_by_key[key]

    for item in configured_rows or []:
        vehicle_count = int(item.get("vehicle_count", 0) or 0)
        if vehicle_count <= 0:
            continue
        row = _ensure_row(item)
        vehicle_capacity_ton = float(item.get("vehicle_capacity_ton", 0) or 0)
        total_capacity_ton = float(item.get("total_capacity_ton", vehicle_capacity_ton * vehicle_count) or 0)
        row[configured_count_label] = vehicle_count
        row["总运力(吨)"] = round(total_capacity_ton, 2)

    for item in used_rows or []:
        vehicle_count = int(item.get("vehicle_count", 0) or 0)
        if vehicle_count <= 0:
            continue
        row = _ensure_row(item)
        vehicle_capacity_ton = float(item.get("vehicle_capacity_ton", 0) or 0)
        total_capacity_ton = float(item.get("total_capacity_ton", vehicle_capacity_ton * vehicle_count) or 0)
        row[used_count_label] = vehicle_count
        if not row["总运力(吨)"]:
            row["总运力(吨)"] = round(total_capacity_ton, 2)

    return pd.DataFrame([rows_by_key[key] for key in ordered_keys])


def build_route_segment_rows(route_result: dict, route_context: dict) -> list[dict]:
    rows: list[dict] = []
    segments = route_result.get("segments", []) or []
    segment_labels = route_result.get("segment_labels", []) or []
    route_names = get_ordered_route_names(route_result, route_context)
    if not segments:
        return rows

    for seg_idx, segment in enumerate(segments):
        if seg_idx < len(segment_labels):
            segment_name = str(segment_labels[seg_idx])
        elif seg_idx + 1 < len(route_names):
            segment_name = f"{route_names[seg_idx]} -> {route_names[seg_idx + 1]}"
        else:
            segment_name = f"分段 {seg_idx + 1}"

        rows.append(
            {
                "序号": seg_idx + 1,
                "分段": segment_name,
                "距离(km)": round(float(segment.get("distance_km", 0) or 0), 2),
                "装载(吨)": round(float(segment.get("load_kg", 0) or 0) / 1000.0, 3),
                "碳排放(kg CO2)": round(float(segment.get("carbon_kg", 0) or 0), 4),
            }
        )
    return rows


def _is_blank_display_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _get_depot_display_value(depot: dict, *keys: str) -> object:
    for key in keys:
        value = depot.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def get_depot_display_name(depot: dict, depot_index: int | None = None) -> str:
    name = _get_depot_display_value(
        depot,
        "仓库名称",
        "nearest_candidate_name",
        "中转仓名称",
        "warehouse_name",
        "中转仓编号",
    )
    if name is not None:
        return str(name)
    if depot_index is None:
        return "中转仓"
    return f"中转仓{depot_index}"


def _format_depot_cost_model(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return COST_MODEL_DISPLAY_MAP.get(text, text)


def build_depot_results_dataframe(depot_results_list: list[dict]) -> pd.DataFrame:
    if not depot_results_list:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    ordered_columns = [
        "中转仓名称",
        "省",
        "市",
        "经度",
        "纬度",
        "服务场馆数",
        "服务场馆列表",
        "物资总量(kg)",
        "平均距离(km)",
        "干线距离(km)",
        "干线碳排(kg CO2)",
        "干线趟次",
        "配送路线数",
        "分配车辆数",
        "已用车队",
        "剩余车队",
    ]

    for depot_index, depot in enumerate(depot_results_list, start=1):
        average_distance = _get_depot_display_value(depot, "平均距离(km)")
        if isinstance(average_distance, str) and average_distance.strip().upper() == "N/A":
            average_distance = "暂无"

        rows.append(
            {
                "中转仓名称": get_depot_display_name(depot, depot_index),
                "省": _get_depot_display_value(depot, "省", "province"),
                "市": _get_depot_display_value(depot, "市", "city"),
                "经度": _get_depot_display_value(depot, "经度", "lng"),
                "纬度": _get_depot_display_value(depot, "纬度", "lat"),
                "服务场馆数": _get_depot_display_value(depot, "服务场馆数"),
                "服务场馆列表": _get_depot_display_value(depot, "服务场馆列表"),
                "物资总量(kg)": _get_depot_display_value(depot, "物资总量(kg)", "weight"),
                "平均距离(km)": average_distance,
                "干线距离(km)": _get_depot_display_value(depot, "干线距离(km)", "trunk_distance_km"),
                "干线碳排(kg CO2)": _get_depot_display_value(depot, "干线碳排(kg CO2)", "trunk_carbon_kg"),
                "干线趟次": _get_depot_display_value(depot, "干线趟次", "trunk_trip_count"),
                "配送路线数": _get_depot_display_value(depot, "配送路线数", "route_count"),
                "分配车辆数": _get_depot_display_value(depot, "分配车辆数", "allocated_vehicle_count"),
                "已用车队": _get_depot_display_value(depot, "已用车队", "fleet_used_summary_text"),
                "剩余车队": _get_depot_display_value(depot, "剩余车队", "remaining_fleet_summary_text"),
            }
        )

    dataframe = pd.DataFrame(rows)
    visible_columns = []
    for column in ordered_columns:
        if column not in dataframe.columns:
            continue
        if dataframe[column].apply(_is_blank_display_value).all():
            continue
        visible_columns.append(column)

    return dataframe[visible_columns]


def build_route_map(
    nodes: list[dict],
    route_results: list[dict],
    depot_results: list[dict],
    demands_dict: dict,
    route_context: dict,
) -> folium.Map | None:
    if not nodes:
        return None

    center_lat = sum(float(node.get("lat", 0) or 0) for node in nodes) / len(nodes)
    center_lng = sum(float(node.get("lng", 0) or 0) for node in nodes) / len(nodes)
    map_chart = folium.Map(location=[center_lat, center_lng], zoom_start=12)
    node_route_colors: dict[str, str] = {}

    for route_index, route_result in enumerate(route_results):
        route_color = ROUTE_COLORS[route_index % len(ROUTE_COLORS)]
        route_nodes = get_ordered_route_nodes(route_result, route_context)
        route_segments = get_ordered_route_segments(route_result, route_context)
        segment_metrics = route_result.get("segments", []) or []

        for route_node in route_nodes:
            if route_node.get("node_type") == "venue" and route_node.get("name"):
                node_route_colors[normalize_name(route_node["name"])] = route_color

        if not route_segments:
            continue

        route_name = route_result.get("vehicle_name", f"派车 {route_index + 1}")
        route_text = " -> ".join(get_ordered_route_names(route_result, route_context))
        vehicle_name = get_route_vehicle_display_name(route_result)
        for segment_index, segment in enumerate(route_segments, start=1):
            from_node = segment["from_node"]
            to_node = segment["to_node"]
            is_trunk_segment = is_warehouse_depot_segment(from_node, to_node)
            metric_row = segment_metrics[segment_index - 1] if segment_index - 1 < len(segment_metrics) else {}
            distance_km = float(metric_row.get("distance_km", 0) or 0)
            carbon_kg = float(metric_row.get("carbon_kg", 0) or 0)
            load_tons = float(metric_row.get("load_kg", 0) or 0) / 1000.0

            folium.PolyLine(
                segment["coords"],
                color="#6B7280" if is_trunk_segment else route_color,
                weight=3 if is_trunk_segment else 4,
                opacity=0.75 if is_trunk_segment else 0.85,
                dash_array="8,8" if is_trunk_segment else None,
                popup=(
                    f"{route_name} ({vehicle_name})<br>"
                    f"路线：{route_text}<br>"
                    f"分段：{from_node['name']} -> {to_node['name']}<br>"
                    f"距离：{distance_km:.2f} km<br>"
                    f"载重：{load_tons:.2f} 吨<br>"
                    f"分段碳排：{carbon_kg:.2f} kg CO2"
                ),
            ).add_to(map_chart)

    warehouse_node = nodes[0]
    folium.Marker(
        [warehouse_node["lat"], warehouse_node["lng"]],
        popup=f"<b>总仓</b><br>{warehouse_node['name']}<br>{warehouse_node.get('address', '')}",
        tooltip="总仓",
        icon=folium.Icon(color="darkred", icon="star"),
    ).add_to(map_chart)

    for depot_index, depot in enumerate(depot_results, start=1):
        depot_lat = depot.get("纬度", depot.get("çº¬åº¦", 0))
        depot_lng = depot.get("经度", depot.get("ç»åº¦", 0))
        if depot_lat is None or depot_lng is None:
            continue
        depot_name = get_depot_display_name(depot, depot_index)
        folium.Marker(
            [depot_lat, depot_lng],
            popup=folium.Popup(f"<b>{depot_name}</b>", max_width=360),
            tooltip=depot_name,
            icon=folium.Icon(color="red", icon="home", prefix="fa"),
        ).add_to(map_chart)

    for node in nodes[1:]:
        demand_value = get_total_demand_value(demands_dict.get(node["name"], 0))
        marker_color = node_route_colors.get(normalize_name(node["name"]), "#2F6BFF")
        folium.CircleMarker(
            [node["lat"], node["lng"]],
            radius=8,
            popup=f"<b>{node['name']}</b><br>总需求：{demand_value:.1f} kg",
            tooltip=f"{node['name']} ({demand_value:.1f} kg)",
            color=marker_color,
            weight=2,
            fill=True,
            fill_color=marker_color,
            fill_opacity=0.95,
        ).add_to(map_chart)

    add_route_map_legend(map_chart)
    return map_chart
