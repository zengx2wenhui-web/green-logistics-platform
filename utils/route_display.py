# 路由显示工具
from __future__ import annotations
from typing import Any
from utils.file_reader import normalize_name


EXPLICIT_ROUTE_NODE_KEYS = (
    "route_nodes",
    "ordered_route_nodes",
    "full_route_nodes",
    "display_route_nodes",
    "full_path_nodes",
    "path_nodes",
    "route_sequence_nodes",
)


# 获取第一个非空值
def _first_non_empty(*values: object) -> object:
    for value in values:
        if value not in (None, ""):
            return value
    return None


# 将任意值转换为 float，失败时返回 None
def _to_float(value: object) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


# 将原始节点类型值规范化为 warehouse/depot/venue 等标准类型
def _normalize_node_type(raw_type: object) -> str:
    value = str(raw_type or "").strip().lower()
    if value in {"warehouse", "main_warehouse", "总仓", "总仓库"}:
        return "warehouse"
    if value in {"depot", "hub", "transfer", "transit", "中转仓", "中转站"}:
        return "depot"
    if value in {"venue", "stadium", "site", "场馆", "配送点"}:
        return "venue"
    return value


# 从路由上下文中查找节点信息，优先级：仓库 > 中转仓 > 位置
def _lookup_node(route_context: dict[str, Any] | None, name: str) -> dict[str, Any]:
    if not route_context or not name:
        return {}

    normalized = normalize_name(name)
    warehouse_node = route_context.get("warehouse_node")
    if warehouse_node and normalize_name(warehouse_node.get("name", "")) == normalized:
        return dict(warehouse_node)

    depot_lookup = route_context.get("depot_lookup", {})
    if normalized in depot_lookup:
        return dict(depot_lookup[normalized])

    location_lookup = route_context.get("location_lookup", {})
    if normalized in location_lookup:
        return dict(location_lookup[normalized])

    return {}


# 将输入的节点信息规范化为包含 name/node_type/lat/lng/address 的字典
def _normalize_route_node(
    node_like: object,
    *,
    fallback_type: str,
    route_context: dict[str, Any] | None = None,
    fallback_lat: float | None = None,
    fallback_lng: float | None = None,
) -> dict[str, Any]:
    if isinstance(node_like, dict):
        name = str(
            _first_non_empty(
                node_like.get("name"),
                node_like.get("node_name"),
                node_like.get("label"),
                node_like.get("节点名称"),
                node_like.get("节点"),
            )
            or ""
        ).strip()
        base = _lookup_node(route_context, name)

        node_type = _normalize_node_type(
            _first_non_empty(
                node_like.get("node_type"),
                node_like.get("type"),
                node_like.get("kind"),
                node_like.get("节点类型"),
            )
        )
        if not node_type:
            if node_like.get("is_warehouse"):
                node_type = "warehouse"
            elif node_like.get("is_depot") or node_like.get("is_hub"):
                node_type = "depot"
            else:
                node_type = str(base.get("node_type") or fallback_type)

        lat = _to_float(
            _first_non_empty(
                node_like.get("lat"),
                node_like.get("latitude"),
                node_like.get("纬度"),
            )
        )
        lng = _to_float(
            _first_non_empty(
                node_like.get("lng"),
                node_like.get("lon"),
                node_like.get("longitude"),
                node_like.get("经度"),
            )
        )
        address = str(
            _first_non_empty(
                node_like.get("address"),
                node_like.get("地址"),
            )
            or base.get("address")
            or ""
        ).strip()
        base_lat = _to_float(base.get("lat")) if base else None
        base_lng = _to_float(base.get("lng")) if base else None

        return {
            "name": name or str(base.get("name") or ""),
            "node_type": node_type,
            "lat": lat if lat is not None else base_lat if base_lat is not None else fallback_lat,
            "lng": lng if lng is not None else base_lng if base_lng is not None else fallback_lng,
            "address": address,
        }

    name = str(node_like or "").strip()
    base = _lookup_node(route_context, name)
    return {
        "name": name or str(base.get("name") or ""),
        "node_type": str(base.get("node_type") or fallback_type),
        "lat": _to_float(base.get("lat")) if base else fallback_lat,
        "lng": _to_float(base.get("lng")) if base else fallback_lng,
        "address": str(base.get("address") or ""),
    }


