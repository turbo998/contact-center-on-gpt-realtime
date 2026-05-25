# 06 · Deployment

本仓库 demo 设计为两种部署形态：**本地 docker-compose** 用于开发/演示，**Azure Container Apps** 用于云端/对外。

---

## 6.1 前置条件

| 工具 | 版本 | 用途 |
|------|------|------|
| Docker Desktop | 24+ | 本地容器 |
| Node.js | 20 LTS | 前端开发 |
| Python | 3.11+ | 后端开发 |
| Azure CLI | latest | 云上配额 / 权限 |
| Azure Developer CLI (`azd`) | latest | 一键部署 |
| `gh` CLI（可选） | latest | 推 Issue / PR |

**Foundry 资源要求**：

- 一个 **Azure AI Foundry / Azure OpenAI** 资源
- 三个模型部署：
  - `gpt-realtime-translate`
  - `gpt-realtime-whisper`
  - `gpt-realtime-2`
- 区域选择 —— translate 模型 GA 初期仅 **Canada Central / France Central / India South**，部署前请用 `az cognitiveservices account list-models` 确认目标区域可用

---

## 6.2 本地运行（docker-compose）

### 步骤

```bash
# 1. 克隆
git clone https://github.com/turbo998/contact-center-on-gpt-realtime.git
cd contact-center-on-gpt-realtime

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY 等

# 3. 一键起服务
docker compose up --build

# 4. 打开浏览器
# 前端:    http://localhost:3000
# 后端:    http://localhost:8000  (健康检查 GET /health)
# WS 测试: ws://localhost:8000/ws/customer
```

### 浏览器麦克风权限

- **`localhost` 在主流浏览器中默认豁免 HTTPS 要求**，可直接授权麦克风
- 如果走 IP（如 `192.168.x.x`）访问，需要自签证书或 ngrok

### 停止与清理

```bash
docker compose down              # 停服务
docker compose down -v           # 停 + 删卷（会清掉 audit 日志卷）
```

---

## 6.3 本地开发（不走 docker）

```bash
# Terminal 1 — backend
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1            # Windows
# source .venv/bin/activate           # macOS/Linux
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev                            # http://localhost:3000
```

---

## 6.4 Azure 部署（`azd up`）

### 一键部署

```bash
# 1. 登录
azd auth login
az login            # bicep provisioning 需要

# 2. 初始化环境（首次）
azd env new demo

# 3. 设置必需变量（preprovision hook 会校验）
azd env set AZURE_LOCATION              eastus
azd env set AZURE_FOUNDRY_ACCOUNT_NAME  <你的 Foundry 账户名>
azd env set AZURE_OPENAI_ENDPOINT       https://<account>.openai.azure.com
# 可选 — 默认值见 infra/main.parameters.json
azd env set AZURE_OPENAI_TRANSLATE_DEPLOYMENT  gpt-realtime-translate
azd env set AZURE_OPENAI_WHISPER_DEPLOYMENT    gpt-realtime-whisper
azd env set AZURE_OPENAI_RT2_DEPLOYMENT        gpt-realtime-2

# 4. 一键 provision + build + push + deploy
azd up
```

`azd up` 内部会：

1. 跑 `infra/main.bicep` 创建：
   - Log Analytics Workspace（PerGB2018, 30 天, 1 GB/day cap）
   - Container Apps Environment（attached to LAW）
   - User-Assigned Managed Identity（赋 **Cognitive Services OpenAI User** 角色到 Foundry 账户）
   - Azure Container Registry（Basic SKU, admin user 关闭；UAMI 获 **AcrPull**）
   - Backend Container App（external ingress :8000, transport=auto, `azd-service-name=backend`）
   - Frontend Container App（external ingress :3000, `azd-service-name=frontend`）
