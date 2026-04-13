import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import axios from "axios";
import { pool, insertGenerationRecord, ensureSchema } from "./db.js";

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

    if (!String(content).trim()) {
      return res.status(400).json({
        message: "content must not be empty"
      });
    }

    const aiResponse = await axios.post(`${aiServiceUrl}/generate-testcases`, {
      sourceType,
      content,
      testTechnique: "black-box"
    });

    const generated = aiResponse.data;
    const quality = analyzeBlackBoxQuality(generated?.testcases || []);
    const record = await insertGenerationRecord(
      sourceType,
      String(content).slice(0, 500),
      generated,
      {
        qualityScore: quality.qualityScore,
        tokensEstimate: Math.ceil(String(content).length / 4)
      }
    );

    res.json({
      message: "Black-box test cases generated",
      technique: "black-box",
      record,
      quality,
      data: generated
    });
  } catch (error) {
    res.status(500).json({
      message: "Failed to generate test cases",
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
