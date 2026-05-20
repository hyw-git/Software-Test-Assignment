# DEVELOPMENT_LOG — Assignment2 AutoTestDesign

> 文档版本：`2026-05-20` · Prompt `autotestdesign-v6-fr-complete` · 规则引擎 `autotestdesign-engine-v2`  
> 目标应用：**FitnessAI**（智能健身辅助系统）。风险报告、测试计划、详细测试设计等 **PDF 交付物面向 FitnessAI**，而非本工具本身。

---

## 1. 项目概述

### 1.1 作业定位

| 维度 | 说明 |
| --- | --- |
| **工具** | AI 驱动的 AutoTestDesign：需求解析 → 结构化 → 风险 → 黑盒/白盒设计 → 预言 → 套件优化 → 导出 |
| **目标应用** | FitnessAI：姿态分析、状态机计数、训练计划、记录过滤、仪表盘统计 |
| **必做 FR** | FR 1.0、1.1、2.0、3.0、6.0 + **交互式审查**（Assignment2「主要内容」） |
| **加分 FR** | FR 4.0、5.0、7.0（当前代码已实现） |

### 1.2 技术栈

```
┌─────────────┐     HTTP      ┌─────────────┐     HTTP      ┌─────────────┐
│  Vue 3 +    │ ────────────► │  Express    │ ────────────► │  FastAPI    │
│  Vite 前端   │               │  backend    │               │  ai-service │
│  :5173      │               │  :3000      │               │  :8000      │
└─────────────┘               └──────┬──────┘               └──────┬──────┘
                                     │                              │
                                     │         engines/ + LLM       │
                                     ▼                              ▼
                              ┌─────────────┐              OpenAI 兼容 API
                              │ PostgreSQL  │              （可选，无 Key 用 mock）
                              │  :5432      │
                              └─────────────┘
```

### 1.3 仓库结构

| 路径 | 职责 |
| --- | --- |
| `frontend/src/App.vue` | 多源输入、生成、符合性面板、规则引擎信息、JSON 审查、四种导出、历史 |
| `backend/src/index.js` | API 编排、质量分析、`assignmentCompliance`、导出、历史 |
| `backend/src/db.js` | 生成记录持久化（含结构化产物 JSONB 列） |
| `ai-service/app/main.py` | Prompt、LLM 调用、`_finalize_generation`（引擎 + LLM 合并） |
| `ai-service/app/engines/` | FR 1.0–7.0 确定性规则引擎 |
| `FitnessAI_LLM_CONTEXT.md` | 目标应用需求/接口上下文（供导入与 Prompt 参考） |
| `docker-compose.yml` | postgres + ai-service + backend |
| `README.md` | 安装、启动、API 速查 |

---

## 2. Assignment2 符合性审查

### 2.1 工具功能性需求（FR）

