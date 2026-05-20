# AutoTestDesign — AI 驱动测试设计工具

面向 **Software Testing Assignment 2** 的全栈 AutoTestDesign 实现：在规则引擎（确定性）与 LLM（可选增强）双轨下，完成需求解析、风险分析、黑盒/白盒测试设计、测试预言、套件优化与多格式导出，并以 **FitnessAI**（智能健身辅助系统）作为目标应用验证工具有效性。

| 元数据 | 值 |
| --- | --- |
| Prompt 版本 | `autotestdesign-v6-fr-complete` |
| 规则引擎版本 | `autotestdesign-engine-v2` |
| 目标应用 | FitnessAI |
| 详细开发记录 | [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md) |
| 作业原文 | [Assignment2.md](Assignment2.md) |
| 目标应用上下文 | [FitnessAI_LLM_CONTEXT.md](FitnessAI_LLM_CONTEXT.md) |

---

## 目录

1. [项目简介](#1-项目简介)
2. [系统架构](#2-系统架构)
3. [功能与 Assignment2 符合性](#3-功能与-assignment2-符合性)
4. [仓库结构](#4-仓库结构)
5. [环境准备](#5-环境准备)
6. [快速启动](#6-快速启动)
7. [使用指南](#7-使用指南)
8. [API 参考](#8-api-参考)
9. [规则引擎模块](#9-规则引擎模块)
10. [导出与历史](#10-导出与历史)
11. [测试与验证](#11-测试与验证)
12. [常见问题](#12-常见问题)
13. [作业交付物清单](#13-作业交付物清单)
14. [相关文档](#14-相关文档)

---

## 1. 项目简介

### 1.1 做什么

本仓库实现的是 **AutoTestDesign 工具本身**（被测对象不是本工具）。工具流程对齐 ISTQB / ISO/IEC/IEEE 29119-4 思路：

```
多源需求输入 → 需求结构化 → 风险评分与优先级 → 黑盒/白盒用例设计
    → 测试预言 → 套件优化 → 交互式审查 → JSON / CSV / Markdown / Excel 导出
```

生成结果可写入 PostgreSQL，支持历史回看、实验指标统计与答辩演示。

### 1.2 测谁（目标应用）

**FitnessAI** 为固定目标应用，核心范围包括：

| 模块 | 测试关注点 |
| --- | --- |
| 姿态分析 `POST /api/analytics/pose` | `exerciseType` 等价类；MediaPipe `landmarks` 32/33/34 边界 |
| 状态机计数 | UP → DESCENDING → DOWN → ASCENDING → UP 完整循环；非法短循环不计数 |
| 训练记录过滤 | `count < 3` 且 `durationSeconds < 30` 不入库 |
| 训练计划 | 难度、组数、休息、`skipRest` 组合 |
| 仪表盘 | 趋势、分布、卡路里（MET × 体重 × 时长） |

导入 [FitnessAI_LLM_CONTEXT.md](FitnessAI_LLM_CONTEXT.md) 或点击前端 **填入示例** 即可快速演示。

### 1.3 设计原则

- **确定性优先**：`ai-service/app/engines/` 在无 API Key 时仍可产出完整 FR 工件（`mock+engine`）。
- **LLM 增强**：配置 `OPENAI_API_KEY` 后合并 LLM 输出，并经 `schema_validator` 校验。
- **可审查**：覆盖项、测试策略、用例（表格/JSON）、追溯矩阵均可编辑后 **Apply Changes**。
- **可追踪**：`engineMetadata`、`timingMetrics`、`promptVersion` 随响应与历史记录保存。

---

## 2. 系统架构

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         浏览器  http://localhost:5173                     │
│   Vue 3 + Vite：输入 / 生成 / 符合性面板 / 审查 / 导出 / 历史              │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │ HTTP
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    Express Backend  :3000                                 │
│   编排 · 质量分析 · assignmentCompliance · 落库 · 导出代理 · 历史 API      │
└───────────────┬──────────────────────────────────────┬───────────────────┘
                │                                      │
                ▼                                      ▼
┌───────────────────────────────┐      ┌───────────────────────────────────┐
│  FastAPI ai-service  :8000    │      │  PostgreSQL  :5432                 │
│  engines/ 规则引擎 (≤2s NFR)  │      │  generation_records（JSONB 列）    │
│  LLM（OpenAI 兼容，可选）      │      └───────────────────────────────────┘
│  openpyxl → .xlsx 四表导出    │
└───────────────────────────────┘
```

### 2.1 生成流水线

1. 前端合并 **纯文本 / CSV / 上传文件** 为 `content` + `documents`。
2. `backend` 转发至 `ai-service` `POST /generate-testcases`。
3. `run_deterministic_pipeline()` 产出引擎工件并记录 `engineMs`。
4. （可选）LLM 生成 JSON，`merge_engine_with_llm()` 与引擎结果合并。
5. `backend` 质量分析、`buildAssignmentCompliance`，`insertGenerationRecord` 落库。
6. 前端 `syncReviewFromResult()` 填充审查区（合并 API 与 LLM 解析，避免策略丢失）。

### 2.2 运行模式

| 模式 | 条件 | 行为 |
| --- | --- | --- |
| 离线演示 | `OPENAI_API_KEY` 为空 | 规则引擎 + 内置 mock 文本，FR 面板仍可全绿 |
| 在线增强 | 配置 Key + `OPENAI_BASE_URL` + `OPENAI_MODEL` | LLM 补充用例与叙述，`totalMs` 含 LLM 耗时 |

---

## 3. 功能与 Assignment2 符合性

### 3.1 功能性需求（FR）

| FR | 描述 | 实现状态 | 主要实现 |
| --- | --- | --- | --- |
| **FR 1.0** | CSV / 纯文本 / 文件导入 | ✅ | 前端多源输入；`requirement_parser` |
| **FR 1.1** | 需求结构化 | ✅ | `requirementsStructured`（字段、范围、条件、预期） |
| **FR 2.0** | 风险分与 H/M/L 优先级 | ✅ | `riskScore = impact × likelihood`；`GET /api/risk-matrix` |
| **FR 3.0** | ≥3 种黑盒技术 | ✅ | EP、BVA、DecisionTable、Combinatorial（Pairwise） |
| **FR 4.0** | 白盒状态模型与序列 | ✅ 加分 | `whitebox_engine`；`all-states` / `all-transitions` |
| **FR 5.0** | 测试预言 | ✅ 加分 | 用例 `oracle` 字段；`oracle_engine` |
| **FR 6.0** | JSON / CSV / Excel 导出 | ✅ | `.xlsx` 四表；Markdown；`POST /api/export/artifacts` |
| **FR 7.0** | 套件优化 | ✅ 加分 | `risk-first` / `minimize`；`testSuiteOptimization` |
| **交互式审查** | 编辑并应用变更 | ✅ | 覆盖项 / 策略 / 用例表格 / 追溯 |

各 FR 的实现原理、验证步骤与答辩论证见 [DEVELOPMENT_LOG.md §2.5](DEVELOPMENT_LOG.md#25-各-fr-实现原理验证流程与对应论证)。

### 3.2 非功能性需求（NFR）

| NFR | 说明 |
| --- | --- |
| 性能 | 规则引擎目标 ≤2s；界面展示 `engineMs`、`engineMeetsNfr`、`totalMs` |
| 可用性 | FitnessAI 工作区、填入示例、Advanced Options、符合性双面板、响应式布局 |
| 安全 | API Key 仅 `.env`；生产需收紧 CORS |
| 可维护性 | 引擎按 FR 分文件；版本号可追踪；Docker Compose 一键部署 |

---

## 4. 仓库结构

```
Software-Test-Assignment/
├── frontend/                      # Vue 3 + Vite 单页应用
│   └── src/App.vue                # 主界面：输入、生成、审查、导出、历史
├── backend/                       # Express API 网关与持久化
│   └── src/
│       ├── index.js               # 路由、符合性、导出、历史
│       └── db.js                  # PostgreSQL schema 与 INSERT
├── ai-service/                    # FastAPI + 规则引擎 + LLM
│   ├── app/
│   │   ├── main.py                # Prompt、生成、风险矩阵、xlsx 导出
│   │   ├── export_xlsx.py         # openpyxl 四表工作簿
│   │   └── engines/               # FR 1.0–7.0 确定性实现
│   │       ├── requirement_parser.py
│   │       ├── risk_engine.py / risk_config.py
│   │       ├── blackbox_engine.py
│   │       ├── whitebox_engine.py
│   │       ├── oracle_engine.py
│   │       ├── suite_optimizer.py
│   │       ├── strategy_builder.py
│   │       ├── schema_validator.py
│   │       └── pipeline.py
│   └── tests/test_engines.py      # 引擎单元测试
├── infra/postgres/init.sql        # 库表初始化（新卷）
├── docker-compose.yml             # postgres + ai-service + backend
├── .env.example
├── Assignment2.md                 # 作业说明
├── FitnessAI_LLM_CONTEXT.md       # 目标应用需求上下文
├── DEVELOPMENT_LOG.md             # 开发日志、测试流程、FR 深度对照
└── README.md                      # 本文档
```

> **说明**：前端默认 **本地** `npm run dev`，不打包进 Docker；后端与 AI 服务由 Compose 构建。

---

## 5. 环境准备

### 5.1 先决条件

- **Windows / macOS / Linux**
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)（运行 postgres、backend、ai-service）
- **Node.js 20+** 与 **npm 10+**（前端开发与构建）
- （可选）Python 3.11+（本地跑 `ai-service/tests`）

### 5.2 配置环境变量

在项目根目录执行：

```powershell
Copy-Item .env.example .env
```

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `POSTGRES_*` | 见 `.env.example` | 数据库连接 |
| `BACKEND_PORT` | `3000` | Express 端口 |
| `AI_SERVICE_PORT` | `8000` | FastAPI 端口 |
| `FRONTEND_PORT` | `5173` | 前端 dev 端口（文档用） |
| `OPENAI_API_KEY` | 空 | 留空则离线 `mock+engine` |
| `OPENAI_MODEL` | 空 | 如 `deepseek-chat`、`gpt-4o-mini` |
| `OPENAI_BASE_URL` | 空 | OpenAI 兼容网关 |
| `ENABLE_PARSE_FALLBACK` | `false` | 建议保持 `false`，避免静默回退 mock |
| `TEST_TECHNIQUE` | `black-box` | 默认测试技术标签 |

---

## 6. 快速启动

### 6.1 启动后端栈（Docker）

```powershell
cd Software-Test-Assignment
docker compose up -d --build
docker compose ps
```

预期三个容器均为 **Up**（ai-service 为 **healthy**）：

| 容器名 | 端口 |
| --- | --- |
| `aitest-postgres` | 5432 |
| `aitest-ai-service` | 8000 |
| `aitest-backend` | 3000 |

健康检查：

```powershell
Invoke-RestMethod http://localhost:3000/health
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:3000/api/engines/info
```

`engines/info` 应返回 `engineVersion: autotestdesign-engine-v2`。

### 6.2 启动前端（本地）

```powershell
cd frontend
npm install
npm run dev
```

浏览器访问：**http://localhost:5173**

### 6.3 修改代码后

| 改动位置 | 操作 |
| --- | --- |
| `backend/` 或 `ai-service/` | `docker compose up -d --build`（或只 rebuild 对应服务） |
| `frontend/` | 重启 `npm run dev`，浏览器 **Ctrl+F5** 强刷 |

### 6.4 停止与清理

```powershell
docker compose down          # 停止容器，保留数据卷
docker compose down -v       # 清空数据库（慎用，历史记录会丢失）
```

---

## 7. 使用指南

### 7.1 推荐演示流程（约 10 分钟）

1. 打开前端，确认标题区目标应用为 **FitnessAI**。
2. 点击 **填入示例**（纯文本 + CSV 样例）。
3. 在 **Advanced Options** 勾选 White-box、Oracle、Optimization；可选填写状态图描述（如 `UP -> DOWN -> UP`）。
4. 点击 **Generate Test Design**。
5. 查看：
   - **Metrics**：用例数、方法种类、`qualityScore`
   - **Assignment2 Compliance**：各 FR 通过状态
   - **Deterministic FR Engines**：`engineMs`、`parseChannel`
   - **Timing**：`engineMeetsNfr`（引擎 ≤2s）
6. 在 **Interactive Review** 中：
   - 编辑一条 `riskItems` 优先级或删增一条用例
   - 确认 **Coverage items** 为可读文本行（非 `[object Object]`）
   - 确认 **testStrategies (JSON)** 含 `STR-001` 等条目
   - 点击 **Apply Changes**
7. 依次导出 **Markdown / JSON / CSV / Excel (.xlsx)**。
8. 打开 **History** → **View** 回填某条记录。

### 7.2 输入方式

| 方式 | 操作 | 引擎识别 |
| --- | --- | --- |
| 纯文本 | Manual requirements 文本框 | `[Plain-text requirements]` |
| CSV | CSV requirements 文本框（含表头） | `parseChannel` 含 `csv` |
| 文件 | 底部导入 `.md` / `.txt` 等 | 并入 `documents[]` |
| 示例 | **填入示例** 按钮 | 预置 FitnessAI 场景 |

**CSV 表头示例**（与引擎解析一致）：

```csv
id,feature,input,condition,expected
REQ-POSE-001,姿态分析,exerciseType+landmarks,合法类型且33点,返回count/score/feedback
REQ-POSE-002,状态机计数,帧序列,完整UP-DOWN循环,count+1
```

### 7.3 审查区说明

| 区域 | 格式 | 说明 |
| --- | --- | --- |
| Artifacts JSON | JSON | 完整工件：`requirementsStructured`、`riskItems`、`stateModel` 等 |
| Coverage items | 每行一条 | 由引擎字符串列表渲染；对象项会自动提取 `feature`/`id` 等字段 |
| testStrategies (JSON) | JSON 数组 | ISO 29119-4 策略映射，含 `method`、`isoRef`、`linkedTestcases` |
| Test cases | 表格 / JSON | 表格可改 `title`、`steps`、`expected`、`oracle` |
| Traceability | JSON | `reqId` ↔ `coverageItems` ↔ `testcases` |

### 7.4 建议 Prompt（底部输入框，可选）

避免将 **工具能力** 写成 FitnessAI 需求，可使用：

```
请为目标应用 FitnessAI 生成测试设计工件。导入内容为 FitnessAI 的需求/接口/CSV，
不要分析 AutoTestDesign 工具本身。输出需包含：结构化需求、覆盖项、风险(impact×likelihood)、
至少三种黑盒技术、状态模型、oracle、套件优化与 traceability。保持系统要求的 JSON 结构。

FitnessAI 重点：/api/analytics/pose；SQUAT/PUSHUP/PLANK/JUMPING_JACK；
landmarks 32/33/34；深蹲状态循环；count<3 且 duration<30 过滤；计划模式组合；仪表盘卡路里。
```

---

## 8. API 参考

### 8.1 Backend（`:3000`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 服务健康；`targetApplication: FitnessAI` |
| GET | `/api/target-application` | 目标应用元数据 |
| GET | `/api/engines/info` | 规则引擎版本与 FR 模块映射 |
| POST | `/api/testcases/generate` | **主生成接口** |
| GET | `/api/history?limit=20` | 历史记录列表 |
| DELETE | `/api/history/:id` | 删除一条历史 |
| GET | `/api/risk-matrix` | 可配置风险矩阵（代理 ai-service） |
| POST | `/api/export/artifacts` | 导出 JSON / CSV / **xlsx**（xlsx 优先代理 ai-service） |
| GET | `/api/export?format=json\|csv` | 批量导出历史元数据 |
| GET | `/api/analysis/experiment?limit=200` | 实验统计指标 |

#### `POST /api/testcases/generate`

请求体示例：

```json
{
  "sourceType": "requirements",
  "content": "[Plain-text requirements]\n...\n[CSV requirements]\nid,feature,...",
  "promptMode": "custom",
  "customPrompt": "",
  "documents": [
    { "name": "FitnessAI_LLM_CONTEXT.md", "type": "text/markdown", "content": "..." }
  ],
  "testTechnique": "black-box",
  "includeWhitebox": true,
  "includeOracle": true,
  "includeOptimization": true,
  "whiteboxDescription": "UP -> DESCENDING -> DOWN -> ASCENDING -> UP",
  "coverageCriterion": "all-states"
}
```

响应要点（字段名可能嵌套在 `artifacts` / `data` 下）：

| 字段 | 说明 |
| --- | --- |
| `artifacts.requirementsStructured` | 结构化需求 |
| `artifacts.riskItems` | 风险项（含 `riskScore`、`priority`） |
| `artifacts.coverageItems` | 覆盖项列表 |
| `artifacts.testStrategies` | 测试策略（ISO 29119-4） |
| `artifacts.stateModel` | 白盒状态模型 |
| `artifacts.testSuiteOptimization` | 优化后套件 |
| `data.testcases` | 测试用例数组 |
| `assignmentCompliance` | 各 FR 通过状态与证据 |
| `engineMetadata` | `engineVersion`、`frEngines`、`parseChannel` |
| `timingMetrics` | `engineMs`、`llmMs`、`totalMs`、`engineMeetsNfr` |
| `quality` | 黑盒方法覆盖统计 |

### 8.2 AI Service（`:8000`，一般由 backend 调用）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | AI 服务健康 |
| POST | `/generate-testcases` | 引擎 + LLM 生成 |
| GET | `/api/risk-matrix` | 风险矩阵 JSON |
| POST | `/export-artifacts` | openpyxl 生成 xlsx 二进制 |
| GET | `/prompt-template` | 内置 Prompt 模板 |

---

## 9. 规则引擎模块

路径：`ai-service/app/engines/`

| 模块 | FR | 职责 |
| --- | --- | --- |
| `requirement_parser.py` | 1.0 / 1.1 | CSV、编号文本、FitnessAI 默认需求模板 |
| `risk_engine.py` + `risk_config.py` | 2.0 | `riskScore = impact × likelihood` → priority |
| `blackbox_engine.py` | 3.0 | EP、BVA、决策表、Pairwise 组合 |
| `whitebox_engine.py` | 4.0 | JSON/箭头 状态描述 + 默认深蹲模型 + 迁移序列 |
| `oracle_engine.py` | 5.0 | 规则化 `oracle` 附加 |
| `strategy_builder.py` | 策略 | ISO 29119-4 方法 → `testStrategies` |
| `suite_optimizer.py` | 7.0 | `risk-first` / `minimize` |
| `schema_validator.py` | 校验 | LLM JSON 结构校验 |
| `pipeline.py` | 编排 | `run_deterministic_pipeline`、`merge_engine_with_llm` |
| `export_xlsx.py` | 6.0 | Requirements / Risks / Strategies / TestCases 四表 |

本地运行引擎测试：

```powershell
cd ai-service
python -m unittest tests.test_engines -v
```

---

## 10. 导出与历史

### 10.1 导出格式

| 格式 | 入口 | 内容 |
| --- | --- | --- |
| Markdown | 前端按钮 | `llmRawOutput` 渲染稿 |
| JSON | 前端按钮 | 完整 `artifacts` + `testcases` |
| CSV | 前端按钮 | 扁平化用例表 |
| Excel `.xlsx` | 前端按钮 → `POST /api/export/artifacts` | 四工作表标准工件包 |

### 10.2 历史记录

每次成功生成写入 `generation_records`，包含：用例、结构化需求、覆盖项、风险、状态模型、优化结果、追溯、策略、`engine_metadata`、耗时等。  
**History → View** 可回填至审查区继续编辑。

---

## 11. 测试与验证

### 11.1 自动化

```powershell
# 前端生产构建
cd frontend && npm run build

# 引擎单元测试
cd ai-service && python -m unittest tests.test_engines -v

# 后端语法检查
cd backend && node --check src/index.js
```

### 11.2 冒烟清单

- [ ] `http://localhost:3000/health` 返回 ok
- [ ] `http://localhost:8000/health` 返回 ok
- [ ] 填入示例 → Generate → 无 INSERT 报错
- [ ] `testStrategies` 与 Coverage 审查区有内容
- [ ] xlsx 可用 Excel 打开且含四表
- [ ] History 可 View / Delete

完整场景 A–E 见 [DEVELOPMENT_LOG.md §6](DEVELOPMENT_LOG.md#6-完整工具测试流程)。

---

## 12. 作业交付物清单

仓库 **代码与 README** 支撑工具交付（约 20%）；其余 PDF/PPT/视频需小组基于工具输出撰写：

| # | 交付物 | 权重 | 仓库状态 |
| --- | --- | --- | --- |
| 1 | AutoTestDesign 源码 + README + 演示视频 | 20% | ✅ 代码/README；⬜ 视频待录制 |
| 2 | FitnessAI 风险分析报告 PDF | 10% | ⬜ 用导出 `riskItems` 撰写 |
| 3 | FitnessAI 测试计划 PDF | 40% | ⬜ 范围、架构、组织、框架、成本估算 |
| 4 | 详细测试设计与执行 PDF + PyTest | 30% | ⬜ 建议姿态 API 或状态机模块 |
| — | 演示 PPT（含团队信息首页） | — | ⬜ 约 15 分钟 |

---

## 13. 相关文档

| 文档 | 用途 |
| --- | --- |
| [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md) | FR 深度对照、引擎/API 明细、完整测试流程、版本记录 |
| [Assignment2.md](Assignment2.md) | 课程作业原文与评分结构 |
| [FitnessAI_LLM_CONTEXT.md](FitnessAI_LLM_CONTEXT.md) | 目标应用需求与接口说明（可导入生成） |

---

## 许可证与课程说明

本项目为课程作业实现，目标应用 **FitnessAI** 仅用于验证 AutoTestDesign 工具有效性。使用 LLM 时请遵守校方与 API 服务商规定，勿将真实 API Key 提交至公开仓库。
