from __future__ import annotations

import multiprocessing
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from utils.fleet_summary import build_count_by_type, build_vehicle_pool_summary
from utils.vehicle_lib import carbon_per_segment, get_vehicle_params


CAPACITY_MULTIPLIER = 1000
_ROUTE_COST_EPSILON_G = 1e-6
_MAX_REFINEMENT_PASSES = 12
_SOLVER_COST_MODEL = "fixed cold-start carbon + proxy arc carbon cost (grams CO2 integer)"


@dataclass(frozen=True)
class FleetEntry:
    vehicle_type: str
    load_ton: float
    count_max: int


def _expand_vehicle_pool(
    fleet: List[FleetEntry],
    capacity_multiplier: int = CAPACITY_MULTIPLIER,
) -> Tuple[List[int], List[str], List[float]]:
    vehicle_capacities_scaled: List[int] = []
    vehicle_types: List[str] = []
    vehicle_load_ton: List[float] = []

    for entry in fleet:
        if entry.count_max <= 0 or entry.load_ton <= 0:
            continue

        capacity_scaled = int(round(entry.load_ton * 1000 * capacity_multiplier))
        for _ in range(int(entry.count_max)):
            vehicle_capacities_scaled.append(capacity_scaled)
            vehicle_types.append(entry.vehicle_type)
            vehicle_load_ton.append(float(entry.load_ton))

    return vehicle_capacities_scaled, vehicle_types, vehicle_load_ton


def _get_vehicle_display_name(vehicle_type: str) -> str:
    params = get_vehicle_params(vehicle_type) or {}
    return str(params.get("name") or vehicle_type or "unknown")


def _get_route_customer_count(route: List[int], depot: int) -> int:
    return sum(1 for node in route if node != depot)


def _normalize_route(route: List[int], depot: int) -> List[int]:
    customers = [int(node) for node in route if int(node) != int(depot)]
    return [int(depot), *customers, int(depot)]


def _get_route_total_demand_kg(
    route: List[int],
    demands_kg: List[float],
    depot: int,
) -> float:
    total_demand_kg = 0.0
    for node in route:
        if node == depot:
            continue
        total_demand_kg += max(float(demands_kg[node] or 0), 0.0)
    return total_demand_kg


def _get_route_exact_emission_g(
    *,
    route: List[int],
    vehicle_type: str,
    distance_matrix_km: List[List[float]],
    demands_kg: List[float],
    depot: int,
    season: str,
    h2_source: str,
    include_cold_start: bool = True,
) -> float:
    normalized_route = _normalize_route(route, depot)
    if _get_route_customer_count(normalized_route, depot) <= 0:
        return 0.0

    total_emission_g = 0.0
    if include_cold_start:
        total_emission_g += float((get_vehicle_params(vehicle_type) or {}).get("cold_start_g", 0) or 0)

    remaining_load_kg = _get_route_total_demand_kg(normalized_route, demands_kg, depot)
    for idx in range(len(normalized_route) - 1):
        from_node = normalized_route[idx]
        to_node = normalized_route[idx + 1]
        segment_distance_km = float(distance_matrix_km[from_node][to_node] or 0)
        total_emission_g += float(
            carbon_per_segment(
                vehicle_type,
                remaining_load_kg,
                segment_distance_km,
                season,
                h2_source,
            )
        )

        if to_node != depot:
            remaining_load_kg -= max(float(demands_kg[to_node] or 0), 0.0)
            remaining_load_kg = max(remaining_load_kg, 0.0)

    return total_emission_g


def _build_refined_solution_metadata(
    route_records: List[dict[str, int | List[int]]],
    vehicle_types: List[str],
    distance_matrix_km: List[List[float]],
    demands_kg: List[float],
    depot: int,
    season: str,
    h2_source: str,
    *,
    initial_exact_emission_g: float,
    refinement_passes: int,
    refinement_elapsed_s: float,
    refinement_applied: bool,
) -> dict[str, object]:
    final_exact_emission_g = sum(
        _get_route_exact_emission_g(
            route=record["route"],
            vehicle_type=vehicle_types[int(record["vehicle_pool_id"])],
            distance_matrix_km=distance_matrix_km,
            demands_kg=demands_kg,
            depot=depot,
            season=season,
            h2_source=h2_source,
            include_cold_start=True,
        )
        for record in route_records
    )

    return {
        "objective_model": "OR-Tools heterogeneous fleet proxy arc carbon + exact-carbon local refinement",
        "initial_exact_emission_g": round(initial_exact_emission_g, 4),
        "final_exact_emission_g": round(final_exact_emission_g, 4),
        "exact_emission_improvement_g": round(max(initial_exact_emission_g - final_exact_emission_g, 0.0), 4),
        "refinement_passes": refinement_passes,
        "refinement_elapsed_s": round(refinement_elapsed_s, 3),
        "refinement_applied": refinement_applied,
    }


