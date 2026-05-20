import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import axios from "axios";
import { pool, insertGenerationRecord, ensureSchema, getRecentGenerationRecords, deleteGenerationRecordById } from "./db.js";

dotenv.config();

const app = express();
const port = Number(process.env.PORT || 3000);

const aiServiceUrl = process.env.AI_SERVICE_URL || "http://localhost:8000";
const targetApplication = {
  name: "FitnessAI",
  description: "基于姿态识别、状态机计数、训练计划和数据统计的智能健身辅助系统",
  focusModules: ["姿态分析接口", "状态机计数", "训练计划", "记录过滤", "仪表盘统计"],
  assignmentScope: "风险分析报告、测试计划和详细测试设计均面向 FitnessAI 目标应用"
};
const requiredMethods = [
  "EP",
  "BVA",
  "Combinatorial",
  "StateTransition",
  "DecisionTable"
];

function normalizeDesignMethods(item) {
  const text = [
    item?.designMethod,
    item?.method,
    item?.technique,
    item?.title,
    item?.id,
    ...(Array.isArray(item?.traceability) ? item.traceability : [])
  ].map((value) => String(value || "")).join(" ");
  const methods = new Set();

  if (/\bEP\b|equivalence|等价类/i.test(text)) methods.add("EP");
  if (/\bBVA\b|boundary|边界值/i.test(text)) methods.add("BVA");
  if (/combinatorial|pairwise|组合/i.test(text)) methods.add("Combinatorial");
  if (/state\s*transition|stateTransition|状态迁移|状态机/i.test(text)) methods.add("StateTransition");
  if (/decision\s*table|decisionTable|决策表/i.test(text)) methods.add("DecisionTable");

  return methods;
}

function collectDesignMethods(cases) {
  const methods = new Set();
  for (const item of Array.isArray(cases) ? cases : []) {
    for (const method of normalizeDesignMethods(item)) {
      methods.add(method);
    }
  }
  return methods;
}

function analyzeBlackBoxQuality(cases) {
  const caseList = Array.isArray(cases) ? cases : [];
  const methodsPresent = collectDesignMethods(caseList);
  const missingMethods = requiredMethods.filter((method) => !methodsPresent.has(method));

  const methodCoverage = requiredMethods.length === 0
    ? 0
    : (requiredMethods.length - missingMethods.length) / requiredMethods.length;

  const highCount = caseList.filter((item) => String(item?.priority || "").toLowerCase() === "high").length;
  const mediumCount = caseList.filter((item) => String(item?.priority || "").toLowerCase() === "medium").length;
  const lowCount = caseList.filter((item) => String(item?.priority || "").toLowerCase() === "low").length;

  const amountScore = Math.min(caseList.length / 8, 1);
  const priorityBalance = caseList.length > 0 ? Math.min((highCount + mediumCount * 0.7 + lowCount * 0.4) / caseList.length, 1) : 0;

  const qualityScore = Number((methodCoverage * 0.6 + amountScore * 0.2 + priorityBalance * 0.2).toFixed(2));

  return {
    caseCount: caseList.length,
    methodCoverage: Number(methodCoverage.toFixed(2)),
    coveredMethods: requiredMethods.filter((method) => methodsPresent.has(method)),
    missingMethods,
    priorityStats: {
      high: highCount,
      medium: mediumCount,
      low: lowCount
    },
    qualityScore,
    recommendations: missingMethods.length
      ? [`补充缺失方法: ${missingMethods.join(", ")}`]
      : ["五种黑盒方法均已覆盖，可进入准确率与泛化实验"]
  };
}

