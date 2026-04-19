"""高德地图 API 工具模块

提供地理编码、逆地理编码、驾车距离查询及批量距离测量功能。
核心优化：
- 指数退避重试机制，应对网络抖动
- SQLite 持久化缓存，保护每日 5000 次免费配额
- 批量距离测量 API（/v3/distance），大幅降低距离矩阵构建耗时
- 线程安全的令牌桶限流器（带超时上限）
"""
import requests
import time
import math
import sqlite3
import logging
from pathlib import Path
from typing import Tuple, Optional, List, Dict, Any
from threading import Lock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===================== 配置常量 =====================
_RATE_LIMIT: int = 10          # 每秒最大请求数
_RATE_LIMIT_MAX_WAIT: float = 5.0  # 限流最长等待时间（秒）
_MAX_RETRIES: int = 3          # 最大重试次数
_RETRY_BASE_DELAY: float = 1.0 # 重试基础延迟（秒）
_REQUEST_TIMEOUT: int = 10     # 单次请求超时（秒）
_CACHE_DB_PATH: Path = Path("data/cache/amap_cache.db")

# 中国经纬度合法范围
_LNG_RANGE: Tuple[float, float] = (73.0, 135.0)
_LAT_RANGE: Tuple[float, float] = (3.0, 54.0)

# ===================== 令牌桶限流器 =====================
_rate_limiter_lock = Lock()
_request_timestamps: List[float] = []


def _acquire_rate_limit() -> None:
    """线程安全的令牌桶限流器，超过 QPS 限制时阻塞等待（带超时上限）。"""
    global _request_timestamps
    with _rate_limiter_lock:
        now = time.time()
        _request_timestamps = [ts for ts in _request_timestamps if now - ts < 1.0]
        if len(_request_timestamps) >= _RATE_LIMIT:
            sleep_time = min(1.0 - (now - _request_timestamps[0]),
                             _RATE_LIMIT_MAX_WAIT)
            if sleep_time > 0:
                time.sleep(sleep_time)
            now = time.time()
            _request_timestamps = [ts for ts in _request_timestamps if now - ts < 1.0]
        _request_timestamps.append(time.time())


# ===================== SQLite 缓存层 =====================

_cache_conn: Optional[sqlite3.Connection] = None
_cache_lock = Lock()


def _get_cache_conn() -> sqlite3.Connection:
    """获取模块级 SQLite 缓存连接（单例）。"""
    global _cache_conn
    if _cache_conn is None:
        _CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _cache_conn = sqlite3.connect(str(_CACHE_DB_PATH), check_same_thread=False)
        _cache_conn.execute("""
            CREATE TABLE IF NOT EXISTS amap_cache (
                cache_key   TEXT PRIMARY KEY,
                namespace   TEXT,
                value1      REAL,
                value2      REAL
            )
        """)
        _cache_conn.commit()
    return _cache_conn


def _cache_read(namespace: str, key: str) -> Optional[Tuple[float, float]]:
    """从 SQLite 缓存读取。"""
    with _cache_lock:
        conn = _get_cache_conn()
        row = conn.execute(
            "SELECT value1, value2 FROM amap_cache WHERE cache_key=? AND namespace=?",
            (key, namespace),
        ).fetchone()
        return (row[0], row[1]) if row else None


def _cache_write(namespace: str, key: str, v1: float, v2: float) -> None:
    """向 SQLite 缓存写入。"""
    with _cache_lock:
        conn = _get_cache_conn()
        conn.execute(
            "INSERT OR REPLACE INTO amap_cache (cache_key, namespace, value1, value2) "
            "VALUES (?, ?, ?, ?)",
            (key, namespace, v1, v2),
        )
        conn.commit()



# ===================== 带重试的 HTTP 请求 =====================

def _request_with_retry(
    url: str,
    params: Dict[str, str],
    label: str = "API",
) -> Optional[Dict[str, Any]]:
    """
    带指数退避重试的 HTTP GET 请求。

    Args:
        url: 请求 URL
        params: 请求参数字典
        label: 日志标签

    Returns:
        解析后的 JSON 响应字典；全部重试失败返回 None
    """
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            _acquire_rate_limit()
            response = requests.get(url, params=params, timeout=_REQUEST_TIMEOUT)
            response.raise_for_status()
            data: Dict[str, Any] = response.json()

            if data.get("status") == "1":
                return data

            # API 业务错误（如 key 无效），不重试
            errcode = data.get("errcode", "")
            errmsg = data.get("errmsg", "未知错误")
            logger.error(f"[{label}] API业务错误: {errcode} - {errmsg}")
            return None

        except requests.exceptions.Timeout:
            logger.warning(f"[{label}] 请求超时 (第{attempt}/{_MAX_RETRIES}次)")
        except requests.exceptions.ConnectionError:
            logger.warning(f"[{label}] 网络连接失败 (第{attempt}/{_MAX_RETRIES}次)")
        except requests.exceptions.HTTPError as e:
            logger.warning(f"[{label}] HTTP错误: {e} (第{attempt}/{_MAX_RETRIES}次)")
        except Exception as e:
            logger.error(f"[{label}] 未预期异常: {e}")
            return None

        # 指数退避
        if attempt < _MAX_RETRIES:
            delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.info(f"[{label}] {delay:.1f}s 后重试...")
            time.sleep(delay)

    logger.error(f"[{label}] 已达最大重试次数({_MAX_RETRIES})，放弃请求")
    return None


