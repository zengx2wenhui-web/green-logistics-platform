"""Green CVRP 求解器 — 目标函数为最小化总碳排放

基于贪心最近邻算法实现，公式: E = distance × emission_factor × load_ton

核心特性：
- 贪心最近邻 VRP 求解（稳定可靠，无外部求解器依赖）
- 修复 _extract_detailed_route 中未初始化 current_load 的致命 Bug
- 修复 print_vrp_result 中字典键名不一致（load_before_kg vs load_before_ton）
- 前置输入校验器（需求超容量、矩阵维度不匹配等）
- 精确逐站载重递减碳排放计算
- 细化异常捕获，消除裸 except
"""
from typing import List, Dict, Optional
import logging
import math

import numpy as np

from utils.vehicle_config import load_vehicle_types, get_vehicle_params  # noqa: F401

logger = logging.getLogger(__name__)


# ===================== 输入校验器 =====================

def _validate_inputs(
    distance_matrix: List[List[float]],
    demands: List[float],
    vehicle_capacity: float,
) -> Optional[str]:
    """
    前置校验 VRP 输入数据，返回错误信息字符串；通过则返回 None。

    检查项:
    1. 距离矩阵维度与需求列表长度一致
    2. 无单个需求超过车辆容量
    3. 距离矩阵无负值
    """
    n = len(distance_matrix)
    if n != len(demands):
        return (
            f"距离矩阵维度({n})与需求列表长度({len(demands)})不一致"
        )

    over_capacity = [
        i for i, d in enumerate(demands) if d > vehicle_capacity
    ]
    if over_capacity:
        return (
            f"节点 {over_capacity} 的需求超过车辆容量 "
            f"({vehicle_capacity} kg)，无法完成配送"
        )

    for i, row in enumerate(distance_matrix):
        if len(row) != n:
            return f"距离矩阵第 {i} 行长度({len(row)})与矩阵维度({n})不一致"
        for j, val in enumerate(row):
            if val < 0:
                return f"距离矩阵[{i}][{j}]为负值({val})，请检查数据"

    return None


# ===================== 贪心最近邻 VRP 求解器 =====================

def _greedy_nearest_neighbor(
    distance_matrix: List[List[float]],
    demands: List[float],
    vehicle_capacity: float,
    num_vehicles: int,
    depot: int = 0,
) -> List[List[int]]:
    """
    贪心最近邻 VRP 求解：每辆车从仓库出发，依次选择距离当前位置
    最近且剩余容量可容纳的未服务节点，直到无法继续则返回仓库。

    Args:
        distance_matrix: N×N 距离矩阵（km）
        demands: 各节点需求量（kg），索引 depot 为仓库（需求 = 0）
        vehicle_capacity: 车辆载重上限（kg）
        num_vehicles: 可用车辆数
        depot: 仓库节点索引

    Returns:
        路线列表，每条路线为节点索引列表（含起始仓库，不含末尾仓库）
    """
    n = len(distance_matrix)
    remaining = list(demands)
    remaining[depot] = 0
    routes: List[List[int]] = []

    for _ in range(num_vehicles):
        if sum(remaining) <= 0:
            break

        route = [depot]
        current_load = 0.0
        current_pos = depot

        while True:
            best_dist = float("inf")
            best_node = -1
            for j in range(n):
                if j == depot or remaining[j] <= 0:
                    continue
                if current_load + remaining[j] <= vehicle_capacity:
                    if distance_matrix[current_pos][j] < best_dist:
                        best_dist = distance_matrix[current_pos][j]
                        best_node = j

            if best_node == -1:
                break

            route.append(best_node)
            current_load += remaining[best_node]
            remaining[best_node] = 0
            current_pos = best_node

        if len(route) > 1:
            routes.append(route)

    # 如果还有未服务节点（车辆不够），继续用额外车辆
    while sum(remaining) > 0:
        route = [depot]
        current_load = 0.0
        current_pos = depot

        while True:
            best_dist = float("inf")
            best_node = -1
            for j in range(n):
                if j == depot or remaining[j] <= 0:
                    continue
                if current_load + remaining[j] <= vehicle_capacity:
                    if distance_matrix[current_pos][j] < best_dist:
                        best_dist = distance_matrix[current_pos][j]
                        best_node = j
            if best_node == -1:
                break

            route.append(best_node)
            current_load += remaining[best_node]
            remaining[best_node] = 0
            current_pos = best_node

        if len(route) > 1:
            routes.append(route)
        else:
            break

    return routes


