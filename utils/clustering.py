"""
加权 K-Medoids 聚类模块 — 全国中转仓选址

核心优化：
- 全面采用 Haversine 球面距离
- 采用 K-Medoids (PAM) 算法，确保选出的中转仓绝对是现实中可用的真实物流园
"""
import numpy as np
import logging
from typing import List, Tuple, Dict, Optional, Callable
import warnings

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

# ===================== 距离算法 =====================

def haversine_distance(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """计算单点对单点的 Haversine 球面距离（公里）"""
    lat1, lng1, lat2, lng2 = map(np.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlng/2)**2
    return 2 * 6371 * np.arcsin(np.sqrt(a))

# ===================== 需求聚合器 =====================

def aggregate_demands(multi_category_demands: Dict[int, Dict[str, float]]) -> List[float]:
    """将多品类需求矩阵压扁为一维总重量列表"""
    if not multi_category_demands:
        return []
    max_idx = max(multi_category_demands.keys())
    result = [0.0] * (max_idx + 1)
    for idx, categories in multi_category_demands.items():
        result[idx] = sum(categories.values())
    return result

# ===================== 加权 K-Medoids 聚类器 =====================

class WeightedKMedoids:
    """K-Medoids 聚类器，中心点必须来源于提供的真实候选集。"""

    def __init__(self, n_clusters: int = 3):
        self.n_clusters: int = n_clusters
        self.medoids_: Optional[np.ndarray] = None
        self.labels_: Optional[np.ndarray] = None
        self.cluster_weights_: Optional[List[float]] = None
        self.distance_matrix_: Optional[np.ndarray] = None

    def fit(self, coords: List[Tuple[float, float]], weights: List[float], candidates: List[Tuple[float, float]]) -> "WeightedKMedoids":
        if len(candidates) < self.n_clusters:
            raise ValueError(f"候选点数({len(candidates)})少于聚类数({self.n_clusters})")

        coords_array = np.array(coords, dtype=np.float64)
        weights_array = np.array(weights, dtype=np.float64)
        candidates_array = np.array(candidates, dtype=np.float64)

        n_points = len(coords)
        n_candidates = len(candidates)
        self.distance_matrix_ = np.zeros((n_points, n_candidates))

        # 预计算：需求点到所有候选点的球面距离
        for i in range(n_points):
            for j in range(n_candidates):
                self.distance_matrix_[i, j] = haversine_distance(
                    coords_array[i, 0], coords_array[i, 1],
                    candidates_array[j, 0], candidates_array[j, 1]
                )

        # 初始化：随机选 K 个候选点
        np.random.seed(42)
        medoid_indices = np.random.choice(n_candidates, self.n_clusters, replace=False)
        self.medoids_ = candidates_array[medoid_indices].copy()

        max_iter = 100
        for iteration in range(max_iter):
            # 步骤1: 依据最近加权距离分配标签
            labels = np.zeros(n_points, dtype=int)
            for i in range(n_points):
                distances_to_medoids = []
                for j in range(self.n_clusters):
                    medoid_idx = np.where((candidates_array == self.medoids_[j]).all(axis=1))[0]
                    if len(medoid_idx) > 0:
                        distances_to_medoids.append(self.distance_matrix_[i, medoid_idx[0]])
                    else:
                        dist = haversine_distance(coords_array[i, 0], coords_array[i, 1], self.medoids_[j, 0], self.medoids_[j, 1])
                        distances_to_medoids.append(dist)
                labels[i] = np.argmin(distances_to_medoids)

            # 步骤2: 更新中心点
            new_medoids = self.medoids_.copy()
            changed = False

            for k in range(self.n_clusters):
                cluster_points = coords_array[labels == k]
                if len(cluster_points) == 0:
                    continue

                best_cost = float('inf')
                best_medoid = self.medoids_[k]

                # 在所有真实候选点中寻找能让该簇总成本最低的点
                for candidate in candidates_array:
                    total_cost = 0
                    for point, weight in zip(cluster_points, weights_array[labels == k]):
                        dist = haversine_distance(point[0], point[1], candidate[0], candidate[1])
                        total_cost += dist * weight

                    if total_cost < best_cost:
                        best_cost = total_cost
                        best_medoid = candidate

                if not np.array_equal(best_medoid, self.medoids_[k]):
                    new_medoids[k] = best_medoid
                    changed = True

            self.medoids_ = new_medoids
            if not changed:
                break

        self.labels_ = labels
        self.cluster_weights_ = self._calc_cluster_weights(weights_array)
        return self

    def _calc_cluster_weights(self, weights: np.ndarray) -> List[float]:
        cluster_w = [0.0] * self.n_clusters
        for label, w in zip(self.labels_, weights):
            cluster_w[label] += w
        return cluster_w

    def get_medoids(self) -> List[Tuple[float, float]]:
        return [(float(m[0]), float(m[1])) for m in self.medoids_] if self.medoids_ is not None else []

    def get_labels(self) -> List[int]:
        return self.labels_.tolist() if self.labels_ is not None else []


# ===================== 核心选址主逻辑 =====================

def find_optimal_k_kmedoids(
    coords: List[Tuple[float, float]], weights: List[float], candidates: List[Tuple[float, float]], k_range: range
) -> Dict:
    """基于总加权距离选择最优 K 值"""
    valid_results = {}
    
    for k in k_range:
        if k > len(candidates):
            continue
        try:
            kmedoids = WeightedKMedoids(n_clusters=k)
            kmedoids.fit(coords, weights, candidates)
            valid_results[k] = {"medoids": kmedoids.get_medoids(), "labels": kmedoids.get_labels(), "cluster_weights": kmedoids.cluster_weights_}
        except Exception as e:
            logger.warning(f"[K-Medoids K={k}] 评估失败: {e}")

    if not valid_results:
        return {"optimal_k": min(k_range), "error": "未找到有效聚类结果"}

    k_scores = {}
    for k, result in valid_results.items():
        total_weighted_distance = sum(
            haversine_distance(coords[i][0], coords[i][1], result["medoids"][result["labels"][i]][0], result["medoids"][result["labels"][i]][1]) * weights[i]
            for i in range(len(coords))
        )
        k_scores[k] = total_weighted_distance

    optimal_k = min(k_scores.keys(), key=lambda k: k_scores[k])
    logger.info(f"最优 K={optimal_k}, 总加权距离={k_scores[optimal_k]:.2f}")
    
    return {
        "optimal_k": optimal_k,
        "total_weighted_distance": k_scores[optimal_k],
        "medoids": valid_results[optimal_k]["medoids"],
        "labels": valid_results[optimal_k]["labels"],
        "cluster_weights": valid_results[optimal_k]["cluster_weights"]
    }

def select_warehouse_locations(
    coords: List[Tuple[float, float]], weights: List[float], max_warehouses: int, snap_candidates: List[Tuple[float, float]]
) -> Dict:
    """中转仓选址主函数，执行 K-Medoids"""
    if len(coords) < 2:
        return {
            "optimal_k": 1,
            "warehouses": [{"warehouse_idx": 0, "lng": coords[0][0], "lat": coords[0][1], "weight": sum(weights), "venue_count": len(coords), "venues": list(range(len(coords)))}],
            "venue_assignments": [{"venue_idx": i, "warehouse_idx": 0, "coord": coords[i], "weight": weights[i]} for i in range(len(coords))],
        }

    k_range = range(1, min(max_warehouses + 1, len(snap_candidates)))
    logger.info(f"[中转仓选址] 评估 K={k_range.start}~{k_range.stop - 1}, 算法=K-Medoids")

    result = find_optimal_k_kmedoids(coords, weights, snap_candidates, k_range)
    optimal_k, centers, labels = result["optimal_k"], result["medoids"], result["labels"]

    warehouses = []
    for i, center in enumerate(centers):
        venue_indices = [idx for idx, lb in enumerate(labels) if lb == i]
        warehouses.append({
            "warehouse_idx": i, "lng": center[0], "lat": center[1],
            "weight": sum(weights[idx] for idx in venue_indices),
            "venue_count": len(venue_indices), "venues": venue_indices,
        })

    venue_assignments = [
        {"venue_idx": idx, "warehouse_idx": labels[idx], "coord": coord, "weight": weight, "warehouse_coord": centers[labels[idx]]}
        for idx, (coord, weight) in enumerate(zip(coords, weights))
    ]

    return {"optimal_k": optimal_k, "total_weighted_distance": result.get("total_weighted_distance", 0), "warehouses": warehouses, "venue_assignments": venue_assignments, "total_weight": sum(weights), "algorithm": "K-Medoids"}


# ===================== 候选仓库集成与元数据匹配 =====================

def select_warehouse_from_national_candidates(
    venue_coords: List[Tuple[float, float]], venue_weights: List[float], max_warehouses: int = 6
) -> Tuple[Optional[Dict], Optional[str]]:
    """使用全国候选仓库进行 K-Medoids 选址并返回包含名称的明细"""
    try:
        from utils.warehouse_candidate_loader import load_and_prepare_candidates
        
        nodes, candidate_coords, err = load_and_prepare_candidates()
        if err or not candidate_coords:
            return None, f"加载候选仓库失败: {err}"

        result = select_warehouse_locations(venue_coords, venue_weights, max_warehouses, candidate_coords)

        # 直接通过坐标绝对一致性查找对应候选仓库信息（因为 K-Medoids 输出的点必定在池子里）
        if nodes and result.get("warehouses"):
            for wh in result["warehouses"]:
                matched_node = None
                for node in nodes:
                    # 允许 1e-6 的浮点数容差
                    if abs(node["lng"] - wh["lng"]) < 1e-6 and abs(node["lat"] - wh["lat"]) < 1e-6:
                        matched_node = node
                        break
                
                if matched_node:
                    wh["nearest_candidate_id"] = matched_node.get("warehouse_id", "未知ID")
                    wh["nearest_candidate_name"] = matched_node.get("name", "未命名物流园")
                    wh["province"] = matched_node.get("省", "")
                    wh["city"] = matched_node.get("市", "")
                else:
                    wh["nearest_candidate_name"] = "数据匹配失败"
                    
        return result, None

    except Exception as e:
        error_msg = f"全国候选仓库选址异常: {str(e)}"
        logger.error(error_msg)
        return None, error_msg


# ===================== 报告打印与测试 =====================

def print_clustering_report(result: Dict) -> None:
    print("\n" + "=" * 60)
    print(f"中转仓选址报告 (算法: {result.get('algorithm', '未知')})")
    print("=" * 60)
    print(f"\n最优仓库数量: {result['optimal_k']}")
    print(f"总加权距离: {result.get('total_weighted_distance', 0):.2f}")
    print(f"总物资量: {result.get('total_weight', 0):,.0f} kg")

    print("\n--- 仓库详情 ---")
    for wh in result.get("warehouses", []):
        print(f"\n仓库 {wh['warehouse_idx'] + 1} [{wh.get('nearest_candidate_name', '模拟点')}]:")
        if "province" in wh:
            print(f"  位置: {wh['province']} {wh['city']}")
        print(f"  坐标: ({wh['lng']:.6f}, {wh['lat']:.6f})")
        print(f"  覆盖场馆数: {wh['venue_count']}")
        print(f"  物资总量: {wh['weight']:,.0f} kg")

    print("\n--- 场馆分配 ---")
    for va in result.get("venue_assignments", []):
        print(f"场馆{va['venue_idx']} 需求{va['weight']:.0f}kg -> 分配至仓库{va['warehouse_idx'] + 1}")

if __name__ == "__main__":
    print("=== 全国候选集 K-Medoids 中转仓选址测试 ===\n")
    pass