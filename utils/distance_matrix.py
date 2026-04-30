# 距离矩阵构建模块
import math
import sqlite3
import hashlib
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Callable, Any
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)

# 缓存数据库路径
_CACHE_DB_PATH: Path = Path("data/cache/distance_cache.db")

# 模块级单例连接
_db_conn: Optional[sqlite3.Connection] = None

# Haversine 直线距离 
def haversine_distance(
    lng1: float, lat1: float,
    lng2: float, lat2: float,
) -> float:
    R = 6371.0
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = lat2_r - lat1_r
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


# 向量化 Haversine 距离矩阵计算
def haversine_matrix_vectorized(
    lngs: np.ndarray, lats: np.ndarray,
) -> np.ndarray:
    R = 6371.0
    lats_r = np.radians(lats)
    lngs_r = np.radians(lngs)

    dlat = lats_r[:, None] - lats_r[None, :]
    dlng = lngs_r[:, None] - lngs_r[None, :]

    a = (np.sin(dlat / 2) ** 2
         + np.cos(lats_r[:, None]) * np.cos(lats_r[None, :])
         * np.sin(dlng / 2) ** 2)
    return R * 2 * np.arcsin(np.sqrt(a))


# 通用向量化 Haversine 距离矩阵计算
def haversine_matrix_general(
    coords_a: np.ndarray,
    coords_b: np.ndarray,
) -> np.ndarray:
    R = 6371.0

    lat_a = np.radians(coords_a[:, 1])[:, None]  # shape=(M, 1)
    lon_a = np.radians(coords_a[:, 0])[:, None]  # shape=(M, 1)
    lat_b = np.radians(coords_b[:, 1])[None, :]  # shape=(1, N)
    lon_b = np.radians(coords_b[:, 0])[None, :]  # shape=(1, N)

    dlat = lat_b - lat_a
    dlon = lon_b - lon_a

    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat_a) * np.cos(lat_b) * np.sin(dlon / 2) ** 2
    )
    distances = R * 2 * np.arcsin(np.sqrt(a))

    return distances


# SQLite 缓存层 
def _get_cache_conn() -> sqlite3.Connection:
    global _db_conn
    if _db_conn is None:
        _CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _db_conn = sqlite3.connect(str(_CACHE_DB_PATH), check_same_thread=False)
        _db_conn.execute("""
            CREATE TABLE IF NOT EXISTS distance_cache (
                pair_key  TEXT PRIMARY KEY,
                lng1      REAL, lat1 REAL,
                lng2      REAL, lat2 REAL,
                distance_km  REAL,
                duration_min REAL,
                source    TEXT DEFAULT 'api'
            )
        """)
        _db_conn.commit()
    return _db_conn


# 初始化缓存数据库
def _init_cache_db() -> sqlite3.Connection:
    return _get_cache_conn()


# 生成坐标对的唯一缓存键
def _pair_key(lng1: float, lat1: float, lng2: float, lat2: float) -> str:
    raw = f"{lng1:.6f},{lat1:.6f},{lng2:.6f},{lat2:.6f}"
    return hashlib.md5(raw.encode()).hexdigest()


# 查询缓存中的距离和时间
def _query_cache(
    conn: sqlite3.Connection,
    lng1: float, lat1: float,
    lng2: float, lat2: float,
) -> Optional[Tuple[float, float]]:
    key = _pair_key(lng1, lat1, lng2, lat2)
    row = conn.execute(
        "SELECT distance_km, duration_min FROM distance_cache WHERE pair_key=?",
        (key,),
    ).fetchone()
    return (row[0], row[1]) if row else None