# ===================== Haversine 直线距离 =====================

def haversine_distance(
    coord1: Tuple[float, float],
    coord2: Tuple[float, float],
) -> float:
    """
    Haversine 公式计算两点间球面直线距离。

    Args:
        coord1: 起点坐标 (lng, lat)
        coord2: 终点坐标 (lng, lat)

    Returns:
        直线距离（km）
    """
    from utils.distance_matrix import haversine_distance as _haversine
    return _haversine(coord1[0], coord1[1], coord2[0], coord2[1])


# ===================== 坐标校验 =====================

def _validate_coord(coord: Tuple[float, float], label: str = "坐标") -> bool:
    """校验坐标是否在中国经纬度范围内。"""
    if not coord or len(coord) != 2:
        logger.error(f"[坐标校验] {label}格式错误，应为 (lng, lat)")
        return False
    lng, lat = coord
    if not (_LNG_RANGE[0] <= lng <= _LNG_RANGE[1]
            and _LAT_RANGE[0] <= lat <= _LAT_RANGE[1]):
        logger.error(f"[坐标校验] {label}超出中国范围: ({lng}, {lat})")
        return False
    return True


# ===================== 地理编码 =====================

def geocode(address: str, api_key: str) -> Optional[Tuple[float, float]]:
    """
    调用高德地理编码 API，将地址转换为经纬度坐标（支持本地缓存）。

    Args:
        address: 地址字符串，如 "广州市天河区体育西路"
        api_key: 高德地图 API 密钥

    Returns:
        (lng, lat) 元组；失败返回 None
    """
    if not address or not address.strip():
        logger.error("[高德地理编码] 地址不能为空")
        return None
    if not api_key or not api_key.strip():
        logger.error("[高德地理编码] API密钥不能为空")
        return None

    address = address.strip()

    # 查 SQLite 缓存
    cached = _cache_read("geocode", address)
    if cached:
        lng, lat = cached
        logger.info(f"[高德地理编码] 缓存命中: {address} -> ({lng}, {lat})")
        return (lng, lat)

    # 调用 API
    data = _request_with_retry(
        url="https://restapi.amap.com/v3/geocode/geo",
        params={"key": api_key, "address": address},
        label="高德地理编码",
    )
    if data is None:
        return None

    geocodes = data.get("geocodes", [])
    if not geocodes:
        logger.warning(f"[高德地理编码] 未找到地址对应的坐标: {address}")
        return None

    location = geocodes[0].get("location", "")
    if not location:
        logger.error("[高德地理编码] 返回的坐标字段为空")
        return None

    try:
        lng, lat = map(float, location.split(","))
    except (ValueError, IndexError) as e:
        logger.error(f"[高德地理编码] 坐标解析失败: {e}")
        return None

    # 写 SQLite 缓存
    _cache_write("geocode", address, lng, lat)
    logger.info(f"[高德地理编码] 成功: {address} -> ({lng}, {lat})")
    return (lng, lat)


# ===================== 逆地理编码 =====================

def reverse_geocode(lng: float, lat: float, api_key: str) -> str:
    """
    调用高德逆地理编码 API，将经纬度转换为地址字符串。

    Args:
        lng: 经度
        lat: 纬度
        api_key: 高德地图 API 密钥

    Returns:
        地址字符串；失败返回 "未知地址(lng, lat)"
    """
    fallback = f"未知地址({lng:.4f}, {lat:.4f})"
    if not api_key or not api_key.strip():
        return fallback

    data = _request_with_retry(
        url="https://restapi.amap.com/v3/geocode/regeo",
        params={
            "key": api_key,
            "location": f"{lng},{lat}",
            "extensions": "base",
            "output": "json",
        },
        label="高德逆地理编码",
    )
    if data is None:
        return fallback

    regeocode = data.get("regeocode")
    if regeocode:
        address = regeocode.get("formatted_address", "")
        if address:
            return address
    return fallback


# ===================== 驾车距离（单对单） =====================