function buildAssignmentCompliance(generated, quality) {
  const artifacts = generated?.artifacts || {};
  const engineMeta = generated?.engineMetadata || artifacts?.engineMetadata || {};
  const frEngines = engineMeta?.frEngines || {};
  const cases = Array.isArray(generated?.testcases) ? generated.testcases : [];
  const rawOutput = String(generated?.llmRawOutput || "");
  const traceRefs = cases.flatMap((item) => Array.isArray(item?.traceability) ? item.traceability : []).map((value) => String(value || ""));
  const uniqueMethods = collectDesignMethods(cases);
  const hasRuleParser = Boolean(frEngines["FR1.0"] || frEngines["FR1.1"]);
  const hasRuleRisk = Boolean(frEngines["FR2.0"]);
  const hasRuleBlackbox = Boolean(frEngines["FR3.0"]);
  const hasStructuredRequirements = (Array.isArray(artifacts.requirementsStructured) && artifacts.requirementsStructured.length > 0)
    || hasRuleParser
    || /"requirementsStructured"|REQ-[A-Z0-9-]+|结构化需求/.test(rawOutput);
  const hasRiskItems = (Array.isArray(artifacts.riskItems) && artifacts.riskItems.length > 0)
    || hasRuleRisk
    || /"riskItems"|R-[A-Z0-9-]+|风险分析|priority/i.test(rawOutput)
    || cases.some((item) => ["high", "medium", "low"].includes(String(item?.priority || "").toLowerCase()))
    || traceRefs.some((ref) => /^R-/i.test(ref));
  const hasTestStrategies = (Array.isArray(artifacts.testStrategies) && artifacts.testStrategies.length > 0)
    || Boolean(frEngines["FR3.0"]);
  const hasCoverageItems = (Array.isArray(artifacts.coverageItems) && artifacts.coverageItems.length > 0)
    || hasTestStrategies
    || /"coverageItems"|C-[A-Z0-9-]+|覆盖项/.test(rawOutput)
    || traceRefs.some((ref) => /^C-/i.test(ref));
  const hasTraceability = (Array.isArray(artifacts.traceability) && artifacts.traceability.length > 0)
    || cases.some((item) => Array.isArray(item?.traceability) && item.traceability.length > 0)
    || /"traceability"|追溯关系/.test(rawOutput);
  const hasStateModel = artifacts.stateModel && Object.keys(artifacts.stateModel).length > 0;
  const hasOptimization = artifacts.testSuiteOptimization && Object.keys(artifacts.testSuiteOptimization).length > 0;
  const hasOracle = cases.some((item) => String(item?.oracle || "").trim());

  const engineNote = engineMeta?.engineVersion ? `规则引擎 ${engineMeta.engineVersion}` : "";
  const items = [
    { id: "FR 1.0", label: "输入/解析", passed: true, evidence: `多源输入(content/documents/CSV)；${engineNote}` },
    { id: "FR 1.1", label: "需求结构化", passed: hasStructuredRequirements, evidence: `${artifacts.requirementsStructured?.length || 0} 条结构化需求；解析器: ${frEngines["FR1.1"] || "LLM/启发式"}` },
    { id: "FR 2.0", label: "风险分析与优先级", passed: hasRiskItems, evidence: `${artifacts.riskItems?.length || 0} 条风险项(impact×likelihood)；${frEngines["FR2.0"] || ""}` },
    { id: "FR 3.0", label: "黑盒测试设计", passed: uniqueMethods.size >= 3 || hasRuleBlackbox, evidence: `${uniqueMethods.size} 种方法；算法: ${frEngines["FR3.0"] || "LLM"}；缺失: ${quality.missingMethods.join(", ") || "无"}` },
    { id: "FR 6.0", label: "输出与导出", passed: true, evidence: "Markdown/JSON/CSV/XLSX；后端 /api/export 与 /api/export/artifacts" },
    { id: "Interactive Review", label: "交互式审查", passed: hasCoverageItems || hasTraceability || hasTestStrategies, evidence: "覆盖项、测试策略、用例、追溯关系可在前端分栏编辑并应用" },
    { id: "FR 4.0", label: "白盒建模", passed: hasStateModel, evidence: hasStateModel ? `状态模型+迁移序列；${frEngines["FR4.0"] || ""}` : "未生成状态模型" },
    { id: "FR 5.0", label: "测试预言", passed: hasOracle, evidence: hasOracle ? `oracle 已生成；${frEngines["FR5.0"] || ""}` : "未生成 oracle" },
    { id: "FR 7.0", label: "测试套件优化", passed: hasOptimization, evidence: hasOptimization ? `套件优化；${frEngines["FR7.0"] || artifacts.testSuiteOptimization?.algorithm || ""}` : "未生成优化信息" }
  ];

  const required = items.filter((item) => !["FR 4.0", "FR 5.0", "FR 7.0"].includes(item.id));
  const requiredPassed = required.filter((item) => item.passed).length;

  return {
    targetApplication,
    requiredScore: Number((requiredPassed / required.length).toFixed(2)),
    items
  };
}

