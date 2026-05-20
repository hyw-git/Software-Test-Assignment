<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import DOMPurify from "dompurify";
import { marked } from "marked";

const sourceType = ref("requirements");
const result = ref(null);
const loading = ref(false);
const status = ref("Import files and configure the prompt to generate black-box test Markdown.");
const historyRecords = ref([]);
const historyLoading = ref(false);
const deletingHistoryId = ref(null);
const activeHistoryRecord = ref(null);
const uploadedDocs = ref([]);
const chatPrompt = ref("");
const fileInputRef = ref(null);
const resultWindowRef = ref(null);
const resultScrollTop = ref(0);
const showSettings = ref(false);
const showHistoryModal = ref(false);
const includeWhitebox = ref(true);
const includeOracle = ref(true);
const includeOptimization = ref(true);
const whiteboxDescription = ref("");
const coverageCriterion = ref("all-states");
const reviewArtifactsText = ref("");
const reviewCoverageText = ref("");
const reviewStrategiesText = ref("");
const reviewTestcasesText = ref("");
const reviewTraceabilityText = ref("");
const reviewError = ref("");
const reviewViewMode = ref("table");
const rawIsJson = ref(false);
const manualRequirementText = ref("");
const csvRequirementText = ref("");

const TARGET_APP_CONTEXT = {
  name: "FitnessAI Intelligent Fitness Assistant System",
  modules: [
    "Real-time Pose Analysis",
    "State Machine Counting",
    "Training Plans",
    "Record Filtering",
    "Dashboard Analytics"
  ],
  risks: [
    "Missing pose keypoints causes misjudgment",
    "Invalid state transitions cause duplicate counting",
    "Invalid workout records pollute analytics",
    "Plan mode edge cases and rest flow errors"
  ]
};

const ASSIGNMENT_CHECKLIST = [
  { id: "FR1.0", label: "Multi-source input/parsing" },
  { id: "FR1.1", label: "Requirement structuring" },
  { id: "FR2.0", label: "Risk scoring" },
  { id: "FR3.0", label: "3+ black-box techniques" },
  { id: "FR6.0", label: "JSON/CSV/Markdown export" },
  { id: "Review", label: "Interactive review and edits" },
  { id: "FR4/5/7", label: "White-box/oracle/optimization bonus" }
];

const FITNESS_REQUIREMENT_SAMPLE = `FitnessAI target application requirements:
1. The pose analysis endpoint /api/analytics/pose accepts exerciseType and 33 MediaPipe landmarks, supporting SQUAT, PUSHUP, PLANK, and JUMPING_JACK.
2. Squat and pushup counting uses a state machine and must prevent invalid UP/DOWN transitions and short-interval double counting.
3. When saving workout records, entries with count < 3 and durationSeconds < 30 should be filtered; other records should enter history analytics.
4. Plan mode generates sets, reps, and rest time by difficulty; users can skip rest and continue to the next set.
5. The dashboard shows today's stats, historical trends, calorie burn, and exercise type distribution.`;

function openHistoryModal() {
  if (resultWindowRef.value) {
    resultScrollTop.value = resultWindowRef.value.scrollTop;
  }
  showHistoryModal.value = true;
}

function closeHistoryModal() {
  showHistoryModal.value = false;
  if (resultWindowRef.value) {
    resultWindowRef.value.scrollTop = resultScrollTop.value;
  }
}

function handleGlobalKeydown(event) {
  if (event.key !== "Escape") {
    return;
  }
  showSettings.value = false;
  closeHistoryModal();
}

marked.setOptions({ gfm: true, breaks: true });

const METHOD_SIGNALS = [
  {
    name: "EP",
    patterns: [/等价类/i, /equivalence\s*partition/i, /\bEP\b/i]
  },
  {
    name: "BVA",
    patterns: [/边界值/i, /boundary\s*value/i, /\bBVA\b/i]
  },
  {
    name: "Combinatorial",
    patterns: [/组合/i, /combinatorial/i, /pairwise/i]
  },
  {
    name: "StateTransition",
    patterns: [/状态迁移/i, /state\s*transition/i]
  },
  {
    name: "DecisionTable",
    patterns: [/决策表/i, /decision\s*table/i]
  }
];

function formatDate(value) {
  if (!value) {
    return "-";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString("en-US", { hour12: false });
}

function viewHistory(record) {
  const markdown = String(record.llmRawOutput || "").trim();
  activeHistoryRecord.value = {
    id: record.id,
    createdAt: record.createdAt,
    sourceType: record.sourceType,
    modelName: record.modelName
  };
  result.value = {
    message: "History record restored",
    technique: record.technique || "black-box",
    quality: record.quality || null,
    artifacts: {
      requirementsStructured: record.structuredRequirements || [],
      coverageItems: record.coverageItems || [],
      riskItems: record.riskItems || [],
      stateModel: record.stateModel || {},
      testSuiteOptimization: record.suiteOptimization || {},
      traceability: record.traceability || [],
      testStrategies: record.testStrategies || [],
      engineMetadata: record.engineMetadata || {}
    },
    engineMetadata: record.engineMetadata || {},
    timingMetrics: record.timingMetrics || {},
    prompt: {
      version: record.promptVersion || "unknown",
      used: record.promptUsed || ""
    },
    llmRawOutput: record.llmRawOutput || "",
    data: {
      model: record.modelName || "unknown",
      testTechnique: record.technique || "black-box",
      testcases: record.generatedCases || []
    }
  };
  result.value.assignmentCompliance = buildClientAssignmentCompliance(
    result.value,
    result.value.artifacts,
    result.value.data.testcases
  );

  status.value = `Loaded history record #${record.id}${markdown ? " (Markdown restored)" : ""}`;
  syncReviewFromResult();
  closeHistoryModal();
}

async function loadHistory(limit = 20) {
  historyLoading.value = true;
  try {
    const response = await fetch(`http://localhost:3000/api/history?limit=${limit}`);
    const payload = await response.json();
    historyRecords.value = response.ok ? (payload.records || []) : [];
    if (!response.ok) {
      status.value = payload.message || "History load failed";
    }
  } catch (_error) {
    historyRecords.value = [];
    status.value = "History load failed. Please confirm the backend is available.";
  } finally {
    historyLoading.value = false;
  }
}

async function deleteHistory(record) {
  if (!record?.id) {
    return;
  }

  const ok = window.confirm(`Delete history record #${record.id}? This cannot be undone.`);
  if (!ok) {
    return;
  }

  deletingHistoryId.value = record.id;
  try {
    const response = await fetch(`http://localhost:3000/api/history/${record.id}`, {
      method: "DELETE"
    });
    const payload = await response.json();
    if (!response.ok) {
      status.value = payload.message || "Delete failed";
      return;
    }

    status.value = `Deleted history record #${record.id}`;
    if (activeHistoryRecord.value?.id === record.id) {
      activeHistoryRecord.value = null;
    }
    await loadHistory();
  } catch (_error) {
    status.value = "Delete failed. Please confirm the backend is available.";
  } finally {
    deletingHistoryId.value = null;
  }
}

function onFileChange(event) {
  const files = Array.from(event.target.files || []);
  if (!files.length) {
    return;
  }

  Promise.all(
    files.map(
      (file) =>
        new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => {
            resolve({
              name: file.name,
              size: file.size,
              type: file.type || "text/plain",
              content: String(reader.result || "")
            });
          };
          reader.onerror = () => reject(new Error("read failed"));
          reader.readAsText(file, "utf-8");
        })
    )
  )
    .then((docs) => {
      uploadedDocs.value = [...uploadedDocs.value, ...docs];
      const totalChars = uploadedDocs.value.reduce((acc, item) => acc + item.content.length, 0);
      status.value = `Imported ${uploadedDocs.value.length} files (${totalChars} chars)`;
    })
    .catch(() => {
      status.value = "File read failed. Please retry.";
    });

  if (event.target) {
    event.target.value = "";
  }
}

