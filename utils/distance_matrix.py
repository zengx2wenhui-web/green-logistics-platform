"""距离矩阵构建模块 - 本地Haversine公式计算，支持缓存"""
import json
import os
import hashlib
from typing import List, Tuple, Dict, Optional, Callable
import numpy as np
import math


def haversine_distance(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """
    用 Haversine 公式计算两个经纬度之间的直线距离(km)

    Args:
        lng1: 起点经度
        lat1: 起点纬度
        lng2: 终点经度
        lat2: 终点纬度

    Returns:
        直线距离，单位 km
    """
    R = 6371  # 地球半径(km)
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = lat2_rad - lat1_rad
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def build_distance_matrix(
    nodes: List[Dict],
    road_factor: float = 1.4,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> np.ndarray:
    """
    用 Haversine 公式构建距离矩阵。

    参数：
    - nodes: 节点列表，每项包含 name, lng, lat
    - road_factor: 道路弯曲系数，直线距离 × 此系数 ≈ 实际驾车距离
      城市内部建议 1.3-1.5，跨城市建议 1.2-1.4
    - progress_callback: 进度回调函数，签名为 (progress: float, message: str) -> None

    返回：N×N 的 numpy 数组，单位 km
    """
    n = len(nodes)
    matrix = np.zeros((n, n))

    total_ops = n * (n - 1) // 2
    completed = 0

    if progress_callback:
        progress_callback(0.0, f"开始构建 {n}×{n} 距离矩阵...")

    for i in range(n):
        for j in range(i + 1, n):
            dist = haversine_distance(
                nodes[i]["lng"], nodes[i]["lat"],
                nodes[j]["lng"], nodes[j]["lat"]
            )
            road_dist = dist * road_factor
            matrix[i][j] = round(road_dist, 2)
            matrix[j][i] = round(road_dist, 2)

            completed += 1
            if progress_callback and completed % max(1, total_ops // 20) == 0:
                progress = completed / total_ops
                progress_callback(progress, f"处理中: {completed}/{total_ops}")

    if progress_callback:
        progress_callback(1.0, "距离矩阵构建完成！")

    return matrix


def build_distance_matrix_from_coords(
    coords: List[Tuple[float, float]],
    road_factor: float = 1.4,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> List[List[float]]:
    """
    用 Haversine 公式构建距离矩阵（兼容旧接口）。

    参数：
    - coords: 坐标列表，每个元素为 (lng, lat)
    - road_factor: 道路弯曲系数
    - progress_callback: 进度回调函数

    返回：N×N 的二维列表，单位 km
    """
    nodes = [{"lng": c[0], "lat": c[1]} for c in coords]
    matrix = build_distance_matrix(nodes, road_factor, progress_callback)
    return matrix.tolist()


def get_matrix_info(matrix: List[List[float]]) -> Dict:
    """获取矩阵统计信息"""
    n = len(matrix)
    if n == 0:
        return {"size": 0, "total": 0, "avg": 0, "max": 0, "min": 0}

    values = []
    for i in range(n):
        for j in range(i + 1, n):
            values.append(matrix[i][j])

    return {
        "size": f"{n}×{n}",
        "total": sum(values),
        "avg": sum(values) / len(values) if values else 0,
        "max": max(values) if values else 0,
        "min": min(values) if values else 0
    }


if __name__ == "__main__":
    # 测试用例
    print("=== 距离矩阵模块测试 ===")

    test_coords = [
        (113.2644, 23.1291),  # 仓库
        (113.2650, 23.1320),  # 场馆1
        (113.2700, 23.1280),  # 场馆2
        (113.2600, 23.1350),  # 场馆3
        (113.2680, 23.1250),  # 场馆4
    ]

    def progress(prog: float, msg: str):
        print(f"[进度 {prog*100:.1f}%] {msg}")

    matrix = build_distance_matrix_from_coords(test_coords, road_factor=1.4, progress_callback=progress)

    print("\n距离矩阵:")
    for i, row in enumerate(matrix):
        print(f"  节点{i}: {row}")

    print(f"\n矩阵大小: {len(matrix)} × {len(matrix[0])}")
    info = get_matrix_info(matrix)
    print(f"统计信息: {info}")