def _build_depot_node(depot: dict, index: int) -> dict[str, Any]:
    return _normalize_route_node(
        {
            "name": depot.get("仓库名称") or depot.get("中转仓编号") or f"中转仓{index}",
            "node_type": "depot",
            "lat": depot.get("纬度"),
            "lng": depot.get("经度"),
            "address": depot.get("建议地址") or f"{depot.get('省', '')}{depot.get('市', '')}".strip(),
        },
        fallback_type="depot",
    )


def build_route_context(nodes: list[dict], depot_results_list: list[dict]) -> dict[str, Any]:
    warehouse_node: dict[str, Any] | None = None
    location_lookup: dict[str, dict[str, Any]] = {}
    depot_lookup: dict[str, dict[str, Any]] = {}

    for index, node in enumerate(nodes or []):
        normalized_node = _normalize_route_node(
            node,
            fallback_type="warehouse" if index == 0 or node.get("is_warehouse") else "venue",
        )
        if not normalized_node.get("name"):
            continue

        location_lookup[normalize_name(normalized_node["name"])] = normalized_node
        if normalized_node.get("node_type") == "warehouse" and warehouse_node is None:
            warehouse_node = normalized_node

    for index, depot in enumerate(depot_results_list or [], start=1):
        depot_node = _build_depot_node(depot, index)
        if not depot_node.get("name"):
            continue
        depot_lookup[normalize_name(depot_node["name"])] = depot_node

    if warehouse_node is None and nodes:
        warehouse_node = _normalize_route_node(nodes[0], fallback_type="warehouse")

    return {
        "warehouse_node": warehouse_node,
        "location_lookup": location_lookup,
        "depot_lookup": depot_lookup,
    }

# 从路由结果中提取明确的节点列表，优先使用 explicit_route_node_keys 定义的字段，如果没有则尝试从 route_path_names 和 route_coords 中构建节点列表
def _extract_explicit_route_nodes(route_result: dict, route_context: dict[str, Any]) -> list[dict[str, Any]]:
    for key in EXPLICIT_ROUTE_NODE_KEYS:
        route_nodes = route_result.get(key)
        if not isinstance(route_nodes, list) or not route_nodes:
            continue

        normalized_nodes = [
            _normalize_route_node(node, fallback_type="venue", route_context=route_context)
            for node in route_nodes
        ]
        normalized_nodes = [node for node in normalized_nodes if node.get("name")]
        if len(normalized_nodes) > 1:
            return normalized_nodes

    path_names = route_result.get("route_path_names")
    if not isinstance(path_names, list) or len(path_names) < 2:
        return []

    warehouse_node = route_context.get("warehouse_node") or {}
    warehouse_name = str(warehouse_node.get("name") or "").strip()
    route_scope = str(route_result.get("route_scope") or "").strip().lower()
    has_depot = bool(str(route_result.get("depot_name") or "").strip())
    normalized_path_names = [str(item or "").strip() for item in path_names if str(item or "").strip()]
    if len(normalized_path_names) < 2:
        return []

    is_full_loop = bool(
        warehouse_name
        and normalize_name(normalized_path_names[0]) == normalize_name(warehouse_name)
        and normalize_name(normalized_path_names[-1]) == normalize_name(warehouse_name)
    )
    if route_scope in {"terminal", "multi_depot", "multi_depot_full"} and has_depot and not is_full_loop:
        return []

    route_coords = route_result.get("route_coords")
    if isinstance(route_coords, list) and len(route_coords) == len(normalized_path_names):
        normalized_nodes: list[dict[str, Any]] = []
        for name, coord in zip(normalized_path_names, route_coords):
            lat = None
            lng = None
            if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                lat = _to_float(coord[0])
                lng = _to_float(coord[1])
            normalized_nodes.append(
                _normalize_route_node(
                    {"name": name},
                    fallback_type="venue",
                    route_context=route_context,
                    fallback_lat=lat,
                    fallback_lng=lng,
                )
            )
        return [node for node in normalized_nodes if node.get("name")]

    if is_full_loop:
        normalized_nodes = [
            _normalize_route_node(name, fallback_type="venue", route_context=route_context)
            for name in normalized_path_names
        ]
        return [node for node in normalized_nodes if node.get("name")]

    return []


