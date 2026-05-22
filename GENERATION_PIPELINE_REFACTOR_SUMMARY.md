# Generation Pipeline 重构说明

## 1. 重构目标

本次修改将测试用例生成主流程统一切换到新的 `generation_pipeline`，并将黑盒、白盒能力拆分为可独立调度的 worker。

核心目标：

- 黑盒测试：5 种技术可独立选择、独立生成、独立归档。
- 白盒测试：新增 `WhiteBoxJava`，基于 Java 方法级 CFG 确定性生成覆盖项与测试序列。
- LLM 使用边界：LLM 只做白盒测试设计的自然语言增强，不参与 CFG、coverage item、path、coverageTargets 的识别或修改。
- 前端交互：QRA、黑盒技术、白盒技术、结果汇总均采用更清晰的 tab/分区工作流。

## 2. 当前主流程

前端调用：

1. `frontend/src/App.vue` 发送 `POST /api/testcases/generate`。
2. `backend/src/index.js` 转发到 `ai-service` 的 `POST /generate-testcases`。
3. `ai-service/app/main.py` 构造 `GlobalContext`。
4. `ai-service/app/engines/generation_pipeline.py` 根据 `selectedTechniques` 路由到对应 worker。
5. reduce 阶段汇总 `testcases`、`coverageItems`、`testStrategies`、`traceability`、`engineMetadata`、`llmEnhancedTestcases` 等工件。

旧 `pipeline.py` 已移除，不再作为 FastAPI 主流程入口。

## 3. 黑盒测试设计

当前黑盒技术由 `blackbox_workers.py` 提供：

- `EP`
- `BVA`
- `DecisionTable`
- `Combinatorial`
- `StateTransition`

黑盒 worker 的行为：

- 优先使用 OpenAI-compatible LLM 生成更贴近用户输入 prompt 的测试用例。
- LLM 不可用或结果不可解析时，降级到确定性 fallback。
- fallback 逻辑位于 `blackbox_fallbacks.py`，替代原 `blackbox_engine.py` 的旧命名。
- `StateTransition` 使用 `state_transition_worker.py`，必要时通过 `state_model_engine.py` 构造确定性状态模型。

## 4. Java 白盒测试设计

新增白盒技术 ID：

```text
WhiteBoxJava
```

相关模块：

- `whitebox_java_analyzer.py`：解析 Java source，构造方法级 CFG。
- `whitebox_coverage.py`：从 CFG 生成 statement / branch coverage items。
- `whitebox_sequence_generator.py`：基于 CFG 路径搜索生成 test sequences。
- `input_hint_generator.py`：从简单条件推导输入提示、路径约束和 setup hints。
- `whitebox_java_worker.py`：对外 worker 入口，保持 `worker_whitebox_java(ctx, start_index=1)`。
- `whitebox_llm_enhancer.py`：LLM 后处理增强层。

支持能力：

- Method / Constructor 级分析。
- nested class 递归分析，类名使用 `Outer.Inner`。
- 顺序语句、if/else、nested if、switch、for/while/do-while、try/catch、return、throw、break、continue 的简化 CFG。
- statement coverage。
- branch / decision coverage。
- reviewer overrides：
  - `coverageItemSelection`
  - `manualCoverageItems`
- 输出结构化 `testSequences`，包含：
  - `path`
  - `pathConstraints`
  - `inputHints`
  - `setupHints`
  - `constraintConflicts`
  - `exceptionTriggerHints`
  - `oracleHints`
  - `needsReview`

## 5. LLM Enhancement Layer

`whitebox_llm_enhancer.py` 将 deterministic whitebox sequence 转换为更自然、可审查的测试设计说明。

允许 LLM 新增：

- `naturalLanguageTitle`
- `testIntentSummary`
- `refinedInputSuggestions`
- `refinedSetupSuggestions`
- `refinedOracleSuggestions`
- `reviewerQuestions`
- `reviewerWarnings`

禁止 LLM 输出或修改：

- CFG node / edge
- coverageItems
- coverageTargets
- path
- sourceNodeId / sourceEdgeId

如果未配置真实 LLM client，系统会保留 `promptPreview` 和 warning；配置 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL` 后会调用真实 OpenAI-compatible client。

## 6. 前端显示与归档

前端已经接入：

- White-Box tab：
  - coverage criterion 选择。
  - Java snippet / Java file 上传切换。
  - coverage items 勾选。
  - manual coverage item。
  - Java Analysis Result。
  - LLM Enhanced Test Design。
- Generated Results Summary：
  - `Coverage Items`
  - `Test Strategies`
  - `Test Cases`
  - `Traceability`
  - `LLM Enhancements`
- 导出的 Markdown 会包含：
  - 原始结构化 testcases。
  - `LLM enhanced white-box design`。

## 7. 清理内容

本次整理中完成：

- 删除旧主流程 `ai-service/app/engines/pipeline.py`。
- 将旧 `blackbox_engine.py` 改名为 `blackbox_fallbacks.py`，明确其职责是黑盒 worker 的确定性 fallback/helper。
- 将旧 `whitebox_engine.py` 改名为 `state_model_engine.py`，明确其职责是 StateTransition 的状态模型 fallback/helper。
- 移除 `main.py`、测试、worker 中对旧模块名的直接引用。
- `ai-service/app/engines/__init__.py` 改为只导出新主入口 `run_generation_pipeline`。

保留原因：

- `blackbox_fallbacks.py` 仍被黑盒 worker 用于 LLM 不可用时的降级生成。
- `state_model_engine.py` 仍被 StateTransition worker 用于确定性状态模型构造。

## 8. 关键输出字段

`WhiteBoxJava` worker artifacts 至少包含：

```json
{
  "whiteboxAnalysis": {},
  "coverageItems": [],
  "testSequences": [],
  "llmEnhancedTestcases": [],
  "llmReadyWhiteboxContext": {},
  "warnings": [],
  "engineMetadata": {}
}
```

`engineMetadata` 中保留边界说明：

```text
identificationMode = deterministic CFG-based coverage item identification
llmBoundary = LLM may later explain coverage items, refine input/setup/oracle, and draft JUnit, but must not create/delete CFG coverage items.
```

## 9. 验证建议

后端重建：

```bash
docker compose up -d --build
```

前端：

```bash
cd frontend
npm run dev
```

建议接口验证：

```bash
POST http://localhost:3000/api/testcases/generate
```

白盒请求关键字段：

```json
{
  "sourceType": "code",
  "content": "public class LoginService { ... }",
  "selectedTechniques": ["WhiteBoxJava"],
  "coverageCriterion": "statement+branch",
  "reviewerOverrides": {
    "coverageItemSelection": {},
    "manualCoverageItems": []
  }
}
```

预期结果：

- `testcases[*].designMethod` 为 `WhiteBoxJava`。
- `testcases[*].technique` 为 `white-box`。
- `artifacts.coverageItems` 包含 statement / branch 覆盖项。
- `artifacts.testSequences` 包含 CFG path。
- `artifacts.llmEnhancedTestcases` 存在；配置真实 LLM 后包含自然语言增强结果。
- `Generated Results Summary` 的 `LLM Enhancements` tab 可看到增强内容。

本地单元测试建议：

```bash
cd ai-service
python -m unittest discover -s tests
```

前端构建建议：

```bash
cd frontend
npm run build
```

