import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import axios from "axios";
import { pool, insertGenerationRecord, ensureSchema, getRecentGenerationRecords, deleteGenerationRecordById } from "./db.js";

dotenv.config();

const app = express();
const port = Number(process.env.PORT || 3000);

const aiServiceUrl = process.env.AI_SERVICE_URL || "http://localhost:8000";
const requiredMethods = [
  "EP",
  "BVA",
  "Combinatorial",
  "StateTransition",
  "DecisionTable"
];

function analyzeBlackBoxQuality(cases) {
  const caseList = Array.isArray(cases) ? cases : [];
  const methodsPresent = new Set(caseList.map((item) => String(item?.designMethod || "")));
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
    res.json({ status: "ok", service: "backend" });
  } catch (error) {
    res.status(500).json({ status: "error", message: error.message });
  }
});

app.post("/api/testcases/generate", async (req, res) => {
  try {
    const {
      sourceType = "requirements",
      content = "",
      promptMode = "default",
      customPrompt = "",
      documents = [],
      testTechnique = process.env.TEST_TECHNIQUE || "black-box"
    } = req.body || {};

    if (!["requirements", "codebase"].includes(sourceType)) {
      return res.status(400).json({
        message: "sourceType must be requirements or codebase"
      });
    }

    if (testTechnique !== "black-box") {
      return res.status(400).json({
        message: "Only black-box testing is supported in this project"
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
      testTechnique: "black-box"
    });

    const generated = aiResponse.data;
    const summaryFromDocs = Array.isArray(documents)
      ? documents.map((item) => String(item?.name || "").trim()).filter(Boolean).join(", ")
      : "";
    const sourceSummary = String(content).trim()
      ? String(content).slice(0, 500)
      : `files: ${summaryFromDocs}`.slice(0, 500);
    const quality = analyzeBlackBoxQuality(generated?.testcases || []);
    const record = await insertGenerationRecord(
      sourceType,
      sourceSummary,
      generated,
      {
        qualityScore: quality.qualityScore,
        tokensEstimate: Math.ceil((String(content).length + JSON.stringify(documents || []).length) / 4)
      }
    );

    res.json({
      message: "Black-box test cases generated",
      technique: "black-box",
      record,
      quality,
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