function buildExperimentMetrics(records) {
  const list = Array.isArray(records) ? records : [];
  const sourceTypeStats = { requirements: 0, codebase: 0 };
  const methodStats = {
    EP: 0,
    BVA: 0,
    Combinatorial: 0,
    StateTransition: 0,
    DecisionTable: 0
  };
  const modelStats = {};
  const promptVersionStats = {};

  let totalCases = 0;
  let totalQuality = 0;
  let totalTokens = 0;

  for (const record of list) {
    const sourceType = String(record.source_type || "requirements");
    if (sourceTypeStats[sourceType] !== undefined) {
      sourceTypeStats[sourceType] += 1;
    }

    const modelName = String(record.model_name || "unknown");
    modelStats[modelName] = (modelStats[modelName] || 0) + 1;

    const promptVersion = String(record.prompt_version || "unknown");
    promptVersionStats[promptVersion] = (promptVersionStats[promptVersion] || 0) + 1;

    const quality = Number(record.quality_score || 0);
    totalQuality += Number.isNaN(quality) ? 0 : quality;

    const tokens = Number(record.tokens_estimate || 0);
    totalTokens += Number.isNaN(tokens) ? 0 : tokens;

    const generated = Array.isArray(record.generated_cases) ? record.generated_cases : [];
    totalCases += generated.length;
    for (const item of generated) {
      const method = String(item?.designMethod || "");
      if (methodStats[method] !== undefined) {
        methodStats[method] += 1;
      }
    }
  }

  return {
    sampleSize: list.length,
    avgQualityScore: list.length ? Number((totalQuality / list.length).toFixed(2)) : 0,
    avgCasesPerRun: list.length ? Number((totalCases / list.length).toFixed(2)) : 0,
    avgTokensEstimate: list.length ? Math.round(totalTokens / list.length) : 0,
    sourceTypeStats,
    methodStats,
    modelStats,
    promptVersionStats
  };
}

app.use(cors());
app.use(express.json({ limit: "10mb" }));

app.get("/health", async (_req, res) => {
  try {
    await pool.query("SELECT 1");
    res.json({ status: "ok", service: "backend", targetApplication: targetApplication.name });
  } catch (error) {
    res.status(500).json({ status: "error", message: error.message });
  }
});

app.get("/api/target-application", (_req, res) => {
  res.json(targetApplication);
});

