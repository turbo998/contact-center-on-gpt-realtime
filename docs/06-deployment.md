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

# 2. 初始化（首次）
azd init --template .

# 3. 部署
azd up
# azd 会问：
#   - environment name (e.g. dev)
#   - Azure subscription
#   - location (建议: eastus / canadacentral)
#   - openaiLocation (Foundry 区域，可与 location 不同)
```

`azd up` 内部会：

1. 用 `infra/main.bicep` 创建：
   - Resource Group
   - Azure Container Registry
   - Log Analytics Workspace
   - Container Apps Environment
   - 两个 Container App（frontend、backend）
   - User-Assigned Managed Identity（赋 `Cognitive Services User` 角色到 Foundry 资源）
2. 构建并推送两个 Docker 镜像到 ACR
3. 部署 Container Apps 并注入环境变量
4. 输出前端公开 URL（`https://contact-center-frontend.<random>.<region>.azurecontainerapps.io`）

### 增量部署

```bash
azd deploy frontend            # 只更新前端镜像
azd deploy backend             # 只更新后端镜像
azd provision                  # 只跑 Bicep，不重建镜像
```

### 查看日志

```bash
azd monitor                                              # 打开 portal
az containerapp logs show -n backend -g rg-<env> --follow
az containerapp logs show -n frontend -g rg-<env> --follow
```

### 清理

```bash
azd down --purge                # 删除所有资源，含 Key Vault 的软删除
```

---

## 6.5 云上认证：API Key vs Managed Identity

| 环境 | 推荐 | 备注 |
|------|------|------|
| 本地开发 | `AZURE_OPENAI_API_KEY` | 写在 `.env`，不要提交 |
| Azure Container Apps | Managed Identity + `DefaultAzureCredential` | Bicep 已经把 `Cognitive Services User` 角色赋给 UAMI；后端代码 `DefaultAzureCredential()` 自动拿 token |

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