# ===================== Green CVRP 求解器 =====================

class GreenCVRP:
    """Green CVRP 求解器 — 基于贪心最近邻算法最小化碳排放。"""

    def __init__(
        self,
        distance_matrix: List[List[float]],
        demands: List[float],
        vehicle_capacity: float,
        vehicle_type: str = "diesel_heavy",
        fixed_cost_per_vehicle: float = 0.0,
    ):
        """
        Args:
            distance_matrix: N×N 距离矩阵（km）
            demands: 各节点需求量（kg），索引 0 为仓库（需求 = 0）
            vehicle_capacity: 车辆载重上限（kg）
            vehicle_type: 车型 ID
            fixed_cost_per_vehicle: 预留参数（贪心算法暂不使用）
        """
        # 输入校验
        err = _validate_inputs(distance_matrix, demands, vehicle_capacity)
        if err:
            raise ValueError(f"[GreenCVRP] 输入校验失败: {err}")

        self.distance_matrix = distance_matrix
        self.demands = demands
        self.num_nodes = len(distance_matrix)
        self.vehicle_capacity = vehicle_capacity
        self.vehicle_type = vehicle_type
        self.fixed_cost = fixed_cost_per_vehicle
        self.routes: List[List[int]] = []

    def solve(
        self,
        num_vehicles: int,
        depot: int = 0,
        time_limit_seconds: int = 60,
    ) -> Optional[Dict]:
        """
        求解 CVRP（贪心最近邻算法）。

        Args:
            num_vehicles: 可用车辆数
            depot: 仓库节点索引
            time_limit_seconds: 预留参数（贪心算法不需要时间限制）

        Returns:
            求解结果字典；无解返回 None
        """
        self.routes = _greedy_nearest_neighbor(
            self.distance_matrix,
            self.demands,
            self.vehicle_capacity,
            num_vehicles,
            depot,
        )

        if not self.routes:
            return None

        return self._build_result()

    def _extract_detailed_route(self, route: List[int]) -> Dict:
        """
        计算单条路线的精确碳排放（逐站载重递减）。

        修复说明: 原代码 current_load 未正确初始化，此处统一使用 kg 单位。
        """
        params = get_vehicle_params(self.vehicle_type)
        ef = params["emission_factor"]

        segments: List[Dict] = []
        total_distance = 0.0
        total_carbon = 0.0

        # 初始载重 = 路线中所有配送节点需求之和
        route_demand_kg = sum(self.demands[n] for n in route if n != route[0])
        current_load_kg = min(route_demand_kg, self.vehicle_capacity)

        for i in range(len(route) - 1):
            from_node = route[i]
            to_node = route[i + 1]

            distance = self.distance_matrix[from_node][to_node]
            load_ton = current_load_kg / 1000.0
            carbon = distance * ef * load_ton

            segments.append({
                "from": from_node,
                "to": to_node,
                "distance_km": round(distance, 2),
                "load_before_kg": round(current_load_kg, 1),
                "demand_kg": self.demands[to_node],
                "load_after_kg": round(
                    max(current_load_kg - self.demands[to_node], 0), 1,
                ),
                "carbon_kg": round(carbon, 4),
            })

            total_distance += distance
            total_carbon += carbon

            # 卸货后载重减少
            current_load_kg -= self.demands[to_node]
            current_load_kg = max(current_load_kg, 0.0)

        return {
            "route": route,
            "segments": segments,
            "total_distance_km": round(total_distance, 2),
            "total_carbon_kg": round(total_carbon, 4),
            "vehicle_type": self.vehicle_type,
        }

    def _build_result(self) -> Dict:
        """组装最终求解结果。"""
        route_details: List[Dict] = []
        total_distance = 0.0
        total_carbon = 0.0

        for route in self.routes:
            detail = self._extract_detailed_route(route)
            route_details.append(detail)
            total_distance += detail["total_distance_km"]
            total_carbon += detail["total_carbon_kg"]

        return {
            "success": True,
            "routes": self.routes,
            "route_details": route_details,
            "total_distance_km": round(total_distance, 2),
            "total_carbon_kg": round(total_carbon, 4),
            "num_vehicles_used": len(self.routes),
            "vehicle_type": self.vehicle_type,
            "vehicle_capacity": self.vehicle_capacity,
        }


