# 04 · Tech Stack

## 4.1 技术选型矩阵

| 层 | 选择 | 版本（建议） | 理由 |
|----|------|--------------|------|
| **前端框架** | Next.js (App Router) | 14.x | SSR + 路由统一、对 WS / Streaming 友好 |
| **前端语言** | TypeScript | 5.x | 类型安全 |
| **UI 组件** | Tailwind CSS + shadcn/ui | latest | 三栏布局快速搭建 |
| **音频采集** | Web Audio API + AudioWorklet | — | 浏览器原生，低延迟 PCM16 输出 |
| **音频播放** | Web Audio API (AudioBufferSourceNode) | — | 低延迟流式播放 |
| **WS 客户端** | 浏览器原生 `WebSocket` | — | 简单稳定 |
| **后端框架** | FastAPI | 0.115+ | 原生 async、WS 支持完善、生态成熟 |
| **ASGI server** | uvicorn (+ uvloop on Linux) | latest | 配 `--ws websockets` |
| **AI SDK** | `openai` (async, Azure 模式) | 1.x | 同一 SDK 调三模型 |
| **Realtime SDK** | `openai.beta.realtime` | — | 直接对接 Realtime API |
| **配置管理** | `pydantic-settings` | 2.x | 12-factor 环境变量 |
| **认证（本地）** | API Key (`.env`) | — | 开发期最快路径 |
| **认证（云上）** | User-Assigned Managed Identity + `DefaultAzureCredential` | — | 零信任最佳实践 |
| **容器** | Docker | 24+ | 多阶段构建 |
| **本地编排** | docker-compose | v2 | 前后端一起起 |
| **云部署** | Azure Developer CLI (`azd`) | latest | `azd up` 一键 |
| **IaC** | Bicep | latest | 微软原生、可读性高 |
| **托管平台** | Azure Container Apps | — | WSS 长连接友好、按量计费 |
| **日志** | Azure Log Analytics | — | Container Apps 默认对接 |
| **可选缓存** | Azure Cache for Redis | — | 多副本时跨实例 session 共享 |
| **可选存档** | Azure Blob Storage (Append Blob) | — | 合规 JSONL 落地 |

## 4.2 目录结构

```
contact-center-on-gpt-realtime/
├── README.md
├── LICENSE
├── .gitignore
├── .env.example
├── docker-compose.yml
├── azure.yaml                    # azd 元数据
├── infra/                        # Bicep
│   ├── main.bicep
│   ├── main.parameters.json
│   └── modules/
│       ├── container-app.bicep
│       ├── container-registry.bicep
│       ├── log-analytics.bicep
│       ├── managed-identity.bicep
│       └── foundry-role-assignment.bicep
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── ruff.toml
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI 入口 + 路由挂载
│   │   ├── config.py             # pydantic-settings
│   │   ├── deps.py               # DI: settings / clients / session_store
│   │   ├── realtime/
│   │   │   ├── __init__.py
│   │   │   ├── base.py           # Realtime WS 公共封装
│   │   │   ├── translate.py
│   │   │   ├── whisper.py
│   │   │   └── assistant.py
│   │   ├── ws/
│   │   │   ├── __init__.py
│   │   │   ├── customer.py
│   │   │   ├── agent.py
│   │   │   └── assist.py
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── mock_crm.py
│   │   │   └── schemas.py        # function-calling JSON schema
│   │   ├── audit/
│   │   │   ├── __init__.py
│   │   │   ├── logger.py
│   │   │   └── sinks.py          # local / blob
│   │   └── session_store.py
│   └── tests/
│       ├── conftest.py
│       ├── test_translate.py
│       ├── test_whisper.py
│       ├── test_assistant.py
│       ├── test_tools.py
│       └── test_ws.py
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   ├── next.config.js
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx              # 三栏工作台
│   │   ├── globals.css
│   │   └── api/health/route.ts
│   ├── components/
│   │   ├── CustomerPane.tsx
│   │   ├── AgentPane.tsx
│   │   ├── AssistPane.tsx
│   │   ├── TranscriptList.tsx
│   │   ├── EscalateButton.tsx
│   │   ├── ReasoningTrace.tsx
│   │   └── ToolCallList.tsx
│   ├── lib/
│   │   ├── audio-worklet.ts
│   │   ├── audio-player.ts
│   │   ├── ws-client.ts
│   │   └── types.ts
│   └── public/
│       └── audio-worklet-processor.js
└── docs/
    ├── 01-overview.md
    ├── 02-business-scenario.md
    ├── 03-architecture.md
    ├── 04-tech-stack.md           ← 你正在看
    ├── 05-implementation-plan.md
    ├── 06-deployment.md
    ├── 07-cost-estimate.md
    ├── 08-risks-and-mitigations.md
    ├── 09-acceptance-criteria.md
    ├── 10-future-extensions.md
    └── assets/
        └── architecture.mmd
```

