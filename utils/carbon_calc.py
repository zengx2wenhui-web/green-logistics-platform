from typing import Dict, List
import logging
import pandas as pd

from utils.vehicle_lib import get_vehicle_params, carbon_per_segment, SEASON_MAP, VEHICLE_LIB

logger = logging.getLogger(__name__)


# ===================== 全局电网与基准参数 =====================

# 广东电网碳排放强度（kg CO₂/kWh），用于 BEV 间接排放核算
GUANGDONG_GRID_INTENSITY: float = 0.50
# 全国平均电网碳排放强度
NATIONAL_GRID_INTENSITY: float = 0.60
# 碳排放强度阈值（kg CO₂/吨·km），超过即建议优化
_HIGH_INTENSITY_THRESHOLD: float = 0.080


# ===================== 动态获取排放因子 =====================

def get_emission_factor(vehicle_type: str, season: str = "夏", h2_source: str = "工业副产氢") -> float:
    """
    获取指定车型的碳排放因子（kg CO₂/吨·km）。

    使用 vehicle_lib 中的参数，支持季节调整（仅新能源车）和氢源调整（FCEV）。
    """
    clean_vtype = vehicle_type.split('_')[0].lower()
    params = get_vehicle_params(clean_vtype)
    season_key = SEASON_MAP.get(season, 'summer')
    
    # FCEV 特殊处理氢源
    if clean_vtype == "fcev":
        from utils.vehicle_lib import H2_INTENSITY
        intensity_g = H2_INTENSITY.get(h2_source, 35)
    else:
        intensity_g = params.get("intensity_g_per_tkm", 60)
    
    # 转换为 kg CO₂/吨·km
    base_ef = intensity_g / 1000.0
    
    # 新能源车季节修正
    if params.get("is_new_energy", False):
        from utils.vehicle_lib import SEASON_FACTOR
        base_ef *= SEASON_FACTOR.get(season_key, 1.00)
    
    return base_ef


# ===================== 核心碳排放计算 =====================

def calc_emission(
    distance_km: float,
    load_kg: float,
    vehicle_type: str = "diesel_heavy",
    season: str = "夏",
    h2_source: str = "工业副产氢",
) -> float:
    """
    单段碳排放计算（对接双公式）。
    
    载重大于 0 时按有载算，载重等于 0 时按空驶算。
    """
    # 距离非法或载重为负时不计算（允许 load_kg == 0 作为空驶）
    if distance_km <= 0 or load_kg < 0:
        return 0.0
        
    clean_vtype = vehicle_type.split('_')[0].lower()
    
    # 使用 vehicle_lib 的双公式计算，返回 g，转为 kg
    carbon_g = carbon_per_segment(
        vtype=clean_vtype, 
        load_kg=load_kg, 
        distance_km=distance_km, 
        season=season, 
        h2_source=h2_source
    )
    return carbon_g / 1000.0


def calc_trunk_emission(
    distance_km: float,
    total_weight_kg: float,
    vehicle_type: str = "diesel_heavy",
    season: str = "夏",
    h2_source: str = "工业副产氢",
) -> float:
    """
    干线运输碳排放计算（总仓 → 中转仓，满载直达）。
    干线场景下以总调拨重量作为载重，包含单次冷启动碳排。
    """
    clean_vtype = vehicle_type.split('_')[0].lower()
    params = get_vehicle_params(clean_vtype)
    
    # 包含该车型的冷启动碳排
    cold_start_kg = params.get("cold_start_g", 0) / 1000.0
    running_carbon_kg = calc_emission(distance_km, total_weight_kg, vehicle_type, season, h2_source)
    
    return cold_start_kg + running_carbon_kg


def calc_terminal_emission(
    distances: List[float],
    demands_kg: List[float],
    vehicle_capacity_kg: float,
    vehicle_type: str = "diesel_heavy",
    season: str = "夏",
    h2_source: str = "工业副产氢",
) -> Dict[str, object]:
    """末端配送碳排放计算（中转仓 → 各配送点，逐站卸货载重递减）。"""
    current_load_kg = min(sum(demands_kg), vehicle_capacity_kg)
    segments: List[Dict[str, float]] = []
    total_carbon = 0.0

    for i, dist in enumerate(distances):
        # 使用双公式计算
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
    }


def compute_route_emission(
    distances: List[float],
    demands_kg: List[float],
    vehicle_type: str = "diesel_heavy",
    season: str = "夏",
    h2_source: str = "工业副产氢",
    include_cold_start: bool = True,
) -> Dict[str, object]:
    """按路径分段计算整条路线的碳排放（包含冷启动 + 实际起始载重）。"""
    clean_vtype = vehicle_type.split('_')[0].lower()
    params = get_vehicle_params(clean_vtype)
    
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
        
        if i < len(demands_kg):
            current_load_kg -= demands_kg[i]
            current_load_kg = max(current_load_kg, 0.0)

    return {
        "total_carbon_kg": round(total_carbon, 4),
        "segments": segments,
        "total_distance_km": round(sum(distances), 2),
        "initial_load_kg": sum(demands_kg),
    }