# ===================== 便捷求解函数 =====================

def solve_green_cvrp(
    distance_matrix: List[List[float]],
    demands: List[float],
    vehicle_capacity: float,
    num_vehicles: Optional[int] = None,
    vehicle_type: str = "diesel_heavy",
    depot: int = 0,
    time_limit_seconds: int = 60,
    fixed_cost_per_vehicle: float = 0.0,
) -> Optional[Dict]:
    """
    求解 Green CVRP（最小化碳排放）的便捷入口。

    Args:
        distance_matrix: N×N 距离矩阵（km）
        demands: 各节点需求量（kg），索引 0 为仓库
        vehicle_capacity: 车辆载重上限（kg）
        num_vehicles: 车辆数量；None 时自动按需求推算
        vehicle_type: 车型 ID
        depot: 仓库节点索引
        time_limit_seconds: 预留参数
        fixed_cost_per_vehicle: 预留参数

    Returns:
        求解结果字典；无解返回 None
    """
    # 输入校验
    err = _validate_inputs(distance_matrix, demands, vehicle_capacity)
    if err:
        logger.error(f"[VRP] 输入校验失败: {err}")
        return None

    n = len(distance_matrix)

    if num_vehicles is None:
        total_demand = sum(demands)
        num_vehicles = max(1, int(math.ceil(total_demand / vehicle_capacity)))
        num_vehicles = min(num_vehicles, n - 1)

    try:
        solver = GreenCVRP(
            distance_matrix=distance_matrix,
            demands=demands,
            vehicle_capacity=vehicle_capacity,
            vehicle_type=vehicle_type,
            fixed_cost_per_vehicle=fixed_cost_per_vehicle,
        )

        result = solver.solve(num_vehicles, depot, time_limit_seconds)
        if result:
            return result

    except ValueError as e:
        logger.error(f"[VRP] {e}")

    return None


# ===================== 车队规模优化 =====================

def optimize_vehicle_count(
    distance_matrix: List[List[float]],
    demands: List[float],
    vehicle_capacity: float,
    vehicle_type: str = "diesel_heavy",
    depot: int = 0,
    fixed_cost_per_vehicle: float = 0.0,
) -> Dict:
    """
    遍历不同车辆数量，找到总碳排放最低的车队规模。

    Returns:
        最优结果字典；无解时含 "error" 键
    """
    n = len(distance_matrix)
    total_demand = sum(demands)
    min_v = max(1, int(math.ceil(total_demand / vehicle_capacity)))
    max_v = min(min_v * 2, n - 1)

    best_result: Optional[Dict] = None
    best_carbon = float("inf")

    logger.info(f"[车队优化] 尝试 {min_v}~{max_v} 辆车")

    for nv in range(min_v, max_v + 1):
        result = solve_green_cvrp(
            distance_matrix=distance_matrix,
            demands=demands,
            vehicle_capacity=vehicle_capacity,
            num_vehicles=nv,
            vehicle_type=vehicle_type,
            depot=depot,
            time_limit_seconds=30,
            fixed_cost_per_vehicle=fixed_cost_per_vehicle,
        )
        if result:
            carbon = result["total_carbon_kg"]
            logger.info(
                f"  车辆数={nv}: 碳排放={carbon:.2f}kg, "
                f"距离={result['total_distance_km']:.2f}km"
            )
            if carbon < best_carbon:
                best_carbon = carbon
                best_result = result
                best_result["num_vehicles_tested"] = nv

    return best_result or {"error": "未找到可行解"}