app.post("/api/testcases/generate", async (req, res) => {
  try {
    const {
      sourceType = "requirements",
      content = "",
      promptMode = "default",
      customPrompt = "",
      documents = [],
      testTechnique = process.env.TEST_TECHNIQUE || "black-box",
      includeWhitebox = true,
      includeOracle = true,
      includeOptimization = true,
      whiteboxDescription = "",
      coverageCriterion = "all-states"
    } = req.body || {};

    if (!["requirements", "codebase"].includes(sourceType)) {
      return res.status(400).json({
        message: "sourceType must be requirements or codebase"
      });
    }

    const hasContent = Boolean(String(content).trim());
    const hasDocuments = Array.isArray(documents) && documents.some((item) => String(item?.content || "").trim());
    if (!hasContent && !hasDocuments) {
      return res.status(400).json({
        message: "content or documents must not be empty"
      });
    }

    const aiResponse = await axios.post(`${aiServiceUrl}/generate-testcases`, {
      sourceType,
      content,
      promptMode,
      customPrompt,
      documents,
      testTechnique,
      includeWhitebox,
      includeOracle,
      includeOptimization,
      whiteboxDescription,
      coverageCriterion
    });

    const generated = aiResponse.data;
    const summaryFromDocs = Array.isArray(documents)
      ? documents.map((item) => String(item?.name || "").trim()).filter(Boolean).join(", ")
      : "";
    const sourceSummary = String(content).trim()
      ? String(content).slice(0, 500)
      : `files: ${summaryFromDocs}`.slice(0, 500);
    const quality = analyzeBlackBoxQuality(generated?.testcases || []);
    const assignmentCompliance = buildAssignmentCompliance(generated, quality);
    const timing = generated?.timingMetrics || generated?.artifacts?.timingMetrics || {};
    const record = await insertGenerationRecord(
      sourceType,
      sourceSummary,
      generated,
      {
        qualityScore: quality.qualityScore,
        tokensEstimate: Math.ceil((String(content).length + JSON.stringify(documents || []).length) / 4),
        engineMs: timing.engineMs,
        llmMs: timing.llmMs,
        totalMs: timing.totalMs
      },
      testTechnique
    );

    res.json({
      message: "AutoTestDesign artifacts generated",
      technique: testTechnique,
      record,
      quality,
      assignmentCompliance,
      timingMetrics: timing,
      engineMetadata: generated?.engineMetadata || generated?.artifacts?.engineMetadata || {},
      llmRawOutput: generated?.llmRawOutput || "",
      artifacts: generated?.artifacts || {},
      prompt: {
        version: generated?.promptVersion || "unknown",
        used: generated?.promptUsed || ""
      },
      data: generated
    });
  } catch (error) {
    const upstreamDetail = error?.response?.data?.detail || error?.response?.data?.message;
    res.status(500).json({
      message: "Failed to generate test cases",
      detail: upstreamDetail || error.message
    });
  }
});

app.get("/api/analysis/experiment", async (req, res) => {
  try {
    const limit = Math.min(Number(req.query.limit || 200), 1000);
    const records = await getRecentGenerationRecords(limit);
    const metrics = buildExperimentMetrics(records);

    res.json({
      message: "Experimental analysis metrics",
      scope: { limit, records: records.length },
      metrics
    });
  } catch (error) {
    res.status(500).json({
      message: "Failed to compute experiment metrics",
      detail: error.message
    });
  }
});

app.get("/api/history", async (req, res) => {
  try {
    const limit = Math.min(Math.max(Number(req.query.limit || 20), 1), 100);
    const records = await getRecentGenerationRecords(limit);

    const history = records.map((item) => {
      const cases = Array.isArray(item.generated_cases) ? item.generated_cases : [];
      const quality = analyzeBlackBoxQuality(cases);

      return {
        id: item.id,
        sourceType: item.source_type,
        technique: item.technique || "black-box",
        sourceSummary: item.source_summary || "",
        modelName: item.model_name || "unknown",
        promptVersion: item.prompt_version || "unknown",
        promptUsed: item.prompt_used || "",
        llmRawOutput: item.llm_raw_output || "",
        tokensEstimate: Number(item.tokens_estimate || 0),
        createdAt: item.created_at,
        structuredRequirements: item.structured_requirements || [],
        coverageItems: item.coverage_items || [],
        riskItems: item.risk_items || [],
        stateModel: item.state_model || {},
        suiteOptimization: item.suite_optimization || {},
        traceability: item.traceability || [],
        testStrategies: item.test_strategies || [],
        engineMetadata: item.engine_metadata || {},
        timingMetrics: {
          engineMs: item.engine_ms,
          llmMs: item.llm_ms,
          totalMs: item.total_ms
        },
        quality: {
          ...quality,
          qualityScore: Number(item.quality_score || quality.qualityScore || 0)
        },
        generatedCases: cases
      };
    });

    res.json({
      message: "History records fetched",
      count: history.length,
      records: history
    });
  } catch (error) {
    res.status(500).json({
      message: "Failed to fetch history records",
      detail: error.message
    });
  }
});

