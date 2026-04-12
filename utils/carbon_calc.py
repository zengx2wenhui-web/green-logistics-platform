"""碳排放计算工具模块

基于绿色物流标准公式 E = d(a,b) × e_f × L(a,b) 进行碳排放核算。
支持多车型碳因子、区域电网碳强度差异、干线 / 末端分段计算。

核心优化：
- 废弃 "基准排放 × 惩罚系数" 粗略算法，采用精准乘积公式
- 车型碳因子直接引用 vehicle_types.json（含全链排放）
- 树木年吸收量修正为 12 kg CO₂/棵·年（中国林科院参考值）
- 新增碳排放强度诊断与优化建议输出
"""
from typing import Dict, List
import logging

import pandas as pd

from utils.vehicle_config import load_vehicle_types as _load_raw_vehicle_types

logger = logging.getLogger(__name__)

# ===================== 十五运会专项碳排放因子字典 =====================
# 单位: kg CO₂/吨·km（全链排放，含间接能耗）
# 数据来源: vehicle_types.json + IPCC + 中国碳核算数据库
FIFTEENTH_GAMES_EMISSION_FACTORS: Dict[str, float] = {
    "diesel_heavy": 0.060,
    "lng":          0.038,
    "hev":          0.042,
    "phev":         0.025,
    "bev":          0.029,
    "fcev":         0.069,
}

# 广东电网碳排放强度（kg CO₂/kWh），用于 BEV 间接排放核算
GUANGDONG_GRID_INTENSITY: float = 0.50
# 全国平均电网碳排放强度
NATIONAL_GRID_INTENSITY: float = 0.60

# 碳排放强度阈值（kg CO₂/吨·km），超过即建议优化
_HIGH_INTENSITY_THRESHOLD: float = 0.080


# ===================== 动态加载车型库 =====================

def _load_vehicle_types() -> Dict[str, Dict]:
    """从 vehicle_types.json 加载车型参数并索引。"""
    vehicles = _load_raw_vehicle_types()
    if vehicles:
        return {v["id"]: v for v in vehicles}
    logger.warning("[车型库] 未找到车型数据，使用内置默认因子")
    return {}


_VEHICLE_LIB: Dict[str, Dict] = _load_vehicle_types()


def get_emission_factor(vehicle_type: str) -> float:
    """
    获取指定车型的碳排放因子（kg CO₂/吨·km）。

    优先从车型库文件读取，其次使用十五运会专项因子表，最后使用柴油重卡默认值。
    """
    vehicle = _VEHICLE_LIB.get(vehicle_type)
    if vehicle:
        return vehicle.get("emission_factor_default", 0.060)
    return FIFTEENTH_GAMES_EMISSION_FACTORS.get(vehicle_type, 0.060)


# ===================== 核心碳排放计算 =====================

def calc_emission(
    distance_km: float,
    load_kg: float,
    vehicle_type: str = "diesel_heavy",
) -> float:
    """
    单段碳排放计算（标准公式）。

    公式: E = distance_km × emission_factor × load_ton

    Args:
        distance_km: 行驶距离（km）
        load_kg: 当前载重（kg）
        vehicle_type: 车型 ID

    Returns:
        碳排放量（kg CO₂）
    """
    if distance_km <= 0 or load_kg <= 0:
        return 0.0
    ef = get_emission_factor(vehicle_type)
    load_ton = load_kg / 1000.0
    return distance_km * ef * load_ton


def calc_trunk_emission(
    distance_km: float,
    total_weight_kg: float,
    vehicle_type: str = "diesel_heavy",
) -> float:
    """
    干线运输碳排放计算（总仓 → 中转仓，满载直达）。

    干线场景下以总调拨重量作为载重，不涉及逐站卸货。

    Args:
        distance_km: 干线距离（km）
        total_weight_kg: 批量调拨总重（kg）
        vehicle_type: 车型 ID

    Returns:
        干线碳排放（kg CO₂）
    """
    return calc_emission(distance_km, total_weight_kg, vehicle_type)


def calc_terminal_emission(
    distances: List[float],
    demands_kg: List[float],
    vehicle_capacity_kg: float,
    vehicle_type: str = "diesel_heavy",
) -> Dict[str, object]:
    """
    末端配送碳排放计算（中转仓 → 各配送点，逐站卸货载重递减）。

    Args:
        distances: 路线中各段距离列表（km），长度 = 节点数 - 1
        demands_kg: 各配送节点的需求量列表（kg），与路线中非仓库节点对应
        vehicle_capacity_kg: 车辆载重上限（kg）
        vehicle_type: 车型 ID

    Returns:
        {"total_carbon_kg": ..., "segments": [...]}
    """
    ef = get_emission_factor(vehicle_type)
    current_load_kg = min(sum(demands_kg), vehicle_capacity_kg)
    segments: List[Dict[str, float]] = []
    total_carbon = 0.0

    for i, dist in enumerate(distances):
        load_ton = current_load_kg / 1000.0
        carbon = dist * ef * load_ton
        segments.append({
            "segment_idx": i,
            "distance_km": dist,
            "load_kg": current_load_kg,
            "carbon_kg": round(carbon, 4),
        })
        total_carbon += carbon
        # 到达节点后卸货
        if i < len(demands_kg):
            current_load_kg -= demands_kg[i]
            current_load_kg = max(current_load_kg, 0.0)

    return {
        "total_carbon_kg": round(total_carbon, 4),
        "segments": segments,
    }