def _refine_routes_with_exact_carbon(
    *,
    routes: List[List[int]],
    route_vehicle_ids: List[int],
    vehicle_types: List[str],
    vehicle_capacities_kg: List[int],
    distance_matrix_km: List[List[float]],
    demands_kg: List[float],
    depot: int,
    season: str,
    h2_source: str,
    time_limit_seconds: int,
) -> tuple[List[List[int]], List[int], dict[str, object]]:
    route_records: List[dict[str, int | List[int]]] = [
        {"route": _normalize_route(route, depot), "vehicle_pool_id": int(vehicle_pool_id)}
        for route, vehicle_pool_id in zip(routes, route_vehicle_ids)
        if _get_route_customer_count(route, depot) > 0
    ]

    if not route_records:
        return [], [], _build_refined_solution_metadata(
            route_records=[],
            vehicle_types=vehicle_types,
            distance_matrix_km=distance_matrix_km,
            demands_kg=demands_kg,
            depot=depot,
            season=season,
            h2_source=h2_source,
            initial_exact_emission_g=0.0,
            refinement_passes=0,
            refinement_elapsed_s=0.0,
            refinement_applied=False,
        )

    refinement_start = time.perf_counter()
    refinement_budget_s = min(12.0, max(1.0, float(time_limit_seconds or 0) * 0.35))
    route_cost_cache: dict[tuple[tuple[int, ...], int], float] = {}

    def _has_time_budget() -> bool:
        return (time.perf_counter() - refinement_start) < refinement_budget_s

    def _get_route_capacity_kg(vehicle_pool_id: int) -> int:
        return int(vehicle_capacities_kg[vehicle_pool_id] or 0)

    def _get_route_load_kg(route: List[int]) -> float:
        return _get_route_total_demand_kg(route, demands_kg, depot)

    def _get_route_cost_g(route: List[int], vehicle_pool_id: int) -> float:
        route_key = (tuple(route), int(vehicle_pool_id))
        cached = route_cost_cache.get(route_key)
        if cached is not None:
            return cached

        vehicle_type = vehicle_types[int(vehicle_pool_id)]
        exact_cost_g = _get_route_exact_emission_g(
            route=route,
            vehicle_type=vehicle_type,
            distance_matrix_km=distance_matrix_km,
            demands_kg=demands_kg,
            depot=depot,
            season=season,
            h2_source=h2_source,
            include_cold_start=True,
        )
        route_cost_cache[route_key] = exact_cost_g
        return exact_cost_g

    def _drop_empty_routes() -> None:
        route_records[:] = [
            record for record in route_records
            if _get_route_customer_count(record["route"], depot) > 0
        ]

    def _try_improve_single_route() -> bool:
        for record in route_records:
            route = list(record["route"])
            vehicle_pool_id = int(record["vehicle_pool_id"])
            if len(route) <= 3:
                continue

            base_cost_g = _get_route_cost_g(route, vehicle_pool_id)

            for start_idx in range(1, len(route) - 2):
                for end_idx in range(start_idx + 1, len(route) - 1):
                    candidate_route = route[:start_idx] + route[start_idx:end_idx + 1][::-1] + route[end_idx + 1:]
                    if candidate_route == route:
                        continue
                    candidate_cost_g = _get_route_cost_g(candidate_route, vehicle_pool_id)
                    if candidate_cost_g + _ROUTE_COST_EPSILON_G < base_cost_g:
                        record["route"] = candidate_route
                        return True

            for source_idx in range(1, len(route) - 1):
                source_node = route[source_idx]
                stripped_route = route[:source_idx] + route[source_idx + 1:]
                for insert_idx in range(1, len(stripped_route)):
                    candidate_route = stripped_route[:insert_idx] + [source_node] + stripped_route[insert_idx:]
                    if candidate_route == route:
                        continue
                    candidate_cost_g = _get_route_cost_g(candidate_route, vehicle_pool_id)
                    if candidate_cost_g + _ROUTE_COST_EPSILON_G < base_cost_g:
                        record["route"] = candidate_route
                        return True

        return False

    def _try_assign_unused_vehicle() -> bool:
        assigned_vehicle_ids = {int(record["vehicle_pool_id"]) for record in route_records}
        unused_vehicle_ids = [vehicle_id for vehicle_id in range(len(vehicle_types)) if vehicle_id not in assigned_vehicle_ids]
        if not unused_vehicle_ids:
            return False

        for record in route_records:
            route = list(record["route"])
            route_load_kg = _get_route_load_kg(route)
            current_vehicle_pool_id = int(record["vehicle_pool_id"])
            base_cost_g = _get_route_cost_g(route, current_vehicle_pool_id)

            for candidate_vehicle_pool_id in unused_vehicle_ids:
                if route_load_kg > _get_route_capacity_kg(candidate_vehicle_pool_id):
                    continue
                candidate_cost_g = _get_route_cost_g(route, candidate_vehicle_pool_id)
                if candidate_cost_g + _ROUTE_COST_EPSILON_G < base_cost_g:
                    record["vehicle_pool_id"] = candidate_vehicle_pool_id
                    return True

        return False

    def _try_swap_vehicle_assignments() -> bool:
        for left_idx in range(len(route_records)):
            for right_idx in range(left_idx + 1, len(route_records)):
                left_record = route_records[left_idx]
                right_record = route_records[right_idx]
                left_vehicle_pool_id = int(left_record["vehicle_pool_id"])
                right_vehicle_pool_id = int(right_record["vehicle_pool_id"])
                if left_vehicle_pool_id == right_vehicle_pool_id:
                    continue

                left_route = list(left_record["route"])
                right_route = list(right_record["route"])
                left_load_kg = _get_route_load_kg(left_route)
                right_load_kg = _get_route_load_kg(right_route)
                if left_load_kg > _get_route_capacity_kg(right_vehicle_pool_id):
                    continue
                if right_load_kg > _get_route_capacity_kg(left_vehicle_pool_id):
                    continue

                current_cost_g = (
                    _get_route_cost_g(left_route, left_vehicle_pool_id)
                    + _get_route_cost_g(right_route, right_vehicle_pool_id)
                )
                swapped_cost_g = (
                    _get_route_cost_g(left_route, right_vehicle_pool_id)
                    + _get_route_cost_g(right_route, left_vehicle_pool_id)
                )
                if swapped_cost_g + _ROUTE_COST_EPSILON_G < current_cost_g:
                    left_record["vehicle_pool_id"] = right_vehicle_pool_id
                    right_record["vehicle_pool_id"] = left_vehicle_pool_id
                    return True

        return False

    def _try_relocate_between_routes() -> bool:
        for source_route_idx in range(len(route_records)):
            for target_route_idx in range(len(route_records)):
                if source_route_idx == target_route_idx:
                    continue

                source_record = route_records[source_route_idx]
                target_record = route_records[target_route_idx]
                source_route = list(source_record["route"])
                target_route = list(target_record["route"])
                source_vehicle_pool_id = int(source_record["vehicle_pool_id"])
                target_vehicle_pool_id = int(target_record["vehicle_pool_id"])
                target_route_load_kg = _get_route_load_kg(target_route)

                current_cost_g = (
                    _get_route_cost_g(source_route, source_vehicle_pool_id)
                    + _get_route_cost_g(target_route, target_vehicle_pool_id)
                )

                for source_pos in range(1, len(source_route) - 1):
                    moved_node = source_route[source_pos]
                    moved_demand_kg = max(float(demands_kg[moved_node] or 0), 0.0)
                    if target_route_load_kg + moved_demand_kg > _get_route_capacity_kg(target_vehicle_pool_id):
                        continue

                    candidate_source_route = _normalize_route(
                        source_route[:source_pos] + source_route[source_pos + 1:],
                        depot,
                    )
                    for target_pos in range(1, len(target_route)):
                        candidate_target_route = target_route[:target_pos] + [moved_node] + target_route[target_pos:]
                        candidate_cost_g = (
                            _get_route_cost_g(candidate_source_route, source_vehicle_pool_id)
                            + _get_route_cost_g(candidate_target_route, target_vehicle_pool_id)
                        )
                        if candidate_cost_g + _ROUTE_COST_EPSILON_G < current_cost_g:
                            source_record["route"] = candidate_source_route
                            target_record["route"] = candidate_target_route
                            _drop_empty_routes()
                            return True

        return False

    def _try_swap_customers_between_routes() -> bool:
        for left_idx in range(len(route_records)):
            for right_idx in range(left_idx + 1, len(route_records)):
                left_record = route_records[left_idx]
                right_record = route_records[right_idx]
                left_route = list(left_record["route"])
                right_route = list(right_record["route"])
                left_vehicle_pool_id = int(left_record["vehicle_pool_id"])
                right_vehicle_pool_id = int(right_record["vehicle_pool_id"])
                left_route_load_kg = _get_route_load_kg(left_route)
                right_route_load_kg = _get_route_load_kg(right_route)

                current_cost_g = (
                    _get_route_cost_g(left_route, left_vehicle_pool_id)
                    + _get_route_cost_g(right_route, right_vehicle_pool_id)
                )

                for left_pos in range(1, len(left_route) - 1):
                    left_node = left_route[left_pos]
                    left_demand_kg = max(float(demands_kg[left_node] or 0), 0.0)
                    for right_pos in range(1, len(right_route) - 1):
                        right_node = right_route[right_pos]
                        right_demand_kg = max(float(demands_kg[right_node] or 0), 0.0)

                        next_left_load_kg = left_route_load_kg - left_demand_kg + right_demand_kg
                        next_right_load_kg = right_route_load_kg - right_demand_kg + left_demand_kg
                        if next_left_load_kg > _get_route_capacity_kg(left_vehicle_pool_id):
                            continue
                        if next_right_load_kg > _get_route_capacity_kg(right_vehicle_pool_id):
                            continue

                        candidate_left_route = list(left_route)
                        candidate_right_route = list(right_route)
                        candidate_left_route[left_pos] = right_node
                        candidate_right_route[right_pos] = left_node

                        candidate_cost_g = (
                            _get_route_cost_g(candidate_left_route, left_vehicle_pool_id)
                            + _get_route_cost_g(candidate_right_route, right_vehicle_pool_id)
                        )
                        if candidate_cost_g + _ROUTE_COST_EPSILON_G < current_cost_g:
                            left_record["route"] = candidate_left_route
                            right_record["route"] = candidate_right_route
                            return True

        return False

    initial_exact_emission_g = sum(
        _get_route_cost_g(list(record["route"]), int(record["vehicle_pool_id"]))
        for record in route_records
    )

    refinement_passes = 0
    refinement_applied = False
    while _has_time_budget() and refinement_passes < _MAX_REFINEMENT_PASSES:
        refinement_passes += 1
        if _try_improve_single_route():
            refinement_applied = True
            continue
        if _try_assign_unused_vehicle():
            refinement_applied = True
            continue
        if _try_swap_vehicle_assignments():
            refinement_applied = True
            continue
        if _try_relocate_between_routes():
            refinement_applied = True
            continue
        if _try_swap_customers_between_routes():
            refinement_applied = True
            continue
        break

    _drop_empty_routes()
    refinement_elapsed_s = time.perf_counter() - refinement_start
    refinement_meta = _build_refined_solution_metadata(
        route_records=route_records,
        vehicle_types=vehicle_types,
        distance_matrix_km=distance_matrix_km,
        demands_kg=demands_kg,
        depot=depot,
        season=season,
        h2_source=h2_source,
        initial_exact_emission_g=initial_exact_emission_g,
        refinement_passes=refinement_passes,
        refinement_elapsed_s=refinement_elapsed_s,
        refinement_applied=refinement_applied,
    )

    refined_routes = [list(record["route"]) for record in route_records]
    refined_route_vehicle_ids = [int(record["vehicle_pool_id"]) for record in route_records]
    return refined_routes, refined_route_vehicle_ids, refinement_meta