function openFilePicker() {
  fileInputRef.value?.click();
}

function removeUploadedDoc(index) {
  uploadedDocs.value = uploadedDocs.value.filter((_, idx) => idx !== index);
  status.value = `Removed 1 file. ${uploadedDocs.value.length} files remaining.`;
}

function clearUploadedDocs() {
  uploadedDocs.value = [];
  status.value = "Cleared uploaded files.";
}

function parseCsvLine(line) {
  const values = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (char === '"') {
      inQuotes = !inQuotes;
      continue;
    }
    if (char === "," && !inQuotes) {
      values.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }
  values.push(current.trim());
  return values;
}

function parseCsvRequirementText(text) {
  const lines = String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length < 2) {
    return "";
  }

  const headers = parseCsvLine(lines[0]);
  const rows = lines.slice(1).map((line, index) => {
    const values = parseCsvLine(line);
    const fields = headers.map((header, fieldIndex) => `${header || `field${fieldIndex + 1}`}: ${values[fieldIndex] || "-"}`);
    const reqId = values[headers.indexOf("id")] || values[0] || `CSV-REQ-${index + 1}`;
    return `${reqId}: ${fields.join("; ")}`;
  });
  return rows.join("\n");
}

function buildManualContent() {
  const chunks = [
    `Target application: ${TARGET_APP_CONTEXT.name}`,
    `Core modules: ${TARGET_APP_CONTEXT.modules.join(", ")}`,
    `Key risks: ${TARGET_APP_CONTEXT.risks.join(", ")}`
  ];

  const manualText = String(manualRequirementText.value || "").trim();
  if (manualText) {
    chunks.push(`[Plain-text requirements]\n${manualText}`);
  }

  const rawCsv = String(csvRequirementText.value || "").trim();
  if (rawCsv) {
    chunks.push(`[CSV requirements]\n${rawCsv}`);
    const csvText = parseCsvRequirementText(csvRequirementText.value);
    if (csvText) {
      chunks.push(`[Parsed CSV summary]\n${csvText}`);
    }
  }

  return chunks.join("\n\n");
}

function loadFitnessSample() {
  manualRequirementText.value = FITNESS_REQUIREMENT_SAMPLE;
  csvRequirementText.value = "id,feature,input,condition,expected\nREQ-POSE-001,pose analysis,exerciseType+landmarks,33 keypoints and valid exerciseType,return count/score/feedback\nREQ-REC-001,record filtering,count+durationSeconds,count<3 and duration<30,filter record from storage\nREQ-PLAN-001,plan mode,difficulty,easy/medium/hard,generate sets/reps/rest";
  status.value = "FitnessAI sample requirements loaded. You can generate test design now.";
}

function clearTextInputs() {
  manualRequirementText.value = "";
  csvRequirementText.value = "";
  status.value = "Cleared plain-text and CSV inputs.";
}

async function generateCases() {
  const hasDocuments = uploadedDocs.value.some((item) => String(item?.content || "").trim());
  const manualContent = buildManualContent();
  const hasManualInput = Boolean(String(manualRequirementText.value || "").trim() || String(csvRequirementText.value || "").trim());
  if (!hasDocuments && !hasManualInput) {
    status.value = "Please upload files or fill in plain-text/CSV requirements before generating.";
    return;
  }

  loading.value = true;
  result.value = null;
  activeHistoryRecord.value = null;
  const promptText = String(chatPrompt.value || "").trim();
  status.value = "AI is generating FitnessAI test design artifacts...";

  try {
    const response = await fetch("http://localhost:3000/api/testcases/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sourceType: sourceType.value,
        content: manualContent,
        promptMode: promptText ? "custom" : "default",
        customPrompt: promptText,
        documents: uploadedDocs.value.map((item) => ({
          name: item.name,
          type: item.type,
          content: item.content
        })),
        testTechnique: "black-box",
        includeWhitebox: includeWhitebox.value,
        includeOracle: includeOracle.value,
        includeOptimization: includeOptimization.value,
        whiteboxDescription: String(whiteboxDescription.value || "").trim(),
        coverageCriterion: coverageCriterion.value
      })
    });
    const payload = await response.json();
    result.value = payload;
    status.value = response.ok
      ? "Generation complete"
      : `Generation failed: ${payload.detail || payload.message || "Please check inputs or service status."}`;
    if (response.ok) {
      chatPrompt.value = "";
      syncReviewFromResult();
      await loadHistory();
    }
  } catch (error) {
    result.value = { message: "Request failed", detail: String(error) };
    status.value = "Request failed. Please confirm the backend is running.";
  } finally {
    loading.value = false;
  }
}

function formatCoverageLine(item) {
  if (item == null) {
    return "";
  }
  if (typeof item === "string") {
    return item.trim();
  }
  if (typeof item === "object") {
    const label = item.label || item.name || item.id || item.feature || item.coverageItem || item.description;
    if (label) {
      return String(label).trim();
    }
    return JSON.stringify(item);
  }
  return String(item).trim();
}

function formatCoverageItemsForEditor(items) {
  return (Array.isArray(items) ? items : [])
    .map(formatCoverageLine)
    .filter(Boolean)
    .join("\n");
}

function pickNonEmptyArray(primary, fallback) {
  const chosen = Array.isArray(primary) ? primary : [];
  return chosen.length ? chosen : (Array.isArray(fallback) ? fallback : []);
}

function mergeReviewArtifacts(apiArtifacts, parsedArtifacts) {
  const api = apiArtifacts && typeof apiArtifacts === "object" ? apiArtifacts : {};
  const parsed = parsedArtifacts && typeof parsedArtifacts === "object" ? parsedArtifacts : {};
  return {
    ...api,
    ...parsed,
    inputVariables: pickNonEmptyArray(parsed.inputVariables, api.inputVariables),
    equivalencePartitions: pickNonEmptyArray(parsed.equivalencePartitions, api.equivalencePartitions),
    boundaryValues: pickNonEmptyArray(parsed.boundaryValues, api.boundaryValues),
    decisionTableRules: pickNonEmptyArray(parsed.decisionTableRules, api.decisionTableRules),
    requirementsStructured: pickNonEmptyArray(parsed.requirementsStructured, api.requirementsStructured),
    coverageItems: pickNonEmptyArray(parsed.coverageItems, api.coverageItems),
    riskItems: pickNonEmptyArray(parsed.riskItems, api.riskItems),
    testStrategies: pickNonEmptyArray(parsed.testStrategies, api.testStrategies),
    traceability: pickNonEmptyArray(parsed.traceability, api.traceability),
    missingItems: pickNonEmptyArray(parsed.missingItems, api.missingItems),
    assumptions: pickNonEmptyArray(parsed.assumptions, api.assumptions),
    stateModel:
      parsed.stateModel && Object.keys(parsed.stateModel).length
        ? parsed.stateModel
        : api.stateModel || {},
    testSuiteOptimization:
      parsed.testSuiteOptimization && Object.keys(parsed.testSuiteOptimization).length
        ? parsed.testSuiteOptimization
        : api.testSuiteOptimization || {},
    engineMetadata: api.engineMetadata || parsed.engineMetadata || {},
    timingMetrics: api.timingMetrics || parsed.timingMetrics || {}
  };
}