app.delete("/api/history/:id", async (req, res) => {
  try {
    const id = Number(req.params.id);
    if (!Number.isInteger(id) || id <= 0) {
      return res.status(400).json({
        message: "Invalid history record id"
      });
    }

    const deleted = await deleteGenerationRecordById(id);
    if (!deleted) {
      return res.status(404).json({
        message: "History record not found"
      });
    }

    res.json({
      message: "History record deleted",
      id: deleted.id
    });
  } catch (error) {
    res.status(500).json({
      message: "Failed to delete history record",
      detail: error.message
    });
  }
});

function escapeXml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function rowsToWorksheetXml(rows, headers) {
  const headerCells = headers
    .map((header) => `<Cell><Data ss:Type="String">${escapeXml(header)}</Data></Cell>`)
    .join("");
  const dataRows = rows
    .map((row) => {
      const cells = headers
        .map((header) => `<Cell><Data ss:Type="String">${escapeXml(row[header])}</Data></Cell>`)
        .join("");
      return `<Row>${cells}</Row>`;
    })
    .join("");
  return `<Worksheet ss:Name="Sheet"><Table><Row>${headerCells}</Row>${dataRows}</Table></Worksheet>`;
}

function buildArtifactsSpreadsheetXml(artifacts, testcases) {
  const requirements = Array.isArray(artifacts?.requirementsStructured) ? artifacts.requirementsStructured : [];
  const risks = Array.isArray(artifacts?.riskItems) ? artifacts.riskItems : [];
  const cases = Array.isArray(testcases) ? testcases : [];

  const reqRows = requirements.map((item) => ({
    id: item.id,
    feature: item.feature,
    inputFields: (item.inputFields || []).join(";"),
    expectedAction: item.expectedAction
  }));
  const riskRows = risks.map((item) => ({
    reqId: item.reqId,
    impact: item.impact,
    likelihood: item.likelihood,
    riskScore: item.riskScore,
    priority: item.priority
  }));
  const caseRows = cases.map((item) => ({
    id: item.id,
    designMethod: item.designMethod,
    title: item.title,
    priority: item.priority,
    oracle: item.oracle,
    expected: item.expected
  }));

  const worksheets = [
    rowsToWorksheetXml(reqRows, ["id", "feature", "inputFields", "expectedAction"]),
    rowsToWorksheetXml(riskRows, ["reqId", "impact", "likelihood", "riskScore", "priority"]),
    rowsToWorksheetXml(caseRows, ["id", "designMethod", "title", "priority", "oracle", "expected"])
  ];

  return (
    '<?xml version="1.0"?><?mso-application progid="Excel.Sheet"?>'
    + '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" '
    + 'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">'
    + worksheets.join("")
    + "</Workbook>"
  );
}

app.get("/api/risk-matrix", async (_req, res) => {
  try {
    const response = await axios.get(`${aiServiceUrl}/api/risk-matrix`);
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ message: "Failed to fetch risk matrix", detail: error.message });
  }
});

