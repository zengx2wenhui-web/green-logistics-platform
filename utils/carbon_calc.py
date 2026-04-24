from typing import Dict, List
import logging
import pandas as pd

from utils.vehicle_lib import VEHICLE_LIB, carbon_per_segment, get_intensity

logger = logging.getLogger(__name__)

# 全局电网与基准参数 
GUANGDONG_GRID_INTENSITY: float = 0.50
NATIONAL_GRID_INTENSITY: float = 0.60
_HIGH_INTENSITY_THRESHOLD: float = 0.080


# 动态获取排放因子
def get_emission_factor(vehicle_type: str, h2_source: str = "byproduct") -> float:
    intensity_g = get_intensity(vehicle_type, h2_source)
    return intensity_g / 1000.0


# 核心碳排放计算
def calc_emission(
    distance_km: float,
    load_kg: float,
    vehicle_type: str = "diesel",
    season: str = "夏",
    h2_source: str = "byproduct",
) -> float:
    if distance_km <= 0 or load_kg < 0:
        return 0.0
    carbon_g = carbon_per_segment(vehicle_type, load_kg, distance_km, season, h2_source)
    return carbon_g / 1000.0


# 路线碳排计算（逐段卸货，载重递减）
def compute_route_emission(
    distances: List[float],
    demands_kg: List[float],
    vehicle_type: str = "diesel",
    season: str = "夏",
    h2_source: str = "byproduct",
    include_cold_start: bool = True,
) -> Dict[str, object]:
    params = VEHICLE_LIB.get(vehicle_type, VEHICLE_LIB["diesel"])
    total_carbon = 0.0
    segments: List[Dict[str, float]] = []
    current_load_kg = sum(demands_kg)
    if include_cold_start:
        total_carbon += params.get("cold_start_g", 0) / 1000.0

    for i, dist in enumerate(distances):
        carbon_kg = calc_emission(dist, current_load_kg, vehicle_type, season, h2_source)
        
        segments.append({
            "segment_idx": i,
            "distance_km": dist,
            "load_kg": current_load_kg,
            "carbon_kg": round(carbon_kg, 4),
        })
        total_carbon += carbon_kg
        
        # 到达节点后卸货
        if i < len(demands_kg):
            current_load_kg -= demands_kg[i]
            current_load_kg = max(current_load_kg, 0.0)

    return {
        "total_carbon_kg": round(total_carbon, 4),
        "segments": segments,
        "total_distance_km": round(sum(distances), 2),
        "initial_load_kg": sum(demands_kg),
    }


# 计算多路段碳排放快速汇总
def calc_total_carbon(
    route_distances: List[float],
    route_loads: List[float],
    vehicle_type: str = "diesel",
    season: str = "夏",
    h2_source: str = "byproduct",
) -> Dict[str, float]:
    total_distance = sum(route_distances)
    emissions = [
        calc_emission(d, load, vehicle_type, season, h2_source)
        for d, load in zip(route_distances, route_loads)
    ]
    total_emission = sum(emissions)

    return {
        "total_distance_km": round(total_distance, 2),
        "total_carbon_kg": round(total_emission, 4),
        "avg_carbon_per_km": (
            round(total_emission / total_distance, 4) if total_distance > 0 else 0.0
        ),
        "route_count": len(route_distances),
    }


# 碳排放等价物 
def carbon_equivalents(carbon_kg: float) -> Dict[str, float]:
    return {
        "trees_per_year": round(carbon_kg / 12.0, 1),
        "household_months": round(carbon_kg / 180.0, 1),
        "car_years": round(carbon_kg / 2400.0, 2),
        "gasoline_liters": round(carbon_kg / 2.3, 1),
        "electricity_kwh": round(carbon_kg / 0.6, 1),
    }


# 碳排放强度标签 
def get_carbon_intensity_label(carbon_per_ton_km: float) -> str:
    if carbon_per_ton_km < 0.030: return "🟢 优秀（新能源领先）"
    elif carbon_per_ton_km < 0.045: return "🟢 良好"
    elif carbon_per_ton_km < 0.060: return "🟡 达标"
    elif carbon_per_ton_km < 0.080: return "🟠 偏高"
    else: return "🔴 需优化"


# 优化建议生成 
def generate_optimization_suggestions(
    total_carbon_kg: float,
    vehicle_type: str,
    total_distance_km: float = 0.0,
) -> List[str]:
    suggestions: List[str] = []
    current_ef = get_emission_factor(vehicle_type)

    better_types = []
    for v_id, v_info in VEHICLE_LIB.items():
        v_ef = v_info.get("intensity_g_per_tkm", 60) / 1000.0
        if 0 < v_ef < current_ef:
            better_types.append((v_info["name"], v_ef))
            
    if better_types:
        better_types.sort(key=lambda x: x[1])
        best_name, best_ef = better_types[0]
        reduction_pct = (1 - best_ef / current_ef) * 100
        suggestions.append(
            f"当前车队包含高碳排车型，建议逐步替换为 [{best_name}]，"
            f"预计可实现 {reduction_pct:.0f}% 的单车综合减排。"
        )

    # 2. 实际调度优化建议
    suggestions.append(
        "当前系统已启用实际载荷动态核算。为进一步降低碳足迹，建议在实际调度中尽量减少车辆的去程空载或回程空驶率。"
    )

    # 3. 选址优化建议
    if total_distance_km > 500:
        suggestions.append(
            "总行驶距离较长，建议使用系统内置的 K-Medoids 全国候选仓规划功能，"
            "就近增设真实中转枢纽，有效缩短末端高频配送里程。"
        )

    if not suggestions:
        suggestions.append("当前方案碳排放指标良好，处于绿色物流领先水平。")

    return suggestions


# 碳排放报告 
def generate_carbon_report(df_routes: pd.DataFrame) -> pd.DataFrame:
    df = df_routes.copy()
    
    df["碳排放量_kg"] = df.apply(
        lambda row: calc_emission(
            distance_km=row.get("distance_km", 0),
            load_kg=row.get("load_kg", 0),
            vehicle_type=row.get("vehicle_type", "diesel")
        ), axis=1
    )
    
    df["碳排放强度"] = df.apply(
        lambda row: (row["碳排放量_kg"] / row["distance_km"] / (row.get("load_kg", 1) / 1000))
        if row.get("distance_km", 0) > 0 and row.get("load_kg", 0) > 0 else 0.0,
        axis=1
    )
    
    df["碳排放等级"] = df["碳排放强度"].apply(get_carbon_intensity_label)
    return df