2. `docker build` 两个 Dockerfile 推送到 ACR（tag = git sha）
3. 用 UAMI 拉镜像启动 ACA —— **零 API key、零 ACR admin**
4. 注入环境变量：
   - backend: `AZURE_CLIENT_ID` / `AZURE_OPENAI_ENDPOINT` / 三个 deployment 名 / `APP_ENV=production`
   - frontend: `NEXT_PUBLIC_BACKEND_WS_URL`（由 backend URL 推导 `wss://`）
5. `postdeploy` hook 打印 `FRONTEND_URL` 和 `BACKEND_URL`

### 增量部署

```bash
azd deploy frontend            # 只更新前端镜像（不跑 bicep）
azd deploy backend             # 只更新后端镜像
azd provision                  # 只跑 Bicep，不重建镜像
```

### 输出与连接信息

部署完成后，所有输出写入 `.azure/<env>/.env`：

```bash
azd env get-values | grep -E 'URL|REGISTRY|CLIENT'
# FRONTEND_URL=https://ca-frontend-demo.<random>.<region>.azurecontainerapps.io
# BACKEND_URL=https://ca-backend-demo.<random>.<region>.azurecontainerapps.io
# AZURE_CONTAINER_REGISTRY_ENDPOINT=acr<hash>.azurecr.io
# AZURE_MANAGED_IDENTITY_CLIENT_ID=<guid>
```

### 查看日志

```bash
# 实时 tail backend
az containerapp logs show \
  -g "$(azd env get-value AZURE_RESOURCE_GROUP)" \
  -n "ca-backend-$(azd env get-value AZURE_ENV_NAME)" \
  --follow

# Log Analytics 跨容器查询
azd monitor                    # 打开 portal Log workspace
```

### 清理

```bash
azd down --purge               # 删除所有资源，含 Foundry 的软删除回收
```

---

## 6.5 云上认证：API Key vs Managed Identity

| 环境 | 推荐 | 备注 |
|------|------|------|
| 本地开发 | `AZURE_OPENAI_API_KEY` | 写在 `.env`，不要提交 |
| Azure Container Apps | Managed Identity + `DefaultAzureCredential` | Bicep 已经把 `Cognitive Services OpenAI User` 角色赋给 UAMI；后端代码 `DefaultAzureCredential()` 自动拿 token |

后端代码会根据 `APP_ENV` 切换：

```python
# 伪代码
if settings.app_env == "development":
    client = AsyncAzureOpenAI(api_key=settings.api_key, ...)
else:
    cred = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(cred, "https://cognitiveservices.azure.com/.default")
    client = AsyncAzureOpenAI(azure_ad_token_provider=token_provider, ...)
```

---

## 6.6 配额与限流

- **Realtime API 并发会话数**有配额限制，部署前 `az cognitiveservices account list-usage` 确认
- 演示场景一通通话最多并发 3 个会话（customer translate + whisper、agent translate、assist rt-2）
- 多人同时演示请乘以人数 × 3 估算配额

---

## 6.7 常见问题排查

| 现象 | 排查方向 |
|------|----------|
| WS 连接被 502 | Container Apps Ingress 需要勾选 `Transport: HTTP/2 Auto`；后端 ingress 必须 `External` |
| 麦克风提示无权限 | 确认走 `https://` 或 `localhost`；浏览器地址栏点击 🔒 重新授权 |
| `401 Unauthorized` 调 Foundry | 检查 MI 是否真的有 `Cognitive Services User`：`az role assignment list --assignee <miPrincipalId>` |
| 译文不出声 | 检查 AudioContext 是否 suspended（浏览器要求用户先交互一次） |
| audit 文件不生成 | `AUDIT_DIR` 在容器内可写？云上请改用 `AUDIT_SINK=blob` |
| 首音延迟高 | 看 backend 是否离 Foundry 资源跨区域；尽量同区域部署 |

---

下一步：[07-cost-estimate.md](./07-cost-estimate.md) 看演示一通通话大概多少钱。