# 获取有序的路由节点列表，优先使用明确的节点列表字段，如果没有则尝试从路径名称和坐标构建节点列表，最后根据仓库和中转仓信息推断节点列表
def get_ordered_route_nodes(route_result: dict, route_context: dict[str, Any]) -> list[dict[str, Any]]:
    explicit_nodes = _extract_explicit_route_nodes(route_result, route_context)
    if explicit_nodes:
        return explicit_nodes

    warehouse_node = route_context.get("warehouse_node")
    depot_name = str(route_result.get("depot_name") or "").strip()
    visits = [str(item or "").strip() for item in route_result.get("visits", []) if str(item or "").strip()]

    if str(route_result.get("route_scope") or "").strip().lower() == "trunk" and warehouse_node and depot_name:
        depot_node = _normalize_route_node(depot_name, fallback_type="depot", route_context=route_context)
        return [dict(warehouse_node), depot_node, dict(warehouse_node)]

    if warehouse_node and depot_name:
        depot_node = _normalize_route_node(depot_name, fallback_type="depot", route_context=route_context)
        visit_nodes = [
            _normalize_route_node(visit_name, fallback_type="venue", route_context=route_context)
            for visit_name in visits
        ]
        return [
            dict(warehouse_node),
            depot_node,
            *[node for node in visit_nodes if node.get("name")],
            depot_node,
            dict(warehouse_node),
        ]

    if warehouse_node:
        visit_nodes = [
            _normalize_route_node(visit_name, fallback_type="venue", route_context=route_context)
            for visit_name in visits
        ]
        return [dict(warehouse_node), *[node for node in visit_nodes if node.get("name")], dict(warehouse_node)]

    path_names = route_result.get("route_path_names")
    if isinstance(path_names, list):
        return [
            _normalize_route_node(name, fallback_type="venue", route_context=route_context)
            for name in path_names
            if str(name or "").strip()
        ]

    return []


def get_ordered_route_names(route_result: dict, route_context: dict[str, Any]) -> list[str]:
    return [str(node.get("name") or "") for node in get_ordered_route_nodes(route_result, route_context) if node.get("name")]


def get_ordered_route_segments(route_result: dict, route_context: dict[str, Any]) -> list[dict[str, Any]]:
    route_nodes = get_ordered_route_nodes(route_result, route_context)
    segments: list[dict[str, Any]] = []

    for index in range(max(len(route_nodes) - 1, 0)):
        from_node = route_nodes[index]
        to_node = route_nodes[index + 1]
        from_lat = _to_float(from_node.get("lat"))
        from_lng = _to_float(from_node.get("lng"))
        to_lat = _to_float(to_node.get("lat"))
        to_lng = _to_float(to_node.get("lng"))
        if None in {from_lat, from_lng, to_lat, to_lng}:
            continue

        segments.append(
            {
                "from_node": from_node,
                "to_node": to_node,
                "coords": [[from_lat, from_lng], [to_lat, to_lng]],
            }
        )

    return segments


def is_warehouse_depot_segment(from_node: dict[str, Any], to_node: dict[str, Any]) -> bool:
    node_types = {str(from_node.get("node_type") or ""), str(to_node.get("node_type") or "")}
    return node_types == {"warehouse", "depot"}
