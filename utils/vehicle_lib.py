"""
车辆碳排放参数库

集中管理各类车辆的碳排放计算参数，包括季节因子、氢源强度、车辆参数字典等。
"""

from typing import Dict, Any

# ===================== 季节修正因子 =====================
# 仅对新能源车应用，柴油/LNG 基本不受季节影响
SEASON_FACTOR: Dict[str, float] = {
    'spring': 1.00,
    'summer': 1.20,   # 广东夏季高温高湿
    'autumn': 1.05,
    'winter': 1.10    # 冬季制热（广东冬季温和，影响较小）
}

# ===================== 氢源碳排放强度 =====================
# 单位: g CO₂/kg H₂（全链排放）
H2_INTENSITY: Dict[str, float] = {
    "灰氢": 100,
    "工业副产氢": 35,
    "绿氢": 15
}

# ===================== 车辆参数库 =====================
# 单位说明：
# - intensity_g_per_tkm: g CO₂/吨·km（有载碳排强度）
# - empty_g_per_km: g CO₂/km（空驶碳排强度）
# - cold_start_g: g CO₂（冷启动碳排）
# - is_new_energy: 是否新能源车（影响季节修正）
VEHICLE_LIB: Dict[str, Dict[str, Any]] = {
    "diesel": {
        "intensity_g_per_tkm": 60,
        "empty_g_per_km": 6.0,  # 假设空驶为有载的10%
        "cold_start_g": 3500,
        "is_new_energy": False
    },
    "lng": {
        "intensity_g_per_tkm": 38,
        "empty_g_per_km": 3.8,
        "cold_start_g": 3500,
        "is_new_energy": False
    },
    "hev": {
        "intensity_g_per_tkm": 42,
        "empty_g_per_km": 4.2,
        "cold_start_g": 2000,
        "is_new_energy": True
    },
    "phev": {
        "intensity_g_per_tkm": 25,
        "empty_g_per_km": 2.5,
        "cold_start_g": 2000,
        "is_new_energy": True
    },
    "bev": {
        "intensity_g_per_tkm": 29,
        "empty_g_per_km": 2.9,
        "cold_start_g": 100,
        "is_new_energy": True
    },
    "fcev": {
        "intensity_g_per_tkm": 35,  # 默认工业副产氢，将根据氢源调整
        "empty_g_per_km": 3.5,
        "cold_start_g": 200,
        "is_new_energy": True
    }
}

# ===================== 季节映射 =====================
SEASON_MAP: Dict[str, str] = {
    '春': 'spring',
    '夏': 'summer',
    '秋': 'autumn',
    '冬': 'winter'
}

def get_vehicle_params(vtype: str) -> Dict[str, Any]:
    """
    获取指定车型的参数。

    Args:
        vtype: 车辆类型 (diesel, lng, hev, phev, bev, fcev)

    Returns:
        车辆参数字典
    """
    return VEHICLE_LIB.get(vtype.lower(), VEHICLE_LIB["diesel"])

def carbon_per_segment(vtype: str, load_kg: float, distance_km: float, season: str = "夏", h2_source: str = "工业副产氢") -> float:
    """
    计算单段碳排放（支持双公式：有载/空驶）。

    Args:
        vtype: 车辆类型
        load_kg: 载重 (kg)，>0 为有载，=0 为空驶
        distance_km: 距离 (km)
        season: 季节 (春/夏/秋/冬)
        h2_source: 氢源 (仅FCEV有效)

    Returns:
        碳排放量 (g CO₂)
    """
    params = get_vehicle_params(vtype)
    season_key = SEASON_MAP.get(season, 'summer')

    # FCEV 特殊处理氢源
    if vtype.lower() == "fcev":
        intensity = H2_INTENSITY.get(h2_source, 35)
    else:
        intensity = params["intensity_g_per_tkm"]

    # 双公式计算
    if load_kg > 0:
        # 有载：强度 * 载重吨 * 距离
        carbon = intensity * (load_kg / 1000) * distance_km
    else:
        # 空驶：空驶强度 * 距离
        carbon = params["empty_g_per_km"] * distance_km

    # 新能源车季节修正
    if params["is_new_energy"]:
        carbon *= SEASON_FACTOR.get(season_key, 1.00)

    return carbon