| FR | 作业要求 | 实现状态 | 实现位置与证据 | 残余风险 |
| --- | --- | --- | --- | --- |
| **FR 1.0** 输入/解析 | CSV、纯文本、直接输入 | **已满足** | 前端：文件上传、`manualRequirementText`、`csvRequirementText`；`buildManualContent()` 传原始 CSV 块 `[CSV requirements]`；后端接受 `content` + `documents` | 极复杂 CSV（嵌套引号跨行）未单独测尽 |
| **FR 1.1** 需求结构化 | 字段、范围、条件、预期动作 | **已满足** | `engines/requirement_parser.py`：`parse_csv_requirements`、`parse_numbered_requirements`、FitnessAI 默认模板；输出 `requirementsStructured`；可审查编辑 | 非 CSV/编号句式依赖 LLM 补充；无独立 NLP 模型 |
| **FR 2.0** 风险与优先级 | 风险分 + H/M/L | **已满足** | `engines/risk_engine.py`：`riskScore = impact × likelihood`，阈值映射 priority；`riskItems` 可审查 | 影响/似然初值来自特性权重表，非人工校准矩阵 |
| **FR 3.0** 黑盒设计 | ≥3 种 ISO 29119-4 技术 | **已满足** | `engines/blackbox_engine.py`：EP、BVA、DecisionTable、Combinatorial + 工件；`analyzeBlackBoxQuality()` 统计方法覆盖 | 「最优」组合非完备 pairwise；StateTransition 归白盒引擎 |
| **FR 4.0** 白盒建模 | 状态图 + 覆盖 + 序列 | **已满足（加分）** | `engines/whitebox_engine.py`：深蹲默认状态模型；`all-states` / `all-transitions` 生成 `StateTransition` 用例 | 仅当需求 `feature` 含「状态」时建图；非通用图编辑器 |
| **FR 5.0** 测试预言 | 合成预期结果 | **已满足（加分）** | `engines/oracle_engine.py`：规则模板 + 需求绑定；用例 `oracle` 字段 | 非符号执行；复杂业务需人工改 oracle |
| **FR 6.0** 输出导出 | JSON / Excel / CSV | **已满足** | 原生 `.xlsx`（openpyxl 四表）；Markdown/JSON/CSV；`POST /api/export/artifacts` | — |
| **FR 7.0** 套件优化 | 风险优先或最小化 | **已满足（加分）** | `suite_optimizer` 风险排序 + 贪心最小化；`optimizedSuite` 可审查 | 非理论最小集合覆盖 |
| **交互式审查** | 可改覆盖项、策略、用例 | **已满足** | 覆盖项分行编辑、`testStrategies`、用例表格+JSON、追溯、Apply Changes | — |

**生成流水线：** `run_deterministic_pipeline()`（记录 `engineMs`）→（可选）LLM（`llmMs` + `schema_validator`）→ `merge_engine_with_llm()` → 落库 `engine_metadata` / `timingMetrics`。

### 2.2 作业「主要内容」流程支持

Assignment2 要求：概念 → 覆盖项 → 策略与方法 → 用例与追溯 → 提示设计 → 结果分析 → **基于证据的改进** + **交互式验证**。

| 步骤 | 工具支持 | 建议留证 |
| --- | --- | --- |
| 概念 / 覆盖项 | `coverageItems`、`requirementsStructured` | 导出 JSON 截图 |
| 策略与方法 | `designMethod`、EP/BVA/DT 工件 | 符合性面板 FR 3.0 |
| 用例与追溯 | `testcases`、`traceability` | 审查前后 JSON 对比 |
| 提示设计 | `prompt.version`、`prompt.used`；固定 Prompt + 可选自定义 | README + 演示说明 |
| 结果分析 | `quality`（方法覆盖、优先级分布） | Metrics 区 |
| 交互改进 | Apply Changes 后重新导出 Markdown | 两个 `.md` 文件 diff |

### 2.3 非功能性需求（NFR）

| NFR | 状态 | 说明 |
| --- | --- | --- |
| **性能** | **引擎满足 NFR** | 前端展示 `engineMs`、`engineMeetsNfr`（≤2000ms）；`totalMs` 含 LLM；历史表存 `engine_ms/llm_ms` |
| **可用性** | 已满足 | FitnessAI 工作区、填入示例、Advanced Options、符合性/引擎双面板、响应式布局 |
| **安全性** | 基本满足 | API Key 仅 `.env`；无 Key 时不外呼；CORS 开放（开发态，生产需收紧） |
| **可维护性** | 已满足 | 引擎按 FR 分模块；`PROMPT_VERSION` / `ENGINE_VERSION` 可追踪；Docker 一键部署 |

### 2.4 交付物完成度（Assignment2 §1.2）

| 交付物 | 权重 | 仓库内状态 | 待完成（小组文档/演示） |
| --- | --- | --- | --- |
| 1. AutoTestDesign 工具 + README + 演示视频 | 20% | **代码已完成**；README 已有；**视频待录制** | 压缩包含源码与 `.env.example` |
| 2. FitnessAI 风险分析报告 PDF | 10% | **未在仓库** | 用工具导出 `riskItems` 撰写 |
| 3. FitnessAI 测试计划 PDF | 40% | **未在仓库** | 范围、架构、套件设计、组织图、框架、成本估算 |
| 4. 详细测试设计与执行 PDF | 30% | **未在仓库** | 选一模块（建议姿态 API 或状态机）+ PyTest 脚本与结果 |
| 演示 PPT | — | **未在仓库** | 15 分钟覆盖工具 + 目标应用 + 改进案例 |

