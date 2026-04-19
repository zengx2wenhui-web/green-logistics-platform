"""全国候选仓库加载模块

支持从 data/national_warehouse_candidates.xlsx 加载 120 个真实物流枢纽，
并基于 Haversine 球面距离计算候选仓与需求点之间的实际物理距离。

核心功能：
- 加载 Excel 文件中的候选仓库清单（仓库ID、名称、省、市、经度、纬度）
- 提取经纬度作为候选坐标池
- 提供 Haversine 距离矩阵构建接口
"""

import logging
import os
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Any

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# 候选仓库文件路径
_CANDIDATE_FILE_PATH = Path("data/national_warehouse_candidates.xlsx")


# ===================== 数据加载 =====================

def load_candidate_warehouses(
    file_path: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """从 Excel 或 CSV 文件加载全国候选仓库清单。"""
    path = Path(file_path) if file_path else _CANDIDATE_FILE_PATH

    # 自动寻找替代的 .csv 文件（如果 .xlsx 不存在）
    if not path.exists():
        fallback_csv = path.with_suffix('.csv')
        if fallback_csv.exists():
            logger.info(f"未找到 {path.name}，自动切换至读取 {fallback_csv.name}")
            path = fallback_csv
        else:
            error_msg = f"候选仓库文件不存在: {path} (同时也未找到 .csv 格式)"
            logger.error(error_msg)
            return None, error_msg

    try:
        # 根据文件后缀智能选择读取引擎
        if path.suffix.lower() == '.csv':
            df = pd.read_csv(path)
        else:
            df = pd.read_excel(path)
            
        logger.info(f"[候选仓库] 成功加载 {len(df)} 个仓库")
        return df, None
    except Exception as e:
        error_msg = f"加载候选仓库文件失败: {str(e)}"
        logger.error(error_msg)
        return None, error_msg


# ===================== 坐标池提取 =====================

def extract_candidate_coords(
    df: pd.DataFrame,
    lng_col: str = "经度",
    lat_col: str = "纬度",
    validate: bool = True,
) -> Tuple[List[Tuple[float, float]], Optional[str]]:
    """
    从DataFrame中提取经纬度坐标作为候选坐标池。

    Args:
        df: 候选仓库数据框
        lng_col: 经度列名
        lat_col: 纬度列名
        validate: 是否进行坐标校验

    Returns:
        (坐标列表, None) | (None, 错误信息)
    """
    try:
        # 列名检查
        if lng_col not in df.columns or lat_col not in df.columns:
            error_msg = f"数据框缺少必要列: {lng_col} 或 {lat_col}"
            logger.error(error_msg)
            return None, error_msg

        # 提取坐标
        coords = list(zip(df[lng_col].astype(float), df[lat_col].astype(float)))

        if validate:
            # 坐标范围校验（中国范围）
            valid_coords = []
            for i, (lng, lat) in enumerate(coords):
                if not (73 <= lng <= 135 and 3 <= lat <= 54):
                    logger.warning(
                        f"[坐标校验] 仓库{i}坐标超出中国范围: lng={lng}, lat={lat}"
                    )
                    continue
                valid_coords.append((lng, lat))

            if len(valid_coords) < len(coords):
                logger.warning(
                    f"[坐标校验] 有效坐标 {len(valid_coords)} / {len(coords)}"
                )
            coords = valid_coords

        logger.info(f"[坐标池] 提取 {len(coords)} 个候选坐标")
        return coords, None

    except Exception as e:
        error_msg = f"提取坐标失败: {str(e)}"
        logger.error(error_msg)
        return None, error_msg


# ===================== 候选仓库信息构建 =====================

def build_warehouse_nodes(
    df: pd.DataFrame,
    id_col: str = "仓库ID",
    name_col: str = "仓库名称",
    lng_col: str = "经度",
    lat_col: str = "纬度",
    province_col: str = "省",
    city_col: str = "市",
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    从DataFrame构建仓库节点信息（含元数据）。

    Args:
        df: 候选仓库数据框
        id_col, name_col, lng_col, lat_col: 列名映射
        province_col, city_col: 省市列名

    Returns:
        (节点列表, None) | (None, 错误信息)
    """
    try:
        nodes = []
        for idx, row in df.iterrows():
            # 坐标范围校验
            lng = float(row[lng_col])
            lat = float(row[lat_col])
            if not (73 <= lng <= 135 and 3 <= lat <= 54):
                logger.warning(f"跳过超范围坐标: {row.get(name_col)}")
                continue

            node = {
                "warehouse_id": str(row[id_col]),
                "name": str(row[name_col]),
                "lng": lng,
                "lat": lat,
                "province": str(row[province_col]),
                "city": str(row[city_col]),
                "type": "warehouse",
                "source": "national_candidates",
            }
            nodes.append(node)

        logger.info(f"[仓库节点] 构建 {len(nodes)} 个仓库节点")
        return nodes, None

    except Exception as e:
        error_msg = f"构建仓库节点失败: {str(e)}"
        logger.error(error_msg)
        return None, error_msg


# ===================== Haversine 距离矩阵 =====================

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
    lat1_r = np.radians(lat1)
    lat2_r = np.radians(lat2)
    dlat = lat2_r - lat1_r
    dlng = np.radians(lng2 - lng1)
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlng / 2) ** 2
    )
    return R * 2 * np.arcsin(np.sqrt(a))


def haversine_matrix(
    coords_a: np.ndarray, coords_b: np.ndarray
) -> np.ndarray:
    """
    向量化 Haversine 球面距离矩阵计算。

    Args:
        coords_a: shape=(M, 2) 坐标数组 [[lng, lat], ...] （候选仓库或需求点）
        coords_b: shape=(N, 2) 坐标数组 [[lng, lat], ...] （需求点或候选仓库）

    Returns:
        shape=(M, N) 距离矩阵（km）
    """
    # 转为弧度
    lat_a = np.radians(coords_a[:, 1])[:, None]  # shape=(M, 1)
    lon_a = np.radians(coords_a[:, 0])[:, None]  # shape=(M, 1)
    lat_b = np.radians(coords_b[:, 1])[None, :]  # shape=(1, N)
    lon_b = np.radians(coords_b[:, 0])[None, :]  # shape=(1, N)

    # 纬度、经度差
    dlat = lat_b - lat_a  # shape=(M, N)
    dlon = lon_b - lon_a  # shape=(M, N)

    # Haversine 公式
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat_a) * np.cos(lat_b) * np.sin(dlon / 2) ** 2
    )
    distances = 2 * 6371 * np.arcsin(np.sqrt(a))  # shape=(M, N)

    return distances


def compute_distance_to_candidates(
    demand_coords: List[Tuple[float, float]],
    candidate_coords: List[Tuple[float, float]],
) -> Tuple[np.ndarray, Optional[str]]:
    """
    计算需求点到候选仓库的 Haversine 距离矩阵。

    Args:
        demand_coords: 需求点坐标列表 [(lng, lat), ...]
        candidate_coords: 候选仓库坐标列表 [(lng, lat), ...]

    Returns:
        (距离矩阵 shape=(M, N) 单位km, None) | (None, 错误信息)
    """
    try:
        if not demand_coords or not candidate_coords:
            return None, "坐标列表为空"

        demand_arr = np.array(demand_coords, dtype=np.float64)  # shape=(M, 2)
        candidate_arr = np.array(candidate_coords, dtype=np.float64)  # shape=(N, 2)

        dist_matrix = haversine_matrix(demand_arr, candidate_arr)
        logger.info(
            f"[距离矩阵] 计算 {len(demand_coords)}×{len(candidate_coords)} "
            f"Haversine 距离矩阵"
        )
        return dist_matrix, None

    except Exception as e:
        error_msg = f"计算距离矩阵失败: {str(e)}"
        logger.error(error_msg)
        return None, error_msg


# ===================== 高层封装 =====================

def load_and_prepare_candidates(
    file_path: Optional[str] = None,
    validate_coords: bool = True,
) -> Tuple[Optional[List[Dict]], Optional[List[Tuple[float, float]]], Optional[str]]:
    """
    一站式加载并准备候选仓库。

    Args:
        file_path: 文件路径
        validate_coords: 是否进行坐标校验

    Returns:
        (仓库节点列表, 坐标列表, None) | (None, None, 错误信息)
    """
    # Step 1: 加载Excel
    df, err = load_candidate_warehouses(file_path)
    if df is None:
        return None, None, err

    # Step 2: 构建仓库节点
    nodes, err = build_warehouse_nodes(df)
    if nodes is None:
        return None, None, err

    # Step 3: 提取坐标
    coords, err = extract_candidate_coords(df, validate=validate_coords)
    if coords is None:
        return None, None, err

    logger.info(
        f"[候选仓库准备完成] 节点数={len(nodes)}, 坐标数={len(coords)}"
    )
    return nodes, coords, None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("测试候选仓库加载")
    print("=" * 60)

    # 测试数据加载
    nodes, coords, err = load_and_prepare_candidates()
    if err:
        print(f"错误: {err}")
    else:
        print(f"\n✓ 加载成功")
        print(f"  仓库数: {len(nodes)}")
        print(f"  坐标数: {len(coords)}")

        if nodes:
            print(f"\n首个仓库信息:")
            for key, value in nodes[0].items():
                print(f"  {key}: {value}")

        if coords:
            print(f"\n前3个坐标:")
            for i, (lng, lat) in enumerate(coords[:3]):
                print(f"  坐标{i}: lng={lng:.4f}, lat={lat:.4f}")

        # 测试距离矩阵计算
        print(f"\n测试距离矩阵计算...")
        test_demand = [(coords[0][0] + 0.1, coords[0][1] + 0.1)]
        dist_mat, err = compute_distance_to_candidates(test_demand, coords[:5])
        if err:
            print(f"错误: {err}")
        else:
            print(f"✓ 距离矩阵构建成功 shape={dist_mat.shape}")
            print(f"  需求点到前5个候选仓的距离: {dist_mat[0]}")
