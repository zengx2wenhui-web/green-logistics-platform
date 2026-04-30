# 高德地图 API 工具
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

# 配置常量
DEFAULT_AMAP_API_KEY: str = "fda00124b4a41124416dbd3595c4b1ee"
_RATE_LIMIT: int = 10          # 每秒最大请求数
_RATE_LIMIT_MAX_WAIT: float = 5.0  # 限流最长等待时间（秒）
_MAX_RETRIES: int = 3          # 最大重试次数
_RETRY_BASE_DELAY: float = 1.0 # 重试基础延迟（秒）
_REQUEST_TIMEOUT: int = 10     # 单次请求超时（秒）
_CACHE_DB_PATH: Path = Path("data/cache/amap_cache.db")

# 中国经纬度合法范围
_LNG_RANGE: Tuple[float, float] = (73.0, 135.0)
_LAT_RANGE: Tuple[float, float] = (3.0, 54.0)

_rate_limiter_lock = Lock()
_request_timestamps: List[float] = []


# 令牌桶限流器
def _acquire_rate_limit() -> None:
    global _request_timestamps
    sleep_time = 0.0
    
    with _rate_limiter_lock:
        now = time.time()
        # 清理1秒外的时间戳
        _request_timestamps = [ts for ts in _request_timestamps if now - ts < 1.0]
        
        if len(_request_timestamps) >= _RATE_LIMIT:
            # 计算需要睡眠的时间
            sleep_time = min(1.0 - (now - _request_timestamps[0]), _RATE_LIMIT_MAX_WAIT)
            # 预先把未来的时间戳塞进去，假装我们已经在那个时间发起了请求
            _request_timestamps.append(now + sleep_time)
        else:
            _request_timestamps.append(now)
            
    if sleep_time > 0:
        time.sleep(sleep_time)


# SQLite 缓存层
_cache_conn: Optional[sqlite3.Connection] = None
_cache_lock = Lock()

def _get_cache_conn() -> sqlite3.Connection:
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
        # 创建索引加速查询
        _cache_conn.execute("CREATE INDEX IF NOT EXISTS idx_namespace ON amap_cache(namespace)")
        _cache_conn.commit()
    return _cache_conn


# 缓存读写接口
def _cache_read(namespace: str, key: str) -> Optional[Tuple[float, float]]:
    with _cache_lock:
        conn = _get_cache_conn()
        row = conn.execute(
            "SELECT value1, value2 FROM amap_cache WHERE cache_key=? AND namespace=?",
            (key, namespace),
        ).fetchone()
        return (row[0], row[1]) if row else None


def _cache_write(namespace: str, key: str, v1: float, v2: float) -> None:
    with _cache_lock:
        conn = _get_cache_conn()
        conn.execute(
            "INSERT OR REPLACE INTO amap_cache (cache_key, namespace, value1, value2) "
            "VALUES (?, ?, ?, ?)",
            (key, namespace, v1, v2),
        )
        conn.commit()


# 带重试的 HTTP 请求
def _request_with_retry(
    url: str,
    params: Dict[str, str],
    label: str = "API",
) -> Optional[Dict[str, Any]]:
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            _acquire_rate_limit()
            response = requests.get(url, params=params, timeout=_REQUEST_TIMEOUT)
            response.raise_for_status()
            data: Dict[str, Any] = response.json()

            if str(data.get("status")) == "1":
                return data

            errcode = data.get("errcode", data.get("infocode", ""))
            errmsg = data.get("errmsg", data.get("info", "未知错误"))
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


