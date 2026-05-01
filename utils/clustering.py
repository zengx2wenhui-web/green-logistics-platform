from __future__ import annotations

import logging
import warnings
from typing import Dict, List, Optional, Tuple

import numpy as np

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)


def haversine_distance(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """Compute great-circle distance in kilometers."""
    lat1, lng1, lat2, lng2 = map(np.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlng / 2) ** 2
    return float(2 * 6371 * np.arcsin(np.sqrt(a)))


def aggregate_demands(multi_category_demands: Dict[int, Dict[str, float]]) -> List[float]:
    """Flatten multi-category demand values into total demand per point."""
    if not multi_category_demands:
        return []

    max_idx = max(multi_category_demands.keys())
    result = [0.0] * (max_idx + 1)
    for idx, categories in multi_category_demands.items():
        result[idx] = float(sum(categories.values()))
    return result


class WeightedKMedoids:
    def __init__(self, n_clusters: int = 3):
        self.n_clusters: int = n_clusters
        self.medoids_: Optional[np.ndarray] = None
        self.labels_: Optional[np.ndarray] = None
        self.cluster_weights_: Optional[List[float]] = None
        self.distance_matrix_: Optional[np.ndarray] = None

    def fit(
        self,
        coords: List[Tuple[float, float]],
        weights: List[float],
        candidates: List[Tuple[float, float]],
    ) -> "WeightedKMedoids":
        if len(candidates) < self.n_clusters:
            raise ValueError(f"候选点数({len(candidates)})少于聚类数({self.n_clusters})")
        if len(coords) != len(weights):
            raise ValueError("需求点坐标与权重数量不一致")
        if not coords:
            raise ValueError("需求点为空，无法执行 K-Medoids")

        coords_array = np.array(coords, dtype=np.float64)
        weights_array = np.array(weights, dtype=np.float64)
        candidates_array = np.array(candidates, dtype=np.float64)

        n_points = len(coords)
        n_candidates = len(candidates)
        self.distance_matrix_ = np.zeros((n_points, n_candidates), dtype=np.float64)

        for i in range(n_points):
            for j in range(n_candidates):
                self.distance_matrix_[i, j] = haversine_distance(
                    coords_array[i, 0],
                    coords_array[i, 1],
                    candidates_array[j, 0],
                    candidates_array[j, 1],
                )

        np.random.seed(42)
        medoid_indices = np.random.choice(n_candidates, self.n_clusters, replace=False)
        self.medoids_ = candidates_array[medoid_indices].copy()

        max_iter = 100
        for _ in range(max_iter):
            labels = np.zeros(n_points, dtype=int)
            for i in range(n_points):
                distances_to_medoids: list[float] = []
                for j in range(self.n_clusters):
                    medoid_idx = np.where((candidates_array == self.medoids_[j]).all(axis=1))[0]
                    if len(medoid_idx) > 0:
                        distances_to_medoids.append(float(self.distance_matrix_[i, medoid_idx[0]]))
                    else:
                        distances_to_medoids.append(
                            haversine_distance(
                                coords_array[i, 0],
                                coords_array[i, 1],
                                self.medoids_[j, 0],
                                self.medoids_[j, 1],
                            )
                        )
                labels[i] = int(np.argmin(distances_to_medoids))

            new_medoids = self.medoids_.copy()
            changed = False

            for cluster_idx in range(self.n_clusters):
                cluster_points = coords_array[labels == cluster_idx]
                cluster_weights = weights_array[labels == cluster_idx]
                if len(cluster_points) == 0:
                    continue

                best_cost = float("inf")
                best_medoid = self.medoids_[cluster_idx]

                for candidate in candidates_array:
                    total_cost = 0.0
                    for point, weight in zip(cluster_points, cluster_weights):
                        total_cost += haversine_distance(
                            point[0],
                            point[1],
                            candidate[0],
                            candidate[1],
                        ) * float(weight)

                    if total_cost < best_cost:
                        best_cost = total_cost
                        best_medoid = candidate

                if not np.array_equal(best_medoid, self.medoids_[cluster_idx]):
                    new_medoids[cluster_idx] = best_medoid
                    changed = True

            self.medoids_ = new_medoids
            if not changed:
                break

        self.labels_ = labels
        self.cluster_weights_ = self._calc_cluster_weights(weights_array)
        return self

    def _calc_cluster_weights(self, weights: np.ndarray) -> List[float]:
        cluster_weights = [0.0] * self.n_clusters
        if self.labels_ is None:
            return cluster_weights

        for label, weight in zip(self.labels_, weights):
            cluster_weights[int(label)] += float(weight)
        return cluster_weights

    def get_medoids(self) -> List[Tuple[float, float]]:
        if self.medoids_ is None:
            return []
        return [(float(medoid[0]), float(medoid[1])) for medoid in self.medoids_]

    def get_labels(self) -> List[int]:
        return self.labels_.tolist() if self.labels_ is not None else []


def find_optimal_k_kmedoids(
    coords: List[Tuple[float, float]],
    weights: List[float],
    candidates: List[Tuple[float, float]],
    k_range: range,
) -> Dict:
    """Select the k with minimum total weighted distance."""
    candidate_ks = list(k_range)
    valid_results: dict[int, dict[str, object]] = {}

    for k in candidate_ks:
        if k > len(candidates) or k <= 0:
            continue
        try:
            kmedoids = WeightedKMedoids(n_clusters=k)
            kmedoids.fit(coords, weights, candidates)
            valid_results[k] = {
                "medoids": kmedoids.get_medoids(),
                "labels": kmedoids.get_labels(),
                "cluster_weights": kmedoids.cluster_weights_,
            }
        except Exception as exc:
            logger.warning(f"[K-Medoids K={k}] 评估失败: {exc}")

    if not valid_results:
        fallback_k = candidate_ks[0] if candidate_ks else 0
        return {
            "optimal_k": fallback_k,
            "error": "未找到有效聚类结果",
            "medoids": [],
            "labels": [],
            "cluster_weights": [],
        }

    k_scores: dict[int, float] = {}
    for k, result in valid_results.items():
        medoids = result["medoids"]
        labels = result["labels"]
        total_weighted_distance = sum(
            haversine_distance(
                coords[i][0],
                coords[i][1],
                medoids[labels[i]][0],
                medoids[labels[i]][1],
            ) * weights[i]
            for i in range(len(coords))
        )
        k_scores[k] = float(total_weighted_distance)

    optimal_k = min(k_scores.keys(), key=lambda item: k_scores[item])
    logger.info(f"最优 K={optimal_k}, 总加权距离={k_scores[optimal_k]:.2f}")

    return {
        "optimal_k": optimal_k,
        "total_weighted_distance": k_scores[optimal_k],
        "medoids": valid_results[optimal_k]["medoids"],
        "labels": valid_results[optimal_k]["labels"],
        "cluster_weights": valid_results[optimal_k]["cluster_weights"],
    }


def select_warehouse_locations(
    coords: List[Tuple[float, float]],
    weights: List[float],
    max_warehouses: int,
    snap_candidates: List[Tuple[float, float]],
) -> Dict:
    """Run weighted K-Medoids warehouse selection."""
    if not coords:
        return {
            "optimal_k": 0,
            "total_weighted_distance": 0,
            "warehouses": [],
            "venue_assignments": [],
            "total_weight": 0,
            "algorithm": "K-Medoids",
        }

    if len(coords) < 2:
        return {
            "optimal_k": 1,
            "total_weighted_distance": 0,
            "warehouses": [
                {
                    "warehouse_idx": 0,
                    "lng": coords[0][0],
                    "lat": coords[0][1],
                    "weight": sum(weights),
                    "venue_count": len(coords),
                    "venues": list(range(len(coords))),
                }
            ],
            "venue_assignments": [
                {
                    "venue_idx": idx,
                    "warehouse_idx": 0,
                    "coord": coords[idx],
                    "weight": weights[idx],
                }
                for idx in range(len(coords))
            ],
            "total_weight": sum(weights),
            "algorithm": "K-Medoids",
        }

    upper_k = min(max(int(max_warehouses or 0), 1), len(snap_candidates), len(coords))
    if upper_k <= 0:
        return {
            "optimal_k": 0,
            "total_weighted_distance": 0,
            "warehouses": [],
            "venue_assignments": [],
            "total_weight": sum(weights),
            "algorithm": "K-Medoids",
            "error": "无可用候选仓或有效需求点",
        }

    k_range = range(1, upper_k + 1)
    logger.info(f"[中转仓选址] 评估 K={k_range.start}~{k_range.stop - 1}, 算法=K-Medoids")

    result = find_optimal_k_kmedoids(coords, weights, snap_candidates, k_range)
    optimal_k = int(result.get("optimal_k", 0) or 0)
    centers = list(result.get("medoids", []) or [])
    labels = list(result.get("labels", []) or [])

    warehouses = []
    for warehouse_idx, center in enumerate(centers):
        venue_indices = [idx for idx, label in enumerate(labels) if label == warehouse_idx]
        warehouses.append(
            {
                "warehouse_idx": warehouse_idx,
                "lng": center[0],
                "lat": center[1],
                "weight": sum(weights[idx] for idx in venue_indices),
                "venue_count": len(venue_indices),
                "venues": venue_indices,
            }
        )

    venue_assignments = [
        {
            "venue_idx": idx,
            "warehouse_idx": labels[idx],
            "coord": coord,
            "weight": weight,
            "warehouse_coord": centers[labels[idx]],
        }
        for idx, (coord, weight) in enumerate(zip(coords, weights))
        if idx < len(labels) and labels[idx] < len(centers)
    ]

    return {
        "optimal_k": optimal_k,
        "total_weighted_distance": result.get("total_weighted_distance", 0),
        "warehouses": warehouses,
        "venue_assignments": venue_assignments,
        "total_weight": sum(weights),
        "algorithm": "K-Medoids",
    }


def select_warehouse_from_national_candidates(
    venue_coords: List[Tuple[float, float]],
    venue_weights: List[float],
    max_warehouses: int = 6,
) -> Tuple[Optional[Dict], Optional[str]]:
    """Run K-Medoids against the national warehouse candidate set."""
    try:
        from utils.warehouse_candidate_loader import load_and_prepare_candidates

        nodes, candidate_coords, err = load_and_prepare_candidates()
        if err or not candidate_coords:
            return None, f"加载候选仓库失败: {err}"

        result = select_warehouse_locations(
            venue_coords,
            venue_weights,
            max_warehouses,
            candidate_coords,
        )

        if nodes and result.get("warehouses"):
            for warehouse in result["warehouses"]:
                matched_node = None
                for node in nodes:
                    if abs(node["lng"] - warehouse["lng"]) < 1e-6 and abs(node["lat"] - warehouse["lat"]) < 1e-6:
                        matched_node = node
                        break

                if matched_node:
                    warehouse["nearest_candidate_id"] = matched_node.get("warehouse_id", "未知ID")
                    warehouse["nearest_candidate_name"] = matched_node.get("name", "未命名物流园")
                    warehouse["province"] = matched_node.get("province", matched_node.get("省", ""))
                    warehouse["city"] = matched_node.get("city", matched_node.get("市", ""))
                else:
                    warehouse["nearest_candidate_name"] = "数据匹配失败"

        return result, None

    except Exception as exc:
        error_msg = f"全国候选仓库选址异常: {exc}"
        logger.error(error_msg)
        return None, error_msg


def print_clustering_report(result: Dict) -> None:
    print("\n" + "=" * 60)
    print(f"中转仓选址报告 (算法: {result.get('algorithm', '未知')})")
    print("=" * 60)
    print(f"\n最优仓库数量: {result.get('optimal_k', 0)}")
    print(f"总加权距离: {result.get('total_weighted_distance', 0):.2f}")
    print(f"总物资量: {result.get('total_weight', 0):,.0f} kg")

    print("\n--- 仓库详情 ---")
    for warehouse in result.get("warehouses", []):
        print(f"\n仓库 {warehouse['warehouse_idx'] + 1} [{warehouse.get('nearest_candidate_name', '模拟点')}]:")
        if "province" in warehouse:
            print(f"  位置: {warehouse['province']} {warehouse['city']}")
        print(f"  坐标: ({warehouse['lng']:.6f}, {warehouse['lat']:.6f})")
        print(f"  覆盖场馆数: {warehouse['venue_count']}")
        print(f"  物资总量: {warehouse['weight']:,.0f} kg")

    print("\n--- 场馆分配 ---")
    for assignment in result.get("venue_assignments", []):
        print(
            f"场馆{assignment['venue_idx']} 需求{assignment['weight']:.0f}kg -> 分配至仓库{assignment['warehouse_idx'] + 1}"
        )


if __name__ == "__main__":
    pass