# ===================== 结果打印 =====================

def print_vrp_result(
    result: Dict,
    node_names: Optional[Dict[int, str]] = None,
) -> None:
    """打印 VRP 求解结果。"""
    if "error" in result:
        print(f"[VRP求解] 错误: {result['error']}")
        return

    print("\n" + "=" * 70)
    print("Green CVRP 求解结果 — 最小化碳排放")
    print("=" * 70)

    print(f"\n使用车辆数: {result['num_vehicles_used']}")
    print(f"总行驶距离: {result['total_distance_km']:.2f} km")
    print(f"总碳排放: {result['total_carbon_kg']:.2f} kg CO₂")
    if result["total_distance_km"] > 0:
        print(
            f"平均碳效率: "
            f"{result['total_carbon_kg'] / result['total_distance_km']:.4f} "
            f"kg CO₂/km"
        )
    print(f"车型: {result['vehicle_type']}")
    print(f"车辆容量: {result['vehicle_capacity']:.0f} kg")

    print("\n--- 各车辆路线详情 ---")
    names = node_names or {}
    for i, detail in enumerate(result.get("route_details", [])):
        route = detail["route"]
        route_str = " → ".join(names.get(n, f"V{n}") for n in route)

        print(f"\n车辆 {i + 1}:")
        print(f"   路线: {route_str}")
        print(f"   距离: {detail['total_distance_km']:.2f} km")
        print(f"   碳排放: {detail['total_carbon_kg']:.2f} kg CO₂")

        for seg in detail.get("segments", []):
            fn = names.get(seg["from"], f"V{seg['from']}")
            tn = names.get(seg["to"], f"V{seg['to']}")
            print(
                f"     {fn} → {tn}: "
                f"{seg['distance_km']:.2f}km, "
                f"载重 {seg['load_before_kg']:.0f}kg → "
                f"{seg['load_after_kg']:.0f}kg, "
                f"碳排放 {seg['carbon_kg']:.2f}kg"
            )

    # 环保等价
    total = result["total_carbon_kg"]
    trees = total / 12.0  # 12 kg CO₂/棵·年
    print(f"\n环保等价: 相当于种植 {trees:.1f} 棵树一年吸收量")


# ===================== 测试入口 =====================

if __name__ == "__main__":
    print("=== Green CVRP 求解器测试 ===\n")

    test_matrix = [
        [0.0, 5.2, 8.1, 6.3, 9.5],
        [5.2, 0.0, 6.8, 4.2, 7.1],
        [8.1, 6.8, 0.0, 9.3, 5.6],
        [6.3, 4.2, 9.3, 0.0, 8.4],
        [9.5, 7.1, 5.6, 8.4, 0.0],
    ]
    test_demands = [0, 2000, 3000, 1500, 2500]
    test_names = {0: "仓库", 1: "场馆A", 2: "场馆B", 3: "场馆C", 4: "场馆D"}

    print("节点:", test_names)
    print("需求量(kg):", test_demands)
    print()

    result = solve_green_cvrp(
        distance_matrix=test_matrix,
        demands=test_demands,
        vehicle_capacity=10000,
        num_vehicles=2,
        vehicle_type="diesel_heavy",
        time_limit_seconds=30,
    )
    print_vrp_result(result, test_names)

    print("\n\n=== 车辆数优化测试 ===")
    opt = optimize_vehicle_count(
        distance_matrix=test_matrix,
        demands=test_demands,
        vehicle_capacity=10000,
        vehicle_type="diesel_heavy",
    )
    if "error" not in opt:
        print(
            f"\n最优: {opt['num_vehicles_used']}辆车, "
            f"碳排放={opt['total_carbon_kg']:.2f}kg"
        )
