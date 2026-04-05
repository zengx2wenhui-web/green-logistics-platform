"""高德地图API工具模块"""
import requests
import time
import logging
import math
from typing import Tuple, Optional, List, Dict
from threading import Lock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 请求频率限制：每秒最多10次
_rate_limiter_lock = Lock()
_request_timestamps: list = []
_RATE_LIMIT = 10  # 每秒请求数上限


def _acquire_rate_limit() -> None:
    """获取请求令牌，超过限制则等待"""
    global _request_timestamps
    current_time = time.time()

    with _rate_limiter_lock:
        # 清理1秒前的所有时间戳
        _request_timestamps = [ts for ts in _request_timestamps if current_time - ts < 1.0]

        if len(_request_timestamps) >= _RATE_LIMIT:
            # 需要等待
            sleep_time = 1.0 - (current_time - _request_timestamps[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
            # 重新清理
            current_time = time.time()
            _request_timestamps = [ts for ts in _request_timestamps if current_time - ts < 1.0]

        _request_timestamps.append(time.time())


def haversine_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """
    用Haversine公式计算两个经纬度之间的直线距离(km)

    Args:
        coord1: 起点坐标 (lng, lat)
        coord2: 终点坐标 (lng, lat)

    Returns:
        直线距离，单位 km
    """
    R = 6371.0
    lon1, lat1 = math.radians(coord1[0]), math.radians(coord1[1])
    lon2, lat2 = math.radians(coord2[0]), math.radians(coord2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def geocode(address: str, api_key: str) -> Optional[Tuple[float, float]]:
    """
    调用高德地理编码API，将地址转换为经纬度坐标

    Args:
        address: 地址字符串，如"广州市天河区体育西路"
        api_key: 高德地图API密钥

    Returns:
        (lng, lat) 元组，失败返回None

    Example:
        >>> result = geocode("广州市天河区体育西路", "your_api_key")
        >>> if result:
        ...     lng, lat = result
    """
    if not address or not address.strip():
        logger.error("[高德地理编码] 地址不能为空")
        print("[高德地理编码] 错误: 地址不能为空")
        return None

    if not api_key or not api_key.strip():
        logger.error("[高德地理编码] API密钥不能为空")
        print("[高德地理编码] 错误: API密钥不能为空")
        return None

    url = "https://restapi.amap.com/v3/geocode/geo"
    params = {
        "key": api_key,
        "address": address.strip()
    }

    try:
        _acquire_rate_limit()
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        status = data.get("status")
        if status is None:
            logger.error("[高德地理编码] API返回格式异常，缺少status字段")
            print("[高德地理编码] 错误: API返回格式异常")
            return None

        if status != "1":
            errcode = data.get("errcode", "")
            errmsg = data.get("errmsg", "未知错误")
            logger.error(f"[高德地理编码] API调用失败: {errcode} - {errmsg}")
            print(f"[高德地理编码] 错误: API调用失败 ({errcode})")
            return None

        geocodes = data.get("geocodes", [])
        if not geocodes:
            logger.warning(f"[高德地理编码] 未找到地址对应的坐标: {address}")
            print(f"[高德地理编码] 警告: 未找到该地址的坐标信息: {address}")
            return None

        location = geocodes[0].get("location", "")
        if not location:
            logger.error("[高德地理编码] 返回的坐标字段为空")
            print("[高德地理编码] 错误: 返回的坐标字段为空")
            return None

        lng, lat = location.split(",")
        lng, lat = float(lng), float(lat)

        logger.info(f"[高德地理编码] 成功: {address} -> ({lng}, {lat})")
        return (lng, lat)

    except requests.exceptions.Timeout:
        logger.error("[高德地理编码] 请求超时(10秒)")
        print("[高德地理编码] 错误: 请求超时，请检查网络连接")
        return None
    except requests.exceptions.ConnectionError:
        logger.error("[高德地理编码] 网络连接失败")
        print("[高德地理编码] 错误: 网络连接失败，请检查网络")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"[高德地理编码] HTTP错误: {e}")
        print(f"[高德地理编码] 错误: HTTP请求失败 ({e})")
        return None
    except (ValueError, IndexError) as e:
        logger.error(f"[高德地理编码] 数据解析失败: {e}")
        print("[高德地理编码] 错误: 坐标数据解析失败")
        return None
    except Exception as e:
        logger.error(f"[高德地理编码] 未知错误: {e}")
        print(f"[高德地理编码] 错误: 未知错误 ({e})")
        return None


def reverse_geocode(lng: float, lat: float, api_key: str) -> str:
    """
    调用高德逆地理编码API，把经纬度转换为具体地址。

    Args:
        lng: 经度
        lat: 纬度
        api_key: 高德地图API密钥

    Returns:
        地址字符串，失败返回 "未知地址(经度, 纬度)"
    """
    if not api_key or not api_key.strip():
        return f"未知地址({lng:.4f}, {lat:.4f})"

    url = "https://restapi.amap.com/v3/geocode/regeo"
    params = {
        "key": api_key,
        "location": f"{lng},{lat}",
        "extensions": "base",
        "output": "json"
    }

    try:
        _acquire_rate_limit()
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("status") == "1" and data.get("regeocode"):
            address = data["regeocode"].get("formatted_address", "")
            if address:
                return address
        return f"未知地址({lng:.4f}, {lat:.4f})"
    except Exception as e:
        logger.error(f"[高德逆地理编码] 错误: {e}")
        return f"未知地址({lng:.4f}, {lat:.4f})"


def get_driving_distance(
    origin: Tuple[float, float],
    destination: Tuple[float, float],
    api_key: str
) -> Optional[Tuple[float, float]]:
    """
    调用高德路径规划API，获取驾车距离和时间

    Args:
        origin: 起点坐标 (lng, lat)，如 (113.2644, 23.1291)
        destination: 终点坐标 (lng, lat)，如 (113.2650, 23.1320)
        api_key: 高德地图API密钥

    Returns:
        (distance_km, duration_min) 元组，失败返回None

    Example:
        >>> result = get_driving_distance(
        ...     (113.2644, 23.1291),
        ...     (113.2650, 23.1320),
        ...     "your_api_key"
        ... )
        >>> if result:
        ...     distance, duration = result
    """
    if not origin or len(origin) != 2:
        logger.error("[高德路径规划] 起点坐标格式错误")
        print("[高德路径规划] 错误: 起点坐标格式错误，应为(lng, lat)")
        return None

    if not destination or len(destination) != 2:
        logger.error("[高德路径规划] 终点坐标格式错误")
        print("[高德路径规划] 错误: 终点坐标格式错误，应为(lng, lat)")
        return None

    if not api_key or not api_key.strip():
        logger.error("[高德路径规划] API密钥不能为空")
        print("[高德路径规划] 错误: API密钥不能为空")
        return None

    # 验证坐标范围
    lng1, lat1 = origin
    lng2, lat2 = destination

    if not (73.0 <= lng1 <= 135.0 and 3.0 <= lat1 <= 54.0):
        logger.error(f"[高德路径规划] 起点坐标超出中国范围: {origin}")
        print(f"[高德路径规划] 错误: 起点坐标超出中国范围: {origin}")
        return None

    if not (73.0 <= lng2 <= 135.0 and 3.0 <= lat2 <= 54.0):
        logger.error(f"[高德路径规划] 终点坐标超出中国范围: {destination}")
        print(f"[高德路径规划] 错误: 终点坐标超出中国范围: {destination}")
        return None

    url = "https://restapi.amap.com/v3/direction/driving"
    params = {
        "key": api_key,
        "origin": f"{origin[0]},{origin[1]}",
        "destination": f"{destination[0]},{destination[1]}"
    }

    try:
        _acquire_rate_limit()
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        status = data.get("status")
        if status is None:
            logger.error("[高德路径规划] API返回格式异常，缺少status字段")
            print("[高德路径规划] 错误: API返回格式异常")
            return None

        if status != "1":
            errcode = data.get("errcode", "")
            errmsg = data.get("errmsg", "未知错误")
            logger.error(f"[高德路径规划] API调用失败: {errcode} - {errmsg}")
            print(f"[高德路径规划] 错误: API调用失败 ({errcode})")
            return None

        route = data.get("route", {})
        if not route:
            logger.warning("[高德路径规划] 未找到可行路线")
            print("[高德路径规划] 警告: 两点间没有可行的驾车路线")
            return None

        paths = route.get("paths", [])
        if not paths:
            logger.warning("[高德路径规划] 路径结果为空")
            print("[高德路径规划] 警告: 未找到路径规划结果")
            return None

        # 取最优路径（第一条，策略已内置）
        path = paths[0]

        distance_str = path.get("distance", "0")
        duration_str = path.get("duration", "0")

        try:
            distance_km = float(distance_str) / 1000  # 米转公里
            duration_min = float(duration_str) / 60   # 秒转分钟
        except (ValueError, TypeError) as e:
            logger.error(f"[高德路径规划] 距离/时间数据解析失败: {e}")
            print("[高德路径规划] 错误: 距离/时间数据解析失败")
            return None

        logger.info(f"[高德路径规划] 成功: {origin} -> {destination}, 距离{distance_km:.2f}km, 时间{duration_min:.1f}分钟")
        return (distance_km, duration_min)

    except requests.exceptions.Timeout:
        logger.error("[高德路径规划] 请求超时(10秒)")
        print("[高德路径规划] 错误: 请求超时，请检查网络连接")
        return None
    except requests.exceptions.ConnectionError:
        logger.error("[高德路径规划] 网络连接失败")
        print("[高德路径规划] 错误: 网络连接失败，请检查网络")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"[高德路径规划] HTTP错误: {e}")
        print(f"[高德路径规划] 错误: HTTP请求失败 ({e})")
        return None
    except Exception as e:
        logger.error(f"[高德路径规划] 未知错误: {e}")
        print(f"[高德路径规划] 错误: 未知错误 ({e})")
        return None