---

## 2.5 各 FR 实现原理、验证流程与对应论证

### FR 1.0 输入/解析

| 维度 | 说明 |
| --- | --- |
| **实现原理** | 前端三路输入合并为 `content`：`[Plain-text]`、`[CSV requirements]`（原始 CSV 保留供引擎）、`documents[]` 文件；后端校验至少一项非空后转发 ai-service。 |
| **对应** | 作业要求 CSV、纯文本、直接输入三种方式均已实现，且 CSV 使用 RFC 风格引号解析（前端 `parseCsvLine` + 后端 `csv` 模块）。 |
| **验证流程** | ① 仅纯文本生成；② 仅 CSV（§6.5 五行表）；③ 仅上传 `FitnessAI_LLM_CONTEXT.md`；④ 符合性 FR 1.0 为 passed。 |

### FR 1.1 需求结构化

| 维度 | 说明 |
| --- | --- |
| **实现原理** | `requirement_parser.parse_content_blocks`：标准库 `csv.DictReader` 逻辑解析表头 `id,feature,input,condition,expected`；编号/REQ-ID 文本正则；无输入时 FitnessAI 五条默认需求。输出字段：`inputFields`、`ranges`、`conditions`、`expectedAction`、`source`。 |
| **对应** | 覆盖作业要求的输入字段、数据范围、条件、预期动作四要素，且可在 UI 审查 JSON 中修改。 |
| **验证流程** | 导出 JSON 检查 `requirementsStructured` 与 CSV 行 ID 一致；`engineMetadata.parseChannel` 为 `csv` 或 `csv+text`。 |

### FR 2.0 风险分析与优先级

| 维度 | 说明 |
| --- | --- |
| **实现原理** | `risk_config.FEATURE_WEIGHTS` 可配置矩阵 → `impact`×`likelihood`=`riskScore` → 阈值映射 `high/medium/low`；`GET /api/risk-matrix` 可审计。 |
| **对应** | 每条需求一条风险项，含评分与 H/M/L，非纯 Prompt 幻觉。 |
| **验证流程** | 抽查 `riskScore === impact * likelihood`；访问 `http://localhost:3000/api/risk-matrix`。 |

### FR 3.0 黑盒测试设计

| 维度 | 说明 |
| --- | --- |
| **实现原理** | `blackbox_engine` 算法生成：等价类（有效/无效类）、边界值（landmarks 32/33/34、duration 29/30/31）、决策表（记录过滤四规则）、**Pairwise 组合**（`_pairwise_combinations`）；并输出 `equivalencePartitions`、`boundaryValues`、`decisionTableRules` 工件。 |
| **对应** | ≥3 种 ISO 29119-4 核心技术，且 `analyzeBlackBoxQuality` 统计 ≥3 种 `designMethod`。 |
| **验证流程** | Metrics「Design Methods」≥3；导出用例 CSV 含 EP/BVA/DecisionTable/Combinatorial。 |

### FR 4.0 白盒测试建模（加分）

| 维度 | 说明 |
| --- | --- |
| **实现原理** | `parse_custom_state_model` 支持 JSON 状态图或 `A -> B` 箭头描述；否则检测「状态机」类需求启用深蹲默认模型；`generate_state_transition_sequences` 按 `all-states` / `all-transitions` 生成最优覆盖序列（含非法短循环对照）。 |
| **对应** | 产出 `stateModel`（states/transitions/coverageCriterion）+ 可执行 `StateTransition` 用例序列。 |
| **验证流程** | 勾选 White-box，填写状态描述或 JSON → 生成 `TC-ST-*` 用例；检查 `artifacts.stateModel`。 |

### FR 5.0 测试预言（加分）

