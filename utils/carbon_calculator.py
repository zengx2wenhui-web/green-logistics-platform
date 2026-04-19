from typing import List, Dict, Optional
import logging

from utils.vehicle_lib import get_vehicle_params, carbon_per_segment
from utils.carbon_calc import carbon_equivalents as carbon_to_equivalents

logger = logging.getLogger(__name__)


# ===================== 碳排放计算器 =====================

class CarbonCalculator:
    def __init__(self, vehicle_type: str = "diesel"):
        self.vehicle_type: str = vehicle_type.split('_')[0].lower()
        self.vehicle_params: Dict = get_vehicle_params(self.vehicle_type)

    def calc_emission(self, distance_km: float, load_kg: float, season: str = "夏", h2_source: str = "工业副产氢") -> float:
        """调用底层的双公式计算"""
        if distance_km <= 0 or load_kg < 0:
            return 0.0
        
        # 调用黑盒，返回克(g)
        carbon_g = carbon_per_segment(
            vtype=self.vehicle_type, 
            load_kg=load_kg, 
            distance_km=distance_km, 
            season=season, 
            h2_source=h2_source
        )
        # 转为千克(kg)
        return carbon_g / 1000.0

    def calc_trunk_emission(self, distance_km: float, total_weight_kg: float, season: str = "夏", h2_source: str = "工业副产氢") -> float:
        """干线运输碳排放（满载直达，不逐站卸货，但包含一次冷启动）。"""
        running_carbon = self.calc_emission(distance_km, total_weight_kg, season, h2_source)
        cold_start_kg = self.vehicle_params.get("cold_start_g", 0) / 1000.0
        return running_carbon + cold_start_kg


def calc_route_carbon(
    distance_matrix: List[List[float]],
    route: List[int],
    demands: List[float],
    vehicle_type: str = "diesel",
    vehicle_capacity: float = 10000.0,
    season: str = "夏",
    h2_source: str = "工业副产氢"
) -> Dict:
    """计算单条路线碳排放（包含冷启动 + 载重逐站递减双公式）。"""
    
    clean_vtype = vehicle_type.split('_')[0].lower()
    params = get_vehicle_params(clean_vtype)

    segments: List[Dict] = []
    total_distance = 0.0
    
    # 【核心修复1】路线总碳排的底色是该车的冷启动碳排 (g转kg)
    total_carbon = params.get("cold_start_g", 0) / 1000.0

    # 出发时载重 = 路线中所有配送节点需求之和（不超过容量）
    route_demand_kg = sum(demands[n] for n in route if n != route[0])
    current_load_kg = min(route_demand_kg, vehicle_capacity)

    for i in range(len(route) - 1):
        from_node = route[i]
        to_node = route[i + 1]

        distance = distance_matrix[from_node][to_node]
        
        # 【核心修复2】直接调用 vehicle_lib 的双公式计算单段碳排
        carbon_g = carbon_per_segment(
            vtype=clean_vtype,
            load_kg=current_load_kg,
            distance_km=distance,
            season=season,
            h2_source=h2_source
        )
        carbon_kg = carbon_g / 1000.0

        segments.append({
            "from": from_node,
            "to": to_node,
            "distance_km": round(distance, 2),
            "load_before_kg": round(current_load_kg, 1),
            "demand_kg": demands[to_node],
            "load_after_kg": round(max(current_load_kg - demands[to_node], 0), 1),
            "carbon_kg": round(carbon_kg, 4),
        })

        total_distance += distance
        total_carbon += carbon_kg

        # 到达节点后卸货
        current_load_kg -= demands[to_node]
        current_load_kg = max(current_load_kg, 0.0)

    return {
        "total_distance_km": round(total_distance, 2),
        "total_carbon_kg": round(total_carbon, 4),
        "segments": segments,
        "vehicle_type": vehicle_type,
        "vehicle_capacity": vehicle_capacity,
    }


def calc_fleet_carbon(
    distance_matrix: List[List[float]],
    routes: List[List[int]],
    demands: List[float],
    vehicle_type: str = "diesel",
    vehicle_capacity: float = 10000.0,
    season: str = "夏",
    h2_source: str = "工业副产氢"
) -> Dict:
    """计算整个车队的总碳排放（支持传递环境变量）。"""
    route_details: List[Dict] = []
    total_distance = 0.0
    total_carbon = 0.0

    for i, route in enumerate(routes):
        result = calc_route_carbon(
            distance_matrix, route, demands, vehicle_type, vehicle_capacity, season, h2_source
        )
        route_details.append({"vehicle_id": i, "route": route, **result})
        total_distance += result["total_distance_km"]
        total_carbon += result["total_carbon_kg"]

    return {
        "total_distance_km": round(total_distance, 2),
        "total_carbon_kg": round(total_carbon, 4),
        "route_count": len(routes),
        "avg_carbon_per_km": (
            round(total_carbon / total_distance, 4) if total_distance > 0 else 0.0
        ),
        "route_details": route_details,
    }


