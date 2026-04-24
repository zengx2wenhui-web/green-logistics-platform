import logging
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Any
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE_FILE = "data/national_warehouse_candidates.csv"
STANDARD_COLUMNS = ["warehouse_id", "name", "province", "city", "lng", "lat"]

_COLUMN_ALIASES: Dict[str, Tuple[str, ...]] = {
    "warehouse_id": ("warehouse_id", "仓库ID", "仓库Id", "仓库编号", "ID", "id"),
    "name": ("name", "仓库名称", "仓库名", "名称"),
    "province": ("province", "省", "省份"),
    "city": ("city", "市", "城市"),
    "lng": ("lng", "lon", "longitude", "经度"),
    "lat": ("lat", "latitude", "纬度"),
}


def _candidate_path_variants(file_path: str) -> List[Path]:
    raw_path = Path(file_path)
    bases = [Path.cwd(), PROJECT_ROOT]
    variants: List[Path] = []

    def _add_variant(path: Path) -> None:
        if path not in variants:
            variants.append(path)

    def _expand(path: Path) -> None:
        if path.suffix:
            _add_variant(path)
            if path.suffix.lower() != ".csv":
                _add_variant(path.with_suffix(".csv"))
            if path.suffix.lower() != ".xlsx":
                _add_variant(path.with_suffix(".xlsx"))
            return

        _add_variant(path)
        _add_variant(path.with_suffix(".csv"))
        _add_variant(path.with_suffix(".xlsx"))

    if raw_path.is_absolute():
        _expand(raw_path)
        return variants

    for base in bases:
        _expand(base / raw_path)
    return variants


def _resolve_candidate_path(file_path: str = DEFAULT_CANDIDATE_FILE) -> Optional[Path]:
    for path in _candidate_path_variants(file_path):
        if path.exists():
            return path
    return None


def _match_column(columns: List[str], aliases: Tuple[str, ...]) -> Optional[str]:
    exact_lookup = {str(col).strip(): col for col in columns}
    normalized_lookup = {str(col).strip().lower(): col for col in columns}

    for alias in aliases:
        if alias in exact_lookup:
            return exact_lookup[alias]
        lowered = alias.strip().lower()
        if lowered in normalized_lookup:
            return normalized_lookup[lowered]
    return None


