"""加权 K-Means 聚类模块 — 中转仓选址

核心优化：
- 引入 UTM 坐标投影，消除经纬度欧式距离在低纬度区域的失真
- 新增质心吸附机制（Centroid Snapping），使用 cKDTree 加速近邻查询
- 保留轮廓系数作为辅助参考指标，支持外部将碳排放作为终极评价标准
- 新增需求聚合器接口（Demand Aggregator），兼容多品类需求矩阵
- 增强输入校验与异常保护
"""
import numpy as np
import logging
from typing import List, Tuple, Dict, Optional, Callable
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from scipy.spatial import cKDTree
import warnings

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)


# ===================== UTM 坐标投影 =====================

def _lonlat_to_utm(
    coords: np.ndarray,
) -> np.ndarray:
    """
    将 (lng, lat) 坐标转换为近似 UTM 平面坐标（米），用于距离准确的聚类。

    采用简化墨卡托投影：以坐标集中心为投影原点，将经纬度换算为米制偏移量。
    在广东省（约北纬 22°~25°）尺度下精度优于直接使用经纬度欧式距离。

    Args:
        coords: shape=(N, 2)，列顺序为 (lng, lat)

    Returns:
        shape=(N, 2) 的平面坐标（米）
    """
    center_lng = coords[:, 0].mean()
    center_lat = coords[:, 1].mean()

    lat_rad = np.radians(center_lat)
    m_per_deg_lat = 111_132.92
    m_per_deg_lng = 111_132.92 * np.cos(lat_rad)

    projected = np.zeros_like(coords)
    projected[:, 0] = (coords[:, 0] - center_lng) * m_per_deg_lng
    projected[:, 1] = (coords[:, 1] - center_lat) * m_per_deg_lat
    return projected


# ===================== 质心吸附 =====================

def snap_centers_to_nearest(
    centers: np.ndarray,
    candidates: np.ndarray,
) -> np.ndarray:
    """
    将数学质心吸附到最近的候选点（消除"幽灵质心"问题）。

    使用 cKDTree 加速近邻查询，当候选点较多时显著优于暴力遍历。

    Args:
        centers: 聚类质心数组 shape=(K, 2)
        candidates: 候选可达点数组 shape=(M, 2)

    Returns:
        shape=(K, 2) 吸附后的质心坐标
    """
    tree = cKDTree(candidates)
    _, indices = tree.query(centers)
    return candidates[indices]


# ===================== 需求聚合器 =====================

def aggregate_demands(
    multi_category_demands: Dict[int, Dict[str, float]],
) -> List[float]:
    """
    将多品类需求矩阵压扁为一维总重量列表，供 K-Means 选址使用。

    Args:
        multi_category_demands: {节点索引: {"品类名": 重量_kg, ...}, ...}

    Returns:
        长度为 N 的总重量列表（按节点索引升序排列）
    """
    if not multi_category_demands:
        return []
    max_idx = max(multi_category_demands.keys())
    result = [0.0] * (max_idx + 1)
    for idx, categories in multi_category_demands.items():
        result[idx] = sum(categories.values())
    return result


# ===================== 加权 K-Means 聚类器 =====================