def calc_route_carbon(
    distance_km: float,
    load_kg: float = 0.0,
    vehicle_type: str = "diesel_heavy",
    season: str = "夏",
    h2_source: str = "工业副产氢",
) -> float:
    """考虑载重的单路段碳排放（兼容旧接口）。"""
    return calc_emission(distance_km, load_kg, vehicle_type, season, h2_source)


def calc_total_carbon(
    route_distances: List[float],
    route_loads: List[float],
    vehicle_type: str = "diesel_heavy",
    season: str = "夏",
    h2_source: str = "工业副产氢",
) -> Dict[str, float]:
    """计算多路段碳排放汇总。"""
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
            round(total_emission / total_distance, 4)
            if total_distance > 0 else 0.0
        ),
        "route_count": len(route_distances),
    }


# ===================== 碳排放等价物 =====================

def carbon_to_trees(carbon_kg: float) -> float:
    """将碳排放量换算为等效树木年吸收量（12 kg CO₂/棵·年）。"""
    annual_absorption_per_tree = 12.0
    if annual_absorption_per_tree <= 0:
        return 0.0
    return carbon_kg / annual_absorption_per_tree


def carbon_equivalents(carbon_kg: float) -> Dict[str, float]:
    """将碳排放转换为多种易感知的环保等价物。"""
    return {
        "trees_per_year": round(carbon_kg / 12.0, 1),
        "household_months": round(carbon_kg / 180.0, 1),
        "car_years": round(carbon_kg / 2400.0, 2),
        "gasoline_liters": round(carbon_kg / 2.3, 1),
        "electricity_kwh": round(carbon_kg / 0.6, 1),
    }


# ===================== 碳排放强度标签 =====================

def get_carbon_intensity_label(carbon_per_ton_km: float) -> str:
    """根据碳排放强度（kg CO₂/吨·km）返回等级标签。"""
    if carbon_per_ton_km < 0.030:
        return "🟢 优秀（新能源领先）"
    elif carbon_per_ton_km < 0.045:
        return "🟢 良好"
    elif carbon_per_ton_km < 0.060:
        return "🟡 达标"
    elif carbon_per_ton_km < 0.080:
        return "🟠 偏高"
    else:
        return "🔴 需优化"


# ===================== 优化建议生成 =====================

def generate_optimization_suggestions(
    total_carbon_kg: float,
    vehicle_type: str,
    avg_load_rate: float = 0.5, # 保留为了接口兼容，内部不再使用
    total_distance_km: float = 0.0,
) -> List[str]:
    """根据实际碳排放数据生成优化建议（已清理伪装载率命题）。"""
    suggestions: List[str] = []
    
    current_ef = get_emission_factor(vehicle_type)

    TYPE_MAPPING = {
        "diesel": "柴油重卡",
        "lng": "LNG天然气重卡",
        "hev": "混合动力 (HEV)",
        "phev": "插电混动 (PHEV)",
        "bev": "纯电动 (BEV)",
        "fcev": "氢燃料电池 (FCEV)",
    }

    # 1. 车型替换建议：动态从 VEHICLE_LIB 寻找更优解
    better_types = []
    for v_id, v_info in VEHICLE_LIB.items():
        v_ef = v_info.get("intensity_g_per_tkm", 0) / 1000.0
        if 0 < v_ef < current_ef:
             v_name = TYPE_MAPPING.get(v_id, v_id.upper())
             better_types.append((v_name, v_ef))
            
    if better_types:
        better_types.sort(key=lambda x: x[1])
        best_name, best_ef = better_types[0]
        reduction_pct = (1 - best_ef / current_ef) * 100
        suggestions.append(
            f"当前车队包含高碳排车型，建议逐步替换为 [{best_name}]，"
            f"长远来看预计可实现 {reduction_pct:.0f}% 的综合减排。"
        )

    # 2. 实际调度优化建议（替代原先伪逻辑）
    suggestions.append(
        "当前系统已启用实际载荷动态核算。为进一步降低碳足迹，建议在实际调度中"
        "尽量减少车辆的去程空载或回程空驶率。"
    )

    # 3. 选址优化建议（更新为 K-Medoids）
    if total_distance_km > 500:
        suggestions.append(
            "总行驶距离较长，建议使用系统内置的 K-Medoids 全国候选仓规划功能，"
            "就近增设真实中转枢纽，有效缩短末端高频配送里程。"
        )

    if not suggestions:
        suggestions.append("当前方案碳排放指标良好，处于绿色物流领先水平。")

    return suggestions


# ===================== 碳排放报告 =====================

def generate_carbon_report(df_routes: pd.DataFrame) -> pd.DataFrame:
    """为路线 DataFrame 附加碳排放量与等级列。"""
    df = df_routes.copy()
    df["碳排放量_kg"] = df.apply(
        lambda row: calc_emission(
            row.get("distance_km", 0),
            row.get("load_kg", 0),
            row.get("vehicle_type", "diesel_heavy"),
        ),
        axis=1,
    )
    df["碳排放强度"] = df.apply(
        lambda row: (
            row["碳排放量_kg"] / row["distance_km"] / (row.get("load_kg", 1) / 1000)
            if row.get("distance_km", 0) > 0 and row.get("load_kg", 0) > 0
            else 0.0
        ),
        axis=1,
    )
    df["碳排放等级"] = df["碳排放强度"].apply(get_carbon_intensity_label)
    return df