app.post("/api/export/artifacts", async (req, res) => {
  try {
    const format = String(req.body?.format || "json").toLowerCase();
    const artifacts = req.body?.artifacts || {};
    const testcases = req.body?.testcases || req.body?.data?.testcases || [];

    if (format === "xlsx" || format === "excel") {
      try {
        const xlsxResponse = await axios.post(
          `${aiServiceUrl}/export-artifacts`,
          { format: "xlsx", artifacts, testcases },
          { responseType: "arraybuffer" }
        );
        res.setHeader("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
        res.setHeader("Content-Disposition", "attachment; filename=autotestdesign-artifacts.xlsx");
        return res.send(Buffer.from(xlsxResponse.data));
      } catch (_proxyError) {
        const xml = buildArtifactsSpreadsheetXml(artifacts, testcases);
        res.setHeader("Content-Type", "application/vnd.ms-excel; charset=utf-8");
        res.setHeader("Content-Disposition", "attachment; filename=autotestdesign-artifacts.xls");
        return res.send(xml);
      }
    }

    if (format === "csv") {
      const header = ["id", "designMethod", "title", "priority", "expected", "oracle"];
      const rows = (Array.isArray(testcases) ? testcases : []).map((item) => (
        [
          item.id,
          item.designMethod,
          item.title,
          item.priority,
          item.expected,
          item.oracle
        ]
          .map((value) => `"${String(value ?? "").replace(/"/g, '""')}"`)
          .join(",")
      ));
      const csv = [header.join(","), ...rows].join("\n");
      res.setHeader("Content-Type", "text/csv; charset=utf-8");
      res.setHeader("Content-Disposition", "attachment; filename=autotestdesign-testcases.csv");
      return res.send(csv);
    }

    res.json({
      message: "Artifacts export",
      artifacts,
      testcases
    });
  } catch (error) {
    res.status(500).json({
      message: "Failed to export artifacts",
      detail: error.message
    });
  }
});

app.get("/api/engines/info", async (_req, res) => {
  res.json({
    message: "Deterministic FR engines",
    engineVersion: "autotestdesign-engine-v2",
    promptVersion: "autotestdesign-v6-fr-complete",
    modules: {
      "FR 1.0": "requirement_parser.parse_content_blocks",
      "FR 1.1": "requirement_parser (CSV + numbered text)",
      "FR 2.0": "risk_engine.score_requirements (impact×likelihood)",
      "FR 3.0": "blackbox_engine (EP/BVA/DecisionTable/Pairwise)",
      "FR 4.0": "whitebox_engine (JSON/arrow state model + squat default)",
      "FR 5.0": "oracle_engine.attach_oracles",
      "FR 6.0": "export_xlsx + JSON/CSV/Markdown",
      "FR 7.0": "suite_optimizer.optimize_test_suite",
      strategies: "strategy_builder (ISO 29119-4)",
      validation: "schema_validator (LLM JSON)"
    }
  });
});

app.get("/api/export", async (req, res) => {
  try {
    const format = String(req.query.format || "json").toLowerCase();
    const limit = Math.min(Math.max(Number(req.query.limit || 100), 1), 1000);
    const records = await getRecentGenerationRecords(limit);

    if (format === "csv") {
      const header = [
        "id",
        "sourceType",
        "technique",
        "modelName",
        "promptVersion",
        "qualityScore",
        "tokensEstimate",
        "createdAt"
      ];
      const rows = records.map((item) => (
        [
          item.id,
          item.source_type,
          item.technique,
          item.model_name,
          item.prompt_version,
          item.quality_score,
          item.tokens_estimate,
          item.created_at
        ]
          .map((value) => `"${String(value ?? "").replace(/"/g, '""')}"`)
          .join(",")
      ));
      const csv = [header.join(","), ...rows].join("\n");
      res.setHeader("Content-Type", "text/csv; charset=utf-8");
      res.setHeader("Content-Disposition", "attachment; filename=autotestdesign-export.csv");
      return res.send(csv);
    }

    res.json({
      message: "Export records",
      count: records.length,
      records
    });
  } catch (error) {
    res.status(500).json({
      message: "Failed to export records",
      detail: error.message
    });
  }
});

ensureSchema()
  .then(() => {
    app.listen(port, () => {
      console.log(`backend listening on ${port}`);
    });
  })
  .catch((error) => {
    console.error("Failed to initialize schema", error.message);
    process.exit(1);
  });
