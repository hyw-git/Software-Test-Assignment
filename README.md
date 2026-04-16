# AI 增强自动化测试工具系统（Black-box Only）

本项目用于 Assignment1，固定采用黑盒动态测试路线，支持从需求/代码文档自动生成黑盒测试用例，并保存历史结果用于分析。


## 1. 项目结构

```
.
├─ ai-service/                 # FastAPI，负责调用 LLM 生成测试用例
│  ├─ app/main.py
│  ├─ Dockerfile
│  └─ requirements.txt
├─ backend/                    # Express，负责编排、质量分析、落库、历史接口
│  ├─ src/index.js
│  ├─ src/db.js
│  ├─ Dockerfile
│  └─ package.json
├─ frontend/                   # Vue + Vite 前端（聊天式界面）
│  ├─ src/App.vue
│  ├─ src/style.css
│  └─ package.json
├─ infra/postgres/init.sql     # PostgreSQL 初始化脚本
├─ docker-compose.yml
├─ .env.example
└─ README.md
```


## 2. 技术栈与职责

- `frontend`：输入文件 + Prompt，展示 LLM 输出，导出 Markdown，历史弹窗管理
- `backend`：
  - 接收生成请求 `/api/testcases/generate`
  - 调用 `ai-service`
  - 质量分析与统计
  - 写入/查询/删除 PostgreSQL 历史记录
- `ai-service`：
  - 构造黑盒 Prompt
  - 调用 OpenAI 兼容接口（支持 `OPENAI_BASE_URL`）
  - 输出结构化 JSON + `llmRawOutput`
- `postgres`：持久化生成记录

---

## 3. 环境准备

### 3.1 先决条件

- Windows + Docker Desktop
- Node.js 20+
- npm 10+（建议）

### 3.2 配置环境变量

在项目根目录复制：

```powershell
Copy-Item .env.example .env
```

`.env.example` 关键项：

```env
POSTGRES_DB=aitest
POSTGRES_USER=aitest
POSTGRES_PASSWORD=aitest123
POSTGRES_PORT=5432

BACKEND_PORT=3000
AI_SERVICE_PORT=8000
FRONTEND_PORT=5173

TEST_TECHNIQUE=black-box

OPENAI_API_KEY=
OPENAI_MODEL=
OPENAI_BASE_URL=
ENABLE_PARSE_FALLBACK=false
```

说明：

- `OPENAI_API_KEY`：填写真实 Key 才会调用线上模型
- `OPENAI_MODEL`：例如 `deepseek-chat`、`gpt-4o-mini` 等
- `OPENAI_BASE_URL`：兼容网关地址（例如 DeepSeek/OpenAI 代理）
- `ENABLE_PARSE_FALLBACK=false`：建议保持 false，避免“解析失败后回退 mock”影响一致性

---

## 4. 一键启动（推荐）

在项目根目录：

```bash
docker compose up -d --build
```

查看状态：

```bash
docker compose ps
```

预期容器：

- `aitest-postgres`
- `aitest-ai-service`
- `aitest-backend`

健康检查：

- 后端健康：`http://localhost:3000/health`
- AI 服务健康：`http://localhost:8000/health`

停止服务：

```bash
docker compose down
```

清空数据库卷（谨慎）：

```bash
docker compose down -v
```

---

## 5. 前端启动

前端本地运行（建议开发时这样做）：

```bash
cd frontend
npm install
npm run dev
```

访问：

- 前端：`http://localhost:5173`

---

## 6. 联调测试流程

### Step 1：确认后端和 AI 服务正常

浏览器访问：

- `http://localhost:3000/health`
- `http://localhost:8000/health`

### Step 2：前端上传文件并发送

在前端页面中：

1. 点击底部“导入文件”上传需求文档（可多文件）
2. 在底部输入框填写 Prompt（可留空使用默认 Prompt）
3. 点击“发送”
4. 在中部结果窗口查看 LLM 输出（Markdown）

### Step 3：验证历史能力

1. 点击右上“历史记录”
2. 选择一条记录“查看详情”回填
3. 观察结果区出现“当前回填: #ID ...”标志
4. 可测试“删除”功能

### Step 4：导出结果

点击结果区“导出 Markdown”，检查下载文件内容。

---

## 7. API 速查

### 7.1 生成测试用例

`POST /api/testcases/generate`

请求示例：

```json
{
  "sourceType": "requirements",
  "content": "",
  "promptMode": "custom",
  "customPrompt": "请输出黑盒测试用例 Markdown",
  "documents": [
    {
      "name": "req.md",
      "type": "text/markdown",
      "content": "登录、锁定、找回密码"
    }
  ],
  "testTechnique": "black-box"
}
```

说明：

- `content` 与 `documents` 至少一个非空
- 前端当前主要走 `documents + customPrompt`

### 7.2 历史记录

- `GET /api/history?limit=20`
- `DELETE /api/history/:id`

### 7.3 实验分析指标

- `GET /api/analysis/experiment?limit=200`

---

## 8. 常见问题

### Q1: 前端点发送后报错 “Failed to generate test cases”

排查顺序：

1. 是否已上传至少一个文件
2. `backend` 与 `ai-service` 是否健康
3. 查看后端日志：

```bash
docker compose logs -f backend
```

4. 查看 AI 服务日志：

```bash
docker compose logs -f ai-service
```

### Q2: Docker 构建 Python 依赖失败（网络问题）

项目已在 `ai-service/Dockerfile` 使用清华源，若仍失败可检查本地网络代理。

### Q3: 结果区数量或内容异常

确认 `.env` 中：

```env
ENABLE_PARSE_FALLBACK=false
```

避免解析失败后回退 mock 造成理解偏差。

### Q4: 端口冲突

修改 `.env` 的 `BACKEND_PORT / AI_SERVICE_PORT / FRONTEND_PORT` 后重启。

---

## 9. 提交建议

- 前端改动主要在：`frontend/src/App.vue`, `frontend/src/style.css`
- 后端接口改动主要在：`backend/src/index.js`
- 生成逻辑改动主要在：`ai-service/app/main.py`
- 每次提交前至少执行一次：

```bash
cd frontend && npm run build
```

并确认健康接口可访问。

---

## 10. 当前版本说明

- 黑盒测试方法：EP / BVA / Combinatorial / StateTransition / DecisionTable
- 前端形态：全屏三段式（顶部/中部结果/底部输入）
- 结果展示：中部滚动窗口，支持历史回填标识与 Markdown 导出