function syncReviewFromResult() {
  reviewError.value = "";
  const rawText = String(result.value?.llmRawOutput || "").trim();
  const parsed = parseJsonFromText(rawText);
  rawIsJson.value = Boolean(parsed && typeof parsed === "object");

  const apiArtifacts = result.value?.artifacts || result.value?.data?.artifacts || {};
  let artifacts = { ...apiArtifacts };
  let testcases = result.value?.data?.testcases || result.value?.testcases || [];
  let traceability = Array.isArray(artifacts?.traceability) ? artifacts.traceability : [];

  if (rawIsJson.value) {
    const parsedArtifacts = {
      inputVariables: parsed?.inputVariables || [],
      equivalencePartitions: parsed?.equivalencePartitions || [],
      boundaryValues: parsed?.boundaryValues || [],
      decisionTableRules: parsed?.decisionTableRules || [],
      requirementsStructured: parsed?.requirementsStructured || [],
      coverageItems: parsed?.coverageItems || [],
      riskItems: parsed?.riskItems || [],
      stateModel: parsed?.stateModel || {},
      testSuiteOptimization: parsed?.testSuiteOptimization || {},
      testStrategies: parsed?.testStrategies || [],
      traceability: parsed?.traceability || [],
      missingItems: parsed?.missingItems || [],
      assumptions: parsed?.assumptions || []
    };

    artifacts = mergeReviewArtifacts(apiArtifacts, parsedArtifacts);
    testcases = pickNonEmptyArray(parsed?.testcases, testcases);
    traceability = pickNonEmptyArray(parsed?.traceability, traceability);
    artifacts.traceability = traceability;
    if (result.value) {
      result.value.artifacts = artifacts;
      result.value.data = result.value.data || {};
      result.value.data.testcases = Array.isArray(testcases) ? testcases : [];
      result.value.assignmentCompliance = buildClientAssignmentCompliance(result.value, artifacts, testcases);
    }
  }

  if (result.value) {
    result.value.assignmentCompliance = buildClientAssignmentCompliance(result.value, artifacts, testcases);
  }

  const coverage = Array.isArray(artifacts?.coverageItems) ? artifacts.coverageItems : [];
  const strategies = Array.isArray(artifacts?.testStrategies) ? artifacts.testStrategies : [];
  reviewArtifactsText.value = JSON.stringify(artifacts || {}, null, 2);
  reviewCoverageText.value = formatCoverageItemsForEditor(coverage);
  reviewStrategiesText.value = strategies.length ? JSON.stringify(strategies, null, 2) : "[]";
  reviewTestcasesText.value = JSON.stringify(testcases || [], null, 2);
  reviewTraceabilityText.value = JSON.stringify(traceability || [], null, 2);
}

const reviewTableCases = computed(() => {
  try {
    return JSON.parse(reviewTestcasesText.value || "[]");
  } catch (_error) {
    return [];
  }
});

const timingDisplay = computed(() => result.value?.timingMetrics || result.value?.artifacts?.timingMetrics || null);

function parseJsonFromText(text) {
  if (!text) {
    return null;
  }

  const parsedItems = [];
  const seenCandidates = new Set();
  const direct = safeJsonParse(text);
  if (direct) {
    parsedItems.push(direct);
  }

  const codeBlocks = [...text.matchAll(/```(?:json)?\s*([\s\S]*?)\s*```/gi)];
  for (const block of codeBlocks) {
    seenCandidates.add(String(block[1] || "").trim());
    const parsed = safeJsonParse(block[1]);
    if (parsed) {
      parsedItems.push(parsed);
    }
  }

  for (const candidate of balancedJsonCandidates(text)) {
    const normalizedCandidate = candidate.trim();
    if (seenCandidates.has(normalizedCandidate)) {
      continue;
    }
    seenCandidates.add(normalizedCandidate);
    const parsed = safeJsonParse(candidate);
    if (parsed) {
      parsedItems.push(parsed);
    }
  }

  parsedItems.push(...extractKeyedJsonFragments(text));

  return mergeParsedPayloads(parsedItems);
}

function safeJsonParse(value) {
  const raw = String(value || "").trim();
  try {
    return JSON.parse(raw);
  } catch (_error) {
    try {
      const repaired = repairJsonCandidate(raw);
      return repaired === raw ? null : JSON.parse(repaired);
    } catch (_repairError) {
      return null;
    }
  }
}

function repairJsonCandidate(value) {
  return String(value || "")
    .trim()
    .replace(/,\s*([}\]])/g, "$1")
    .replace(/\bNone\b/g, "null")
    .replace(/\bTrue\b/g, "true")
    .replace(/\bFalse\b/g, "false")
    .replace(/\[\s*(\{[^][]*?\})\s+for\s+_\s+in\s+range\(\s*(\d+)\s*\)\s*\]/gs, (_match, objectText, count) => {
      return `["${count} repeated objects: ${String(objectText).replace(/"/g, "'")}"]`;
    })
    .replace(/\[\s*(["'][^][]*?["'])\s+for\s+_\s+in\s+range\(\s*(\d+)\s*\)\s*\]/gs, (_match, itemText, count) => {
      return `["${count} repeated values: ${String(itemText).replace(/^["']|["']$/g, "")}"]`;
    });
}

function balancedJsonCandidates(text) {
  const candidates = [];
  const stack = [];
  const pairs = { "{": "}", "[": "]" };
  let start = null;
  let inString = false;
  let escape = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (inString) {
      if (escape) {
        escape = false;
      } else if (char === "\\") {
        escape = true;
      } else if (char === "\"") {
        inString = false;
      }
      continue;
    }

    if (char === "\"") {
      inString = true;
      continue;
    }

    if (pairs[char]) {
      if (!stack.length) {
        start = index;
      }
      stack.push(pairs[char]);
      continue;
    }

    if (stack.length && char === stack[stack.length - 1]) {
      stack.pop();
      if (!stack.length && start !== null) {
        candidates.push(text.slice(start, index + 1));
        start = null;
      }
    }
  }

  return candidates;
}

function balancedJsonFrom(text, start) {
  const pairs = { "{": "}", "[": "]" };
  const expected = pairs[text[start]];
  if (!expected) {
    return null;
  }

  const stack = [expected];
  let inString = false;
  let escape = false;

  for (let index = start + 1; index < text.length; index += 1) {
    const char = text[index];
    if (inString) {
      if (escape) {
        escape = false;
      } else if (char === "\\") {
        escape = true;
      } else if (char === "\"") {
        inString = false;
      }
      continue;
    }

    if (char === "\"") {
      inString = true;
      continue;
    }
    if (pairs[char]) {
      stack.push(pairs[char]);
      continue;
    }
    if (stack.length && char === stack[stack.length - 1]) {
      stack.pop();
      if (!stack.length) {
        return text.slice(start, index + 1);
      }
    }
  }

  return null;
}