def _standardize_candidate_frame(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    rename_map: Dict[str, str] = {}
    for standard_name, aliases in _COLUMN_ALIASES.items():
        matched = _match_column(list(df.columns), aliases)
        if matched is not None:
            rename_map[matched] = standard_name

    standardized = df.rename(columns=rename_map).copy()

    if "warehouse_id" not in standardized.columns:
        standardized["warehouse_id"] = [f"W{i + 1:04d}" for i in range(len(standardized))]
    if "name" not in standardized.columns:
        standardized["name"] = standardized["warehouse_id"]
    if "province" not in standardized.columns:
        standardized["province"] = ""
    if "city" not in standardized.columns:
        standardized["city"] = ""

    missing_coords = [col for col in ("lng", "lat") if col not in standardized.columns]
    if missing_coords:
        logger.error(f"候选仓文件缺少坐标列: {missing_coords}")
        return None

    standardized["warehouse_id"] = standardized["warehouse_id"].astype(str).str.strip()
    standardized["name"] = standardized["name"].astype(str).str.strip()
    standardized["province"] = standardized["province"].fillna("").astype(str).str.strip()
    standardized["city"] = standardized["city"].fillna("").astype(str).str.strip()
    standardized["lng"] = pd.to_numeric(standardized["lng"], errors="coerce")
    standardized["lat"] = pd.to_numeric(standardized["lat"], errors="coerce")

    standardized = standardized.dropna(subset=["lng", "lat"]).reset_index(drop=True)
    if standardized.empty:
        logger.error("候选仓文件中没有可用的经纬度数据。")
        return None

    return standardized[STANDARD_COLUMNS]

# 加载候选仓数据
def load_candidate_warehouses(file_path: str = DEFAULT_CANDIDATE_FILE) -> Optional[pd.DataFrame]:
    path = _resolve_candidate_path(file_path)
    if path is None:
        logger.error(f"找不到候选仓文件: {file_path}")
        return None
    try:
        return pd.read_csv(path) if path.suffix == '.csv' else pd.read_excel(path)
    except Exception as e:
        logger.error(f"读取文件失败: {e}")
        return None


def load_and_prepare_candidates(
    file_path: str = DEFAULT_CANDIDATE_FILE,
) -> Tuple[List[Dict[str, Any]], List[Tuple[float, float]], Optional[str]]:
    candidates = load_candidate_warehouses(file_path)
    if candidates is None or candidates.empty:
        return [], [], "候选仓数据为空或读取失败。"

    standardized = _standardize_candidate_frame(candidates)
    if standardized is None or standardized.empty:
        return [], [], "候选仓数据缺少有效的经纬度列。"

    nodes: List[Dict[str, Any]] = []
    candidate_coords: List[Tuple[float, float]] = []

    for row in standardized.to_dict(orient="records"):
        lng = float(row["lng"])
        lat = float(row["lat"])
        nodes.append(
            {
                "warehouse_id": row["warehouse_id"],
                "name": row["name"],
                "province": row["province"],
                "city": row["city"],
                "lng": lng,
                "lat": lat,
            }
        )
        candidate_coords.append((lng, lat))

    return nodes, candidate_coords, None


# 距离计算 Haversine 公式
def haversine_matrix(coords_a: np.ndarray, coords_b: np.ndarray) -> np.ndarray:
    """计算两组经纬度点之间的球面距离矩阵"""
    lat_a = np.radians(coords_a[:, 1])[:, None]
    lon_a = np.radians(coords_a[:, 0])[:, None]
    lat_b = np.radians(coords_b[:, 1])[None, :]
    lon_b = np.radians(coords_b[:, 0])[None, :]
    
    dlat = lat_b - lat_a
    dlon = lon_b - lon_a
    a = np.sin(dlat/2)**2 + np.cos(lat_a) * np.cos(lat_b) * np.sin(dlon/2)**2
    return 2 * 6371 * np.arcsin(np.sqrt(a))


# K-Medoids 贪心逻辑
def select_warehouses(weighted_dist: np.ndarray, k: int) -> List[int]:
    """基于需求加权距离矩阵，贪心选出 K 个使总代价最小的中心点"""
    selected = []
    remaining = list(range(weighted_dist.shape[0]))  # 候选仓的索引池
    assigned_min = np.full(weighted_dist.shape[1], np.inf) # 每个场馆当前的最短距离
    
    for _ in range(k):
        best_idx, best_score = None, np.inf
        for c in remaining:
            # 假设选了仓库 c，场馆的距离更新为 现在的距离 和 选 c 的距离 中的较小值
            new_min = np.minimum(assigned_min, weighted_dist[c])
            score = new_min.sum()
            
            if score < best_score:
                best_score, best_idx = score, c
                
        selected.append(best_idx)
        remaining.remove(best_idx)
        assigned_min = np.minimum(assigned_min, weighted_dist[best_idx])
        
    return selected


# 主函数：执行选址流程
def run_k_medoids_selection(
    venues_df: pd.DataFrame, 
    k: int = 3, 
    candidates_path: str = DEFAULT_CANDIDATE_FILE
) -> Optional[pd.DataFrame]:
    # 1. 加载候选点
    candidates = load_candidate_warehouses(candidates_path)
    if candidates is None:
        return None

    standardized_candidates = _standardize_candidate_frame(candidates)
    if standardized_candidates is None:
        return None
    
    # 2. 提取坐标与权重
    try:
        candidate_coords = standardized_candidates[['lng', 'lat']].values
        venue_coords = venues_df[['经度', '纬度']].values
        venue_demands = venues_df['总需求kg'].values
    except KeyError as e:
        logger.error(f"数据框缺少必要的列: {e}")
        return None

    # 3. 计算 Haversine 距离矩阵
    dist_matrix = haversine_matrix(candidate_coords, venue_coords)
    
    # 4. 加入物资需求权重
    weighted_dist = dist_matrix * venue_demands[np.newaxis, :]
    
    # 5. 执行选址算法
    selected_idx = select_warehouses(weighted_dist, k)
    
    # 6. 返回选中的仓库信息
    selected_warehouses = standardized_candidates.iloc[selected_idx].copy()
    logger.info(f"成功选出 {k} 个中转仓。")
    
    return selected_warehouses.rename(
        columns={
            "name": "仓库名称",
            "province": "省",
            "city": "市",
            "lng": "经度",
            "lat": "纬度",
        }
    )[['仓库名称', '省', '市', '经度', '纬度']]

if __name__ == "__main__":
   pass
