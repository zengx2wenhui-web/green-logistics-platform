"""距离矩阵构建模块

支持双轨制距离获取：高德 API 实际驾车距离（首选）+ Haversine 降级估算（备用）。
构建结果同时包含距离矩阵与时间矩阵，为后续 VRP 时间窗扩展奠定基础。

核心优化：
- 集成高德批量距离测量 API（/v3/distance），将数千次请求压缩至几十次
- SQLite 持久化缓存（模块级单例连接），防止配额耗尽与重复计算
- 同时输出 distance_matrix 与 time_matrix
- 支持带节点类型标签的输入（仓库 / 中转仓 / 配送点）
- Haversine 降级方案支持 numpy 向量化加速
"""
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


# ===================== Haversine 直线距离 =====================

def haversine_distance(
    lng1: float, lat1: float,
    lng2: float, lat2: float,
) -> float:
    """
    Haversine 公式计算球面直线距离（km）。

    Args:
        lng1, lat1: 起点经纬度
        lng2, lat2: 终点经纬度

    Returns:
        直线距离（km）
    """
    R = 6371.0
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = lat2_r - lat1_r
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def haversine_matrix_vectorized(
    lngs: np.ndarray, lats: np.ndarray,
) -> np.ndarray:
    """
    向量化 Haversine：一次性计算 N×N 距离矩阵。

    Args:
        lngs: shape=(N,) 经度数组
        lats: shape=(N,) 纬度数组

    Returns:
        shape=(N, N) 距离矩阵（km）
    """
    R = 6371.0
    lats_r = np.radians(lats)
    lngs_r = np.radians(lngs)

    dlat = lats_r[:, None] - lats_r[None, :]
    dlng = lngs_r[:, None] - lngs_r[None, :]

    a = (np.sin(dlat / 2) ** 2
         + np.cos(lats_r[:, None]) * np.cos(lats_r[None, :])
         * np.sin(dlng / 2) ** 2)
    return R * 2 * np.arcsin(np.sqrt(a))


# ===================== SQLite 缓存层 =====================

def _get_cache_conn() -> sqlite3.Connection:
    """获取模块级单例 SQLite 缓存连接。"""
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


def _init_cache_db() -> sqlite3.Connection:
    """初始化 SQLite 缓存数据库，返回连接（兼容旧调用）。"""
    return _get_cache_conn()


def _pair_key(lng1: float, lat1: float, lng2: float, lat2: float) -> str:
    """生成坐标对的唯一缓存键。"""
    raw = f"{lng1:.6f},{lat1:.6f},{lng2:.6f},{lat2:.6f}"
    return hashlib.md5(raw.encode()).hexdigest()


def _query_cache(
    conn: sqlite3.Connection,
    lng1: float, lat1: float,
    lng2: float, lat2: float,
) -> Optional[Tuple[float, float]]:
    """查询缓存中的距离和时间。"""
    key = _pair_key(lng1, lat1, lng2, lat2)
    row = conn.execute(
        "SELECT distance_km, duration_min FROM distance_cache WHERE pair_key=?",
        (key,),
    ).fetchone()
    return (row[0], row[1]) if row else None


def _write_cache(
    conn: sqlite3.Connection,
    lng1: float, lat1: float,
    lng2: float, lat2: float,
    distance_km: float, duration_min: float,
    source: str = "api",
) -> None:
    """向缓存写入一条记录。"""
    key = _pair_key(lng1, lat1, lng2, lat2)
    conn.execute(
        """INSERT OR REPLACE INTO distance_cache
           (pair_key, lng1, lat1, lng2, lat2, distance_km, duration_min, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (key, lng1, lat1, lng2, lat2, distance_km, duration_min, source),
    )
    conn.commit()


# ===================== 距离矩阵构建结果 =====================

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
        """将距离矩阵转为二维列表（兼容旧接口）。"""
        return self.distance_matrix.tolist()


# ===================== 核心矩阵构建 =====================

def build_distance_matrix(
    nodes: List[Dict[str, Any]],
    road_factor: float = 1.4,
    api_key: Optional[str] = None,
    use_api: bool = False,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> DistanceMatrixResult:
    """
    构建 N×N 距离矩阵与时间矩阵。

    双轨策略：
    1. 若 use_api=True 且提供有效 api_key，使用高德批量距离 API 获取真实路网距离，
       并将结果缓存到 SQLite；
    2. 否则使用 Haversine × road_factor 估算。

    Args:
        nodes: 节点列表，每项至少含 {"lng": ..., "lat": ...}，
               可选 {"name": ..., "type": "warehouse|hub|venue"}
        road_factor: 路网弯曲系数（仅 Haversine 模式生效），建议 1.3~1.5
        api_key: 高德 API 密钥
        use_api: 是否启用高德 API
        progress_callback: 进度回调 (progress: float, message: str)

    Returns:
        DistanceMatrixResult 对象
    """
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
                # 收集需要查询的目标节点（排除缓存已有的）
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
        dist_mat = np.round(raw, 2)
        time_mat = np.round(dist_mat / 60 * 60, 1)  # 假设 60 km/h
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


# ===================== 兼容旧接口 =====================

def build_distance_matrix_from_coords(
    coords: List[Tuple[float, float]],
    road_factor: float = 1.4,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> List[List[float]]:
    """
    使用 Haversine 公式构建距离矩阵（兼容旧接口）。

    Args:
        coords: 坐标列表 [(lng, lat), ...]
        road_factor: 路网系数
        progress_callback: 进度回调

    Returns:
        N×N 二维列表（km）
    """
    nodes = [{"lng": c[0], "lat": c[1]} for c in coords]
    result = build_distance_matrix(
        nodes, road_factor=road_factor,
        use_api=False, progress_callback=progress_callback,
    )
    return result.to_list()


# ===================== 矩阵统计 =====================

def get_matrix_info(matrix: List[List[float]]) -> Dict[str, Any]:
    """获取距离矩阵统计信息。"""
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


# ===================== 测试入口 =====================

if __name__ == "__main__":
    print("=== 距离矩阵模块测试 ===")

    test_coords = [
        (113.2644, 23.1291),
        (113.2650, 23.1320),
        (113.2700, 23.1280),
        (113.2600, 23.1350),
        (113.2680, 23.1250),
    ]

    def progress(prog: float, msg: str) -> None:
        print(f"[进度 {prog * 100:.1f}%] {msg}")

    # Haversine 模式
    matrix = build_distance_matrix_from_coords(
        test_coords, road_factor=1.4, progress_callback=progress,
    )

    print("\n距离矩阵:")
    for i, row in enumerate(matrix):
        print(f"  节点{i}: {[round(v, 2) for v in row]}")

    info = get_matrix_info(matrix)
    print(f"\n统计信息: {info}")

    # 带节点类型标签的构建
    nodes = [
        {"name": "总仓库", "type": "warehouse", "lng": 113.2644, "lat": 23.1291},
        {"name": "场馆A", "type": "venue", "lng": 113.2650, "lat": 23.1320},
        {"name": "场馆B", "type": "venue", "lng": 113.2700, "lat": 23.1280},
    ]
    result = build_distance_matrix(nodes, road_factor=1.4)
    print(f"\n节点标签: {result.node_labels}")
    print(f"距离矩阵:\n{result.distance_matrix}")
    print(f"时间矩阵:\n{result.time_matrix}")