# ===================== 多中心（多中转仓）碳排放汇总 =====================

def calc_multi_depot_carbon(
    depot_results: List[Dict],
    trunk_emissions: Optional[List[float]] = None,
) -> Dict:
    """
    合并多个中转仓下属车队的末端碳排放，并可选叠加干线碳排放。

    Args:
        depot_results: 各中转仓的 calc_fleet_carbon 结果列表
        trunk_emissions: 各中转仓对应的干线碳排放（kg CO₂），长度与 depot_results 一致

    Returns:
        全局碳排放汇总字典
    """
    total_terminal = sum(r.get("total_carbon_kg", 0) for r in depot_results)
    total_trunk = sum(trunk_emissions) if trunk_emissions else 0.0
    total_distance = sum(r.get("total_distance_km", 0) for r in depot_results)
    total_vehicles = sum(r.get("route_count", 0) for r in depot_results)

    return {
        "trunk_carbon_kg": round(total_trunk, 4),
        "terminal_carbon_kg": round(total_terminal, 4),
        "total_carbon_kg": round(total_trunk + total_terminal, 4),
        "total_distance_km": round(total_distance, 2),
        "total_vehicles": total_vehicles,
        "depot_count": len(depot_results),
        "trunk_ratio": (
            round(total_trunk / (total_trunk + total_terminal), 4)
            if (total_trunk + total_terminal) > 0 else 0.0
        ),
    }


# ===================== 报告打印 =====================

def print_carbon_report(result: Dict) -> None:
    """打印碳排放车队报告（控制台）。"""
    print("\n" + "=" * 60)
    print("碳排放计算报告")
    print("=" * 60)

    print(f"\n总行驶距离: {result['total_distance_km']:.2f} km")
    print(f"总碳排放: {result['total_carbon_kg']:.2f} kg CO₂")
    print(f"平均碳排放: {result.get('avg_carbon_per_km', 0):.4f} kg CO₂/km")
    print(f"车辆数: {result['route_count']}")

    print("\n--- 各车辆路线详情 ---")
    for detail in result.get("route_details", []):
        vid = detail.get("vehicle_id", "?")
        print(f"\n车辆 {vid + 1}:")
        print(f"  路线: {' -> '.join(map(str, detail['route']))}")
        print(f"  距离: {detail['total_distance_km']:.2f} km")
        print(f"  碳排放: {detail['total_carbon_kg']:.2f} kg CO₂")

        for seg in detail.get("segments", []):
            print(
                f"    {seg['from']} -> {seg['to']}: "
                f"{seg['distance_km']:.2f}km, "
                f"载重 {seg['load_before_kg']:.0f}kg -> {seg['load_after_kg']:.0f}kg, "
                f"碳排放 {seg['carbon_kg']:.2f}kg"
            )

    # 环保等价物
    eq = carbon_to_equivalents(result["total_carbon_kg"])
    print("\n--- 环保等价物 ---")
    print(f"🌳 相当于种植 {eq['trees_per_year']:.0f} 棵树一年吸收量")
    print(f"⛽ 或 {eq['gasoline_liters']:.0f} 升汽油燃烧")
    print(f"💡 或 {eq['electricity_kwh']:.0f} 度电产生")
    print(f"🚗 或 {eq['car_years']:.2f} 辆小汽车一年排放")


# ===================== 测试入口 =====================

if __name__ == "__main__":
    print("=== 碳排放计算引擎测试 ===\n")

    test_matrix = [
        [0.0, 5.2, 8.1, 6.3, 9.5],
        [5.2, 0.0, 6.8, 4.2, 7.1],
        [8.1, 6.8, 0.0, 9.3, 5.6],
        [6.3, 4.2, 9.3, 0.0, 8.4],
        [9.5, 7.1, 5.6, 8.4, 0.0],
    ]
    test_routes = [[0, 1, 3, 0], [0, 2, 4, 0]]
    test_demands = [0, 2000, 3000, 1500, 2500]

    print("距离矩阵:", test_matrix)
    print("路线:", test_routes)
    print("需求量(kg):", test_demands)
    print()

    result = calc_fleet_carbon(
        distance_matrix=test_matrix,
        routes=test_routes,
        demands=test_demands,
        vehicle_type="diesel_heavy",
        vehicle_capacity=10000.0,
    )
    print_carbon_report(result)

    print("\n\n=== 单路段碳排放测试 ===")
    calc = CarbonCalculator("diesel_heavy")
    carbon = calc.calc_emission(distance_km=100, load_kg=5000)
    print(f"100km, 5吨载重: {carbon:.2f} kg CO₂")

    print("\n=== 干线运输碳排放测试 ===")
    trunk = calc.calc_trunk_emission(distance_km=200, total_weight_kg=15000)
    print(f"200km, 15吨满载: {trunk:.2f} kg CO₂")