# 向缓存写入一条记录
def _write_cache(
    conn: sqlite3.Connection,
    lng1: float, lat1: float,
    lng2: float, lat2: float,
    distance_km: float, duration_min: float,
    source: str = "api",
) -> None:
    key = _pair_key(lng1, lat1, lng2, lat2)
    conn.execute(
        """INSERT OR REPLACE INTO distance_cache
           (pair_key, lng1, lat1, lng2, lat2, distance_km, duration_min, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (key, lng1, lat1, lng2, lat2, distance_km, duration_min, source),
    )
    conn.commit()


# 距离矩阵构建结果
@dataclass
class DistanceMatrixResult:
    """距离矩阵构建结果，同时包含距离与时间矩阵。"""
    distance_matrix: np.ndarray  # N×N，单位 km
    time_matrix: np.ndarray      # N×N，单位 min
    node_labels: List[str] = field(default_factory=list)
    api_calls: int = 0
    cache_hits: int = 0
    fallback_count: int = 0

    def to_list(self) -> List[List[float]]:
        """将距离矩阵转为二维列表 """
        return self.distance_matrix.tolist()


# 核心矩阵构建
def build_distance_matrix(
    nodes: List[Dict[str, Any]],
    road_factor: float = 1.4,
    api_key: Optional[str] = None,
    use_api: bool = False,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> DistanceMatrixResult:
    n = len(nodes)
    dist_mat = np.zeros((n, n))
    time_mat = np.zeros((n, n))
    node_labels = [nd.get("name", f"N{i}") for i, nd in enumerate(nodes)]

    api_calls = 0
    cache_hits = 0
    fallback_count = 0
    total_pairs = n * (n - 1) // 2
    completed = 0

    if progress_callback:
        progress_callback(0.0, f"开始构建 {n}×{n} 距离矩阵...")

    # 尝试使用高德 API
    if use_api and api_key:
        conn = _init_cache_db()
        try:
            # 延迟导入，避免循环依赖
            from utils.amap_api import batch_distance_one_to_many

            for i in range(n):
                # 收集需要查询的目标节点
                targets_idx: List[int] = []
                targets_coords: List[Tuple[float, float]] = []

                for j in range(n):
                    if i == j:
                        continue
                    cached = _query_cache(
                        conn,
                        nodes[i]["lng"], nodes[i]["lat"],
                        nodes[j]["lng"], nodes[j]["lat"],
                    )
                    if cached:
                        dist_mat[i][j] = cached[0]
                        time_mat[i][j] = cached[1]
                        cache_hits += 1
                    else:
                        targets_idx.append(j)
                        targets_coords.append((nodes[j]["lng"], nodes[j]["lat"]))

                # 对未缓存的目标批量请求
                if targets_coords:
                    origin = (nodes[i]["lng"], nodes[i]["lat"])
                    results = batch_distance_one_to_many(
                        origin, targets_coords, api_key,
                    )
                    api_calls += 1

                    for k, j in enumerate(targets_idx):
                        r = results[k] if k < len(results) else {}
                        d = r.get("distance_km", 0.0)
                        t = r.get("duration_min", 0.0)

                        if d <= 0 or r.get("source") == "fallback":
                            # API 失败，降级
                            d = haversine_distance(
                                nodes[i]["lng"], nodes[i]["lat"],
                                nodes[j]["lng"], nodes[j]["lat"],
                            ) * road_factor
                            t = d / 60 * 60  # 假设 60 km/h
                            fallback_count += 1
                            source = "fallback"
                        else:
                            source = "api"

                        dist_mat[i][j] = round(d, 2)
                        time_mat[i][j] = round(t, 1)

                        _write_cache(
                            conn,
                            nodes[i]["lng"], nodes[i]["lat"],
                            nodes[j]["lng"], nodes[j]["lat"],
                            dist_mat[i][j], time_mat[i][j], source,
                        )

                completed += len(targets_idx) + (n - 1 - len(targets_idx))
                if progress_callback and total_pairs > 0:
                    progress_callback(
                        min(completed / total_pairs, 1.0),
                        f"API 模式: 节点 {i + 1}/{n} 完成",
                    )
        except ImportError:
            logger.warning("[距离矩阵] 无法导入 amap_api，降级为 Haversine")
            use_api = False

    # Haversine 降级模式（或 API 未启用）— 向量化加速
    if not use_api or not api_key:
        lngs = np.array([nd["lng"] for nd in nodes])
        lats = np.array([nd["lat"] for nd in nodes])
        raw = haversine_matrix_vectorized(lngs, lats) * road_factor
        # 保留算法层距离精度，避免极短路段在这里被舍入成 0 km。
        # 展示层仍会按页面需要做格式化。
        dist_mat = raw.astype(float)
        time_mat = np.round(raw / 60 * 60, 1)  # 假设 60 km/h
        np.fill_diagonal(dist_mat, 0.0)
        np.fill_diagonal(time_mat, 0.0)

        if progress_callback:
            progress_callback(0.9, f"Haversine 向量化模式: {n} 节点完成")

    if progress_callback:
        progress_callback(1.0, "距离矩阵构建完成！")

    return DistanceMatrixResult(
        distance_matrix=dist_mat,
        time_matrix=time_mat,
        node_labels=node_labels,
        api_calls=api_calls,
        cache_hits=cache_hits,
        fallback_count=fallback_count,
    )


# 兼容旧接口
def build_distance_matrix_from_coords(
    coords: List[Tuple[float, float]],
    road_factor: float = 1.4,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> List[List[float]]:
    nodes = [{"lng": c[0], "lat": c[1]} for c in coords]
    result = build_distance_matrix(
        nodes, road_factor=road_factor,
        use_api=False, progress_callback=progress_callback,
    )
    return result.to_list()


# 矩阵统计
def get_matrix_info(matrix: List[List[float]]) -> Dict[str, Any]:
    n = len(matrix)
    if n == 0:
        return {"size": "0×0", "total": 0, "avg": 0, "max": 0, "min": 0}

    values = [
        matrix[i][j] for i in range(n) for j in range(i + 1, n)
    ]

    return {
        "size": f"{n}×{n}",
        "total": round(sum(values), 2),
        "avg": round(sum(values) / len(values), 2) if values else 0,
        "max": round(max(values), 2) if values else 0,
        "min": round(min(values), 2) if values else 0,
    }


if __name__ == "__main__":
    pass
