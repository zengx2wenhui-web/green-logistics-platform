# 大型赛事绿色物流碳足迹优化平台

基于 Streamlit 的十五运会赛事物流碳排放智能分析与路径优化系统

## 功能模块

- 碳排放实时监控与预测
- VRP路径优化（最小化碳排放）
- 加权K-Means中转仓选址（UTM投影 + 质心吸附）
- 新能源车队配置优化

## 8步使用流程

1. 仓库设置 - 配置总仓库地址和坐标
2. 场馆录入 - 批量导入或逐条添加赛事场馆
3. 物资需求 - 为各场馆录入物资配送需求
4. 车辆配置 - 从车型库选择车辆并配置参数
5. 路径优化 - 执行物流网络优化计算（K-Means选址 + 贪心VRP）
6. 碳排放概览 - 赛事物流碳足迹实时监控
7. 碳排放分析 - 基于车型库的碳排放对比分析
8. 优化结果 - 查看优化详细结果与导出方案

## 技术栈

1. Streamlit - Web应用框架
2. Folium + Streamlit-Folium - 地理信息可视化
3. Plotly - 交互式数据可视化
4. Scikit-learn - 加权K-Means中转仓选址
5. SciPy - cKDTree质心吸附加速
6. 高德地图API - 地理编码/逆地理编码
7. NumPy - 向量化Haversine距离矩阵

## 核心算法

1. VRP路径优化
采用贪心最近邻算法，每辆车从仓库出发依次选择最近的未服务节点，直到容量用完返回仓库。
碳排放精确计算采用逐站载重递减公式：`E = Σ(距离 × 碳因子 × 当前载重)`

2. 中转仓选址
加权K-Means聚类，支持UTM坐标投影和cKDTree质心吸附，消除经纬度欧式距离失真。

3. 距离矩阵
向量化Haversine公式计算，配合路网弯曲系数（默认1.3×）估算实际驾车距离，支持SQLite持久化缓存。

## 本地运行

```bash
cd green-logistics-platform
pip install -r requirements.txt
streamlit run app.py
```

## 部署到 Streamlit Cloud

1. 将代码推送到 GitHub 仓库
2. 访问 https://share.streamlit.io/
3. 点击 "New app"
4. 选择你的 GitHub 仓库
5. 选择分支和主文件路径 (app.py)
6. 点击 "Deploy"

## 配置高德API密钥（可选）

在 Streamlit Cloud 的 Settings → Secrets 中添加：

```toml
AMAP_API_KEY = "your_amap_api_key"
```

> 注意：高德API密钥仅用于逆地理编码（中转仓地址显示），路径优化计算使用本地Haversine距离，无需API密钥即可正常运行。