function extractKeyedJsonFragments(text) {
  const keys = [
    "inputVariables",
    "equivalencePartitions",
    "boundaryValues",
    "decisionTableRules",
    "requirementsStructured",
    "coverageItems",
    "riskItems",
    "stateModel",
    "testSuiteOptimization",
    "testStrategies",
    "traceability",
    "testcases",
    "testCases",
    "test_cases",
    "missingItems",
    "assumptions"
  ];
  const fragments = [];
  const keyPattern = keys.map((key) => key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  const matcher = new RegExp(`"(${keyPattern})"\\s*:`, "g");

  for (const match of text.matchAll(matcher)) {
    const rawKey = match[1];
    const key = rawKey === "testCases" || rawKey === "test_cases" ? "testcases" : rawKey;
    let index = match.index + match[0].length;
    while (index < text.length && /\s/.test(text[index])) {
      index += 1;
    }
    if (!["[", "{"].includes(text[index])) {
      continue;
    }
    const candidate = balancedJsonFrom(text, index);
    const parsed = safeJsonParse(candidate || "");
    if (parsed) {
      fragments.push({ [key]: parsed });
    } else if (key === "testcases" && text[index] === "[") {
      const items = extractCompleteArrayItems(text, index);
      if (items.length) {
        fragments.push({ [key]: items });
      }
    }
  }

  return fragments;
}

function extractCompleteArrayItems(text, start) {
  const items = [];
  let index = start + 1;
  while (index < text.length) {
    while (index < text.length && (/\s/.test(text[index]) || text[index] === ",")) {
      index += 1;
    }
    if (index >= text.length || text[index] === "]") {
      break;
    }
    if (!["[", "{"].includes(text[index])) {
      index += 1;
      continue;
    }

    const candidate = balancedJsonFrom(text, index);
    if (!candidate) {
      break;
    }
    const parsed = safeJsonParse(candidate);
    if (parsed) {
      items.push(parsed);
    }
    index += candidate.length;
  }
  return items;
}

function mergeParsedPayloads(items) {
  const knownKeys = new Set([
    "inputVariables",
    "equivalencePartitions",
    "boundaryValues",
    "decisionTableRules",
    "requirementsStructured",
    "coverageItems",
    "riskItems",
    "stateModel",
    "testSuiteOptimization",
    "testStrategies",
    "traceability",
    "testcases",
    "missingItems",
    "assumptions"
  ]);
  const merged = {};

  for (const item of items) {
    if (Array.isArray(item)) {
      if (item.every((entry) => entry && typeof entry === "object")) {
        merged.testcases = [...(merged.testcases || []), ...item];
      }
      continue;
    }

    if (!item || typeof item !== "object") {
      continue;
    }

    const payload = { ...item };
    for (const wrapperKey of ["data", "artifacts", "result", "output"]) {
      if (payload[wrapperKey] && typeof payload[wrapperKey] === "object" && !Array.isArray(payload[wrapperKey])) {
        Object.assign(payload, payload[wrapperKey]);
      }
    }

    for (const [key, value] of Object.entries(payload)) {
      if (!knownKeys.has(key)) {
        continue;
      }
      if (Array.isArray(value)) {
        merged[key] = [...(Array.isArray(merged[key]) ? merged[key] : []), ...value];
      } else if (value && typeof value === "object") {
        merged[key] = { ...(merged[key] && typeof merged[key] === "object" ? merged[key] : {}), ...value };
      } else if (merged[key] === undefined) {
        merged[key] = value;
      }
    }
  }

  return Object.keys(merged).length ? merged : null;
}

function collectDesignMethods(testcases) {
  const methods = new Set();
  for (const item of Array.isArray(testcases) ? testcases : []) {
    const text = [
      item?.designMethod,
      item?.method,
      item?.technique,
      item?.title,
      item?.id,
      ...(Array.isArray(item?.traceability) ? item.traceability : [])
    ].map((value) => String(value || "")).join(" ");

    if (/\bEP\b|equivalence|等价类/i.test(text)) methods.add("EP");
    if (/\bBVA\b|boundary|边界值/i.test(text)) methods.add("BVA");
    if (/combinatorial|pairwise|组合/i.test(text)) methods.add("Combinatorial");
    if (/state\s*transition|stateTransition|状态迁移|状态机/i.test(text)) methods.add("StateTransition");
    if (/decision\s*table|decisionTable|决策表/i.test(text)) methods.add("DecisionTable");
  }
  return methods;
}

function buildClientAssignmentCompliance(currentResult, artifacts, testcases) {
  const rawOutput = String(currentResult?.llmRawOutput || "");
  const engineMeta = currentResult?.engineMetadata || artifacts?.engineMetadata || {};
  const frEngines = engineMeta?.frEngines || {};
  const cases = Array.isArray(testcases) ? testcases : [];
  const traceRefs = cases.flatMap((item) => Array.isArray(item?.traceability) ? item.traceability : []).map((value) => String(value || ""));
  const methods = collectDesignMethods(cases);
  const missingMethods = ["EP", "BVA", "Combinatorial", "StateTransition", "DecisionTable"].filter((method) => !methods.has(method));
  const hasRuleParser = Boolean(frEngines["FR1.0"] || frEngines["FR1.1"]);
  const hasRuleRisk = Boolean(frEngines["FR2.0"]);
  const hasRuleBlackbox = Boolean(frEngines["FR3.0"]);
  const hasStructuredRequirements = (Array.isArray(artifacts?.requirementsStructured) && artifacts.requirementsStructured.length > 0)
    || hasRuleParser
    || /"requirementsStructured"|REQ-[A-Z0-9-]+|结构化需求/.test(rawOutput);
  const hasRiskItems = (Array.isArray(artifacts?.riskItems) && artifacts.riskItems.length > 0)
    || hasRuleRisk
    || /"riskItems"|R-[A-Z0-9-]+|风险分析|priority/i.test(rawOutput)
    || cases.some((item) => ["high", "medium", "low"].includes(String(item?.priority || "").toLowerCase()))
    || traceRefs.some((ref) => /^R-/i.test(ref));
  const hasTestStrategies = (Array.isArray(artifacts?.testStrategies) && artifacts.testStrategies.length > 0) || Boolean(frEngines["FR3.0"]);
  const hasCoverageOrTraceability = (Array.isArray(artifacts?.coverageItems) && artifacts.coverageItems.length > 0)
    || hasTestStrategies
    || (Array.isArray(artifacts?.traceability) && artifacts.traceability.length > 0)
    || cases.some((item) => Array.isArray(item?.traceability) && item.traceability.length > 0)
    || /"coverageItems"|C-[A-Z0-9-]+|"traceability"|覆盖项|追溯关系/.test(rawOutput);
  const hasStateModel = artifacts?.stateModel && Object.keys(artifacts.stateModel).length > 0;
  const hasOracle = cases.some((item) => String(item?.oracle || "").trim());
  const hasOptimization = artifacts?.testSuiteOptimization && Object.keys(artifacts.testSuiteOptimization).length > 0;
  const engineNote = engineMeta?.engineVersion ? `Engine ${engineMeta.engineVersion}` : "";

  const items = [
    { id: "FR 1.0", label: "Input/parsing", passed: true, evidence: `Multi-source input; ${engineNote}` },
    { id: "FR 1.1", label: "Requirement structuring", passed: hasStructuredRequirements, evidence: `${artifacts?.requirementsStructured?.length || 0} reqs; ${frEngines["FR1.1"] || "LLM"}` },
    { id: "FR 2.0", label: "Risk analysis and priority", passed: hasRiskItems, evidence: `${artifacts?.riskItems?.length || 0} risks; ${frEngines["FR2.0"] || ""}` },
    { id: "FR 3.0", label: "Black-box test design", passed: methods.size >= 3 || hasRuleBlackbox, evidence: `${methods.size} methods; ${frEngines["FR3.0"] || "LLM"}; missing: ${missingMethods.join(", ") || "none"}` },
    { id: "FR 6.0", label: "Output and export", passed: true, evidence: "Markdown/JSON/CSV/XLSX export supported" },
    { id: "Interactive Review", label: "Interactive review", passed: hasCoverageOrTraceability, evidence: "Coverage, strategies, cases, traceability editable" },
    { id: "FR 4.0", label: "White-box modeling", passed: hasStateModel, evidence: hasStateModel ? `State model; ${frEngines["FR4.0"] || ""}` : "No state model" },
    { id: "FR 5.0", label: "Test oracle", passed: hasOracle, evidence: hasOracle ? `Oracle present; ${frEngines["FR5.0"] || ""}` : "No oracle" },
    { id: "FR 7.0", label: "Test suite optimization", passed: hasOptimization, evidence: hasOptimization ? `Optimized; ${frEngines["FR7.0"] || ""}` : "No optimization" }
  ];
  const required = items.filter((item) => !["FR 4.0", "FR 5.0", "FR 7.0"].includes(item.id));
  const requiredPassed = required.filter((item) => item.passed).length;

  return {
    ...(currentResult?.assignmentCompliance || {}),
    requiredScore: Number((requiredPassed / required.length).toFixed(2)),
    items
  };
}

function hasMeaningfulContent(value) {
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (value && typeof value === "object") {
    return Object.keys(value).length > 0;
  }
  return Boolean(String(value || "").trim());
}

function applyReviewEdits() {
  reviewError.value = "";
  try {
    const artifacts = JSON.parse(reviewArtifactsText.value || "{}");
    const testcases = JSON.parse(reviewTestcasesText.value || "[]");
    const traceability = JSON.parse(reviewTraceabilityText.value || "[]");
    const strategies = JSON.parse(reviewStrategiesText.value || "[]");
    const coverage = String(reviewCoverageText.value || "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    artifacts.coverageItems = coverage;
    artifacts.testStrategies = Array.isArray(strategies) ? strategies : [];
    artifacts.traceability = Array.isArray(traceability) ? traceability : [];
    if (!result.value) {
      result.value = { message: "Review changes applied", artifacts, data: { testcases } };
    }
    result.value.artifacts = artifacts;
    result.value.data = result.value.data || {};
    result.value.data.testcases = Array.isArray(testcases) ? testcases : [];
    result.value.assignmentCompliance = buildClientAssignmentCompliance(result.value, result.value.artifacts, result.value.data.testcases);
    status.value = "Review changes applied.";
  } catch (error) {
    reviewError.value = `JSON parse failed: ${String(error)}`;
  }
}

function updateCaseField(index, field, value) {
  try {
    const list = JSON.parse(reviewTestcasesText.value || "[]");
    if (!Array.isArray(list) || !list[index]) {
      return;
    }
    list[index][field] = value;
    reviewTestcasesText.value = JSON.stringify(list, null, 2);
  } catch (_error) {
    reviewError.value = "Failed to update testcase table.";
  }
}

function exportJson() {
  if (!result.value) {
    status.value = "Nothing to export.";
    return;
  }
  const payload = {
    artifacts: result.value.artifacts || {},
    testcases: result.value?.data?.testcases || [],
    prompt: result.value?.prompt || {}
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `autotestdesign-${Date.now()}.json`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
  status.value = "JSON report exported.";
}

function exportCsv() {
  if (!result.value) {
    status.value = "Nothing to export.";
    return;
  }
  const testcases = result.value?.data?.testcases || [];
  const header = ["id", "designMethod", "title", "priority", "expected", "oracle"];
  const rows = testcases.map((item) => (
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
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `autotestdesign-${Date.now()}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
  status.value = "CSV report exported.";
}

function buildSpreadsheetXml(artifacts, testcases) {
  const escapeXml = (value) => String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

  const sheet = (name, headers, rows) => {
    const headerRow = headers.map((header) => `<Cell><Data ss:Type="String">${escapeXml(header)}</Data></Cell>`).join("");
    const dataRows = rows.map((row) => {
      const cells = headers.map((header) => `<Cell><Data ss:Type="String">${escapeXml(row[header])}</Data></Cell>`).join("");
      return `<Row>${cells}</Row>`;
    }).join("");
    return `<Worksheet ss:Name="${escapeXml(name)}"><Table><Row>${headerRow}</Row>${dataRows}</Table></Worksheet>`;
  };

  const requirements = Array.isArray(artifacts?.requirementsStructured) ? artifacts.requirementsStructured : [];
  const risks = Array.isArray(artifacts?.riskItems) ? artifacts.riskItems : [];
  const cases = Array.isArray(testcases) ? testcases : [];

  const reqRows = requirements.map((item) => ({
    id: item.id || item.reqId || item.requirementId || "",
    feature: item.feature || item.name || item.title || item.module || "",
    inputFields: Array.isArray(item.inputFields || item.inputs)
      ? (item.inputFields || item.inputs).join(";")
      : String(item.inputFields || item.input || item.inputs || ""),
    expectedAction: item.expectedAction || item.expected || item.expectedResult || item.description || ""
  }));
  const riskRows = risks.map((item) => ({
    reqId: item.reqId || item.id || item.requirementId || "",
    impact: item.impact ?? item.Impact ?? "",
    likelihood: item.likelihood ?? item.Likelihood ?? "",
    riskScore: item.riskScore ?? item.risk_score ?? item.score ?? "",
    priority: item.priority || item.Priority || ""
  }));
  const caseRows = cases.map((item) => ({
    id: item.id || item.testCaseId || item.caseId || "",
    designMethod: item.designMethod || item.method || item.technique || "",
    title: item.title || item.name || item.summary || "",
    priority: item.priority || item.severity || "",
    oracle: item.oracle || "",
    expected: item.expected || item.expectedResult || item.expected_result || ""
  }));

  return (
    '<?xml version="1.0"?><?mso-application progid="Excel.Sheet"?>'
    + '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">'
    + sheet("Requirements", ["id", "feature", "inputFields", "expectedAction"], reqRows)
    + sheet("Risks", ["reqId", "impact", "likelihood", "riskScore", "priority"], riskRows)
    + sheet("TestCases", ["id", "designMethod", "title", "priority", "oracle", "expected"], caseRows)
    + "</Workbook>"
  );
}

function collectExportPayload() {
  let artifacts = result.value?.artifacts || result.value?.data?.artifacts || {};
  let testcases = result.value?.data?.testcases || result.value?.testcases || [];

  try {
    const parsedArtifacts = JSON.parse(reviewArtifactsText.value || "{}");
    if (parsedArtifacts && typeof parsedArtifacts === "object" && Object.keys(parsedArtifacts).length) {
      artifacts = parsedArtifacts;
    }
  } catch (_error) {
    // keep API artifacts
  }

  try {
    const parsedCases = JSON.parse(reviewTestcasesText.value || "[]");
    if (Array.isArray(parsedCases) && parsedCases.length) {
      testcases = parsedCases;
    }
  } catch (_error) {
    // keep API testcases
  }

  return { artifacts, testcases };
}

async function exportXlsx() {
  if (!result.value) {
    status.value = "Nothing to export.";
    return;
  }
  const { artifacts, testcases } = collectExportPayload();
  try {
    const response = await fetch("http://localhost:3000/api/export/artifacts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ format: "xlsx", artifacts, testcases })
    });
    if (!response.ok) {
      throw new Error("xlsx export failed");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `autotestdesign-${Date.now()}.xlsx`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    status.value = "Excel (.xlsx) report exported.";
  } catch (_error) {
    const xml = buildSpreadsheetXml(artifacts, testcases);
    const blob = new Blob([xml], { type: "application/vnd.ms-excel;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `autotestdesign-${Date.now()}.xls`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    status.value = "Excel fallback (.xls) exported.";
  }
}

function buildReviewedMarkdown() {
  const artifacts = result.value?.artifacts || {};
  const testcases = result.value?.data?.testcases || [];
  const traceability = artifacts?.traceability || [];
  const risks = Array.isArray(artifacts?.riskItems) ? artifacts.riskItems : [];
  const requirements = Array.isArray(artifacts?.requirementsStructured) ? artifacts.requirementsStructured : [];

  const lines = [
    "# AutoTestDesign Reviewed Test Design Report",
    "",
    `Target application: ${TARGET_APP_CONTEXT.name}`,
    `Generated at: ${new Date().toLocaleString("en-US", { hour12: false })}`,
    "",
    "## Assignment requirement coverage",
    ...ASSIGNMENT_CHECKLIST.map((item) => `- ${item.id}: ${item.label}`),
    "",
    "## Structured requirements",
    requirements.length ? JSON.stringify(requirements, null, 2) : "No structured requirements.",
    "",
    "## Risk analysis",
    risks.length ? JSON.stringify(risks, null, 2) : "No risk items.",
    "",
    "## Test cases",
    testcases.length ? JSON.stringify(testcases, null, 2) : "No test cases.",
    "",
    "## Traceability",
    traceability.length ? JSON.stringify(traceability, null, 2) : "No traceability items."
  ];

  return lines.join("\n");
}

const markdownStats = computed(() => {
  const text = String(result.value?.llmRawOutput || "").trim();
  if (!text) {
    return null;
  }

  const coveredMethods = METHOD_SIGNALS.filter((signal) => signal.patterns.some((pattern) => pattern.test(text))).map(
    (signal) => signal.name
  );
  const missingMethods = METHOD_SIGNALS.filter((signal) => !coveredMethods.includes(signal.name)).map((signal) => signal.name);

  return {
    coveredMethods,
    missingMethods
  };
});

function exportMarkdown() {
  const reviewedMarkdown = buildReviewedMarkdown();
  const markdown = reviewedMarkdown || String(result.value?.llmRawOutput || "").trim();
  if (!markdown) {
    status.value = "Nothing to export.";
    return;
  }

  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `blackbox-testcases-${Date.now()}.md`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);

  status.value = "Markdown report exported.";
}

const reviewSummary = computed(() => {
  let artifacts = {};
  let testcases = [];
  let traceability = [];

  try {
    artifacts = JSON.parse(reviewArtifactsText.value || "{}");
  } catch (_error) {
    artifacts = {};
  }
  try {
    testcases = JSON.parse(reviewTestcasesText.value || "[]");
  } catch (_error) {
    testcases = [];
  }
  try {
    traceability = JSON.parse(reviewTraceabilityText.value || "[]");
  } catch (_error) {
    traceability = [];
  }

  const risks = Array.isArray(artifacts?.riskItems) ? artifacts.riskItems : [];
  const coverage = Array.isArray(artifacts?.coverageItems) ? artifacts.coverageItems : [];
  const strategies = Array.isArray(artifacts?.testStrategies) ? artifacts.testStrategies : [];
  const requirements = Array.isArray(artifacts?.requirementsStructured) ? artifacts.requirementsStructured : [];
  const methods = new Set((Array.isArray(testcases) ? testcases : []).map((item) => String(item?.designMethod || "")).filter(Boolean));

  return {
    requirements: requirements.length,
    coverage: coverage.length,
    strategies: strategies.length,
    risks: risks.length,
    testcases: Array.isArray(testcases) ? testcases.length : 0,
    traceability: Array.isArray(traceability) ? traceability.length : 0,
    methods: methods.size,
    qualityScore: result.value?.quality?.qualityScore ?? "-"
  };
});

const markdownPreviewHtml = computed(() => {
  const raw = String(result.value?.llmRawOutput || "").trim();
  if (!raw) {
    return "";
  }

  const html = marked.parse(raw);
  return DOMPurify.sanitize(String(html));
});

const hasArtifacts = computed(() => {
  try {
    return hasMeaningfulContent(JSON.parse(reviewArtifactsText.value || "{}"));
  } catch (_error) {
    return false;
  }
});

const hasTestcases = computed(() => {
  try {
    return hasMeaningfulContent(JSON.parse(reviewTestcasesText.value || "[]"));
  } catch (_error) {
    return false;
  }
});

const hasTraceability = computed(() => {
  try {
    return hasMeaningfulContent(JSON.parse(reviewTraceabilityText.value || "[]"));
  } catch (_error) {
    return false;
  }
});

const assistantSummary = computed(() => {
  if (!result.value) {
    return "";
  }
  return result.value.message || "Result received.";
});

onMounted(() => {
  window.addEventListener("keydown", handleGlobalKeydown);
  loadHistory();
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleGlobalKeydown);
});
</script>

<template>
  <main class="page">
    <header class="topbar">
      <div>
        <p class="eyebrow">Assignment2 AutoTestDesign Studio</p>
        <h1>Auto Test Design Workspace</h1>
        <p class="lead">Generate risks, coverage, test cases, oracles, white-box models, and optimized suites for the target app.</p>
      </div>
      <p class="status">{{ status }}</p>
      <div class="topbar-actions">
        <div class="settings-wrap">
          <button class="ghost small-btn" @click="showSettings = !showSettings">Session Settings</button>

          <section class="settings-popover" v-if="showSettings">
            <div class="panel-head compact">
              <h2>Session Settings</h2>
              <button class="ghost small-btn" @click="showSettings = false">Close</button>
            </div>
            <label>
              Source Type
              <select v-model="sourceType">
                <option value="requirements">Requirements Document</option>
                <option value="codebase">Codebase/Modules</option>
              </select>
            </label>
            <label>
              White-box Modeling
              <select v-model="coverageCriterion">
                <option value="all-states">All States Coverage</option>
                <option value="all-transitions">All Transitions Coverage</option>
              </select>
            </label>
            <label>
              Options
              <div class="toggle-grid">
                <label class="toggle-item">
                  <input type="checkbox" v-model="includeWhitebox" />
                  <span>Include White-box Model</span>
                </label>
                <label class="toggle-item">
                  <input type="checkbox" v-model="includeOracle" />
                  <span>Include Test Oracle</span>
                </label>
                <label class="toggle-item">
                  <input type="checkbox" v-model="includeOptimization" />
                  <span>Include Suite Optimization</span>
                </label>
              </div>
            </label>
            <label>
              White-box Model Description (Optional)
              <textarea class="compact-textarea" v-model="whiteboxDescription" placeholder="Describe the state machine or flow..." rows="3"></textarea>
            </label>
            <div class="uploaded-box compact" v-if="uploadedDocs.length">
              <p class="msg">{{ uploadedDocs.length }} files attached</p>
              <ul class="uploaded-list compact">
                <li v-for="(item, index) in uploadedDocs" :key="item.name + item.size + index">
                  <span>{{ item.name }}</span>
                  <button class="ghost mini" @click="removeUploadedDoc(index)">Remove</button>
                </li>
              </ul>
              <button class="ghost" @click="clearUploadedDocs">Clear All Files</button>
            </div>
          </section>
        </div>
        <button class="ghost small-btn" @click="openHistoryModal">History</button>
      </div>
    </header>

    <section class="workspace-shell">
      <aside class="sidebar">
        <article class="panel input-card">
          <div class="panel-head">
            <div>
              <h2>Input and Generate</h2>
              <p class="msg">Files, plain text, CSV, and prompt live here. Results appear on the right.</p>
            </div>
          </div>

          <input
            ref="fileInputRef"
            class="hidden-file-input"
            type="file"
            multiple
            accept=".md,.txt,.json,.java,.ts,.js,.py,.vue,.yaml,.yml"
            @change="onFileChange"
          />

          <div class="button-row">
            <button class="ghost" :disabled="loading" @click="openFilePicker">Upload Docs</button>
            <button class="ghost" @click="loadFitnessSample">Load Sample</button>
            <button class="ghost" @click="clearTextInputs">Clear Text</button>
          </div>

          <div class="composer-files side-files" v-if="uploadedDocs.length">
            <span class="composer-file" v-for="(item, index) in uploadedDocs" :key="item.name + item.size + index">
              {{ item.name }}
              <button class="composer-file-remove" @click="removeUploadedDoc(index)">×</button>
            </span>
            <button class="ghost mini" @click="clearUploadedDocs">Clear Files</button>
          </div>

          <label>
            Prompt
            <textarea
              v-model="chatPrompt"
              rows="8"
              class="prompt-textarea"
              placeholder="Describe your LLM instructions. If LLM_CONTEXT.md is uploaded, a short version is enough."
            ></textarea>
          </label>

          <label>
            Plain-text Requirements
            <textarea
              class="short-textarea"
              v-model="manualRequirementText"
              placeholder="Paste requirements, API notes, or user stories..."
              rows="5"
            ></textarea>
          </label>

          <label>
            CSV Requirements (Header on First Row)
            <textarea
              class="short-textarea"
              v-model="csvRequirementText"
              placeholder="id,feature,input,condition,expected"
              rows="4"
            ></textarea>
          </label>

          <details class="advanced-options">
            <summary>Advanced Options</summary>
            <div class="option-grid">
              <label>
                Source Type
                <select v-model="sourceType">
                  <option value="requirements">Requirements Document</option>
                  <option value="codebase">Codebase/Modules</option>
                </select>
              </label>
              <label>
                Coverage Criterion
                <select v-model="coverageCriterion">
                  <option value="all-states">All States Coverage</option>
                  <option value="all-transitions">All Transitions Coverage</option>
                </select>
              </label>
            </div>
            <div class="toggle-grid inline-toggles">
              <label class="toggle-item">
                <input type="checkbox" v-model="includeWhitebox" />
                <span>White-box Modeling</span>
              </label>
              <label class="toggle-item">
                <input type="checkbox" v-model="includeOracle" />
                <span>Test Oracle</span>
              </label>
              <label class="toggle-item">
                <input type="checkbox" v-model="includeOptimization" />
                <span>Suite Optimization</span>
              </label>
            </div>
            <label>
              White-box Model Description (Optional)
              <textarea class="compact-textarea" v-model="whiteboxDescription" placeholder="Describe the white-box model..." rows="3"></textarea>
            </label>
          </details>

        </article>

        <article class="generate-card">
          <button class="primary generate-btn" :disabled="loading" @click="generateCases">
            {{ loading ? "Generating..." : "Generate Test Design" }}
          </button>
        </article>
      </aside>

      <section class="results-column">
        <article class="panel result" v-if="result">
        <div class="result-head">
          <div>
            <h2>Results</h2>
            <p class="msg">{{ assistantSummary || "Waiting for generation response" }}</p>
          </div>
          <div class="result-tools">
            <span class="badge">{{ result?.data?.model || "assistant" }}</span>
            <button class="ghost export-main-btn" v-if="result" @click="exportMarkdown">Export Markdown</button>
            <button class="ghost export-main-btn" v-if="result" @click="exportJson">Export JSON</button>
            <button class="ghost export-main-btn" v-if="result" @click="exportCsv">Export CSV</button>
            <button class="ghost export-main-btn" v-if="result" @click="exportXlsx">Export Excel</button>
          </div>
        </div>

        <div class="history-focus" v-if="activeHistoryRecord">
          Restored: #{{ activeHistoryRecord.id }} · {{ activeHistoryRecord.sourceType }} ·
          {{ formatDate(activeHistoryRecord.createdAt) }}
        </div>

        <div class="result-window" v-if="result" ref="resultWindowRef">
          <div class="artifact" v-if="result.prompt?.version || result.data?.model">
            <p><b>Prompt Version:</b> {{ result.prompt?.version || "unknown" }}</p>
            <p><b>Model:</b> {{ result.data?.model || "unknown" }}</p>
          </div>

          <div class="metrics">
            <div class="metric">
              <span>Quality Score</span>
              <strong>{{ reviewSummary.qualityScore }}</strong>
            </div>
            <div class="metric">
              <span>Structured Requirements</span>
              <strong>{{ reviewSummary.requirements }}</strong>
            </div>
            <div class="metric">
              <span>Coverage Items</span>
              <strong>{{ reviewSummary.coverage }}</strong>
            </div>
            <div class="metric">
              <span>Risk Items</span>
              <strong>{{ reviewSummary.risks }}</strong>
            </div>
            <div class="metric">
              <span>Test Cases</span>
              <strong>{{ reviewSummary.testcases }}</strong>
            </div>
            <div class="metric">
              <span>Design Methods</span>
              <strong>{{ reviewSummary.methods }}</strong>
            </div>
            <div class="metric" v-if="timingDisplay">
              <span>Engine Time (NFR)</span>
              <strong>{{ timingDisplay.engineMs }} ms</strong>
            </div>
            <div class="metric" v-if="timingDisplay">
              <span>Total Time</span>
              <strong>{{ timingDisplay.totalMs }} ms</strong>
            </div>
          </div>
          <p class="msg timing-note" v-if="timingDisplay">
            Engine {{ timingDisplay.engineMeetsNfr ? "meets" : "exceeds" }} 2s NFR target (LLM adds {{ timingDisplay.llmMs || 0 }} ms).
          </p>

          <div class="engine-panel" v-if="result.engineMetadata?.engineVersion || result.artifacts?.engineMetadata?.engineVersion">
            <h3>Deterministic FR Engines</h3>
            <p class="msg">
              {{ result.engineMetadata?.engineVersion || result.artifacts?.engineMetadata?.engineVersion }}
              · {{ result.engineMetadata?.caseCount || result.artifacts?.engineMetadata?.caseCount || 0 }} engine cases
              · channel: {{ result.engineMetadata?.parseChannel || result.artifacts?.engineMetadata?.parseChannel || "-" }}
            </p>
            <ul class="engine-list" v-if="result.engineMetadata?.frEngines || result.artifacts?.engineMetadata?.frEngines">
              <li v-for="(value, key) in (result.engineMetadata?.frEngines || result.artifacts?.engineMetadata?.frEngines)" :key="key">
                <b>{{ key }}</b>: {{ value || "—" }}
              </li>
            </ul>
          </div>

          <div class="assignment-panel" v-if="result.assignmentCompliance?.items?.length">
            <div class="panel-head compact">
              <h2>Assignment2 Compliance</h2>
              <span class="badge">Required Coverage {{ result.assignmentCompliance.requiredScore }}</span>
            </div>
            <div class="assignment-grid">
              <span
                v-for="item in result.assignmentCompliance.items"
                :key="item.id"
                class="compliance-pill"
                :class="{ passed: item.passed }"
                :title="item.evidence"
              >
                {{ item.passed ? "Covered" : "Needs Work" }} · {{ item.id }} {{ item.label }}
              </span>
            </div>
          </div>

          <div class="chips" v-if="markdownStats?.coveredMethods?.length">
            <span v-for="method in markdownStats.coveredMethods" :key="method" class="chip ok">{{ method }}</span>
          </div>
          <div class="chips" v-if="markdownStats?.missingMethods?.length">
            <span v-for="method in markdownStats.missingMethods" :key="method" class="chip warn">Missing {{ method }}</span>
          </div>

          <details class="collapsible" v-if="markdownPreviewHtml" :open="!rawIsJson">
            <summary>Raw LLM Output</summary>
            <div class="markdown-body" v-html="markdownPreviewHtml"></div>
          </details>

          <details class="collapsible" v-if="hasArtifacts" open>
            <summary>Structured Artifacts and Risks</summary>
            <label>
              artifacts (JSON)
              <textarea v-model="reviewArtifactsText" rows="8"></textarea>
            </label>
          </details>

          <details class="collapsible" v-if="hasArtifacts" open>
            <summary>Coverage Items (one per line)</summary>
            <label>
              coverageItems
              <textarea v-model="reviewCoverageText" rows="5" placeholder="姿态分析接口&#10;状态迁移"></textarea>
            </label>
          </details>

          <details class="collapsible" v-if="hasArtifacts" open>
            <summary>Test Strategies (ISO 29119-4 mapping)</summary>
            <label>
              testStrategies (JSON)
              <textarea v-model="reviewStrategiesText" rows="6"></textarea>
            </label>
          </details>

          <details class="collapsible" v-if="hasTestcases" open>
            <summary>Test Cases (table + JSON)</summary>
            <div class="review-toggle">
              <button class="ghost" :class="{ active: reviewViewMode === 'table' }" @click="reviewViewMode = 'table'">Table</button>
              <button class="ghost" :class="{ active: reviewViewMode === 'json' }" @click="reviewViewMode = 'json'">JSON</button>
            </div>
            <div class="case-table-wrap" v-if="reviewViewMode === 'table' && reviewTableCases.length">
              <table class="case-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Method</th>
                    <th>Title</th>
                    <th>Priority</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, index) in reviewTableCases" :key="row.id || index">
                    <td><input :value="row.id" @input="updateCaseField(index, 'id', $event.target.value)" /></td>
                    <td><input :value="row.designMethod" @input="updateCaseField(index, 'designMethod', $event.target.value)" /></td>
                    <td><input :value="row.title" @input="updateCaseField(index, 'title', $event.target.value)" /></td>
                    <td><input :value="row.priority" @input="updateCaseField(index, 'priority', $event.target.value)" /></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <label v-show="reviewViewMode === 'json'">
              testcases (JSON)
              <textarea v-model="reviewTestcasesText" rows="10"></textarea>
            </label>
          </details>

          <details class="collapsible" v-if="hasTraceability">
            <summary>Traceability</summary>
            <label>
              traceability
              <textarea v-model="reviewTraceabilityText" rows="6"></textarea>
            </label>
          </details>

          <div class="review-actions" v-if="result">
            <p class="msg">Edit JSON directly, then click Apply Changes to update this session.</p>
            <p class="msg" v-if="reviewError">{{ reviewError }}</p>
            <button class="primary" @click="applyReviewEdits">Apply Changes</button>
          </div>
        </div>

        </article>

        <article class="panel result empty-result" v-else>
          <div>
            <p class="eyebrow">Result Workspace</p>
            <h2>Waiting for Test Design</h2>
            <p class="msg">Upload LLM_CONTEXT.md or enter requirements, then click Generate Test Design. After generation, this area shows quality metrics, structured artifacts, test cases, and editable review panels.</p>
          </div>
        </article>
      </section>
    </section>

    <div class="history-modal" v-if="showHistoryModal" @click.self="closeHistoryModal">
      <section class="history-dialog panel">
        <div class="panel-head">
          <h2>History</h2>
          <div class="panel-tools">
            <button class="ghost small-btn" :disabled="historyLoading" @click="loadHistory()">
              {{ historyLoading ? "Refreshing..." : "Refresh" }}
            </button>
            <button class="ghost small-btn" @click="closeHistoryModal">Close</button>
          </div>
        </div>
        <p class="msg">{{ historyRecords.length }} records total. Click View Details to restore.</p>

        <div class="history-list" v-if="historyRecords.length">
          <article
            class="history-item"
            :class="{ active: activeHistoryRecord?.id === item.id }"
            v-for="item in historyRecords"
            :key="item.id"
          >
            <header>
              <h3>#{{ item.id }} · {{ item.sourceType }} · {{ item.modelName }}</h3>
              <span class="badge">{{ formatDate(item.createdAt) }}</span>
            </header>
            <p><b>Summary:</b> {{ item.sourceSummary || "-" }}</p>
            <div class="history-actions">
              <button class="ghost" @click="viewHistory(item)">View Details</button>
              <button
                class="ghost danger"
                :disabled="deletingHistoryId === item.id"
                @click="deleteHistory(item)"
              >
                {{ deletingHistoryId === item.id ? "Deleting..." : "Delete" }}
              </button>
            </div>
          </article>
        </div>

        <p class="msg" v-else>No history yet. Generate test cases first.</p>
      </section>
    </div>

  </main>
</template>