def solve_fsmvrp_ortools(
    *,
    distance_matrix_km: List[List[float]],
    demands_kg: List[float],
    fleet: List[Dict],
    depot: int = 0,
    time_limit_seconds: int = 30,
    season: str = "summer",
    h2_source: str = "byproduct",
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

    vehicle_capacities_scaled, vehicle_types, vehicle_load_ton = _expand_vehicle_pool(
        fleet_entries,
        capacity_multiplier=CAPACITY_MULTIPLIER,
    )

    num_locations = len(distance_matrix_km)
    num_vehicles = len(vehicle_capacities_scaled)
    if num_vehicles <= 0:
        return None

    manager = pywrapcp.RoutingIndexManager(num_locations, num_vehicles, depot)
    routing = pywrapcp.RoutingModel(manager)

    demands_int = [int(round(float(demand or 0) * CAPACITY_MULTIPLIER)) for demand in demands_kg]

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
        cached_evaluator = evaluator_cache.get(key)
        if cached_evaluator is not None:
            return cached_evaluator

        loaded_per_km_g = float(
            carbon_per_segment(
                vtype=vtype,
                load_kg=load_ton * 1000,
                distance_km=1.0,
                season=season,
                h2_source=h2_source,
            )
        )
        empty_per_km_g = float(
            carbon_per_segment(
                vtype=vtype,
                load_kg=0.0,
                distance_km=1.0,
                season=season,
                h2_source=h2_source,
            )
        )

        def arc_cost_callback(from_index: int, to_index: int) -> int:
            to_node = manager.IndexToNode(to_index)
            per_km_g = empty_per_km_g if to_node == depot else loaded_per_km_g
            return int(round(distance_km(from_index, to_index) * per_km_g))

        cb_idx = routing.RegisterTransitCallback(arc_cost_callback)
        evaluator_cache[key] = cb_idx
        return cb_idx

    for vehicle_pool_id in range(num_vehicles):
        vehicle_type = vehicle_types[vehicle_pool_id]
        load_ton = vehicle_load_ton[vehicle_pool_id]
        params = get_vehicle_params(vehicle_type) or {}
        routing.SetFixedCostOfVehicle(int(params.get("cold_start_g", 0) or 0), vehicle_pool_id)
        routing.SetArcCostEvaluatorOfVehicle(
            get_arc_cost_evaluator(vehicle_type, load_ton),
            vehicle_pool_id,
        )

    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    try:
        if int(time_limit_seconds) >= 30:
            search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        else:
            search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.AUTOMATIC
    except Exception:
        pass

    search_params.time_limit.FromSeconds(int(max(1, time_limit_seconds)))
    try:
        cpu_cnt = multiprocessing.cpu_count() or os.cpu_count() or 1
        search_params.num_search_workers = max(1, min(8, int(cpu_cnt)))
    except Exception:
        pass

    solution = routing.SolveWithParameters(search_params)
    if solution is None:
        return None

    routes: List[List[int]] = []
    vehicle_used_flags: List[bool] = []
    route_vehicle_ids: List[int] = []

    for vehicle_pool_id in range(num_vehicles):
        is_used = bool(routing.IsVehicleUsed(solution, vehicle_pool_id))
        vehicle_used_flags.append(is_used)
        if not is_used:
            continue

        index = routing.Start(vehicle_pool_id)
        route: List[int] = []
        while not routing.IsEnd(index):
            route.append(manager.IndexToNode(index))
            index = solution.Value(routing.NextVar(index))
        route.append(manager.IndexToNode(index))
        routes.append(route)
        route_vehicle_ids.append(vehicle_pool_id)

    vehicle_capacities_kg = [capacity // CAPACITY_MULTIPLIER for capacity in vehicle_capacities_scaled]
    refined_routes, refined_route_vehicle_ids, refinement_meta = _refine_routes_with_exact_carbon(
        routes=routes,
        route_vehicle_ids=route_vehicle_ids,
        vehicle_types=vehicle_types,
        vehicle_capacities_kg=vehicle_capacities_kg,
        distance_matrix_km=distance_matrix_km,
        demands_kg=demands_kg,
        depot=depot,
        season=season,
        h2_source=h2_source,
        time_limit_seconds=time_limit_seconds,
    )

    active_vehicle_ids = [int(vehicle_pool_id) for vehicle_pool_id in refined_route_vehicle_ids]
    refined_vehicle_used_flags = [False] * num_vehicles
    for vehicle_pool_id in active_vehicle_ids:
        refined_vehicle_used_flags[vehicle_pool_id] = True

    fleet_used_by_type_capacity = build_vehicle_pool_summary(
        vehicle_types,
        vehicle_capacities_kg,
        active_vehicle_ids=active_vehicle_ids,
        name_resolver=_get_vehicle_display_name,
    )
    used_count_by_type = build_count_by_type(fleet_used_by_type_capacity)

    return {
        "success": True,
        "routes": refined_routes,
        "route_vehicle_ids": refined_route_vehicle_ids,
        "num_vehicles_pool": num_vehicles,
        "num_vehicles_used": len(refined_route_vehicle_ids),
        "vehicle_used_flags": refined_vehicle_used_flags,
        "vehicle_types": vehicle_types,
        "vehicle_capacities_kg": vehicle_capacities_kg,
        "active_vehicle_ids": active_vehicle_ids,
        "fleet_used_by_type": used_count_by_type,
        "fleet_used_by_type_capacity": fleet_used_by_type_capacity,
        "cost_model": _SOLVER_COST_MODEL,
        "refinement_meta": refinement_meta,
    }


if __name__ == "__main__":
    pass