| 维度 | 说明 |
| --- | --- |
| **实现原理** | `oracle_engine.synthesize_oracle`：规则库匹配 landmarks/exerciseType/状态序列/过滤规则/卡路里公式；否则绑定 `expectedAction` 与需求 ID。 |
| **对应** | 每条用例可带可验证 `oracle`，不仅 `expected` 自然语言。 |
| **验证流程** | 勾选 Test Oracle；导出 CSV 检查 oracle 非空；姿态/过滤用例 oracle 可手工执行。 |

### FR 6.0 输出与导出

| 维度 | 说明 |
| --- | --- |
| **实现原理** | 前端 Markdown/JSON/CSV；Excel 调用 `POST /api/export/artifacts` → ai-service `openpyxl` 生成四表 `.xlsx`（Requirements/Risks/Strategies/TestCases）；后端历史 `GET /api/export`。 |
| **对应** | 作业要求 JSON、Excel、CSV 均已支持；Excel 为真 xlsx。 |
| **验证流程** | 生成后依次点击四种导出；用 Excel 打开 `.xlsx` 检查四表。 |

### FR 7.0 测试套件优化（加分）

| 维度 | 说明 |
| --- | --- |
| **实现原理** | `optimize_test_suite`：`risk-first` 按 riskScore 排序保留 Top-K；`minimize` 贪心去重（需求+方法签名）；输出 `optimizedSuite`、`removedCases`、`algorithm`。 |
| **对应** | 同时支持风险优先与最小化两种模式（前端 Advanced 开启即默认 risk-first）。 |
| **验证流程** | 检查 `testSuiteOptimization.optimizedSuite` 非空；对比优化前后用例数。 |

### 交互式审查（作业「主要内容」必做）

| 维度 | 说明 |
| --- | --- |
| **实现原理** | 分栏审查：覆盖项（逐行）、测试策略（JSON）、用例（表格+JSON）、追溯（JSON）、风险/工件（artifacts JSON）；**Apply Changes** 重算符合性与 Metrics。 |
| **对应** | 覆盖「覆盖项、策略、用例」三类设计项的可修改与有效性验证。 |
| **验证流程** | 场景 E（§6.4）：改 priority、增用例 → Apply → 再导出 Markdown/JSON 对比。 |

---

## 3. 核心实现说明

### 3.1 规则引擎 `ai-service/app/engines/`

| 文件 | 功能 |
| --- | --- |
| `requirement_parser.py` | 解析 `[CSV requirements]`、表头 CSV、REQ-ID/编号文本；FitnessAI 默认五条需求 |
| `risk_engine.py` | 按特性权重计算 impact/likelihood → riskScore → priority |
| `blackbox_engine.py` | 生成等价类/边界/决策表工件与 EP/BVA/DT/CB 用例 |
| `whitebox_engine.py` | 默认深蹲状态机；生成状态/迁移覆盖序列 |
| `oracle_engine.py` | 按输入模式与需求 ID 填充 oracle |
| `suite_optimizer.py` | 风险排序或贪心最小化套件 |
| `strategy_builder.py` | ISO 29119-4 测试策略映射 |
| `schema_validator.py` | LLM 输出校验 |
| `risk_config.py` | 可配置风险矩阵 |
| `export_xlsx.py` | openpyxl 四表 xlsx |
| `pipeline.py` | 流水线、计时、`merge_engine_with_llm` |

### 3.2 AI 服务 `main.py`

- `PROMPT_VERSION = autotestdesign-v6-fr-complete`
- `TARGET_APP_CONTEXT` / `FITNESSAI_TEST_FOCUS`：防止把工具能力写成 FitnessAI 需求
- 无 `OPENAI_API_KEY`：`mock+engine` 仍可演示全 FR
- `ENABLE_PARSE_FALLBACK`（默认 false）：避免静默 mock 污染验收