# Haversine 直线距离
def haversine_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Haversine 公式计算两点间球面直线距离 (km)。"""
    lng1, lat1 = map(math.radians, coord1)
    lng2, lat2 = map(math.radians, coord2)
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


# 坐标校验
def _validate_coord(coord: Tuple[float, float], label: str = "坐标") -> bool:
    if not coord or len(coord) != 2:
        logger.error(f"[坐标校验] {label}格式错误，应为 (lng, lat)")
        return False
    lng, lat = coord
    if not (_LNG_RANGE[0] <= lng <= _LNG_RANGE[1]
            and _LAT_RANGE[0] <= lat <= _LAT_RANGE[1]):
        logger.error(f"[坐标校验] {label}超出中国范围: ({lng}, {lat})")
        return False
    return True


def _resolve_api_key(api_key: Optional[str] = None) -> str:
    return str(api_key or "").strip() or DEFAULT_AMAP_API_KEY


# 地理编码
def geocode(address: str, api_key: Optional[str] = None) -> Optional[Tuple[float, float]]:
    if not address or not address.strip():
        return None
    address = address.strip()
    resolved_api_key = _resolve_api_key(api_key)

    cached = _cache_read("geocode", address)
    if cached:
        return cached

    data = _request_with_retry(
        url="https://restapi.amap.com/v3/geocode/geo",
        params={"key": resolved_api_key, "address": address},
        label="高德地理编码",
    )
    if not data:
        return None

    geocodes = data.get("geocodes", [])
    if not geocodes:
        return None

    location = geocodes[0].get("location", "")
    try:
        lng, lat = map(float, location.split(","))
        _cache_write("geocode", address, lng, lat)
        return (lng, lat)
    except Exception as e:
        logger.error(f"[高德地理编码] 解析失败: {e}")
        return None


# 逆地理编码
def reverse_geocode(lng: float, lat: float, api_key: Optional[str] = None) -> str:
    fallback = f"未知地址({lng:.4f}, {lat:.4f})"
    resolved_api_key = _resolve_api_key(api_key)

    data = _request_with_retry(
        url="https://restapi.amap.com/v3/geocode/regeo",
        params={"key": resolved_api_key, "location": f"{lng},{lat}", "extensions": "base"},
        label="逆地理编码",
    )
    if data and data.get("regeocode"):
        return data["regeocode"].get("formatted_address", fallback)
    return fallback


# 驾车距离（单对单）
def get_driving_distance(
    origin: Tuple[float, float],
    destination: Tuple[float, float],
    api_key: Optional[str] = None,
    use_cache: bool = True,
) -> Optional[Tuple[float, float]]:
    if not _validate_coord(origin) or not _validate_coord(destination):
        return None
    resolved_api_key = _resolve_api_key(api_key)

    cache_key = f"{origin[0]:.6f},{origin[1]:.6f}->{destination[0]:.6f},{destination[1]:.6f}"
    if use_cache:
        cached = _cache_read("driving", cache_key)
        if cached:
            return cached

    data = _request_with_retry(
        url="https://restapi.amap.com/v3/direction/driving",
        params={"key": resolved_api_key, "origin": f"{origin[0]},{origin[1]}", "destination": f"{destination[0]},{destination[1]}"},
        label="路径规划",
    )
    
    if not data or not data.get("route", {}).get("paths"):
        return None

    path = data["route"]["paths"][0]
    try:
        dist_km = float(path.get("distance", "0")) / 1000
        dur_min = float(path.get("duration", "0")) / 60
        if use_cache:
            _cache_write("driving", cache_key, dist_km, dur_min)
        return (dist_km, dur_min)
    except Exception:
        return None


# 批量距离测量
def batch_distance(
    origins: List[Tuple[float, float]],
    destinations: List[Tuple[float, float]],
    api_key: Optional[str] = None,
    mode: int = 1,
) -> Optional[List[Dict[str, float]]]:
    if not origins or not destinations:
        return None
    resolved_api_key = _resolve_api_key(api_key)

    origins_str = "|".join(f"{o[0]},{o[1]}" for o in origins)
    destinations_str = "|".join(f"{d[0]},{d[1]}" for d in destinations)

    data = _request_with_retry(
        url="https://restapi.amap.com/v3/distance",
        params={"key": resolved_api_key, "origins": origins_str, "destination": destinations_str, "type": str(mode)},
        label="批量测量",
    )
    
    if not data:
        return None

    results = []
    for item in data.get("results", []):
        try:
            results.append({
                "distance_km": float(item.get("distance", "0")) / 1000,
                "duration_min": float(item.get("duration", "0")) / 60
            })
        except Exception:
            results.append({"distance_km": 0.0, "duration_min": 0.0})
    return results


def batch_distance_one_to_many(
    origin: Tuple[float, float],
    destinations: List[Tuple[float, float]],
    api_key: Optional[str] = None,
    chunk_size: int = 100,
) -> List[Dict[str, float]]:
    all_results = []

    for start in range(0, len(destinations), chunk_size):
        chunk = destinations[start:start + chunk_size]
        result = batch_distance([origin], chunk, api_key, mode=1)

        if result is not None and len(result) == len(chunk):
            all_results.extend(result)
        else:
            logger.warning(f"[批量测量] 分片失败，启用 Haversine 降级")
            for dest in chunk:
                straight = haversine_distance(origin, dest)
                road_dist = round(straight * 1.4, 2)
                all_results.append({
                    "distance_km": road_dist,
                    "duration_min": round(road_dist / 60 * 60, 1),
                    "source": "fallback",
                })

    return all_results