## 4.3 关键依赖清单

### `backend/pyproject.toml`（核心）

```toml
[project]
name = "contact-center-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "websockets>=13.0",
    "openai>=1.55",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "azure-identity>=1.19",
    "python-multipart>=0.0.12",
    "orjson>=3.10",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "ruff>=0.7",
    "mypy>=1.13",
]
blob = [
    "azure-storage-blob>=12.23",
]
```

### `frontend/package.json`（核心）

```json
{
  "name": "contact-center-frontend",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "next": "14.2.x",
    "react": "18.3.x",
    "react-dom": "18.3.x",
    "tailwindcss": "3.4.x",
    "class-variance-authority": "^0.7",
    "clsx": "^2.1",
    "lucide-react": "^0.460",
    "tailwind-merge": "^2.5"
  },
  "devDependencies": {
    "@types/node": "^22",
    "@types/react": "^18",
    "typescript": "^5.6",
    "eslint": "^9",
    "eslint-config-next": "14.2.x",
    "postcss": "^8",
    "autoprefixer": "^10"
  }
}
```

## 4.4 环境变量（`.env.example`）

```bash
# === Foundry / Azure OpenAI ===
AZURE_OPENAI_ENDPOINT=https://<your-foundry-resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=sk-...                 # 本地开发用；云上请用 Managed Identity
AZURE_OPENAI_API_VERSION=2025-04-01-preview

# 模型部署名（在 Foundry 部署时定义）
DEPLOYMENT_TRANSLATE=gpt-realtime-translate
DEPLOYMENT_WHISPER=gpt-realtime-whisper
DEPLOYMENT_ASSISTANT=gpt-realtime-2

# === 应用配置 ===
APP_ENV=development                          # development | production
LOG_LEVEL=INFO
AUDIT_SINK=local                             # local | blob
AUDIT_DIR=./audit                            # 当 AUDIT_SINK=local
AUDIT_BLOB_CONTAINER=audit                   # 当 AUDIT_SINK=blob
AUDIT_BLOB_ACCOUNT=                          # 当 AUDIT_SINK=blob

# === 业务参数 ===
DEFAULT_SOURCE_LANG=zh-CN
DEFAULT_TARGET_LANG=en-US
REASONING_EFFORT=high                        # minimal | low | medium | high
MAX_CALL_DURATION_SEC=300                    # 5 分钟自动断开，防止演示成本失控

# === CORS / 前端 ===
ALLOWED_ORIGINS=http://localhost:3000

# === 前端（NEXT_PUBLIC_）===
NEXT_PUBLIC_BACKEND_WS_BASE=ws://localhost:8000
```

## 4.5 编码规范建议

| 工具 | 配置 | 用途 |
|------|------|------|
| **ruff** | `backend/ruff.toml` | Python lint + format（替代 black + flake8 + isort） |
| **mypy** | strict mode | Python 类型检查（关键模块） |
| **eslint** | `next/core-web-vitals` preset | TS/React lint |
| **prettier** | 默认 + tailwind plugin | 前端 format |
| **pre-commit** | 可选 | 提交前自动跑 ruff + eslint |

约定：

- 后端文件统一 `from __future__ import annotations`
- 所有 IO 操作 `async`
- 配置只从 `app.config.settings` 单一入口读取
- Realtime API 协议消息用 `TypedDict` 强类型化
- 前端组件函数式 + props 接口显式定义

---

下一步：[05-implementation-plan.md](./05-implementation-plan.md) 看分阶段路线图。
