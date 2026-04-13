# AI 增强自动化测试工具系统（Black-box Only）

本项目针对 Assignment1 的要求，选择并实现了单一测试技术路线：黑盒动态测试。

实现目标：

- 工具支持两种输入：需求文本、代码库/模块描述
- AI 自动生成黑盒测试用例（EP/BVA/组合输入/状态迁移/决策表）
- 生成结果写入 PostgreSQL，便于后续准确率与泛化分析
- 前端可视化输入与结果展示

## 目录结构

```
.
├─ ai-service/                 # Python FastAPI，负责黑盒测试用例生成
│  ├─ app/main.py
│  ├─ Dockerfile
│  └─ requirements.txt
├─ backend/                    # Node.js Express，负责业务编排与落库
│  ├─ src/index.js
│  ├─ src/db.js
│  ├─ Dockerfile
│  └─ package.json
├─ frontend/                   # Vue + Vite 前端
│  ├─ src/App.vue
│  ├─ src/main.js
│  ├─ src/style.css
│  ├─ index.html
│  ├─ package.json
│  └─ vite.config.js
├─ infra/
│  └─ postgres/init.sql        # PostgreSQL 初始化表（仅保留生成记录）
├─ docker-compose.yml          # Docker Desktop 编排文件
├─ .env.example
└─ README.md
```

## 架构说明

- frontend：用户输入需求/代码库片段，调用 backend API
- backend：
  - 校验输入类型（requirements/codebase）
  - 调用 ai-service 生成黑盒测试用例
  - 将结果写入 PostgreSQL
- ai-service：
  - 有 OPENAI_API_KEY 时调用 OpenAI
  - 无密钥时回退 mock 用例，保证演示可跑
- postgres：存储测试用例生成记录

## 环境准备

1. 安装 Docker Desktop（Windows）
2. 启动 Docker Desktop
3. 在项目根目录复制环境变量文件

```bash
cp .env.example .env
```

Windows PowerShell 可以使用：

```powershell
Copy-Item .env.example .env
```

可选：在 .env 中配置 OPENAI_API_KEY

## 启动后端和数据库（Docker Desktop 管理）

在项目根目录执行：

```bash
docker compose up -d --build
```

启动后，你可以在 Docker Desktop 看到并管理以下容器：

- aitest-postgres
- aitest-backend
- aitest-ai-service

查看状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs -f backend
```

停止：

```bash
docker compose down
```

连同卷一起清理：

```bash
docker compose down -v
```

## 前端启动

前端默认本地运行（不强依赖 Docker）：

```bash
cd frontend
npm install
npm run dev
```

浏览器访问：

- 前端：http://localhost:5173
- 后端健康检查：http://localhost:3000/health
- AI 服务健康检查：http://localhost:8000/health

## API 说明

### 1) 生成黑盒测试用例

请求：

```http
POST /api/testcases/generate
Content-Type: application/json

{
  "testTechnique": "black-box",
  "sourceType": "requirements",
  "content": "用户输入用户名和密码后登录系统"
}
```

返回：

- AI 生成黑盒测试用例
- 后端写入 generation_records 表

## 数据表

- generation_records：记录黑盒测试用例生成结果

初始化脚本位于 infra/postgres/init.sql。

## 后续建议

1. 增加 black-box 覆盖度评估模块（按方法分类统计）
2. 增加鉴权（JWT）和权限模型
3. 增加测试执行引擎与通过率统计
4. 增加报告导出（PDF/HTML）
5. 引入消息队列处理长耗时任务
