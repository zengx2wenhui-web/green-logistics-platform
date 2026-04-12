# 修改日志

## 修改概览

本次修改涉及 **10 个文件**，核心目标是移除 OR-Tools 依赖、修复已知 Bug、统一显示规范。原始代码文件夹（`origin/`）未做任何更改。

---

## 一、后端 — OR-Tools 移除与 VRP 求解器重写

### `utils/vrp_solver.py` （完全重写）

**问题：** 原新代码依赖 `ortools` 库（`pywrapcp`、`routing_enums_pb2`）进行 CVRP 求解，安装繁琐且在部分环境下不稳定。

**解决方案：** 删除全部 OR-Tools 代码，改用纯 Python **贪心最近邻算法**（与原始代码 `origin/pages/7_path_optimization.py` 的逻辑一致）。

**主要变更：**
- 移除 `from ortools.constraint_solver import routing_enums_pb2, pywrapcp`
- 新增 `_greedy_nearest_neighbor()` 函数：每辆车从仓库出发，依次选择距离当前位置最近且剩余容量可容纳的未服务节点
- 保留 `GreenCVRP` 类接口（`solve()`、`_extract_detailed_route()`、`_build_result()`），内部调用贪心算法
- 保留 `solve_green_cvrp()` 便捷函数、`optimize_vehicle_count()` 车队规模优化、`print_vrp_result()` 结果打印
- 保留 `_validate_inputs()` 输入校验器（距离矩阵维度、需求超容量、负值检测）

**修复的原有 Bug：**
- `_extract_detailed_route` 中 `current_load` 未初始化（原代码只有 `current_load_ton` 但后续使用 `current_load`），统一为 `current_load_kg`
- `print_vrp_result` 中字典键名统一使用 `load_before_kg`

---

## 二、前端 — 路径优化页面重构

### `pages/5_路径优化.py` （大幅修改）

**问题1：** 页面包含 OR-Tools 相关 UI 控件（Use OR-Tools 复选框）和内联的 `greedy_vrp()` 备选函数。
**解决方案：** 移除 `use_ortools` 复选框和内联贪心函数，统一调用 `utils.vrp_solver.solve_green_cvrp`。

**问题2：** 原侧边栏（sidebar）放置 API 密钥输入框，每次计算过程中输入或交互会触发 Streamlit 自动重刷（rerun），导致计算中断。
**解决方案：** API 密钥输入框改为放在主区域（main area），并加入 `key="api_key_input"` 参数和 `st.session_state` 持久化，避免触发页面重刷。同时备注该密钥仅用于逆地理编码（非必填），不影响路径优化计算。

**细节变更：**
- 页面副标题从 "OR-Tools CVRP" 更新为 "贪心最近邻VRP"
- 为帮助文字添加说明："不填则中转仓地址仅显示坐标，不影响路径优化计算"

---

## 三、Bug 修复

### `pages/6_碳排放概览.py` （多处修复）

| Bug | 原代码 | 修复后 |
|-----|--------|--------|
| `carbon_equivalents` 键名不匹配 | `equiv.get("trees")` | `equiv.get("trees_per_year")` |
| `generate_optimization_suggestions` 调用签名错误 | `(baseline_emission, total_emission, vehicle_type)` 位置参数 | `(total_carbon_kg=, vehicle_type=, total_distance_km=)` 关键字参数 |
| `driving_km` 计算错误 | 使用错误变量 | `total_emission / 0.21` |
| 碳效率单位缺少下标 | `g CO/km`、`g CO/kg货物` | `g CO₂/km`、`g CO₂/kg货物` |

### `pages/8_优化结果.py` （键名修复）

| Bug | 原代码 | 修复后 |
|-----|--------|--------|
| `carbon_equivalents` 键名不匹配 | `equiv.get("trees")` | `equiv.get("trees_per_year")` |

### CO₂ 下标字符修复 （5 个文件）

以下页面中所有 `kg CO` 均修正为 `kg CO₂`（Unicode 下标字符 `₂`）：
- `pages/4_车辆配置.py`
- `pages/5_路径优化.py`
- `pages/6_碳排放概览.py`
- `pages/7_碳排放分析.py`
- `pages/8_优化结果.py`

---

## 四、依赖变更

### `requirements.txt`

| 变更 | 说明 |
|------|------|
| 移除 `ortools>=9.7.0` | 不再需要 OR-Tools 求解器 |
| 新增 `scipy>=1.10.0` | `utils/clustering.py` 中 `cKDTree` 空间索引依赖 |

---

## 五、文档更新

### `app.py`

- 首页技术栈描述："Streamlit + Folium + OR-Tools + Scikit-learn" → "Streamlit + Folium + Scikit-learn + 高德API"
- 功能卡片："OR-Tools CVRP求解" → "贪心最近邻VRP求解"
- 技术架构表："OR-Tools | CVRP求解" → "贪心最近邻 | VRP路径优化"
- 修复公式显示中乱码的乘号符号

### `README.md` （完全重写）

- 更新技术栈说明（移除 OR-Tools，新增 SciPy、NumPy）
- 新增算法说明（VRP 贪心最近邻、K-Means 聚类、Haversine 距离矩阵）
- 标注 API 密钥为可选项（仅用于逆地理编码）
- 更新页面步骤描述，与当前中文页面名称一致

### `DEPLOYMENT.md`

- 安装部分新增说明："无需安装 OR-Tools 等重量级求解器"
- API 密钥部分标注为可选，只用于逆地理编码

---

## 六、修改文件清单

| 文件 | 修改类型 |
|------|----------|
| `utils/vrp_solver.py` | 完全重写（OR-Tools → 贪心最近邻） |
| `pages/5_路径优化.py` | 移除 OR-Tools UI/逻辑，修复 API 密钥刷新问题 |
| `pages/6_碳排放概览.py` | 修复 4 个 Bug + CO₂ 显示 |
| `pages/8_优化结果.py` | 修复键名 Bug + CO₂ 显示 |
| `pages/4_车辆配置.py` | CO₂ 显示修复 |
| `pages/7_碳排放分析.py` | CO₂ 显示修复 |
| `requirements.txt` | 移除 ortools，新增 scipy |
| `app.py` | 技术栈描述更新 |
| `README.md` | 完全重写 |
| `DEPLOYMENT.md` | 安装说明更新 |