class WeightedKMeans:
    """加权 K-Means 聚类器，支持 UTM 投影与质心吸附。"""

    def __init__(self, n_clusters: int = 3, use_projection: bool = True):
        """
        Args:
            n_clusters: 聚类数 K
            use_projection: 是否启用 UTM 坐标投影（推荐开启）
        """
        self.n_clusters: int = n_clusters
        self.use_projection: bool = use_projection
        self.centers_: Optional[np.ndarray] = None
        self.labels_: Optional[np.ndarray] = None
        self.cluster_weights_: Optional[List[float]] = None

    def fit(
        self,
        coords: List[Tuple[float, float]],
        weights: List[float],
        snap_candidates: Optional[List[Tuple[float, float]]] = None,
    ) -> "WeightedKMeans":
        """
        执行加权 K-Means 聚类。

        Args:
            coords: 坐标列表 [(lng, lat), ...]
            weights: 各点权重（物资需求量 kg）
            snap_candidates: 可选的质心吸附候选点；为 None 时使用 coords 本身

        Returns:
            self
        """
        if len(coords) < self.n_clusters:
            raise ValueError(
                f"数据点数({len(coords)})少于聚类数({self.n_clusters})"
            )

        coords_array = np.array(coords, dtype=np.float64)
        weights_array = np.array(weights, dtype=np.float64)

        # 归一化权重
        w_sum = weights_array.sum()
        sample_weight = (
            weights_array / w_sum * len(weights)
            if w_sum > 0
            else np.ones_like(weights_array)
        )

        # 可选 UTM 投影
        fit_data = (
            _lonlat_to_utm(coords_array) if self.use_projection else coords_array
        )

        kmeans = KMeans(
            n_clusters=self.n_clusters,
            init="k-means++",
            n_init=10,
            max_iter=300,
            random_state=42,
        )
        kmeans.fit(fit_data, sample_weight=sample_weight)
        self.labels_ = kmeans.labels_

        if self.use_projection:
            # 将投影质心反映射回经纬度：取各簇内加权均值
            self.centers_ = np.zeros((self.n_clusters, 2))
            for k in range(self.n_clusters):
                mask = self.labels_ == k
                if mask.any():
                    cluster_weights = sample_weight[mask]
                    self.centers_[k] = np.average(
                        coords_array[mask], axis=0, weights=cluster_weights
                    )
        else:
            self.centers_ = kmeans.cluster_centers_

        # 质心吸附
        if snap_candidates is not None:
            candidates_array = np.array(snap_candidates, dtype=np.float64)
        else:
            candidates_array = coords_array
        self.centers_ = snap_centers_to_nearest(self.centers_, candidates_array)

        self.cluster_weights_ = self._calc_cluster_weights(weights_array)
        return self

    def _calc_cluster_weights(self, weights: np.ndarray) -> List[float]:
        """计算每个簇的总权重。"""
        cluster_w = [0.0] * self.n_clusters
        for label, w in zip(self.labels_, weights):
            cluster_w[label] += w
        return cluster_w

    def get_centers(self) -> List[Tuple[float, float]]:
        if self.centers_ is None:
            return []
        return [(float(c[0]), float(c[1])) for c in self.centers_]

    def get_labels(self) -> List[int]:
        return self.labels_.tolist() if self.labels_ is not None else []

    def get_cluster_weights(self) -> List[float]:
        return self.cluster_weights_ if self.cluster_weights_ else []


# ===================== 聚类评估 =====================

def evaluate_clustering(
    coords: List[Tuple[float, float]],
    weights: List[float],
    k_range: range = range(2, 7),
    use_projection: bool = True,
) -> Dict:
    """
    评估不同 K 值的聚类效果（轮廓系数作为辅助指标）。

    Args:
        coords: 坐标列表
        weights: 权重列表
        k_range: K 值范围
        use_projection: 是否启用 UTM 投影

    Returns:
        {K: {"silhouette": ..., "centers": ..., "labels": ..., ...}, ...}
    """
    coords_array = np.array(coords, dtype=np.float64)
    weights_array = np.array(weights, dtype=np.float64)

    results: Dict = {}

    for k in k_range:
        if k >= len(coords):
            continue
        try:
            wkm = WeightedKMeans(n_clusters=k, use_projection=use_projection)
            wkm.fit(coords, weights)

            labels = wkm.get_labels()
            silhouette = -1.0
            if len(set(labels)) > 1:
                silhouette = silhouette_score(
                    coords_array, labels
                )

            results[k] = {
                "silhouette": silhouette,
                "centers": wkm.get_centers(),
                "labels": labels,
                "cluster_weights": wkm.get_cluster_weights(),
            }
            logger.info(
                f"[K={k}] 轮廓系数: {silhouette:.4f}, "
                f"簇权重: {wkm.get_cluster_weights()}"
            )

        except Exception as e:
            logger.warning(f"[K={k}] 评估失败: {e}")
            results[k] = {"silhouette": -1.0, "error": str(e)}

    return results


def find_optimal_k(
    coords: List[Tuple[float, float]],
    weights: List[float],
    k_range: range = range(2, 7),
    use_projection: bool = True,
) -> Dict:
    """
    基于轮廓系数选择最优 K 值（辅助参考；全局最优应结合碳排放评估）。

    Returns:
        含最优 K 值、轮廓系数、聚类中心等的字典
    """
    results = evaluate_clustering(coords, weights, k_range, use_projection)
    valid = {k: v for k, v in results.items() if v.get("silhouette", -1) > -1}

    if not valid:
        return {"optimal_k": min(k_range), "error": "未找到有效聚类结果"}

    optimal_k = max(valid.keys(), key=lambda k: valid[k]["silhouette"])
    opt = valid[optimal_k]

    logger.info(f"最优 K={optimal_k}, 轮廓系数={opt['silhouette']:.4f}")
    return {
        "optimal_k": optimal_k,
        "silhouette": opt["silhouette"],
        "centers": opt["centers"],
        "labels": opt["labels"],
        "cluster_weights": opt["cluster_weights"],
        "all_results": valid,
    }


# ===================== 中转仓选址主函数 =====================

