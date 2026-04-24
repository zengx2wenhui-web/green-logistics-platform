# 车辆参数库
from typing import Any

# 季节修正
SEASON_FACTOR = {
    'spring': 1.00,
    'summer': 1.20,
    'autumn': 1.05,
    'winter': 1.10
}
 
# 氢气来源对 FCEV 碳排强度的影响
H2_INTENSITY = {
    'grey':       100,   # 灰氢：最差情形
    'byproduct':  35,    # 工业副产氢：广东主流
    'green':      15,    # 绿氢：最优
}

SEASON_ALIASES = {
    "spring": "spring",
    "春": "spring",
    "春季": "spring",
    "summer": "summer",
    "夏": "summer",
    "夏季": "summer",
    "autumn": "autumn",
    "fall": "autumn",
    "秋": "autumn",
    "秋季": "autumn",
    "winter": "winter",
    "冬": "winter",
    "冬季": "winter",
}

H2_SOURCE_ALIASES = {
    "grey": "grey",
    "gray": "grey",
    "灰氢": "grey",
    "byproduct": "byproduct",
    "工业副产氢": "byproduct",
    "副产氢": "byproduct",
    "green": "green",
    "绿氢": "green",
}
 
VEHICLE_LIB = {
    'diesel': {
        'name':                '柴油重卡（传统）',
        'gvw_range':           (12, 49),       
        'load_range_ton':      (8, 35),        
        'intensity_g_per_tkm': 60,            
        'empty_g_per_km':      312,            
        'full_chain_range':    (780, 1180),    
        'cold_start_g':        3500,
        'is_new_energy':       False,
        'reduction_vs_diesel': 0,           
    },
    'lng': {
        'name':                'LNG 天然气',
        'gvw_range':           (12, 49),
        'load_range_ton':      (7, 22),
        'intensity_g_per_tkm': 38,
        'empty_g_per_km':      276,
        'full_chain_range':    (690, 890),
        'cold_start_g':        3500,
        'is_new_energy':       False,
        'reduction_vs_diesel': 0.15,
    },
    'hev': {
        'name':                '柴电混动 HEV',
        'gvw_range':           (12, 25),
        'load_range_ton':      (8, 15),
        'intensity_g_per_tkm': 42,
        'empty_g_per_km':      260,
        'full_chain_range':    (650, 830),
        'cold_start_g':        2000,
        'is_new_energy':       True,
        'reduction_vs_diesel': 0.20,
    },
    'phev': {
        'name':                '插电混动 PHEV',
        'gvw_range':           (18, 40),
        'load_range_ton':      (10, 20),
        'intensity_g_per_tkm': 25,
        'empty_g_per_km':      192,
        'full_chain_range':    (480, 720),
        'cold_start_g':        2000,
        'is_new_energy':       True,
        'reduction_vs_diesel': 0.33,
    },
    'bev': {
        'name':                '纯电动 BEV',
        'gvw_range':           (19, 44),
        'load_range_ton':      (12, 22),
        'intensity_g_per_tkm': 29,
        'empty_g_per_km':      164,
        'full_chain_range':    (410, 780),
        'cold_start_g':        100,
        'is_new_energy':       True,
        'reduction_vs_diesel': 0.60,
    },
    'fcev': {
        'name':                '氢燃料电池 FCEV',
        'gvw_range':           (25, 49),
        'load_range_ton':      (15, 25),
        'intensity_g_per_tkm': 35,       
        'empty_g_per_km':      184,
        'full_chain_range':    (460, 1600),
        'cold_start_g':        200,
        'is_new_energy':       True,
        'reduction_vs_diesel': 0.50,
    },
}


# 获取车辆完整参数对象
def get_vehicle_params(vtype):
    return VEHICLE_LIB.get(vtype, None)


def _normalize_with_aliases(raw_value: Any, alias_map: dict[str, str], default_key: str) -> str:
    if raw_value is None:
        return default_key

    text = str(raw_value).strip()
    if not text:
        return default_key

    return alias_map.get(text.lower(), alias_map.get(text, default_key))


def normalize_season(season: Any = "summer") -> str:
    return _normalize_with_aliases(season, SEASON_ALIASES, "summer")


def normalize_h2_source(h2_source: Any = "byproduct") -> str:
    return _normalize_with_aliases(h2_source, H2_SOURCE_ALIASES, "byproduct")


# 校验用户输入的载重是否在推荐区间内
def validate_load_input(vtype, load_ton):
    lo, hi = VEHICLE_LIB[vtype]['load_range_ton']
    if lo <= load_ton <= hi:
        return True, ""
    else:
        return False, f"载重 {load_ton}t 超出 {VEHICLE_LIB[vtype]['name']} 推荐区间 {lo}-{hi}t"
 
# 获取碳排强度，FCEV按氢源动态切换
def get_intensity(vtype, h2_source='byproduct'):
    if vtype == 'fcev':
        return H2_INTENSITY[normalize_h2_source(h2_source)]
    return VEHICLE_LIB[vtype]['intensity_g_per_tkm']
 
 # 单段碳排计算
def carbon_per_segment(vtype, load_kg, distance_km,
                       season='summer', h2_source='byproduct'):
    v = VEHICLE_LIB[vtype]
    normalized_season = normalize_season(season)
    if load_kg > 0:
        # 公式A：有货段
        intensity = get_intensity(vtype, h2_source)
        carbon = intensity * (load_kg / 1000) * distance_km
    else:
        # 公式B：空驶段
        carbon = v['empty_g_per_km'] * distance_km

    if v['is_new_energy']:
        carbon *= SEASON_FACTOR[normalized_season]
    
    return carbon