def calc_route_carbon(
    distance_km: float,
    load_kg: float = 0.0,
    vehicle_type: str = "diesel_heavy",
) -> float:
    """
    考虑载重的单路段碳排放（兼容旧接口）。

    采用标准公式，不再使用惩罚系数近似。
    """
    return calc_emission(distance_km, load_kg, vehicle_type)


def calc_total_carbon(
    route_distances: List[float],
    route_loads: List[float],
    vehicle_type: str = "diesel_heavy",
) -> Dict[str, float]:
    """
    计算多路段碳排放汇总。

    Args:
        route_distances: 各路段距离（km）
        route_loads: 各路段起始载重（kg）
        vehicle_type: 车型 ID

    Returns:
        包含总距离、总碳排放、平均碳效率等的字典
    """
    total_distance = sum(route_distances)
    emissions = [
        calc_emission(d, load, vehicle_type)
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
    """
    将碳排放量换算为等效树木年吸收量。

    参考值: 一棵成年树每年约吸收 12 kg CO₂（中国林科院参考值），
    而非此前错误的 5 kg/天。
    """
    annual_absorption_per_tree = 12.0  # kg CO₂/棵·年
    if annual_absorption_per_tree <= 0:
        return 0.0
    return carbon_kg / annual_absorption_per_tree


def carbon_equivalents(carbon_kg: float) -> Dict[str, float]:
    """
    将碳排放转换为多种易感知的环保等价物。

    Args:
        carbon_kg: 碳排放量（kg CO₂）

    Returns:
        包含树木、家用电、小汽车年排放等效值的字典
    """
    return {
        # 树木年吸收量（12 kg CO₂/棵·年）
        "trees_per_year": round(carbon_kg / 12.0, 1),
        # 家庭月用电等效（中国 3 口之家月均 300 kWh × 0.6 kg/kWh = 180 kg）
        "household_months": round(carbon_kg / 180.0, 1),
        # 小汽车年排放等效（中国轿车年均 2400 kg CO₂）
        "car_years": round(carbon_kg / 2400.0, 2),
        # 汽油等效（每升约 2.3 kg CO₂）
        "gasoline_liters": round(carbon_kg / 2.3, 1),
        # 电力等效（全国平均 0.6 kg CO₂/kWh）
        "electricity_kwh": round(carbon_kg / 0.6, 1),
    }


# ===================== 碳排放强度标签 =====================

def get_carbon_intensity_label(carbon_per_ton_km: float) -> str:
    """
    根据碳排放强度（kg CO₂/吨·km）返回等级标签。

    评级标准参考十五运会各车型全链排放因子分布区间。
    """
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
    avg_load_rate: float = 0.5,
    total_distance_km: float = 0.0,
) -> List[str]:
    """
    根据碳排放数据自动生成优化建议。

    Args:
        total_carbon_kg: 总碳排放（kg CO₂）
        vehicle_type: 当前使用车型
        avg_load_rate: 平均装载率（0~1）
        total_distance_km: 总行驶距离（km）

    Returns:
        建议文本列表
    """
    suggestions: List[str] = []
    ef = get_emission_factor(vehicle_type)

    # 碳因子过高 → 推荐替换车型
    if ef >= _HIGH_INTENSITY_THRESHOLD:
        better_types = [
            (k, v) for k, v in FIFTEENTH_GAMES_EMISSION_FACTORS.items()
            if v < ef
        ]
        better_types.sort(key=lambda x: x[1])
        if better_types:
            best_id, best_ef = better_types[0]
            reduction_pct = (1 - best_ef / ef) * 100
            suggestions.append(
                f"当前车型 [{vehicle_type}] 碳因子偏高({ef} kg CO₂/吨·km)，"
                f"建议替换为 [{best_id}]（{best_ef}），预计减排 {reduction_pct:.0f}%"
            )

    # 装载率偏低 → 提升装载率
    if avg_load_rate < 0.6:
        suggestions.append(
            f"平均装载率仅 {avg_load_rate:.0%}，建议优化拼载策略，"
            f"将装载率提升至 80% 以上可降低单位碳排放约 {(1 - avg_load_rate / 0.8) * 100:.0f}%"
        )

    # 距离较长时建议增设中转仓
    if total_distance_km > 500:
        suggestions.append(
            "总行驶距离较长，建议通过 K-Means 聚类增设中转仓，缩短末端配送里程"
        )

    if not suggestions:
        suggestions.append("当前方案碳排放指标良好，暂无进一步优化建议")

    return suggestions


# ===================== 碳排放报告 =====================

def generate_carbon_report(df_routes: pd.DataFrame) -> pd.DataFrame:
    """
    为路线 DataFrame 附加碳排放量与等级列。

    期望 df_routes 至少含 distance_km、load_kg 列，可选 vehicle_type 列。
    """
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