def select_warehouse_locations(
    coords: List[Tuple[float, float]],
    weights: List[float],
    max_warehouses: int = 6,
    snap_candidates: Optional[List[Tuple[float, float]]] = None,
) -> Dict:
    """
    中转仓选址主函数。

    Args:
        coords: 场馆坐标列表 [(lng, lat), ...]
        weights: 各场馆物资需求量 [kg, ...]
        max_warehouses: 最大仓库数量上限
        snap_candidates: 可选的质心吸附候选物流园坐标

    Returns:
        含最优仓库数、仓库详情、场馆分配关系的字典
    """
    if len(coords) < 2:
        return {
            "optimal_k": 1,
            "warehouses": [{
                "warehouse_idx": 0,
                "lng": coords[0][0],
                "lat": coords[0][1],
                "weight": sum(weights),
                "venue_count": len(coords),
                "venues": list(range(len(coords))),
            }],
            "venue_assignments": [
                {
                    "venue_idx": i,
                    "warehouse_idx": 0,
                    "coord": coords[i],
                    "weight": weights[i],
                }
                for i in range(len(coords))
            ],
        }

    k_range = range(1, min(max_warehouses + 1, len(coords)))
    logger.info(f"[中转仓选址] 评估 K={k_range.start}~{k_range.stop - 1}")

    result = find_optimal_k(coords, weights, k_range)
    optimal_k = result["optimal_k"]
    centers = result["centers"]
    labels = result["labels"]

    # 如果有吸附候选点，对最终质心再做一次吸附
    if snap_candidates is not None:
        centers_arr = np.array(centers, dtype=np.float64)
        cand_arr = np.array(snap_candidates, dtype=np.float64)
        centers_arr = snap_centers_to_nearest(centers_arr, cand_arr)
        centers = [(float(c[0]), float(c[1])) for c in centers_arr]

    # 构建仓库信息
    warehouses: List[Dict] = []
    for i, center in enumerate(centers):
        venue_indices = [idx for idx, lb in enumerate(labels) if lb == i]
        wh_weight = sum(weights[idx] for idx in venue_indices)
        warehouses.append({
            "warehouse_idx": i,
            "lng": center[0],
            "lat": center[1],
            "weight": wh_weight,
            "venue_count": len(venue_indices),
            "venues": venue_indices,
        })

    # 构建场馆分配信息
    venue_assignments: List[Dict] = []
    for idx, (coord, weight) in enumerate(zip(coords, weights)):
        wh_idx = labels[idx]
        venue_assignments.append({
            "venue_idx": idx,
            "warehouse_idx": wh_idx,
            "coord": coord,
            "weight": weight,
            "warehouse_coord": centers[wh_idx],
        })

    return {
        "optimal_k": optimal_k,
        "silhouette": result.get("silhouette", 0),
        "warehouses": warehouses,
        "venue_assignments": venue_assignments,
        "total_weight": sum(weights),
        "all_evaluation_results": result.get("all_results", {}),
    }


# ===================== 报告打印 =====================

def print_clustering_report(result: Dict) -> None:
    """打印聚类选址报告。"""
    print("\n" + "=" * 60)
    print("中转仓选址报告")
    print("=" * 60)

    print(f"\n最优仓库数量: {result['optimal_k']}")
    print(f"轮廓系数: {result.get('silhouette', 0):.4f}")
    print(f"总物资量: {result.get('total_weight', 0):,.0f} kg")

    print("\n--- 仓库详情 ---")
    for wh in result.get("warehouses", []):
        print(f"\n仓库 {wh['warehouse_idx'] + 1}:")
        print(f"  坐标: ({wh['lng']:.6f}, {wh['lat']:.6f})")
        print(f"  覆盖场馆数: {wh['venue_count']}")
        print(f"  物资总量: {wh['weight']:,.0f} kg")
        print(f"  覆盖场馆索引: {wh['venues']}")

    print("\n--- 场馆分配 ---")
    for va in result.get("venue_assignments", []):
        print(
            f"场馆{va['venue_idx']}: 分配到仓库{va['warehouse_idx'] + 1}, "
            f"坐标({va['coord'][0]:.4f}, {va['coord'][1]:.4f}), "
            f"需求{va['weight']:.0f}kg"
        )


# ===================== 测试入口 =====================

if __name__ == "__main__":
    print("=== 加权 K-Means 中转仓选址测试 ===\n")

    test_venues = [
        (113.2644, 23.1291),
        (113.2750, 23.1320),
        (113.2600, 23.1350),
        (113.2680, 23.1250),
        (113.2800, 23.1280),
    ]
    test_weights = [3000, 5000, 2000, 4000, 1500]

    print("测试场馆坐标:", test_venues)
    print("测试物资需求(kg):", test_weights)
    print()

    result = select_warehouse_locations(test_venues, test_weights, max_warehouses=4)
    print_clustering_report(result)
