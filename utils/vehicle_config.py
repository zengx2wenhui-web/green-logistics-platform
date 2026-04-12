"""车型库统一加载模块

所有需要读取 vehicle_types.json 的模块统一从此处导入，消除重复代码。
"""
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_vehicle_types_cache: Optional[Dict[str, Dict]] = None


def load_vehicle_types() -> List[Dict]:
    """从 JSON 文件加载车型库列表。"""
    for path in ("data/vehicle_types.json",
                 "green-logistics-platform/data/vehicle_types.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "vehicle_types" in data:
                    return data["vehicle_types"]
                return data
        except FileNotFoundError:
            continue
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"[车型库] 解析失败({path}): {e}")
            continue
    logger.warning("[车型库] 未找到 vehicle_types.json，返回空列表")
    return []


def get_vehicle_params(vehicle_type_id: str) -> Dict:
    """
    获取指定车型的碳排放参数。

    Args:
        vehicle_type_id: 车型 ID，如 "diesel_heavy"、"bev"

    Returns:
        {"emission_factor": ..., "max_load_ton": ..., "fuel_consumption": ...}
    """
    global _vehicle_types_cache
    if _vehicle_types_cache is None:
        _vehicle_types_cache = {v["id"]: v for v in load_vehicle_types()}

    vehicle = _vehicle_types_cache.get(vehicle_type_id, {})
    return {
        "emission_factor": vehicle.get("emission_factor_default", 0.060),
        "max_load_ton": vehicle.get("max_load_ton_default", 15.0),
        "fuel_consumption": vehicle.get("fuel_consumption", "N/A"),
    }