### 3.3 后端 API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 含 `targetApplication: FitnessAI` |
| GET | `/api/target-application` | 目标应用元数据 |
| GET | `/api/engines/info` | 规则引擎模块列表 |
| POST | `/api/testcases/generate` | 生成；返回 `quality`、`assignmentCompliance`、`engineMetadata` |
| GET | `/api/history` | 历史列表 |
| DELETE | `/api/history/:id` | 删除记录 |
| GET | `/api/export` | 历史元数据 JSON/CSV |
| POST | `/api/export/artifacts` | 工件 JSON/CSV/**xlsx** |
| GET | `/api/risk-matrix` | 风险矩阵（FR 2.0） |
| GET | `/api/analysis/experiment` | 实验统计 |
| POST | ai-service `/export-artifacts` | openpyxl xlsx 二进制 |

### 3.4 前端能力摘要

- **输入：** 文件、纯文本、CSV（引号字段解析）、填入示例
- **Advanced：** White-box / Oracle / Optimization、`all-states` | `all-transitions`
- **结果：** Metrics、Assignment2 符合性条、Deterministic FR Engines 面板
- **审查：** artifacts（含 risk、coverage、stateModel、optimization）、testcases、traceability
- **导出：** Markdown、JSON、CSV、Excel(**.xlsx** 四表)
- **审查：** 覆盖项分行、测试策略、用例表格、追溯、计时指标

### 3.5 数据库

`generation_records` 保存：用例、结构化需求、覆盖项、风险、状态模型、套件优化、追溯、Prompt 版本、质量分等，支持历史回填。

---

## 4. FitnessAI 测试范围（目标应用）

与工具内置样本、`FitnessAI_LLM_CONTEXT.md` 一致：

| 模块 | 测试要点 | 建议设计技术 |
| --- | --- | --- |
| 姿态分析 `/api/analytics/pose` | exerciseType 等价类；landmarks 32/33/34 | EP、BVA |
| 状态机计数 | UP→DESCENDING→DOWN→ASCENDING→UP；非法短循环 | StateTransition、白盒全状态 |
| 记录过滤 | count&lt;3 ∧ duration&lt;30 | DecisionTable |
| 训练计划 | 难度、组数、休息、skipRest | Combinatorial |
| 仪表盘 | 趋势、分布、卡路里 MET×体重×时长 | EP、oracle |

---

## 5. 环境与启动

### 5.1 先决条件

Docker Desktop、Node.js 20+、npm 10+。

### 5.2 配置与启动

```powershell
# 项目根目录 Software-Test-Assignment
Copy-Item .env.example .env
docker compose up -d --build
docker compose ps

cd frontend
npm install
npm run dev
```

访问：`http://localhost:5173`（前端）、`http://localhost:3000/health`、`http://localhost:8000/health`。

### 5.3 冒烟检查

```powershell
Invoke-RestMethod http://localhost:3000/health
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:3000/api/engines/info
```

---

## 6. 完整工具测试流程

### 6.1 测试模式

| 模式 | 条件 | 表现 |
| --- | --- | --- |
| 离线 | `OPENAI_API_KEY` 为空 | `mock+engine`，`engineMetadata` 仍完整 |
| 在线 | 配置 Key + Base URL | LLM JSON 与引擎合并，用例数通常更多 |

### 6.2 场景 A — 一键回归（发版必做，约 5 分钟）

1. 打开 `http://localhost:5173`，Advanced 勾选 White-box、Oracle、Optimization。
2. **填入示例** → **Generate Test Design**。
3. 验证：`engineMetadata.engineVersion` = `autotestdesign-engine-v2`；`timingMetrics.engineMeetsNfr` 为 true；`requiredScore` = 1.0；用例 ≥ 8；含 `testStrategies`。
4. 修改 `riskItems[].priority` 与增删一条用例 → **Apply Changes**（表格或 JSON 模式）。
5. 导出 Markdown / JSON / CSV / Excel（**.xlsx** 四表：Requirements / Risks / Strategies / TestCases）。
6. History → View 最新记录。

### 6.3 场景 B / C / D — 分输入通道

| 场景 | 操作 | 验证点 |
| --- | --- | --- |
| **B 纯文本** | 仅填 Plain-text（见 §6.5 样例） | `requirementsStructured` 多 feature |
| **C CSV** | 仅填 CSV（§6.5 五行表） | REQ-ID 一致；BVA+DT+ST；`parseChannel` 含 csv |
| **D 文件** | 导入 `FitnessAI_LLM_CONTEXT.md` 片段 | 文件需求进入 `documents` |

### 6.4 场景 E — 交互式审查留证（作业重点）

1. 生成后导出 JSON（审查前）。
2. 编辑 artifacts / testcases / traceability → Apply Changes。
3. 再导出 JSON 与 Markdown（审查后）。
4. 在报告中附：追溯矩阵截图、`riskScore` 计算示例（impact×likelihood）。

### 6.5 测试数据样例

**纯文本：**

```text
FitnessAI 通过 MediaPipe 提供 33 个关键点，支持 SQUAT/PUSHUP/PLANK/JUMPING_JACK。
深蹲需完整状态循环才计数；count<3 且 durationSeconds<30 的记录应过滤；仪表盘展示趋势与卡路里。
```

**CSV：**

```csv
id,feature,input,condition,expected
REQ-POSE-001,姿态分析,exerciseType+landmarks,合法类型且33点,返回count/score/feedback
REQ-POSE-002,状态机计数,帧序列,完整UP-DOWN循环,count+1
REQ-REC-001,记录过滤,count+durationSeconds,count<3且duration<30,不入库
```

**可选 Prompt（勿上传 Assignment2.md）：**

```text
请为目标应用 FitnessAI 智能健身辅助系统生成测试设计工件。当前导入的内容是 FitnessAI 的需求、接口说明或 CSV 需求，请只围绕 FitnessAI 进行分析，不要把 AutoTestDesign 工具本身作为被测对象。

请按照系统固定的测试设计要求生成结构化结果：需求结构化、覆盖项识别、风险分析、至少三种黑盒测试设计、状态模型、测试预言、风险优先套件优化和 traceability。请保持后端要求的 JSON 输出格式。
注意：文件/文本/CSV 导入能力和 JSON/CSV/Markdown 导出能力属于 AutoTestDesign 工具自身，不要把这些工具能力转写成 FitnessAI 的被测功能需求。

FitnessAI 重点测试范围：
1. /api/analytics/pose 姿态分析接口。
2. exerciseType 支持 SQUAT、PUSHUP、PLANK、JUMPING_JACK。
3. MediaPipe landmarks 理论长度为 33，需要覆盖 32、33、34 等边界。
4. 深蹲或俯卧撑状态机应覆盖 UP、DESCENDING、DOWN、ASCENDING、UP 完整循环，非法短循环不应计数。
5. count < 3 且 durationSeconds < 30 的训练记录应被过滤。
6. 计划模式应覆盖不同难度、组数、次数、休息时间和跳过休息。
7. 仪表盘应覆盖今日统计、历史趋势、运动类型分布和卡路里估算。
```

### 6.6 API 验收（PowerShell）

```powershell
$body = @{
  sourceType = "requirements"
  content = "[CSV requirements]`nid,feature,input,condition,expected`nREQ-POSE-002,状态机计数,frames,full cycle,count+1"
  includeWhitebox = $true
  includeOracle = $true
  includeOptimization = $true
  coverageCriterion = "all-states"
} | ConvertTo-Json -Depth 6

$res = Invoke-RestMethod -Uri http://localhost:3000/api/testcases/generate -Method Post -ContentType "application/json; charset=utf-8" -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
$res.assignmentCompliance.requiredScore
$res.engineMetadata.engineVersion
$res.quality.caseCount
```

### 6.7 静态检查

```powershell
cd frontend; npm run build
cd ..\backend; node --check src/index.js
cd ..\ai-service; python -m py_compile app/main.py app/engines/pipeline.py
```

---

## 7. 15 分钟演示建议

| 时间 | 内容 |
| --- | --- |
| 0–1 min | 工具 vs FitnessAI 边界 |
| 1–2 min | `/health`、`/api/engines/info` |
| 2–4 min | 填入示例 + 多源输入 |
| 4–7 min | 生成 → 符合性 + 规则引擎面板 |
| 7–10 min | 现场改 JSON → Apply → 再导出 |
| 10–12 min | 四种导出 + History |
| 12–15 min | 说明 PDF 交付物与 FitnessAI 模块/Q&A |

---

## 8. 提交前检查清单

### 8.1 工具（20%）

- [ ] `docker compose up -d --build` 成功
- [ ] 场景 A + C + E 通过并留证
- [ ] 四种导出文件入提交压缩包
- [ ] README + `.env.example` + 演示视频

### 8.2 文档（80%，FitnessAI）

- [ ] 风险分析报告 PDF
- [ ] 测试计划 PDF（含组织图、框架、成本估算）
- [ ] 详细测试设计与执行 PDF（含 PyTest 等）
- [ ] 演示 PPT（团队信息首页）

### 8.3 FR 与交互

- [ ] 必做 FR 1.0–3.0、6.0 + Interactive Review 均可演示
- [ ] 加分 FR 4/5/7 在 Advanced 开启时可演示
- [ ] 能说明 `riskScore = impact × likelihood` 与引擎模块对应关系

---

## 9. 后续优化建议（按优先级）

### 已完成（v6 / engine v2，原 P1）

- 原生 `.xlsx`（openpyxl 四表）
- `engineMs` / `llmMs` / `totalMs` 展示与落库
- 用例表格审查 + 覆盖项/策略分栏
- `engine_metadata`、`test_strategies` 历史字段
- Pairwise 组合、可配置风险矩阵、LLM JSON 校验、自定义状态图

### P0 — 提交前建议完成（文档/演示）

1. **补齐三份 PDF + PPT + 演示视频**（占分 80%）。
2. **准备审查前后对比物证**（§6.4 场景 E）。
3. **测试计划引用 `timingMetrics`** 说明引擎满足 2s NFR。

### P2 — 目标应用验证（交付物 4）

| 项 | 说明 |
| --- | --- |
| `tests/fitnessai/` PyTest | 针对 `/api/analytics/pose` 或状态机逻辑的 5–15 条脚本，ID 与工具导出 `TC-*` 对齐 |
| 成本估算数据 | 对比「纯手工设计用例」vs「AutoTestDesign + 审查」人时（写入测试计划） |

### P3 — 算法与泛化（部分已在 v6 完成）

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 自定义状态图 | 已完成 | `whitebox_description` 支持 JSON/箭头语法 |
| 风险矩阵 API | 已完成 | `GET /api/risk-matrix` |
| Pairwise | 已完成 | `blackbox_engine._pairwise_combinations` |
| LLM JSON 校验 | 已完成 | `schema_validator` |
| 通用 DOT 上传 | 待做 | 前端上传 DOT 文件并解析 |
| 安全加固 | 待做 | 生产 CORS 白名单、限流 |

### P4 — 工程化

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 单元测试 | 已完成 | `ai-service/tests/test_engines.py`（5 项 unittest） |
| CI | 待做 | GitHub Actions：`npm run build` + unittest + 冒烟 |
| E2E | 待做 | Playwright「填入示例 → 生成 → xlsx 导出」 |

---

## 10. 版本变更记录

| 版本 | 日期 | 摘要 |
| --- | --- | --- |
| v4 | 早期 | FitnessAI Prompt、符合性面板、交互审查、mock 十条用例 |
| v5 + engine v1 | 2026-05-20 | 新增 `engines/` 全 FR 确定性实现；Excel 导出；`/api/engines/info`；`engineMetadata` |
| v6 + engine v2 | 2026-05-20 | xlsx/openpyxl；计时 NFR；testStrategies；表格审查；风险矩阵 API；Pairwise；自定义状态图；schema 校验；DB 扩展字段；`tests/test_engines.py` |

---

## 附录：与 README 的关系

- **快速上手**：见 [README.md](README.md)  
- **目标应用上下文**：见 [FitnessAI_LLM_CONTEXT.md](FitnessAI_LLM_CONTEXT.md)  
- **作业原文**：见 [Assignment2.md](Assignment2.md)
