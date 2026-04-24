from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from utils.vehicle_lib import get_vehicle_params, carbon_per_segment
import multiprocessing
import os


@dataclass(frozen=True)
class FleetEntry:
    vehicle_type: str
    load_ton: float
    count_max: int

def _expand_vehicle_pool(
    fleet: List[FleetEntry],
    capacity_multiplier: int = 1000,
) -> Tuple[List[int], List[str], List[float]]:
    vehicle_capacities_scaled: List[int] = []
    vehicle_types: List[str] = []
    vehicle_load_ton: List[float] = []

    for entry in fleet:
        if entry.count_max <= 0:
            continue
        if entry.load_ton <= 0:
            continue
        
        # entry.load_ton * 1000 换算为 kg，再乘以 multiplier 提升精度以防抹零
        cap_scaled = int(round(entry.load_ton * 1000 * capacity_multiplier))
        
        for _ in range(int(entry.count_max)):
            vehicle_capacities_scaled.append(cap_scaled)
            vehicle_types.append(entry.vehicle_type)
            vehicle_load_ton.append(float(entry.load_ton))

    return vehicle_capacities_scaled, vehicle_types, vehicle_load_ton


def solve_fsmvrp_ortools(
    *,
    distance_matrix_km: List[List[float]],
    demands_kg: List[float],
    fleet: List[Dict],
    depot: int = 0,
    time_limit_seconds: int = 30,
    season: str = "夏",
    h2_source: str = "工业副产氢",
) -> Optional[Dict]:
    if not distance_matrix_km or not demands_kg:
        return None
    if len(distance_matrix_km) != len(demands_kg):
        return None

    fleet_entries: List[FleetEntry] = []
    for row in fleet or []:
        try:
            fleet_entries.append(
                FleetEntry(
                    vehicle_type=str(row.get("vehicle_type", "")).strip(),
                    load_ton=float(row.get("load_ton", 0.0)),
                    count_max=int(row.get("count_max", 0)),
                )
            )
        except Exception:
            continue

    # 定义统一的精度放大系数
    CAPACITY_MULTIPLIER = 1000

    vehicle_capacities_scaled, vehicle_types, vehicle_load_ton = _expand_vehicle_pool(
        fleet_entries, 
        capacity_multiplier=CAPACITY_MULTIPLIER
    )
    
    num_locations = len(distance_matrix_km)
    num_vehicles = len(vehicle_capacities_scaled)
    if num_vehicles <= 0:
        return None

    manager = pywrapcp.RoutingIndexManager(num_locations, num_vehicles, depot)
    routing = pywrapcp.RoutingModel(manager)

    # Demands callback (同步放大相同的倍数，防止小数被抹零)
    demands_int = [int(round(x * CAPACITY_MULTIPLIER)) for x in demands_kg]

    def demand_callback(from_index: int) -> int:
        node = manager.IndexToNode(from_index)
        return demands_int[node]

    demand_cb_idx = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_cb_idx,
        0, 
        vehicle_capacities_scaled, 
        True, 
        "Capacity",
    )

    def distance_km(from_index: int, to_index: int) -> float:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return float(distance_matrix_km[from_node][to_node])

    evaluator_cache: Dict[Tuple[str, float], int] = {}

    def get_arc_cost_evaluator(vtype: str, load_ton: float) -> int:
        key = (vtype, float(load_ton))
        if key in evaluator_cache:
            return evaluator_cache[key]

        per_km_g = carbon_per_segment(
            vtype=vtype, 
            load_kg=load_ton * 1000, 
            distance_km=1.0, 
            season=season, 
            h2_source=h2_source
        )

        def arc_cost_callback(from_index: int, to_index: int) -> int:
            # 使用预先传入的距离矩阵索引，减少每次闭包查找开销
            d_km = distance_km(from_index, to_index)
            return int(round(d_km * per_km_g))

        cb_idx = routing.RegisterTransitCallback(arc_cost_callback)
        evaluator_cache[key] = cb_idx
        return cb_idx

    for v_id in range(num_vehicles):
        vtype = vehicle_types[v_id]
        load_ton = vehicle_load_ton[v_id]
        # 动态从 vehicle_lib 获取冷启动成本
        params = get_vehicle_params(vtype)
        routing.SetFixedCostOfVehicle(params["cold_start_g"], v_id)
        
        cb_idx = get_arc_cost_evaluator(vtype, load_ton)
        routing.SetArcCostEvaluatorOfVehicle(cb_idx, v_id)

    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    # 对较短时间限制使用自动策略以更快返回，较长时间允许 GUIDED_LOCAL_SEARCH 提升质量
    try:
        if int(time_limit_seconds) >= 30:
            search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        else:
            search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.AUTOMATIC
    except Exception:
        pass
    search_params.time_limit.FromSeconds(int(max(1, time_limit_seconds)))
    # 启用并行搜索 worker（最多 8）以提升求解速度
    try:
        cpu_cnt = multiprocessing.cpu_count() or os.cpu_count() or 1
        search_params.num_search_workers = max(1, min(8, int(cpu_cnt)))
    except Exception:
        pass

    solution = routing.SolveWithParameters(search_params)
    if solution is None:
        return None

    routes: List[List[int]] = []
    vehicle_used: List[bool] = []
    used_count_by_type: Dict[str, int] = {}
    route_vehicle_ids: List[int] = []

    for v_id in range(num_vehicles):
        if not routing.IsVehicleUsed(solution, v_id):
            vehicle_used.append(False)
            continue
        vehicle_used.append(True)
        vtype = vehicle_types[v_id]
        used_count_by_type[vtype] = used_count_by_type.get(vtype, 0) + 1

        index = routing.Start(v_id)
        route: List[int] = []
        while not routing.IsEnd(index):
            route.append(manager.IndexToNode(index))
            index = solution.Value(routing.NextVar(index))
        route.append(manager.IndexToNode(index))
        route_vehicle_ids.append(v_id)
        routes.append(route)

    return {
        "success": True,
        "routes": routes,
        "route_vehicle_ids": route_vehicle_ids,
        "num_vehicles_pool": num_vehicles,
        "num_vehicles_used": sum(1 for x in vehicle_used if x),
        "vehicle_used_flags": vehicle_used,
        "vehicle_types": vehicle_types,
        "vehicle_capacities_kg": [c // CAPACITY_MULTIPLIER for c in vehicle_capacities_scaled], # 还原回kg对外输出
        "fleet_used_by_type": used_count_by_type,
    }


if __name__ == "__main__":
    pass