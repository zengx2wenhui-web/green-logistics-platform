# 部署说明

## 目录

- [本地运行](#本地运行)
- [Streamlit Cloud 部署](#streamlit-cloud-部署)
- [Docker 部署](#docker-部署)
- [生产环境配置](#生产环境配置)
- [常见问题](#常见问题)

---

## 本地运行

### 1. 克隆项目

```bash
git clone https://github.com/your-repo/green-logistics-platform.git
cd green-logistics-platform
```

### 2. 创建虚拟环境（推荐）

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

> 注意：本项目无需安装 OR-Tools 等重量级求解器，所有核心算法均为纯 Python 实现。

### 4. 配置高德API密钥（可选）

高德API密钥仅用于逆地理编码（中转仓地址显示），路径优化计算使用本地Haversine距离，**无需API密钥即可正常运行**。

如需启用：
1. 注册高德开放平台账号: https://lbs.amap.com/
2. 创建应用，获取 Web API 密钥
3. 在路径优化页面的参数设置中填入密钥

### 5. 运行应用

```bash
streamlit run app.py
```

应用将在 `http://localhost:8501` 启动。

---

## Streamlit Cloud 部署

### 前置条件

1. GitHub 账号
2. 项目已推送到 GitHub 仓库
3. Streamlit Cloud 已登录: https://streamlit.io/cloud

### 部署步骤

#### 方法一：从 GitHub 部署

1. **推送代码到 GitHub**

   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/your-username/green-logistics-platform.git
   git push -u origin main
   ```

2. **登录 Streamlit Cloud**

   访问 https://share.streamlit.io/ 并使用 GitHub 账号登录

3. **创建新应用**

   - 点击 **New app**
   - 选择仓库: `your-username/green-logistics-platform`
   - 选择分支: `main`
   - 主文件路径: `app.py`
   - 点击 **Deploy!**

4. **配置 secrets（敏感信息）**

   在 Streamlit Cloud dashboard 中:
   - 点击您的应用 → **Settings** → **Secrets**
   - 添加以下配置:

   ```toml
   # 高德API密钥
   AMAP_API_KEY = "your_amap_api_key_here"

   # 其他配置（如需要）
   ```

   在代码中使用:

   ```python
   import streamlit as st

   api_key = st.secrets["AMAP_API_KEY"]
   ```

#### 方法二：使用 st.cli 部署

```bash
# 安装 streamlit
pip install streamlit

# 部署
streamlit deploy --cloud github -r main -p green-logistics-platform
```

### 部署配置

在项目根目录创建 `.streamlit/config.toml`:

```toml
[server]
port = 8501
enableCORS = false
enableXsrfProtection = true

[client]
showErrorDetails = false
toolbarMode = "minimal"
```

### 目录结构要求

```
green-logistics-platform/
├── app.py                  # 主入口（必需）
├── requirements.txt        # 依赖列表（必需）
├── pages/                  # 多页面目录
│   ├── 1_xxx.py
│   └── 2_xxx.py
├── utils/                  # 工具函数
│   └── *.py
├── data/                   # 数据文件
│   └── *.json
└── .streamlit/
    └── config.toml         # 配置文件（可选）
```

---

## Docker 部署

### Dockerfile

在项目根目录创建 `Dockerfile`:

```dockerfile
# Python 基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8501

# 启动命令
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

### 构建和运行

```bash
# 构建镜像
docker build -t green-logistics-platform .

# 运行容器
docker run -p 8501:8501 \
  -e AMAP_API_KEY="your_api_key" \
  green-logistics-platform
```

### Docker Compose

创建 `docker-compose.yml`:

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8501:8501"
    environment:
      - AMAP_API_KEY=${AMAP_API_KEY}
    volumes:
      # 挂载本地data目录（用于缓存）
      - ./data:/app/data
    restart: unless-stopped
```

运行:

```bash
AMAP_API_KEY="your_key" docker-compose up -d
```

---

## 生产环境配置

### 使用 Nginx 反向代理

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

### HTTPS 配置（使用 Let's Encrypt）

```bash
# 安装 certbot
sudo apt-get install certbot python3-certbot-nginx

# 获取证书
sudo certbot --nginx -d your-domain.com

# 自动续期（certbot会自动配置）
```

### 系统服务配置（systemd）

创建 `/etc/systemd/system/streamlit.service`:

```ini
[Unit]
Description=Streamlit Green Logistics Platform
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/green-logistics-platform
ExecStart=/path/to/venv/bin/streamlit run app.py --server.port=8501
Restart=always
Environment="AMAP_API_KEY=your_key"

[Install]
WantedBy=multi-user.target
```

启用服务:

```bash
sudo systemctl enable streamlit
sudo systemctl start streamlit
sudo systemctl status streamlit
```

### 性能优化

1. **使用 Gunicorn（不推荐，Streamlit有自己的服务器）**

2. **内存限制**

   ```bash
   streamlit run app.py --server.maxUploadSize=200
   ```

3. **缓存配置**

   在代码中使用 `@st.cache_data` 装饰器缓存数据加载

---

## 常见问题

### Q: 部署后地图不显示？

A: 检查:
1. 高德API密钥是否正确配置
2. API密钥是否在对应域名下开通了Web服务
3. 浏览器控制台是否有跨域错误

### Q: 页面加载很慢？

A: 优化建议:
1. 使用 `@st.cache_data` 缓存数据加载
2. 减少页面中的图表数量
3. 使用分页加载大量数据
4. 考虑使用 `st.fragment` 局部刷新

### Q: Session state 数据丢失？

A: Streamlit Cloud 使用无状态容器，每次刷新页面 session_state 会重置。如需持久化，使用:
- 外置数据库（PostgreSQL, MongoDB）
- 文件存储（S3, 本地文件）
- 或者接受无状态设计

### Q: 如何添加自定义页面？

A:
1. 在 `pages/` 目录创建新文件
2. 命名格式: `数字_页面名称.py`（如 `6_自定义分析.py`）
3. 使用 `st.set_page_config()` 配置页面属性
4. 页面会自动出现在侧边栏导航

### Q: 跨域问题（CORS）？

A: Streamlit 默认不允许跨域。在 `.streamlit/config.toml`:

```toml
[server]
enableCORS = false  # 允许所有跨域
# 或
allowedCrossOrigin = ["https://your-domain.com"]
```

---

## 环境变量参考

| 变量名 | 说明 | 示例 |
|-------|------|------|
| `AMAP_API_KEY` | 高德地图API密钥 | `19fb19b215b401509eb327b8c4e46c47` |
| `STREAMLIT_SERVER_PORT` | 服务端口 | `8501` |
| `STREAMLIT_SERVER_HEADLESS` | 无头模式 | `true` |

---

## 监控和维护

### 日志查看

```bash
# 本地
streamlit run app.py 2>&1 | tee logs.txt

# Docker
docker logs -f container_name

# systemd
journalctl -u streamlit -f
```

### 健康检查

```bash
curl http://localhost:8501/_stcore/health
```

应返回: `{"status": "ok"}`