def get_driving_distance(
    origin: Tuple[float, float],
    destination: Tuple[float, float],
    api_key: str,
    use_cache: bool = True,
) -> Optional[Tuple[float, float]]:
    """
    调用高德路径规划 API 获取驾车距离和时间（支持缓存与重试）。

    Args:
        origin: 起点坐标 (lng, lat)
        destination: 终点坐标 (lng, lat)
        api_key: 高德地图 API 密钥
        use_cache: 是否使用本地缓存

    Returns:
        (distance_km, duration_min) 元组；失败返回 None
    """
    if not _validate_coord(origin, "起点") or not _validate_coord(destination, "终点"):
        return None
    if not api_key or not api_key.strip():
        logger.error("[高德路径规划] API密钥不能为空")
        return None

    # 查 SQLite 缓存
    if use_cache:
        cache_key = f"{origin[0]:.6f},{origin[1]:.6f}->{destination[0]:.6f},{destination[1]:.6f}"
        cached = _cache_read("driving", cache_key)
        if cached:
            dist, dur = cached
            logger.info(f"[高德路径规划] 缓存命中: {origin} -> {destination}")
            return (dist, dur)
    else:
        cache_key = ""

    # 调用 API
    data = _request_with_retry(
        url="https://restapi.amap.com/v3/direction/driving",
        params={
            "key": api_key,
            "origin": f"{origin[0]},{origin[1]}",
            "destination": f"{destination[0]},{destination[1]}",
        },
        label="高德路径规划",
    )
    if data is None:
        return None

    route = data.get("route", {})
    paths = route.get("paths", [])
    if not paths:
        logger.warning("[高德路径规划] 未找到可行路线")
        return None

    path = paths[0]
    try:
        distance_km = float(path.get("distance", "0")) / 1000
        duration_min = float(path.get("duration", "0")) / 60
    except (ValueError, TypeError) as e:
        logger.error(f"[高德路径规划] 数据解析失败: {e}")
        return None

    # 写 SQLite 缓存
    if use_cache:
        _cache_write("driving", cache_key, distance_km, duration_min)

    logger.info(
        f"[高德路径规划] 成功: {origin} -> {destination}, "
        f"{distance_km:.2f}km, {duration_min:.1f}min"
    )
    return (distance_km, duration_min)


# ===================== 批量距离测量 =====================

def batch_distance(
    origins: List[Tuple[float, float]],
    destinations: List[Tuple[float, float]],
    api_key: str,
    mode: int = 1,
) -> Optional[List[Dict[str, float]]]:
    """
    调用高德距离测量 API（/v3/distance），批量获取驾车距离和时间。

    单次请求支持 1 个起点对最多 100 个终点，可将 3600 次路径规划请求压缩至
    几十次距离测量请求，大幅降低距离矩阵构建耗时与配额消耗。

    Args:
        origins: 起点坐标列表（当前版本仅取第一个）
        destinations: 终点坐标列表（最多 100 个）
        api_key: 高德地图 API 密钥
        mode: 1=驾车（默认），0=直线

    Returns:
        与 destinations 等长的结果列表；失败返回 None
    """
    if not api_key or not api_key.strip():
        logger.error("[批量距离测量] API密钥不能为空")
        return None
    if not origins or not destinations:
        logger.error("[批量距离测量] 起点或终点列表为空")
        return None

    origins_str = "|".join(f"{o[0]},{o[1]}" for o in origins)
    destinations_str = "|".join(f"{d[0]},{d[1]}" for d in destinations)

    data = _request_with_retry(
        url="https://restapi.amap.com/v3/distance",
        params={
            "key": api_key,
            "origins": origins_str,
            "destination": destinations_str,
            "type": str(mode),
        },
        label="批量距离测量",
    )
    if data is None:
        return None

    results_raw = data.get("results", [])
    results: List[Dict[str, float]] = []
    for item in results_raw:
        try:
            dist_km = float(item.get("distance", "0")) / 1000
            dur_min = float(item.get("duration", "0")) / 60
            results.append({"distance_km": dist_km, "duration_min": dur_min})
        except (ValueError, TypeError):
            results.append({"distance_km": 0.0, "duration_min": 0.0})

    return results


def batch_distance_one_to_many(
    origin: Tuple[float, float],
    destinations: List[Tuple[float, float]],
    api_key: str,
    chunk_size: int = 100,
) -> List[Dict[str, float]]:
    """
    单起点到多终点的批量驾车距离查询，自动分片处理超过 100 个终点的场景。

    当 API 调用失败时，使用 Haversine × 1.4 路网系数进行降级估算，并在结果中
    标记 source="fallback"。

    Args:
        origin: 起点坐标 (lng, lat)
        destinations: 终点坐标列表
        api_key: API 密钥
        chunk_size: 每批最多终点数（高德限制 100）

    Returns:
        与 destinations 等长的列表
    """
    all_results: List[Dict[str, float]] = []

    for start in range(0, len(destinations), chunk_size):
        chunk = destinations[start:start + chunk_size]
        result = batch_distance([origin], chunk, api_key, mode=1)

        if result is not None and len(result) == len(chunk):
            all_results.extend(result)
        else:
            # 降级为 Haversine 估算
            logger.warning(
                f"[批量距离测量] 分片 {start}~{start + len(chunk)} 失败，Haversine 降级"
            )
            for dest in chunk:
                straight = haversine_distance(origin, dest)
                road_dist = round(straight * 1.4, 2)
                all_results.append({
                    "distance_km": road_dist,
                    "duration_min": round(road_dist / 60 * 60, 1),
                    "source": "fallback",
                })

    return all_results