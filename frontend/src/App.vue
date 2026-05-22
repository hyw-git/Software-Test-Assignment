<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import DOMPurify from "dompurify";
import { marked } from "marked";

const sourceType = ref("requirements");
const result = ref(null);
const qraResult = ref(null);
const loading = ref(false);
const qraLoading = ref(false);
const whiteboxLoading = ref(false);
const status = ref("Import files and configure the prompt to generate black-box test Markdown.");
const historyRecords = ref([]);
const historyLoading = ref(false);
const deletingHistoryId = ref(null);
const activeHistoryRecord = ref(null);
const uploadedDocs = ref([]);
const chatPrompt = ref("");
const fileInputRef = ref(null);
const whiteboxFileInputRef = ref(null);
const resultWindowRef = ref(null);
const resultScrollTop = ref(0);
const showSettings = ref(false);
const showHistoryModal = ref(false);
const pendingRequirementDelete = ref(null);
const includeWhitebox = ref(true);
const includeOracle = ref(true);
const includeOptimization = ref(true);
const whiteboxDescription = ref("");
const coverageCriterion = ref("all-states");
const whiteboxCoverageCriterion = ref("statement+branch");
const whiteboxSourceMode = ref("manual");
const whiteboxCoverageSelection = ref({});
const manualWhiteboxCoverageItems = ref([]);
const manualWhiteboxCoverageTarget = ref("");
const BLACKBOX_TECHNIQUE_OPTIONS = [
  { id: "EP", label: "EP", description: "Equivalence Partitioning", prompt: "Focus on valid and invalid equivalence classes for each input domain." },
  { id: "BVA", label: "BVA", description: "Boundary Value Analysis", prompt: "Focus on min-1, min, min+1 and max boundary clusters under the single fault assumption." },
  { id: "DecisionTable", label: "Decision Table", description: "Business rule combinations", prompt: "Extract condition/action rules and cover each meaningful rule row." },
  { id: "Combinatorial", label: "Pairwise", description: "Combinatorial interaction coverage", prompt: "Extract factors and representative levels, then generate pairwise combinations." },
  { id: "StateTransition", label: "State Transition", description: "State model paths", prompt: "Extract states and valid transitions, then cover the selected transition criterion." }
];
const FITNESS_TECHNIQUE_PROMPT_SAMPLES = {
  EP: "Use Equivalence Partitioning for FitnessAI. Identify valid and invalid classes for exerciseType, landmarks length/shape, difficulty, skipRest, count, durationSeconds, weightKg, durationHours, and exerciseType used by calorie calculation. Prefer one representative positive case and one representative negative case per important class, and link each case to the related REQ id.",
  BVA: "Use Boundary Value Analysis for FitnessAI numeric and size constraints. Cover landmarks.length around 33 with 32, 33, 34; count around 3 with 2, 3, 4; durationSeconds around 30 with 29, 30, 31; weightKg around [30, 200] with 29, 30, 31, 199, 200, 201; and durationHours around >0 with 0, a small positive value, and a normal positive value. Mark expected HTTP status and validation messages where relevant.",
  DecisionTable: "Use Decision Table testing for FitnessAI business rules. Build rule coverage for workout record saving: count < 3, count >= 3, durationSeconds < 30, durationSeconds >= 30, with the expected action saved/not saved. Also include training plan difficulty validity and skipRest behavior as condition/action combinations when useful.",
  Combinatorial: "Use pairwise combinatorial testing for FitnessAI. Treat exerciseType, difficulty, skipRest, record-save classification, and representative input validity as factors. Generate a compact pairwise suite that avoids impossible combinations, keeps expected outcomes explicit, and prioritizes interactions that affect pose analysis, plan mode, record saving, and dashboard analytics.",
  StateTransition: "Use State Transition testing for FitnessAI repetition counting. Model states UP, DESCENDING, DOWN, ASCENDING, and completed cycle. Cover the valid UP->DESCENDING->DOWN->ASCENDING->UP path, invalid short paths such as UP->DESCENDING->UP, repeated/duplicate frames, and cooldown behavior after a completed rep. Include expected count changes for each transition sequence."
};
const selectedTechniques = ref(BLACKBOX_TECHNIQUE_OPTIONS.map((item) => item.id));
const techniquePrompts = ref(Object.fromEntries(BLACKBOX_TECHNIQUE_OPTIONS.map((item) => [item.id, ""])));
const activeTechnique = ref("");
const reviewCoverageText = ref("");
const reviewStrategiesText = ref("");
const reviewTestcasesText = ref("");
const reviewTraceabilityText = ref("");
const reviewError = ref("");
const reviewViewMode = ref("table");
const reviewStrategiesViewMode = ref("table");
const reviewTraceabilityViewMode = ref("table");
const rawIsJson = ref(false);
const manualRequirementText = ref("");
const csvRequirementText = ref("");
const reviewedRequirements = ref([]);
const reviewedRisks = ref([]);
const requirementDraft = ref([]);
const riskDraft = ref([]);
const requirementReviewDirty = ref(false);
const riskReviewDirty = ref(false);
const activePrimaryTab = ref("qra");
const activeQraTab = ref("requirements");
const activeSummaryTab = ref("coverage");
const activeBlackboxTechnique = ref("EP");
const techniqueResults = ref({});
const whiteboxResult = ref(null);
const PRIMARY_TABS = [
  { id: "qra", label: "QRA", disabled: false },
  { id: "blackbox", label: "Black-Box Technique Test Design", disabled: false },
  { id: "whitebox", label: "White-Box Technique Test Design", disabled: false },
  { id: "summary", label: "Generated Results Summary", disabled: false }
];
const QRA_TABS = [
  { id: "requirements", label: "Structured Requirements" },
  { id: "risks", label: "Risk Items Review" }
];
const SUMMARY_TABS = [
  { id: "coverage", label: "Coverage Items" },
  { id: "strategies", label: "Test Strategies" },
  { id: "cases", label: "Test Cases" },
  { id: "enhancements", label: "LLM Enhancements" },
  { id: "traceability", label: "Traceability" }
];

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

const FITNESS_REQUIREMENT_SAMPLE = `FitnessAI System Requirements - Test Target

REQ-POSE-001: The pose analysis API (/api/analytics/pose) accepts two inputs:
  - exerciseType: one of SQUAT, PUSHUP, PLANK, JUMPING_JACK (valid); any other value is invalid.
  - landmarks: an array of exactly 33 MediaPipe Pose keypoints (valid range: 32-34);
    arrays with fewer than 32 or more than 34 points are invalid and must be rejected.
  Expected: returns JSON with count, score, feedback, state, angle fields; HTTP 200.
  Invalid input expected: HTTP 400 with descriptive error message.

REQ-POSE-002: Exercise repetition counting uses a finite state machine per exercise type.
  For SQUAT and PUSHUP, the valid state cycle is:
    UP -> DESCENDING -> DOWN -> ASCENDING -> UP  (count increments by 1 on completion)
  Invalid transitions (short-circuits) such as UP -> DESCENDING -> UP (skipping DOWN)
  must NOT increment the counter. Cooldown after each completed rep: 500 ms.

REQ-REC-001: Workout record saving applies the following filtering rule (logical AND):
  - If count < 3 AND durationSeconds < 30: the record is filtered out (not saved).
  - If count >= 3 OR durationSeconds >= 30: the record is saved to history.
  Boundary values: count boundary = 3; durationSeconds boundary = 30.

REQ-PLAN-001: Training plan mode supports three difficulty levels: easy, medium, hard.
  - easy:   3 sets x 8 reps, rest = 60 s between sets.
  - medium: 4 sets x 12 reps, rest = 45 s between sets.
  - hard:   5 sets x 15 reps, rest = 30 s between sets.
  Users may skip the rest interval (skipRest = true) to proceed to the next set immediately.
  Any difficulty value other than easy/medium/hard is invalid and must return HTTP 400.

REQ-DASH-001: The dashboard computes calorie burn using:
    calories = MET x weightKg x durationHours
  where MET values are: SQUAT=5.0, PUSHUP=3.8, PLANK=3.0, JUMPING_JACK=8.0.
  weightKg must be in range [30, 200] kg; durationHours must be > 0.
  Dashboard refreshes every 30 s and shows today's stats, weekly trends, and exercise distribution.`;

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
    patterns: [/equivalence\s*partition/i, /\bEP\b/i]
  },
  {
    name: "BVA",
    patterns: [/boundary\s*value/i, /\bBVA\b/i]
  },
  {
    name: "Combinatorial",
    patterns: [/combinatorial/i, /pairwise/i]
  },
  {
    name: "StateTransition",
    patterns: [/state\s*transition/i, /stateTransition/i]
  },
  {
    name: "DecisionTable",
    patterns: [/decision\s*table/i, /decisionTable/i]
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

  qraResult.value = {
    message: "QRA restored from history",
    artifacts: {
      requirementsStructured: record.structuredRequirements || [],
      riskItems: record.riskItems || []
    },
    engineMetadata: record.engineMetadata || {},
    timingMetrics: record.timingMetrics || {}
  };
  initQraReview(qraResult.value);

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

function openWhiteboxFilePicker() {
  whiteboxFileInputRef.value?.click();
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
  csvRequirementText.value = [
    "id,feature,input,condition,expected",
    "REQ-POSE-001,pose analysis,exerciseType+landmarks,exerciseType in [SQUAT;PUSHUP;PLANK;JUMPING_JACK] AND landmarks.length==33,HTTP 200 returns count/score/feedback/state/angle",
    "REQ-POSE-001-INV,pose analysis invalid input,exerciseType+landmarks,exerciseType=YOGA OR landmarks.length=32 OR landmarks.length=34,HTTP 400 returns explainable error",
    "REQ-POSE-002,state-machine counting,frameSequence+exerciseType,valid cycle: UP>DESCENDING>DOWN>ASCENDING>UP,count increments only after a complete cycle",
    "REQ-POSE-002-SC,state-machine short cycle,frameSequence,invalid: UP>DESCENDING>UP skips DOWN,count does not change",
    "REQ-REC-001,record filtering,count+durationSeconds,count<3 AND durationSeconds<30,record is not saved",
    "REQ-REC-001-SAVE,record saving,count+durationSeconds,count>=3 OR durationSeconds>=30,record is saved",
    "REQ-PLAN-001,training plan easy,difficulty+skipRest,difficulty=easy AND skipRest=false,3 sets x 8 reps rest 60s",
    "REQ-PLAN-001-MED,training plan medium,difficulty+skipRest,difficulty=medium AND skipRest=true,4 sets x 12 reps skip rest",
    "REQ-PLAN-001-HARD,training plan hard,difficulty+skipRest,difficulty=hard AND skipRest=false,5 sets x 15 reps rest 30s",
    "REQ-DASH-001,dashboard calories,weightKg+durationHours+exerciseType,weightKg in [30;200] AND durationHours>0,calories=MET*weightKg*durationHours"
  ].join("\n");
  chatPrompt.value = "FitnessAI is an intelligent fitness assistant with pose analysis, repetition counting, training plans, workout record filtering, and dashboard analytics.\n\n" +
    "Please generate test cases from the reviewed QRA requirements and risk items. Focus on API-level and business-flow behavior that can reveal validation errors, incorrect state counting, record filtering mistakes, invalid plan handling, and dashboard calculation defects.\n\n" +
    "Use clear test case titles, explicit input data, expected results/oracles, priority, and traceability to requirement or risk IDs. Keep the output suitable for manual review and later automation.";
  techniquePrompts.value = {
    ...techniquePrompts.value,
    ...FITNESS_TECHNIQUE_PROMPT_SAMPLES
  };
  status.value = "FitnessAI sample requirements loaded. Run QRA to review risks.";
}

function clearTextInputs() {
  manualRequirementText.value = "";
  csvRequirementText.value = "";
  status.value = "Cleared plain-text and CSV inputs.";
}

function cloneRiskItems(items) {
  return JSON.parse(JSON.stringify(Array.isArray(items) ? items : []));
}

function cloneRequirementItems(items) {
  return JSON.parse(JSON.stringify(Array.isArray(items) ? items : []));
}

function extractQraArtifacts(payload) {
  const artifacts = payload?.artifacts || payload?.data?.artifacts || payload?.data || payload || {};
  return {
    requirementsStructured: Array.isArray(artifacts.requirementsStructured) ? artifacts.requirementsStructured : [],
    riskItems: Array.isArray(artifacts.riskItems) ? artifacts.riskItems : []
  };
}

function initQraReview(payload) {
  const artifacts = extractQraArtifacts(payload);
  reviewedRequirements.value = artifacts.requirementsStructured;
  reviewedRisks.value = artifacts.riskItems;
  requirementDraft.value = cloneRequirementItems(artifacts.requirementsStructured);
  riskDraft.value = cloneRiskItems(artifacts.riskItems);
  requirementReviewDirty.value = false;
  riskReviewDirty.value = false;
}

function normalizeRequirementItem(item, index) {
  const inputFields = Array.isArray(item.inputFields)
    ? item.inputFields
    : Array.isArray(item.inputs)
      ? item.inputs
      : String(item.inputFields || item.input || item.inputs || "")
        .split(/[\n,]/)
        .map((value) => value.trim())
        .filter(Boolean);
  return {
    ...item,
    id: String(item.id || `REQ-EDIT-${String(index + 1).padStart(3, "0")}`).trim(),
    feature: String(item.feature || item.name || item.title || "").trim(),
    inputFields,
    expectedAction: String(item.expectedAction || item.expected || item.expectedResult || item.description || "").trim()
  };
}

function updateRequirementField(index, field, value) {
  const list = cloneRequirementItems(requirementDraft.value);
  if (!list[index]) {
    return;
  }
  if (field === "inputFields") {
    list[index].inputFields = String(value || "")
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean);
  } else {
    list[index][field] = value;
  }
  requirementDraft.value = list;
  requirementReviewDirty.value = true;
}

function addRequirementRow() {
  const list = cloneRequirementItems(requirementDraft.value);
  list.push({
    id: `REQ-EDIT-${String(list.length + 1).padStart(3, "0")}`,
    feature: "",
    inputFields: [],
    expectedAction: ""
  });
  requirementDraft.value = list;
  requirementReviewDirty.value = true;
}

function requestDeleteRequirementRow(index) {
  const row = requirementDraft.value[index];
  if (!row) {
    return;
  }
  const label = row?.id || row?.feature || `row ${index + 1}`;
  pendingRequirementDelete.value = { index, label };
}

function cancelDeleteRequirementRow() {
  pendingRequirementDelete.value = null;
}

function confirmDeleteRequirementRow() {
  const index = pendingRequirementDelete.value?.index;
  if (!Number.isInteger(index)) {
    pendingRequirementDelete.value = null;
    return;
  }
  const list = cloneRequirementItems(requirementDraft.value);
  if (!list[index]) {
    pendingRequirementDelete.value = null;
    return;
  }
  list.splice(index, 1);
  requirementDraft.value = list;
  requirementReviewDirty.value = true;
  pendingRequirementDelete.value = null;
}

function saveRequirementEdits() {
  reviewedRequirements.value = cloneRequirementItems(requirementDraft.value).map(normalizeRequirementItem);
  requirementDraft.value = cloneRequirementItems(reviewedRequirements.value);
  if (qraResult.value) {
    qraResult.value.artifacts = qraResult.value.artifacts || {};
    qraResult.value.artifacts.requirementsStructured = reviewedRequirements.value;
  }
  if (result.value?.artifacts) {
    result.value.artifacts.requirementsStructured = reviewedRequirements.value;
    result.value.assignmentCompliance = buildClientAssignmentCompliance(
      result.value,
      result.value.artifacts,
      result.value.data?.testcases || []
    );
  }
  requirementReviewDirty.value = false;
  status.value = "Structured requirements saved.";
}

function updateRiskField(index, field, value) {
  const list = cloneRiskItems(riskDraft.value);
  if (!list[index]) {
    return;
  }
  let nextValue = value;
  if (["impact", "likelihood"].includes(field)) {
    const parsed = Number(value);
    nextValue = Number.isNaN(parsed) ? value : Math.min(5, Math.max(1, parsed));
  }
  list[index][field] = nextValue;
  if (field === "impact" || field === "likelihood") {
    const impact = Number(list[index].impact) || 1;
    const likelihood = Number(list[index].likelihood) || 1;
    const riskScore = computeRiskScore(impact, likelihood);
    list[index].riskScore = riskScore;
    list[index].priority = priorityFromScore(riskScore);
  }
  riskDraft.value = list;
  riskReviewDirty.value = true;
}

function computeRiskScore(impact, likelihood) {
  const rawImpact = Number(impact);
  const rawLikelihood = Number(likelihood);
  if (Number.isNaN(rawImpact) || Number.isNaN(rawLikelihood)) {
    return 1;
  }
  return Math.max(1, Math.min(25, rawImpact * rawLikelihood));
}

function priorityFromScore(score) {
  const value = Number(score) || 0;
  if (value >= 16) return "high";
  if (value >= 9) return "medium";
  return "low";
}

function recalculateRiskScores() {
  const list = cloneRiskItems(riskDraft.value).map((item) => {
    const impact = Number(item.impact) || 1;
    const likelihood = Number(item.likelihood) || 1;
    const riskScore = computeRiskScore(impact, likelihood);
    return {
      ...item,
      impact,
      likelihood,
      riskScore,
      priority: priorityFromScore(riskScore)
    };
  });
  riskDraft.value = list;
  riskReviewDirty.value = true;
  status.value = "Risk scores recalculated. Save changes to apply.";
}

function saveRiskEdits() {
  reviewedRisks.value = cloneRiskItems(riskDraft.value).map((item) => {
    const impact = Number(item.impact) || 1;
    const likelihood = Number(item.likelihood) || 1;
    const riskScore = computeRiskScore(impact, likelihood);
    return {
      ...item,
      impact,
      likelihood,
      riskScore,
      priority: priorityFromScore(riskScore)
    };
  });
  riskDraft.value = cloneRiskItems(reviewedRisks.value);
  if (qraResult.value) {
    qraResult.value.artifacts = qraResult.value.artifacts || {};
    qraResult.value.artifacts.riskItems = reviewedRisks.value;
  }
  if (result.value?.artifacts) {
    result.value.artifacts.riskItems = reviewedRisks.value;
  }
  riskReviewDirty.value = false;
  status.value = "Risk review saved.";
}

async function runQra() {
  const hasDocuments = uploadedDocs.value.some((item) => String(item?.content || "").trim());
  const manualContent = buildManualContent();
  const hasManualInput = Boolean(String(manualRequirementText.value || "").trim() || String(csvRequirementText.value || "").trim());
  if (!hasDocuments && !hasManualInput) {
    status.value = "Please upload files or fill in plain-text/CSV requirements before running QRA.";
    return;
  }

  qraLoading.value = true;
  result.value = null;
  techniqueResults.value = {};
  whiteboxResult.value = null;
  whiteboxCoverageSelection.value = {};
  manualWhiteboxCoverageItems.value = [];
  activeHistoryRecord.value = null;
  reviewCoverageText.value = "";
  reviewStrategiesText.value = "";
  reviewTestcasesText.value = "";
  reviewTraceabilityText.value = "";
  activePrimaryTab.value = "qra";
  status.value = "Running QRA to structure requirements and score risks...";

  try {
    const response = await fetch("http://localhost:3000/api/qra", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sourceType: sourceType.value,
        content: manualContent,
        documents: uploadedDocs.value.map((item) => ({
          name: item.name,
          type: item.type,
          content: item.content
        }))
      })
    });
    const payload = await response.json();
    qraResult.value = response.ok ? payload : null;
    status.value = response.ok
      ? "QRA complete. Review and save risk edits before generating test cases."
      : `QRA failed: ${payload.detail || payload.message || "Please check inputs or service status."}`;
    if (response.ok) {
      initQraReview(payload);
      activePrimaryTab.value = "qra";
    }
  } catch (error) {
    qraResult.value = null;
    status.value = "QRA request failed. Please confirm the backend is running.";
  } finally {
    qraLoading.value = false;
  }
}

function getPayloadArtifacts(payload) {
  return payload?.artifacts || payload?.data?.artifacts || {};
}

function getPayloadTestcases(payload) {
  const cases = payload?.data?.testcases || payload?.testcases || [];
  return Array.isArray(cases) ? cases : [];
}

function testcaseKey(item) {
  const id = String(item?.id || item?.testcaseId || item?.caseId || "").trim();
  return id || JSON.stringify(item || {});
}

function uniqueArrayByJson(items) {
  const seen = new Set();
  const output = [];
  for (const item of Array.isArray(items) ? items : []) {
    const key = JSON.stringify(item);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    output.push(item);
  }
  return output;
}

function uniqueTestcases(items) {
  const seen = new Set();
  const output = [];
  for (const item of Array.isArray(items) ? items : []) {
    const key = testcaseKey(item);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    output.push(item);
  }
  return output;
}

function collectSummaryTiming() {
  const timing = { engineMs: 0, llmMs: 0, totalMs: 0, engineMeetsNfr: true };
  for (const payload of Object.values(techniqueResults.value || {})) {
    const itemTiming = payload?.timingMetrics || getPayloadArtifacts(payload)?.timingMetrics || {};
    timing.engineMs += Number(itemTiming.engineMs || 0);
    timing.llmMs += Number(itemTiming.llmMs || 0);
    timing.totalMs += Number(itemTiming.totalMs || 0);
    if (itemTiming.engineMeetsNfr === false) {
      timing.engineMeetsNfr = false;
    }
  }
  return timing;
}

function mergeSummaryArtifacts(existingArtifacts, incomingArtifacts, techniqueId, caseCount) {
  const existing = existingArtifacts && typeof existingArtifacts === "object" ? existingArtifacts : {};
  const incoming = incomingArtifacts && typeof incomingArtifacts === "object" ? incomingArtifacts : {};
  const arrayKeys = [
    "inputVariables",
    "equivalencePartitions",
    "boundaryValues",
    "decisionTableRules",
    "coverageItems",
    "testStrategies",
    "traceability",
    "testSequences",
    "llmEnhancedTestcases",
    "missingItems",
    "assumptions",
    "warnings"
  ];
  const artifacts = { ...existing, ...incoming };
  for (const key of arrayKeys) {
    artifacts[key] = uniqueArrayByJson([...(Array.isArray(existing[key]) ? existing[key] : []), ...(Array.isArray(incoming[key]) ? incoming[key] : [])]);
  }
  artifacts.requirementsStructured = reviewedRequirements.value.length
    ? reviewedRequirements.value
    : uniqueArrayByJson([...(Array.isArray(existing.requirementsStructured) ? existing.requirementsStructured : []), ...(Array.isArray(incoming.requirementsStructured) ? incoming.requirementsStructured : [])]);
  artifacts.riskItems = reviewedRisks.value.length
    ? reviewedRisks.value
    : uniqueArrayByJson([...(Array.isArray(existing.riskItems) ? existing.riskItems : []), ...(Array.isArray(incoming.riskItems) ? incoming.riskItems : [])]);
  artifacts.stateModel = {
    ...(existing.stateModel && typeof existing.stateModel === "object" ? existing.stateModel : {}),
    ...(incoming.stateModel && typeof incoming.stateModel === "object" ? incoming.stateModel : {})
  };
  artifacts.whiteboxAnalysis = {
    ...(existing.whiteboxAnalysis && typeof existing.whiteboxAnalysis === "object" ? existing.whiteboxAnalysis : {}),
    ...(incoming.whiteboxAnalysis && typeof incoming.whiteboxAnalysis === "object" ? incoming.whiteboxAnalysis : {})
  };
  artifacts.llmReadyWhiteboxContext = {
    ...(existing.llmReadyWhiteboxContext && typeof existing.llmReadyWhiteboxContext === "object" ? existing.llmReadyWhiteboxContext : {}),
    ...(incoming.llmReadyWhiteboxContext && typeof incoming.llmReadyWhiteboxContext === "object" ? incoming.llmReadyWhiteboxContext : {})
  };
  artifacts.testSuiteOptimization = {
    ...(existing.testSuiteOptimization && typeof existing.testSuiteOptimization === "object" ? existing.testSuiteOptimization : {}),
    ...(incoming.testSuiteOptimization && typeof incoming.testSuiteOptimization === "object" ? incoming.testSuiteOptimization : {})
  };

  const existingMeta = existing.engineMetadata || {};
  const incomingMeta = incoming.engineMetadata || {};
  const activatedTechniques = new Set([
    ...(Array.isArray(existingMeta.activatedTechniques) ? existingMeta.activatedTechniques : []),
    ...(Array.isArray(existingMeta.selectedTechniques) ? existingMeta.selectedTechniques : []),
    ...(Array.isArray(incomingMeta.activatedTechniques) ? incomingMeta.activatedTechniques : []),
    ...(Array.isArray(incomingMeta.selectedTechniques) ? incomingMeta.selectedTechniques : []),
    techniqueId
  ].filter(Boolean));
  artifacts.engineMetadata = {
    ...existingMeta,
    ...incomingMeta,
    pipelineVersion: incomingMeta.pipelineVersion || existingMeta.pipelineVersion || "generation-pipeline-ui-summary",
    activatedTechniques: Array.from(activatedTechniques),
    workerTimingMs: {
      ...(existingMeta.workerTimingMs || {}),
      ...(incomingMeta.workerTimingMs || {})
    },
    caseCount
  };
  return artifacts;
}

function archiveTechniquePayload(techniqueId, payload) {
  const previousPayload = techniqueResults.value[techniqueId];
  const previousCaseKeys = new Set(getPayloadTestcases(previousPayload).map(testcaseKey));
  techniqueResults.value = {
    ...techniqueResults.value,
    [techniqueId]: payload
  };

  const existingCases = getPayloadTestcases(result.value).filter((item) => !previousCaseKeys.has(testcaseKey(item)));
  const incomingCases = getPayloadTestcases(payload);
  const testcases = uniqueTestcases([...existingCases, ...incomingCases]);
  const artifacts = mergeSummaryArtifacts(result.value?.artifacts, getPayloadArtifacts(payload), techniqueId, testcases.length);
  const modelName = payload?.data?.model || result.value?.data?.model || "generation-pipeline";

  result.value = {
    ...(result.value || {}),
    message: "Generated results summary",
    technique: "black-box",
    artifacts,
    engineMetadata: artifacts.engineMetadata,
    timingMetrics: collectSummaryTiming(),
    prompt: {
      version: "generation-pipeline-summary",
      used: String(chatPrompt.value || "").trim()
    },
    data: {
      ...(result.value?.data || {}),
      model: modelName,
      testTechnique: "black-box",
      testcases
    }
  };
  result.value.assignmentCompliance = buildClientAssignmentCompliance(result.value, artifacts, testcases);
}

function normalizeWhiteboxPayload(payload) {
  const cases = getPayloadTestcases(payload).map((item, index) => ({
    ...(item || {}),
    id: item?.id || `TC-WBJ-${String(index + 1).padStart(3, "0")}`,
    technique: "white-box",
    designMethod: item?.designMethod || "WhiteBoxJava"
  }));
  const artifacts = payload?.artifacts || getPayloadArtifacts(payload);
  return {
    ...payload,
    data: {
      ...(payload?.data || {}),
      testcases: cases
    },
    artifacts: {
      ...artifacts,
      engineMetadata: {
        ...(artifacts?.engineMetadata || payload?.engineMetadata || {}),
        activatedTechniques: ["WhiteBoxJava"]
      }
    }
  };
}

function syncWhiteboxCoverageSelection(payload) {
  const coverage = getWhiteboxCoverageItems(payload);
  const next = { ...whiteboxCoverageSelection.value };
  for (const item of coverage) {
    if (!item?.id) {
      continue;
    }
    if (next[item.id] === undefined) {
      next[item.id] = item.selected !== false;
    }
  }
  whiteboxCoverageSelection.value = next;
}

function buildWhiteboxReviewerOverrides() {
  return {
    coverageItemSelection: { ...whiteboxCoverageSelection.value },
    manualCoverageItems: manualWhiteboxCoverageItems.value.map((item) => ({ ...item }))
  };
}

function addManualWhiteboxCoverageItem() {
  const target = String(manualWhiteboxCoverageTarget.value || "").trim();
  if (!target) {
    status.value = "Please enter a manual white-box coverage target first.";
    return;
  }
  const index = manualWhiteboxCoverageItems.value.length + 1;
  manualWhiteboxCoverageItems.value = [
    ...manualWhiteboxCoverageItems.value,
    {
      id: `COV-MANUAL-${String(index).padStart(3, "0")}`,
      type: "manual",
      methodId: whiteboxMethods.value[0]?.id || "",
      target,
      selected: true
    }
  ];
  manualWhiteboxCoverageTarget.value = "";
}

function removeManualWhiteboxCoverageItem(index) {
  manualWhiteboxCoverageItems.value = manualWhiteboxCoverageItems.value.filter((_item, itemIndex) => itemIndex !== index);
}

function archiveWhiteboxPayload(payload) {
  const normalized = normalizeWhiteboxPayload(payload);
  whiteboxResult.value = normalized;
  syncWhiteboxCoverageSelection(normalized);

  const existingCases = getPayloadTestcases(result.value).filter((item) => String(item?.technique || "") !== "white-box");
  const incomingCases = getPayloadTestcases(normalized);
  const testcases = uniqueTestcases([...existingCases, ...incomingCases]);
  const artifacts = mergeSummaryArtifacts(result.value?.artifacts, getPayloadArtifacts(normalized), "WhiteBox", testcases.length);
  artifacts.stateModel = getPayloadArtifacts(normalized).stateModel || artifacts.stateModel || {};

  result.value = {
    ...(result.value || {}),
    message: "Generated results summary",
    technique: "mixed",
    artifacts,
    engineMetadata: artifacts.engineMetadata,
    timingMetrics: normalized?.timingMetrics || result.value?.timingMetrics || {},
    prompt: {
      version: "generation-pipeline-summary",
      used: String(chatPrompt.value || "").trim()
    },
    data: {
      ...(result.value?.data || {}),
      model: normalized?.data?.model || result.value?.data?.model || "generation-pipeline",
      testTechnique: "mixed",
      testcases
    }
  };
  result.value.assignmentCompliance = buildClientAssignmentCompliance(result.value, artifacts, testcases);
}

async function generateWhiteboxTestcases() {
  if (qraResult.value && requirementReviewDirty.value) {
    status.value = "Please save structured requirement edits before generating white-box test cases.";
    activePrimaryTab.value = "qra";
    activeQraTab.value = "requirements";
    return;
  }
  if (qraResult.value && riskReviewDirty.value) {
    status.value = "Please save risk edits before generating white-box test cases.";
    activePrimaryTab.value = "qra";
    activeQraTab.value = "risks";
    return;
  }

  const whiteboxSnippet = String(whiteboxDescription.value || "").trim();
  const codeDocs = whiteboxCodeDocs.value;
  const useFileSource = whiteboxSourceMode.value === "file";
  const hasWhiteboxSource = useFileSource
    ? codeDocs.some((item) => String(item?.content || "").trim())
    : Boolean(whiteboxSnippet);
  if (!hasWhiteboxSource) {
    status.value = useFileSource
      ? "Please upload at least one .java source file before generating."
      : "Please paste a Java source snippet before generating.";
    return;
  }

  whiteboxLoading.value = true;
  activeHistoryRecord.value = null;
  status.value = "Analyzing Java control flow and generating white-box sequences...";
  try {
    const promptText = String(chatPrompt.value || "").trim();
    const response = await fetch("http://localhost:3000/api/testcases/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sourceType: "codebase",
        content: useFileSource ? "" : whiteboxSnippet,
        promptMode: promptText ? "custom" : "default",
        customPrompt: promptText,
        documents: (useFileSource ? codeDocs : []).map((item) => ({
          name: item.name,
          type: item.type,
          content: item.content
        })),
        requirementsStructured: reviewedRequirements.value,
        riskItems: reviewedRisks.value,
        testTechnique: "white-box",
        selectedTechniques: ["WhiteBoxJava"],
        techniquePrompts: {},
        reviewerOverrides: buildWhiteboxReviewerOverrides(),
        includeWhitebox: true,
        includeOracle: false,
        includeOptimization: false,
        whiteboxDescription: useFileSource ? "" : whiteboxSnippet,
        coverageCriterion: whiteboxCoverageCriterion.value
      })
    });
    const payload = await response.json();
    status.value = response.ok
      ? "White-box generation complete"
      : `White-box generation failed: ${payload.detail || payload.message || "Please check inputs or service status."}`;
    if (response.ok) {
      archiveWhiteboxPayload(payload);
      syncReviewFromResult();
      activePrimaryTab.value = "whitebox";
      await loadHistory();
    }
  } catch (error) {
    status.value = "White-box request failed. Please confirm the backend is running.";
  } finally {
    whiteboxLoading.value = false;
  }
}

async function generateTestcases(techniqueId) {
  if (!qraResult.value) {
    status.value = "Run QRA first to review requirements and risks.";
    return;
  }
  if (requirementReviewDirty.value) {
    status.value = "Please save structured requirement edits before generating test cases.";
    activePrimaryTab.value = "qra";
    activeQraTab.value = "requirements";
    return;
  }
  if (riskReviewDirty.value) {
    status.value = "Please save risk edits before generating test cases.";
    activePrimaryTab.value = "qra";
    activeQraTab.value = "risks";
    return;
  }

  const hasDocuments = uploadedDocs.value.some((item) => String(item?.content || "").trim());
  const manualContent = buildManualContent();
  const hasManualInput = Boolean(String(manualRequirementText.value || "").trim() || String(csvRequirementText.value || "").trim());
  if (!hasDocuments && !hasManualInput) {
    status.value = "Please upload files or fill in plain-text/CSV requirements before generating.";
    return;
  }
  const selected = techniqueId ? [techniqueId] : selectedTechniques.value;
  if (!selected.length) {
    status.value = "Choose a black-box test design technique.";
    return;
  }

  loading.value = true;
  activeTechnique.value = selected[0] || "";
  activeHistoryRecord.value = null;
  const promptText = String(chatPrompt.value || "").trim();
  status.value = `Generating ${selected.join(", ")} test cases...`;

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
        requirementsStructured: reviewedRequirements.value,
        riskItems: reviewedRisks.value,
        testTechnique: "black-box",
        selectedTechniques: selected,
        techniquePrompts: Object.fromEntries(
          selected.map((id) => [id, String(techniquePrompts.value[id] || "").trim()]).filter(([, value]) => value)
        ),
        includeWhitebox: includeWhitebox.value,
        includeOracle: includeOracle.value,
        includeOptimization: includeOptimization.value,
        whiteboxDescription: String(whiteboxDescription.value || "").trim(),
        coverageCriterion: coverageCriterion.value
      })
    });
    const payload = await response.json();
    status.value = response.ok
      ? `${selected.join(", ")} generation complete`
      : `Generation failed: ${payload.detail || payload.message || "Please check inputs or service status."}`;
    if (response.ok) {
      activeBlackboxTechnique.value = selected[0] || activeBlackboxTechnique.value;
      archiveTechniquePayload(selected[0], payload);
      syncReviewFromResult();
      activePrimaryTab.value = "blackbox";
      await loadHistory();
    }
  } catch (error) {
    status.value = "Request failed. Please confirm the backend is running.";
  } finally {
    loading.value = false;
    activeTechnique.value = "";
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
    const label = item.label || item.name || item.id || item.feature || item.coverageItem || item.description || item.target;
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
    testSequences: pickNonEmptyArray(parsed.testSequences, api.testSequences),
    llmEnhancedTestcases: pickNonEmptyArray(parsed.llmEnhancedTestcases, api.llmEnhancedTestcases),
    missingItems: pickNonEmptyArray(parsed.missingItems, api.missingItems),
    assumptions: pickNonEmptyArray(parsed.assumptions, api.assumptions),
    warnings: pickNonEmptyArray(parsed.warnings, api.warnings),
    whiteboxAnalysis:
      parsed.whiteboxAnalysis && Object.keys(parsed.whiteboxAnalysis).length
        ? parsed.whiteboxAnalysis
        : api.whiteboxAnalysis || {},
    llmReadyWhiteboxContext:
      parsed.llmReadyWhiteboxContext && Object.keys(parsed.llmReadyWhiteboxContext).length
        ? parsed.llmReadyWhiteboxContext
        : api.llmReadyWhiteboxContext || {},
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
      whiteboxAnalysis: parsed?.whiteboxAnalysis || {},
      testSuiteOptimization: parsed?.testSuiteOptimization || {},
      testSequences: parsed?.testSequences || [],
      llmEnhancedTestcases: parsed?.llmEnhancedTestcases || [],
      llmReadyWhiteboxContext: parsed?.llmReadyWhiteboxContext || {},
      testStrategies: parsed?.testStrategies || [],
      traceability: parsed?.traceability || [],
      missingItems: parsed?.missingItems || [],
      assumptions: parsed?.assumptions || [],
      warnings: parsed?.warnings || []
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

const reviewTableStrategies = computed(() => {
  try {
    return JSON.parse(reviewStrategiesText.value || "[]");
  } catch (_error) {
    return [];
  }
});

const reviewTableTraceability = computed(() => {
  try {
    return JSON.parse(reviewTraceabilityText.value || "[]");
  } catch (_error) {
    return [];
  }
});

const requirementsTableRows = computed(() => (Array.isArray(requirementDraft.value) ? requirementDraft.value : []));

const riskTableRows = computed(() => (Array.isArray(riskDraft.value) ? riskDraft.value : []));

const qraSummary = computed(() => {
  const timing = qraResult.value?.timingMetrics || null;
  return {
    requirements: requirementsTableRows.value.length,
    risks: riskTableRows.value.length,
    timing
  };
});

const timingDisplay = computed(() => result.value?.timingMetrics || result.value?.artifacts?.timingMetrics || null);
const pipelineMetadata = computed(() => result.value?.engineMetadata || result.value?.artifacts?.engineMetadata || {});
const activeTechniqueOption = computed(() =>
  BLACKBOX_TECHNIQUE_OPTIONS.find((item) => item.id === activeBlackboxTechnique.value) || BLACKBOX_TECHNIQUE_OPTIONS[0]
);
const activeTechniqueResult = computed(() => techniqueResults.value[activeBlackboxTechnique.value] || null);
const activeTechniqueCases = computed(() => getPayloadTestcases(activeTechniqueResult.value));
const whiteboxArtifacts = computed(() => getPayloadArtifacts(whiteboxResult.value));
const whiteboxCodeDocs = computed(() =>
  uploadedDocs.value
    .map((item, index) => ({ ...item, sourceIndex: index }))
    .filter((item) => /\.java$/i.test(String(item?.name || "")) && String(item?.content || "").trim())
);
const whiteboxCodeCharCount = computed(() => whiteboxCodeDocs.value.reduce((acc, item) => acc + String(item.content || "").length, 0));
const whiteboxStateModel = computed(() => whiteboxArtifacts.value?.stateModel || {});
const whiteboxAnalysis = computed(() => whiteboxArtifacts.value?.whiteboxAnalysis || {});
const whiteboxClasses = computed(() => Array.isArray(whiteboxAnalysis.value?.classes) ? whiteboxAnalysis.value.classes : []);
const whiteboxMethods = computed(() => whiteboxClasses.value.flatMap((item) => Array.isArray(item.methods) ? item.methods.map((method) => ({ ...method, className: item.name })) : []));
const whiteboxCoverageItems = computed(() => getWhiteboxCoverageItems(whiteboxResult.value));
const selectedWhiteboxCoverageCount = computed(() => whiteboxCoverageItems.value.filter((item) => whiteboxCoverageSelection.value[item.id] !== false).length);
const whiteboxSequences = computed(() => Array.isArray(whiteboxArtifacts.value?.testSequences) ? whiteboxArtifacts.value.testSequences : []);
const whiteboxEnhancedTestcases = computed(() => Array.isArray(whiteboxArtifacts.value?.llmEnhancedTestcases) ? whiteboxArtifacts.value.llmEnhancedTestcases : []);
const whiteboxWarnings = computed(() => Array.isArray(whiteboxArtifacts.value?.warnings) ? whiteboxArtifacts.value.warnings : []);
const whiteboxCases = computed(() => getPayloadTestcases(whiteboxResult.value));
const summaryEnhancedTestcases = computed(() => {
  const artifacts = result.value?.artifacts || result.value?.data?.artifacts || {};
  return Array.isArray(artifacts?.llmEnhancedTestcases) ? artifacts.llmEnhancedTestcases : [];
});
const whiteboxTransitions = computed(() => Array.isArray(whiteboxStateModel.value?.transitions) ? whiteboxStateModel.value.transitions : []);
const whiteboxStates = computed(() => Array.isArray(whiteboxStateModel.value?.states) ? whiteboxStateModel.value.states : []);

function enhancedTitle(item) {
  return item?.naturalLanguageTitle || item?.testIntentSummary || item?.baseSequenceId || "LLM enhancement";
}

function enhancedList(item, field) {
  const value = item?.[field];
  return Array.isArray(value) ? value.filter((entry) => String(entry || "").trim()) : [];
}

function enhancementForSequence(sequenceId) {
  return whiteboxEnhancedTestcases.value.find((item) => String(item?.baseSequenceId || "") === String(sequenceId || "")) || null;
}

function enhancedNotes(item) {
  return [...enhancedList(item, "reviewerQuestions"), ...enhancedList(item, "reviewerWarnings")];
}

function getWhiteboxCoverageItems(payload) {
  const artifacts = getPayloadArtifacts(payload);
  const coverage = Array.isArray(artifacts?.coverageItems) ? artifacts.coverageItems : [];
  return coverage.filter((item) => item && typeof item === "object" && String(item.id || "").startsWith("COV-"));
}

function displayCaseValue(value) {
  if (Array.isArray(value)) {
    return value.map((item) => (typeof item === "object" ? JSON.stringify(item) : String(item))).join("\n");
  }
  if (value && typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }
  return String(value || "");
}

function displayCaseInputs(item) {
  return displayCaseValue(item?.inputData ?? item?.inputs ?? item?.input ?? item?.steps ?? "");
}

function displayCaseExpected(item) {
  return displayCaseValue(item?.expectedResult ?? item?.expected ?? item?.expectedOutput ?? "");
}

function updateTechniqueCaseField(index, field, value) {
  const techniqueId = activeBlackboxTechnique.value;
  const payload = techniqueResults.value[techniqueId];
  if (!payload) {
    return;
  }

  const cases = getPayloadTestcases(payload).map((item) => ({ ...(item || {}) }));
  if (!cases[index]) {
    return;
  }

  const oldKey = testcaseKey(cases[index]);
  if (field === "traceability") {
    cases[index][field] = String(value || "")
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean);
  } else {
    cases[index][field] = value;
  }

  const nextPayload = {
    ...payload,
    data: {
      ...(payload.data || {}),
      testcases: cases
    }
  };
  if (Array.isArray(payload.testcases)) {
    nextPayload.testcases = cases;
  }
  techniqueResults.value = {
    ...techniqueResults.value,
    [techniqueId]: nextPayload
  };

  if (result.value) {
    const updatedCase = cases[index];
    let replaced = false;
    const summaryCases = getPayloadTestcases(result.value).map((item) => {
      if (testcaseKey(item) !== oldKey) {
        return item;
      }
      replaced = true;
      return updatedCase;
    });
    if (!replaced) {
      summaryCases.push(updatedCase);
    }
    result.value.data = result.value.data || {};
    result.value.data.testcases = summaryCases;
    result.value.assignmentCompliance = buildClientAssignmentCompliance(result.value, result.value.artifacts || {}, summaryCases);
    reviewTestcasesText.value = JSON.stringify(summaryCases, null, 2);
  }
}

function updateWhiteboxCaseField(index, field, value) {
  if (!whiteboxResult.value) {
    return;
  }
  const cases = whiteboxCases.value.map((item) => ({ ...(item || {}) }));
  if (!cases[index]) {
    return;
  }
  const oldKey = testcaseKey(cases[index]);
  if (field === "traceability") {
    cases[index][field] = String(value || "")
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean);
  } else {
    cases[index][field] = value;
  }
  whiteboxResult.value = {
    ...whiteboxResult.value,
    data: {
      ...(whiteboxResult.value.data || {}),
      testcases: cases
    }
  };

  if (result.value) {
    const updatedCase = cases[index];
    const summaryCases = getPayloadTestcases(result.value).map((item) => (testcaseKey(item) === oldKey ? updatedCase : item));
    result.value.data = result.value.data || {};
    result.value.data.testcases = summaryCases;
    result.value.assignmentCompliance = buildClientAssignmentCompliance(result.value, result.value.artifacts || {}, summaryCases);
    reviewTestcasesText.value = JSON.stringify(summaryCases, null, 2);
  }
}

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
    "whiteboxAnalysis",
    "testSequences",
    "llmEnhancedTestcases",
    "llmReadyWhiteboxContext",
    "warnings",
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
    "whiteboxAnalysis",
    "testSequences",
    "llmEnhancedTestcases",
    "llmReadyWhiteboxContext",
    "warnings",
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

    if (/\bEP\b|equivalence/i.test(text)) methods.add("EP");
    if (/\bBVA\b|boundary/i.test(text)) methods.add("BVA");
    if (/combinatorial|pairwise/i.test(text)) methods.add("Combinatorial");
    if (/state\s*transition|stateTransition/i.test(text)) methods.add("StateTransition");
    if (/decision\s*table|decisionTable/i.test(text)) methods.add("DecisionTable");
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
    || /"requirementsStructured"|REQ-[A-Z0-9-]+/i.test(rawOutput);
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
    || /"coverageItems"|C-[A-Z0-9-]+|"traceability"/i.test(rawOutput);
  const hasStateModel = artifacts?.stateModel && Object.keys(artifacts.stateModel).length > 0;
  const hasJavaWhitebox = (artifacts?.whiteboxAnalysis && Object.keys(artifacts.whiteboxAnalysis).length > 0)
    || (Array.isArray(artifacts?.testSequences) && artifacts.testSequences.length > 0)
    || cases.some((item) => String(item?.designMethod || "") === "WhiteBoxJava");
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
    { id: "FR 4.0", label: "White-box modeling", passed: hasStateModel || hasJavaWhitebox, evidence: hasJavaWhitebox ? "Java statement/branch sequences" : (hasStateModel ? `State model; ${frEngines["FR4.0"] || ""}` : "No white-box model") },
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

function syncResultArtifacts(nextArtifacts = {}, nextTestcases) {
  if (!result.value) {
    return;
  }

  result.value.artifacts = {
    ...(result.value.artifacts || {}),
    ...nextArtifacts
  };

  if (Array.isArray(nextTestcases)) {
    result.value.data = result.value.data || {};
    result.value.data.testcases = nextTestcases;
  }

  result.value.assignmentCompliance = buildClientAssignmentCompliance(
    result.value,
    result.value.artifacts,
    result.value.data?.testcases || []
  );
}

function saveCoverageItems() {
  const artifacts = {
    coverageItems: String(reviewCoverageText.value || "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
  };
  syncResultArtifacts(artifacts);
  status.value = "Coverage items saved.";
}

function saveTestStrategies() {
  reviewError.value = "";
  try {
    const parsed = JSON.parse(reviewStrategiesText.value || "[]");
    const strategies = Array.isArray(parsed) ? parsed : [];
    syncResultArtifacts({ testStrategies: strategies });
    status.value = "Test strategies saved.";
  } catch (error) {
    reviewError.value = `Test strategies JSON parse failed: ${String(error)}`;
  }
}

function saveTestcasesOnly() {
  reviewError.value = "";
  try {
    const testcases = JSON.parse(reviewTestcasesText.value || "[]");
    if (!Array.isArray(testcases)) {
      throw new Error("testcases must be an array");
    }
    syncResultArtifacts({}, testcases);
    status.value = "Test cases saved.";
  } catch (error) {
    reviewError.value = `Test cases JSON parse failed: ${String(error)}`;
  }
}

function saveTraceability() {
  reviewError.value = "";
  try {
    const traceability = JSON.parse(reviewTraceabilityText.value || "[]");
    const parsed = Array.isArray(traceability) ? traceability : [];
    syncResultArtifacts({ traceability: parsed });
    status.value = "Traceability saved.";
  } catch (error) {
    reviewError.value = `Traceability JSON parse failed: ${String(error)}`;
  }
}

function applyReviewEdits() {
  reviewError.value = "";
  try {
    const testcases = JSON.parse(reviewTestcasesText.value || "[]");
    const traceability = JSON.parse(reviewTraceabilityText.value || "[]");
    const strategies = JSON.parse(reviewStrategiesText.value || "[]");
    const coverage = String(reviewCoverageText.value || "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    const artifacts = { ...(result.value?.artifacts || {}) };
    artifacts.coverageItems = coverage;
    artifacts.testStrategies = Array.isArray(strategies) ? strategies : [];
    artifacts.traceability = Array.isArray(traceability) ? traceability : [];
    if (reviewedRisks.value.length) {
      artifacts.riskItems = reviewedRisks.value;
    }
    if (reviewedRequirements.value.length) {
      artifacts.requirementsStructured = reviewedRequirements.value;
    }
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

function updateStrategyField(index, field, value) {
  try {
    const list = JSON.parse(reviewStrategiesText.value || "[]");
    if (!Array.isArray(list) || !list[index]) {
      return;
    }
    if (field === 'coverageItems' || field === 'linkedRequirements' || field === 'linkedTestcases') {
      list[index][field] = String(value || "")
        .split(",")
        .map(x => x.trim())
        .filter(Boolean);
    } else {
      list[index][field] = value;
    }
    reviewStrategiesText.value = JSON.stringify(list, null, 2);
  } catch (_error) {
    reviewError.value = "Failed to update strategy table.";
  }
}

function addStrategy() {
  try {
    const list = JSON.parse(reviewStrategiesText.value || "[]");
    list.push({
      id: `STR-${String(list.length + 1).padStart(3, '0')}`,
      method: "EP",
      name: "Equivalence Partitioning",
      isoRef: "ISO/IEC/IEEE 29119-4 鈥?equivalence partitioning",
      description: "",
      coverageItems: [],
      linkedRequirements: [],
      linkedTestcases: [],
      rationale: ""
    });
    reviewStrategiesText.value = JSON.stringify(list, null, 2);
  } catch (_error) {
    reviewError.value = "Failed to add strategy.";
  }
}

function deleteStrategy(index) {
  try {
    const list = JSON.parse(reviewStrategiesText.value || "[]");
    list.splice(index, 1);
    reviewStrategiesText.value = JSON.stringify(list, null, 2);
  } catch (_error) {
    reviewError.value = "Failed to delete strategy.";
  }
}

function updateTraceabilityField(index, field, value) {
  try {
    const list = JSON.parse(reviewTraceabilityText.value || "[]");
    if (!Array.isArray(list) || !list[index]) {
      return;
    }
    if (field === 'coverageItems' || field === 'testcases') {
      list[index][field] = String(value || "")
        .split(",")
        .map(x => x.trim())
        .filter(Boolean);
    } else {
      list[index][field] = value;
    }
    reviewTraceabilityText.value = JSON.stringify(list, null, 2);
  } catch (_error) {
    reviewError.value = "Failed to update traceability table.";
  }
}

function addTraceabilityRow() {
  try {
    const list = JSON.parse(reviewTraceabilityText.value || "[]");
    list.push({
      reqId: `REQ-NEW-${String(list.length + 1).padStart(3, '0')}`,
      coverageItems: [],
      testcases: []
    });
    reviewTraceabilityText.value = JSON.stringify(list, null, 2);
  } catch (_error) {
    reviewError.value = "Failed to add traceability mapping.";
  }
}

function deleteTraceabilityRow(index) {
  try {
    const list = JSON.parse(reviewTraceabilityText.value || "[]");
    list.splice(index, 1);
    reviewTraceabilityText.value = JSON.stringify(list, null, 2);
  } catch (_error) {
    reviewError.value = "Failed to delete traceability mapping.";
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

  const coverage = String(reviewCoverageText.value || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  artifacts = {
    ...artifacts,
    coverageItems: coverage,
    testStrategies: (() => {
      try {
        const parsed = JSON.parse(reviewStrategiesText.value || "[]");
        return Array.isArray(parsed) ? parsed : [];
      } catch (_error) {
        return artifacts.testStrategies || [];
      }
    })(),
    traceability: (() => {
      try {
        const parsed = JSON.parse(reviewTraceabilityText.value || "[]");
        return Array.isArray(parsed) ? parsed : [];
      } catch (_error) {
        return artifacts.traceability || [];
      }
    })(),
    riskItems: reviewedRisks.value.length ? reviewedRisks.value : (artifacts.riskItems || []),
    requirementsStructured: reviewedRequirements.value.length ? reviewedRequirements.value : (artifacts.requirementsStructured || [])
  };

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
  const enhanced = Array.isArray(artifacts?.llmEnhancedTestcases) ? artifacts.llmEnhancedTestcases : [];
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
    "## LLM enhanced white-box design",
    enhanced.length ? JSON.stringify(enhanced, null, 2) : "No LLM-enhanced white-box entries.",
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
  const artifacts = result.value?.artifacts || {};
  let testcases = [];
  let traceability = [];

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

  const coverage = String(reviewCoverageText.value || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  let strategies = [];
  try {
    const parsed = JSON.parse(reviewStrategiesText.value || "[]");
    strategies = Array.isArray(parsed) ? parsed : [];
  } catch (_error) {
    strategies = Array.isArray(artifacts?.testStrategies) ? artifacts.testStrategies : [];
  }

  const requirements = reviewedRequirements.value.length
    ? reviewedRequirements.value
    : (Array.isArray(artifacts?.requirementsStructured) ? artifacts.requirementsStructured : []);
  const risks = reviewedRisks.value.length
    ? reviewedRisks.value
    : (Array.isArray(artifacts?.riskItems) ? artifacts.riskItems : []);
  const methods = new Set((Array.isArray(testcases) ? testcases : []).map((item) => String(item?.designMethod || "")).filter(Boolean));

  return {
    requirements: requirements.length,
    coverage: coverage.length,
    strategies: strategies.length,
    risks: risks.length,
    testcases: Array.isArray(testcases) ? testcases.length : 0,
    enhancements: Array.isArray(artifacts?.llmEnhancedTestcases) ? artifacts.llmEnhancedTestcases.length : 0,
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
  return hasMeaningfulContent(result.value?.artifacts || result.value?.data?.artifacts || {});
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
                <option value="all-transition-pairs">1-switch Transition Pairs</option>
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
                  <option value="all-transition-pairs">1-switch Transition Pairs</option>
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
          <div class="generate-stack">
            <button class="primary generate-btn" :disabled="qraLoading || loading" @click="runQra">
              {{ qraLoading ? "Running QRA..." : "Run QRA" }}
            </button>
            <p class="msg">Run QRA first, edit risks, then generate one technique at a time below.</p>
          </div>
        </article>
      </aside>

      <section class="results-column">
        <nav class="primary-tabs" aria-label="Main workspace sections">
          <button
            v-for="tab in PRIMARY_TABS"
            :key="tab.id"
            class="primary-tab"
            :class="{ active: activePrimaryTab === tab.id }"
            :disabled="tab.disabled"
            @click="activePrimaryTab = tab.id"
          >
            {{ tab.label }}
          </button>
        </nav>

        <article class="panel technique-workbench" v-show="activePrimaryTab === 'blackbox'">
          <div class="panel-head">
            <div>
              <h2>Black-Box Technique Test Design</h2>
              <p class="msg">Select one technique, tune its prompt, and generate cases independently.</p>
            </div>
            <span class="badge">{{ Object.keys(techniqueResults).length }}/5 generated</span>
          </div>

          <div class="technique-locked" v-if="!qraResult">
            <p class="eyebrow">QRA Required</p>
            <h2>Run QRA first</h2>
            <p class="msg">The five black-box workers use reviewed requirements and risk items as their shared context.</p>
          </div>

          <div class="blackbox-tech-layout" v-else>
            <section class="blackbox-control-card">
              <div>
                <p class="eyebrow">Technique</p>
                <div class="technique-picker" aria-label="Black-box technique selector">
                  <button
                    v-for="technique in BLACKBOX_TECHNIQUE_OPTIONS"
                    :key="technique.id"
                    class="technique-pill"
                    :class="{ active: activeBlackboxTechnique === technique.id, complete: techniqueResults[technique.id] }"
                    @click="activeBlackboxTechnique = technique.id"
                  >
                    <strong>{{ technique.label }}</strong>
                    <span>{{ techniqueResults[technique.id] ? `${getPayloadTestcases(techniqueResults[technique.id]).length}` : "-" }}</span>
                  </button>
                </div>
                <p class="msg selected-technique-note">{{ activeTechniqueOption.description }}</p>
              </div>

              <label class="technical-prompt-box">
                Technical Prompt
                <textarea
                  v-model="techniquePrompts[activeTechniqueOption.id]"
                  :placeholder="activeTechniqueOption.prompt"
                  rows="9"
                ></textarea>
              </label>

              <div class="generate-box">
                <button
                  class="primary"
                  :disabled="loading || qraLoading || riskReviewDirty"
                  @click="generateTestcases(activeTechniqueOption.id)"
                >
                  {{ loading && activeTechnique === activeTechniqueOption.id ? "Generating..." : "Generate Test Cases" }}
                </button>
                <p class="msg" v-if="riskReviewDirty">Save QRA risk edits before generating.</p>
                <p class="msg" v-else>Successful output is archived into Generated Results Summary.</p>
              </div>
            </section>

            <section class="technique-result-card">
              <div class="technique-result-head">
                <div>
                  <h3>{{ activeTechniqueOption.label }} Result</h3>
                  <p class="msg">{{ activeTechniqueCases.length }} cases in this technique.</p>
                </div>
                <span class="badge">{{ activeTechniqueResult ? "Archived" : "Empty" }}</span>
              </div>

              <div class="technique-case-list" v-if="activeTechniqueCases.length">
                <article class="technique-case-card" v-for="(item, index) in activeTechniqueCases" :key="item.id || index">
                  <div class="technique-case-grid">
                    <label>
                      ID
                      <input :value="item.id" @input="updateTechniqueCaseField(index, 'id', $event.target.value)" />
                    </label>
                    <label>
                      Method
                      <input :value="item.designMethod || item.method || activeTechniqueOption.id" @input="updateTechniqueCaseField(index, 'designMethod', $event.target.value)" />
                    </label>
                    <label>
                      Priority
                      <input :value="item.priority" @input="updateTechniqueCaseField(index, 'priority', $event.target.value)" />
                    </label>
                  </div>
                  <label>
                    Title
                    <input :value="item.title || item.name" @input="updateTechniqueCaseField(index, 'title', $event.target.value)" />
                  </label>
                  <div class="technique-case-grid two">
                    <label>
                      Inputs / Steps
                      <textarea :value="displayCaseInputs(item)" rows="4" @input="updateTechniqueCaseField(index, 'inputData', $event.target.value)"></textarea>
                    </label>
                    <label>
                      Expected / Oracle
                      <textarea :value="displayCaseExpected(item)" rows="4" @input="updateTechniqueCaseField(index, 'expectedResult', $event.target.value)"></textarea>
                    </label>
                  </div>
                  <label>
                    Traceability
                    <input :value="Array.isArray(item.traceability) ? item.traceability.join(', ') : item.traceability" @input="updateTechniqueCaseField(index, 'traceability', $event.target.value)" />
                  </label>
                </article>
              </div>
              <div class="technique-empty" v-else>
                <p class="eyebrow">Result Display</p>
                <h3>No cases generated for this technique yet</h3>
                <p class="msg">Choose a technique on the left, adjust the prompt if needed, then generate.</p>
              </div>
            </section>
          </div>
        </article>

        <article class="panel result" v-show="activePrimaryTab === 'qra'">
          <div class="result-head">
            <div>
              <h2>QRA Review</h2>
              <p class="msg">Structured requirements and risk items ready for review.</p>
            </div>
            <div class="result-tools">
              <span class="badge">QRA</span>
            </div>
          </div>

          <div class="metrics">
            <div class="metric">
              <span>Requirements</span>
              <strong>{{ qraSummary.requirements }}</strong>
            </div>
            <div class="metric">
              <span>Risk Items</span>
              <strong>{{ qraSummary.risks }}</strong>
            </div>
            <div class="metric" v-if="qraSummary.timing">
              <span>Engine Time</span>
              <strong>{{ qraSummary.timing.engineMs }} ms</strong>
            </div>
          </div>

          <div class="inner-tabs">
            <button
              v-for="tab in QRA_TABS"
              :key="tab.id"
              class="inner-tab"
              :class="{ active: activeQraTab === tab.id }"
              @click="activeQraTab = tab.id"
            >
              {{ tab.label }}
            </button>
          </div>

          <section class="tab-pane" v-show="activeQraTab === 'requirements'">
            <div class="review-actions risk-review-actions compact-review-actions">
              <div class="risk-review-buttons">
                <button class="ghost small-btn" @click="addRequirementRow">Add Requirement</button>
                <button class="primary small-btn" @click="saveRequirementEdits">Save Changes</button>
              </div>
              <p class="msg" v-if="requirementReviewDirty">Unsaved requirement edits detected.</p>
              <p class="msg" v-else>All requirement edits saved.</p>
            </div>
            <div class="case-table-wrap expanded-table" v-if="requirementsTableRows.length">
              <table class="case-table requirements-edit-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Feature</th>
                    <th>Inputs</th>
                    <th>Expected</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, index) in requirementsTableRows" :key="row.id || index">
                    <td>
                      <input :value="row.id" @input="updateRequirementField(index, 'id', $event.target.value)" />
                    </td>
                    <td>
                      <input :value="row.feature || row.name || row.title" @input="updateRequirementField(index, 'feature', $event.target.value)" />
                    </td>
                    <td>
                      <textarea
                        rows="3"
                        :value="Array.isArray(row.inputFields || row.inputs) ? (row.inputFields || row.inputs).join(', ') : (row.inputFields || row.input || row.inputs || '')"
                        @input="updateRequirementField(index, 'inputFields', $event.target.value)"
                      ></textarea>
                    </td>
                    <td>
                      <textarea
                        rows="3"
                        :value="row.expectedAction || row.expected || row.expectedResult || row.description || ''"
                        @input="updateRequirementField(index, 'expectedAction', $event.target.value)"
                      ></textarea>
                    </td>
                    <td>
                      <button class="danger small-btn" @click="requestDeleteRequirementRow(index)">Delete</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p class="msg" v-else>No structured requirements returned.</p>
          </section>

          <section class="tab-pane" v-show="activeQraTab === 'risks'">
            <div class="review-actions risk-review-actions compact-review-actions">
              <div class="risk-review-buttons">
                <button class="ghost small-btn" @click="recalculateRiskScores">Recalculate</button>
                <button class="primary small-btn" @click="saveRiskEdits">Save Changes</button>
              </div>
              <p class="msg" v-if="riskReviewDirty">Unsaved edits detected.</p>
              <p class="msg" v-else>All edits saved.</p>
            </div>
            <div class="case-table-wrap expanded-table" v-if="riskTableRows.length">
              <table class="case-table risk-table">
                <thead>
                  <tr>
                    <th>Req ID</th>
                    <th>Impact</th>
                    <th>Likelihood</th>
                    <th>Risk Score</th>
                    <th>Priority</th>
                    <th>Rationale</th>
                    <th>Source</th>
                    <th>Matrix Ref</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, index) in riskTableRows" :key="row.reqId || index">
                    <td>{{ row.reqId }}</td>
                    <td><input type="number" min="1" max="5" :value="row.impact" @input="updateRiskField(index, 'impact', $event.target.value)" /></td>
                    <td><input type="number" min="1" max="5" :value="row.likelihood" @input="updateRiskField(index, 'likelihood', $event.target.value)" /></td>
                    <td><span class="readonly-metric">{{ row.riskScore }}</span></td>
                    <td><span class="badge readonly-badge">{{ String(row.priority || '').toUpperCase() }}</span></td>
                    <td><input :value="row.rationale" @input="updateRiskField(index, 'rationale', $event.target.value)" /></td>
                    <td><input :value="row.source" @input="updateRiskField(index, 'source', $event.target.value)" /></td>
                    <td><input :value="row.matrixRef" @input="updateRiskField(index, 'matrixRef', $event.target.value)" /></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p class="msg" v-else>No risk items returned.</p>
          </section>
        </article>

        <article class="panel technique-workbench" v-show="activePrimaryTab === 'whitebox'">
          <div class="panel-head">
            <div>
              <h2>White-Box Technique Test Design</h2>
              <p class="msg">Analyze Java methods, review coverage targets, and generate design-level test sequences.</p>
            </div>
            <span class="badge">{{ whiteboxCases.length }} cases</span>
          </div>

          <div class="whitebox-java-layout">
            <section class="blackbox-control-card whitebox-control-card">
              <div>
                <p class="eyebrow">Technique</p>
                <div class="whitebox-tech-card">
                  <strong>WhiteBoxJava</strong>
                  <span>Java method CFG + statement/branch coverage</span>
                </div>
              </div>

              <div class="whitebox-compact-controls">
                <section class="whitebox-mini-card">
                  <p class="field-label">Coverage Criterion</p>
                  <select v-model="whiteboxCoverageCriterion">
                    <option value="statement">Statement Coverage</option>
                    <option value="branch">Branch / Decision Coverage</option>
                    <option value="statement+branch">Statement + Branch Coverage</option>
                  </select>
                </section>

                <section class="whitebox-mini-card manual-criterion-card">
                  <div>
                    <p class="field-label">Manual Criterion</p>
                    <p class="msg">Optional reviewer-added target</p>
                  </div>
                  <div class="manual-criterion-row">
                    <input v-model="manualWhiteboxCoverageTarget" placeholder="Invalid password retry scenario" />
                    <button class="ghost small-btn" type="button" @click="addManualWhiteboxCoverageItem">Add</button>
                  </div>
                  <div class="manual-coverage-list compact" v-if="manualWhiteboxCoverageItems.length">
                    <span v-for="(item, index) in manualWhiteboxCoverageItems" :key="item.id">
                      {{ item.id }}
                      <button class="ghost mini" type="button" @click="removeManualWhiteboxCoverageItem(index)">Remove</button>
                    </span>
                  </div>
                </section>
              </div>

              <section class="whitebox-source-card">
                <div class="source-card-head">
                  <div>
                    <p class="field-label">Java Source Hint / Optional Snippet</p>
                    <p class="msg">Use a pasted Java snippet or upload one or more .java files.</p>
                  </div>
                  <div class="inner-tabs source-mode-toggle">
                    <button
                      class="inner-tab"
                      :class="{ active: whiteboxSourceMode === 'manual' }"
                      type="button"
                      @click="whiteboxSourceMode = 'manual'"
                    >
                      Manual Input
                    </button>
                    <button
                      class="inner-tab"
                      :class="{ active: whiteboxSourceMode === 'file' }"
                      type="button"
                      @click="whiteboxSourceMode = 'file'"
                    >
                      Upload File
                    </button>
                  </div>
                </div>

                <textarea
                  v-if="whiteboxSourceMode === 'manual'"
                  v-model="whiteboxDescription"
                  placeholder="Paste Java source here. Example: public class LoginService { public String login(...) { ... } }"
                  rows="12"
                ></textarea>

                <div v-else class="whitebox-upload-panel">
                  <input
                    ref="whiteboxFileInputRef"
                    class="hidden-file-input"
                    type="file"
                    multiple
                    accept=".java"
                    @change="onFileChange"
                  />
                  <div class="whitebox-upload-action">
                    <button class="ghost small-btn" type="button" @click="openWhiteboxFilePicker">Upload .java Files</button>
                    <p class="msg">{{ whiteboxCodeDocs.length }} Java files · {{ whiteboxCodeCharCount }} chars</p>
                  </div>
                  <div class="uploaded-box compact whitebox-file-list" v-if="whiteboxCodeDocs.length">
                    <ul class="uploaded-list compact">
                      <li v-for="item in whiteboxCodeDocs" :key="item.name + item.size + item.sourceIndex">
                        <span>{{ item.name }}</span>
                        <button class="ghost mini" type="button" @click="removeUploadedDoc(item.sourceIndex)">Remove</button>
                      </li>
                    </ul>
                  </div>
                  <p class="msg" v-else>No Java source file selected yet.</p>
                </div>
              </section>

              <div class="generate-box">
                <button
                  class="primary"
                  :disabled="whiteboxLoading || qraLoading || (qraResult && (requirementReviewDirty || riskReviewDirty))"
                  @click="generateWhiteboxTestcases"
                >
                  {{ whiteboxLoading ? "Generating..." : "Generate White-Box Sequences" }}
                </button>
                <p class="msg" v-if="qraResult && (requirementReviewDirty || riskReviewDirty)">Save QRA edits before generation.</p>
                <p class="msg" v-else>{{ whiteboxCoverageItems.length ? selectedWhiteboxCoverageCount : "All detected" }} coverage items selected.</p>
              </div>
            </section>

            <section class="technique-result-card whitebox-result-card">
              <div class="technique-result-head">
                <div>
                  <h3>Java Analysis Result</h3>
                  <p class="msg">{{ whiteboxMethods.length }} methods · {{ whiteboxCoverageItems.length }} coverage items · {{ whiteboxSequences.length }} sequences</p>
                </div>
                <span class="badge">{{ whiteboxResult ? "Archived" : "Empty" }}</span>
              </div>

              <div class="whitebox-warnings" v-if="whiteboxWarnings.length">
                <p v-for="(item, index) in whiteboxWarnings" :key="index">{{ item }}</p>
              </div>

              <div class="whitebox-result-scroll" v-if="whiteboxResult">
                <section class="whitebox-section" v-if="whiteboxMethods.length">
                  <p class="eyebrow">Methods</p>
                  <div class="whitebox-method-grid">
                    <article v-for="method in whiteboxMethods" :key="method.id" class="whitebox-method-card">
                      <strong>{{ method.className }}.{{ method.name }}</strong>
                      <span>{{ method.returnType }} · lines {{ method.startLine }}-{{ method.endLine }}</span>
                      <small>{{ (method.parameters || []).map((param) => `${param.type} ${param.name}`).join(", ") || "no parameters" }}</small>
                    </article>
                  </div>
                </section>

                <section class="whitebox-section" v-if="whiteboxCoverageItems.length">
                  <p class="eyebrow">Coverage Review</p>
                  <div class="coverage-review-list">
                    <label
                      v-for="item in whiteboxCoverageItems"
                      :key="item.id"
                      class="coverage-review-item"
                    >
                      <input
                        type="checkbox"
                        :checked="whiteboxCoverageSelection[item.id] !== false"
                        @change="whiteboxCoverageSelection = { ...whiteboxCoverageSelection, [item.id]: $event.target.checked }"
                      />
                      <span>
                        <strong>{{ item.id }} · {{ item.type }}</strong>
                        <small>{{ item.target }}</small>
                        <small>{{ item.location }}</small>
                      </span>
                    </label>
                  </div>
                </section>

                <section class="whitebox-section" v-if="whiteboxSequences.length">
                  <p class="eyebrow">Test Sequences</p>
                  <article class="sequence-card" v-for="sequence in whiteboxSequences" :key="sequence.id">
                    <div>
                      <strong>{{ sequence.id }} · {{ sequence.title }}</strong>
                      <span class="badge">{{ sequence.needsReview ? "Needs Review" : "Ready" }}</span>
                    </div>
                    <p class="msg">Targets: {{ (sequence.coverageTargets || []).join(", ") || "-" }}</p>
                    <p class="msg" v-if="enhancementForSequence(sequence.id)?.naturalLanguageTitle">
                      LLM title: {{ enhancementForSequence(sequence.id).naturalLanguageTitle }}
                    </p>
                    <pre>{{ JSON.stringify(sequence.inputHints || {}, null, 2) }}</pre>
                  </article>
                </section>

                <section class="whitebox-section" v-if="whiteboxEnhancedTestcases.length">
                  <p class="eyebrow">LLM Enhanced Test Design</p>
                  <article class="llm-enhancement-card" v-for="item in whiteboxEnhancedTestcases" :key="item.baseSequenceId">
                    <div class="enhancement-head">
                      <strong>{{ enhancedTitle(item) }}</strong>
                      <span class="badge">{{ item.baseSequenceId }}</span>
                    </div>
                    <p class="msg" v-if="item.testIntentSummary">{{ item.testIntentSummary }}</p>
                    <div class="enhancement-grid">
                      <div v-if="enhancedList(item, 'refinedInputSuggestions').length">
                        <span>Inputs</span>
                        <ul><li v-for="entry in enhancedList(item, 'refinedInputSuggestions')" :key="entry">{{ entry }}</li></ul>
                      </div>
                      <div v-if="enhancedList(item, 'refinedSetupSuggestions').length">
                        <span>Setup</span>
                        <ul><li v-for="entry in enhancedList(item, 'refinedSetupSuggestions')" :key="entry">{{ entry }}</li></ul>
                      </div>
                      <div v-if="enhancedList(item, 'refinedOracleSuggestions').length">
                        <span>Oracle</span>
                        <ul><li v-for="entry in enhancedList(item, 'refinedOracleSuggestions')" :key="entry">{{ entry }}</li></ul>
                      </div>
                    </div>
                    <details v-if="enhancedNotes(item).length">
                      <summary>Review notes</summary>
                      <ul>
                        <li v-for="entry in enhancedNotes(item)" :key="entry">{{ entry }}</li>
                      </ul>
                    </details>
                    <details v-if="item.promptPreview">
                      <summary>Prompt preview</summary>
                      <pre>{{ item.promptPreview }}</pre>
                    </details>
                  </article>
                </section>

                <section class="whitebox-section" v-if="whiteboxCases.length">
                  <p class="eyebrow">Editable Test Cases</p>
                  <div class="technique-case-list">
                    <article class="technique-case-card" v-for="(item, index) in whiteboxCases" :key="item.id || index">
                      <div class="technique-case-grid">
                        <label>
                          ID
                          <input :value="item.id" @input="updateWhiteboxCaseField(index, 'id', $event.target.value)" />
                        </label>
                        <label>
                          Method
                          <input :value="item.designMethod || 'WhiteBoxJava'" @input="updateWhiteboxCaseField(index, 'designMethod', $event.target.value)" />
                        </label>
                        <label>
                          Priority
                          <input :value="item.priority" @input="updateWhiteboxCaseField(index, 'priority', $event.target.value)" />
                        </label>
                      </div>
                      <label>
                        Title
                        <input :value="item.title || item.name" @input="updateWhiteboxCaseField(index, 'title', $event.target.value)" />
                      </label>
                      <div class="technique-case-grid two">
                        <label>
                          Inputs / Steps
                          <textarea :value="displayCaseInputs(item)" rows="4" @input="updateWhiteboxCaseField(index, 'inputData', $event.target.value)"></textarea>
                        </label>
                        <label>
                          Expected / Oracle
                          <textarea :value="displayCaseExpected(item)" rows="4" @input="updateWhiteboxCaseField(index, 'expectedResult', $event.target.value)"></textarea>
                        </label>
                      </div>
                      <label>
                        Traceability
                        <input :value="Array.isArray(item.traceability) ? item.traceability.join(', ') : item.traceability" @input="updateWhiteboxCaseField(index, 'traceability', $event.target.value)" />
                      </label>
                    </article>
                  </div>
                </section>
              </div>

              <div class="technique-empty" v-else>
                <p class="eyebrow">Java White-Box</p>
                <h3>No Java analysis yet</h3>
                <p class="msg">Upload a .java file or paste a Java method snippet, choose coverage, then generate.</p>
              </div>
            </section>
          </div>
        </article>

        <article class="panel result" v-show="activePrimaryTab === 'summary' && result">
        <div class="result-head">
          <div>
            <h2>Generated Results Summary</h2>
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
          <div class="artifact compact-artifact" v-if="result.prompt?.version || result.data?.model">
            <p><b>Prompt Version:</b> {{ result.prompt?.version || "unknown" }}</p>
            <p><b>Model:</b> {{ result.data?.model || "unknown" }}</p>
          </div>

          <div class="metrics compact-metrics">
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
              <span>LLM Enhancements</span>
              <strong>{{ reviewSummary.enhancements }}</strong>
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
          <p class="msg timing-note compact-note" v-if="timingDisplay">
            Engine {{ timingDisplay.engineMeetsNfr ? "meets" : "exceeds" }} 2s NFR target (LLM adds {{ timingDisplay.llmMs || 0 }} ms).
          </p>

          <details class="engine-panel compact-meta-panel" v-if="pipelineMetadata.engineVersion || pipelineMetadata.pipelineVersion">
            <summary>{{ pipelineMetadata.pipelineVersion ? "Generation Pipeline" : "Deterministic FR Engines" }}</summary>
            <p class="msg">
              {{ pipelineMetadata.pipelineVersion || pipelineMetadata.engineVersion }}
              · {{ pipelineMetadata.caseCount || 0 }} cases
              · active: {{ (pipelineMetadata.activatedTechniques || pipelineMetadata.selectedTechniques || []).join(", ") || "-" }}
            </p>
            <ul class="engine-list" v-if="pipelineMetadata.workerTimingMs">
              <li v-for="(value, key) in pipelineMetadata.workerTimingMs" :key="key">
                <b>{{ key }}</b>: {{ value }} ms
              </li>
            </ul>
            <ul class="engine-list" v-else-if="pipelineMetadata.frEngines">
              <li v-for="(value, key) in pipelineMetadata.frEngines" :key="key">
                <b>{{ key }}</b>: {{ value || "-" }}
              </li>
            </ul>
          </details>

          <details class="assignment-panel compact-meta-panel" v-if="result.assignmentCompliance?.items?.length">
            <summary>Assignment2 Compliance · Required Coverage {{ result.assignmentCompliance.requiredScore }}</summary>
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
          </details>

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

          <div class="inner-tabs summary-inner-tabs">
            <button
              v-for="tab in SUMMARY_TABS"
              :key="tab.id"
              class="inner-tab"
              :class="{ active: activeSummaryTab === tab.id }"
              @click="activeSummaryTab = tab.id"
            >
              {{ tab.label }}
            </button>
          </div>

          <section class="collapsible result-tab-pane" v-if="hasArtifacts" v-show="activeSummaryTab === 'coverage'">
            <h3 class="pane-title">Coverage Items</h3>
            <label>
              coverageItems
              <textarea v-model="reviewCoverageText" rows="5" placeholder="Pose analysis API&#10;State transition coverage"></textarea>
            </label>
            <div class="section-save-row">
              <button class="ghost small-btn" @click="saveCoverageItems">Save Coverage</button>
            </div>
          </section>

          <section class="collapsible result-tab-pane" v-if="hasArtifacts" v-show="activeSummaryTab === 'strategies'">
            <h3 class="pane-title">Test Strategies</h3>
            <div class="review-toggle">
              <button class="ghost" :class="{ active: reviewStrategiesViewMode === 'table' }" @click="reviewStrategiesViewMode = 'table'">Table</button>
              <button class="ghost" :class="{ active: reviewStrategiesViewMode === 'json' }" @click="reviewStrategiesViewMode = 'json'">JSON</button>
            </div>

            <div class="case-table-wrap" v-if="reviewStrategiesViewMode === 'table' && reviewTableStrategies.length">
              <table class="case-table">
                <thead>
                  <tr>
                    <th style="width: 100px;">ID</th>
                    <th style="width: 130px;">Method</th>
                    <th style="width: 150px;">Name</th>
                    <th style="width: 200px;">ISO Ref</th>
                    <th>Rationale</th>
                    <th style="width: 80px;">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <template v-for="(row, index) in reviewTableStrategies" :key="row.id || index">
                    <tr>
                      <td><input :value="row.id" @input="updateStrategyField(index, 'id', $event.target.value)" /></td>
                      <td>
                        <select :value="row.method" @change="updateStrategyField(index, 'method', $event.target.value)">
                          <option value="EP">EP</option>
                          <option value="BVA">BVA</option>
                          <option value="DecisionTable">DecisionTable</option>
                          <option value="Combinatorial">Combinatorial</option>
                          <option value="StateTransition">StateTransition</option>
                        </select>
                      </td>
                      <td><input :value="row.name" @input="updateStrategyField(index, 'name', $event.target.value)" /></td>
                      <td><input :value="row.isoRef" @input="updateStrategyField(index, 'isoRef', $event.target.value)" /></td>
                      <td><input :value="row.rationale" @input="updateStrategyField(index, 'rationale', $event.target.value)" /></td>
                      <td>
                        <button class="ghost small-btn danger" style="min-height: 28px; padding: 2px 6px;" @click="deleteStrategy(index)">Delete</button>
                      </td>
                    </tr>
                    <tr class="detail-row" style="background: rgba(45, 124, 246, 0.03);">
                      <td colspan="6" style="padding: 8px 12px; border-bottom: 2px solid var(--line);">
                        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;">
                          <div>
                            <span style="font-size: 0.76rem; font-weight: 600; color: var(--muted); display: block;">Description:</span>
                            <textarea style="min-height: 48px; padding: 4px 8px; margin-top: 2px; border-radius: 6px;" :value="row.description" @input="updateStrategyField(index, 'description', $event.target.value)"></textarea>
                          </div>
                          <div>
                            <span style="font-size: 0.76rem; font-weight: 600; color: var(--muted); display: block;">Coverage Items (comma-separated):</span>
                            <input style="margin-top: 2px; padding: 6px 8px; border-radius: 6px;" :value="Array.isArray(row.coverageItems) ? row.coverageItems.join(', ') : ''" @input="updateStrategyField(index, 'coverageItems', $event.target.value)" />
                          </div>
                          <div>
                            <span style="font-size: 0.76rem; font-weight: 600; color: var(--muted); display: block;">Linked Testcases (comma-separated):</span>
                            <input style="margin-top: 2px; padding: 6px 8px; border-radius: 6px;" :value="Array.isArray(row.linkedTestcases) ? row.linkedTestcases.join(', ') : ''" @input="updateStrategyField(index, 'linkedTestcases', $event.target.value)" />
                          </div>
                        </div>
                      </td>
                    </tr>
                  </template>
                </tbody>
              </table>
              <div style="padding: 8px; display: flex; justify-content: flex-start;">
                <button class="ghost small-btn" @click="addStrategy">+ Add Strategy</button>
              </div>
            </div>

            <label v-show="reviewStrategiesViewMode === 'json'">
              testStrategies (JSON)
              <textarea v-model="reviewStrategiesText" rows="6"></textarea>
            </label>
            <div class="section-save-row">
              <button class="ghost small-btn" @click="saveTestStrategies">Save Strategies</button>
            </div>
          </section>

          <section class="collapsible result-tab-pane" v-if="hasTestcases" v-show="activeSummaryTab === 'cases'">
            <h3 class="pane-title">Test Cases</h3>
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
            <div class="section-save-row">
              <button class="ghost small-btn" @click="saveTestcasesOnly">Save Test Cases</button>
            </div>
          </section>

          <section class="collapsible result-tab-pane" v-if="summaryEnhancedTestcases.length" v-show="activeSummaryTab === 'enhancements'">
            <h3 class="pane-title">LLM Enhanced White-Box Test Design</h3>
            <p class="msg">These entries are LLM post-processing notes based on deterministic CFG paths. Coverage items and paths are unchanged.</p>
            <div class="llm-enhancement-list">
              <article class="llm-enhancement-card" v-for="item in summaryEnhancedTestcases" :key="item.baseSequenceId">
                <div class="enhancement-head">
                  <strong>{{ enhancedTitle(item) }}</strong>
                  <span class="badge">{{ item.baseSequenceId }}</span>
                </div>
                <p class="msg" v-if="item.testIntentSummary">{{ item.testIntentSummary }}</p>
                <div class="enhancement-grid">
                  <div v-if="enhancedList(item, 'refinedInputSuggestions').length">
                    <span>Inputs</span>
                    <ul><li v-for="entry in enhancedList(item, 'refinedInputSuggestions')" :key="entry">{{ entry }}</li></ul>
                  </div>
                  <div v-if="enhancedList(item, 'refinedSetupSuggestions').length">
                    <span>Setup</span>
                    <ul><li v-for="entry in enhancedList(item, 'refinedSetupSuggestions')" :key="entry">{{ entry }}</li></ul>
                  </div>
                  <div v-if="enhancedList(item, 'refinedOracleSuggestions').length">
                    <span>Oracle</span>
                    <ul><li v-for="entry in enhancedList(item, 'refinedOracleSuggestions')" :key="entry">{{ entry }}</li></ul>
                  </div>
                </div>
                <details v-if="enhancedNotes(item).length">
                  <summary>Review notes</summary>
                  <ul><li v-for="entry in enhancedNotes(item)" :key="entry">{{ entry }}</li></ul>
                </details>
                <details v-if="item.promptPreview">
                  <summary>Prompt preview</summary>
                  <pre>{{ item.promptPreview }}</pre>
                </details>
              </article>
            </div>
          </section>

          <section class="collapsible result-tab-pane" v-if="hasTraceability" v-show="activeSummaryTab === 'traceability'">
            <h3 class="pane-title">Traceability</h3>
            <div class="review-toggle">
              <button class="ghost" :class="{ active: reviewTraceabilityViewMode === 'table' }" @click="reviewTraceabilityViewMode = 'table'">Table</button>
              <button class="ghost" :class="{ active: reviewTraceabilityViewMode === 'json' }" @click="reviewTraceabilityViewMode = 'json'">JSON</button>
            </div>

            <div class="case-table-wrap" v-if="reviewTraceabilityViewMode === 'table' && reviewTableTraceability.length">
              <table class="case-table">
                <thead>
                  <tr>
                    <th style="width: 150px;">Req ID</th>
                    <th>Coverage Items (comma-separated)</th>
                    <th>Linked Test Cases (comma-separated)</th>
                    <th style="width: 80px;">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, index) in reviewTableTraceability" :key="row.reqId || index">
                    <td><input :value="row.reqId" @input="updateTraceabilityField(index, 'reqId', $event.target.value)" /></td>
                    <td><input :value="Array.isArray(row.coverageItems) ? row.coverageItems.join(', ') : ''" @input="updateTraceabilityField(index, 'coverageItems', $event.target.value)" /></td>
                    <td><input :value="Array.isArray(row.testcases) ? row.testcases.join(', ') : ''" @input="updateTraceabilityField(index, 'testcases', $event.target.value)" /></td>
                    <td>
                      <button class="ghost small-btn danger" style="min-height: 28px; padding: 2px 6px;" @click="deleteTraceabilityRow(index)">Delete</button>
                    </td>
                  </tr>
                </tbody>
              </table>
              <div style="padding: 8px; display: flex; justify-content: flex-start;">
                <button class="ghost small-btn" @click="addTraceabilityRow">+ Add Traceability Mapping</button>
              </div>
            </div>

            <label v-show="reviewTraceabilityViewMode === 'json'">
              traceability
              <textarea v-model="reviewTraceabilityText" rows="6"></textarea>
            </label>
            <div class="section-save-row">
              <button class="ghost small-btn" @click="saveTraceability">Save Traceability</button>
            </div>
          </section>

          <p class="msg review-tip" v-if="result">Each section now has its own Save button. Risk edits are saved separately in QRA review.</p>
          <p class="msg" v-if="reviewError">{{ reviewError }}</p>
        </div>

        </article>

        <article class="panel result empty-result" v-show="activePrimaryTab === 'summary' && !result">
          <div>
            <p class="eyebrow">Generated Results Summary</p>
            <h2>Waiting for Generated Cases</h2>
            <p class="msg">Generate one or more black-box techniques. Successful outputs will be merged here and can be edited.</p>
          </div>
        </article>
      </section>
    </section>

    <div class="confirm-modal" v-if="pendingRequirementDelete" @click.self="cancelDeleteRequirementRow">
      <section class="confirm-dialog panel" role="dialog" aria-modal="true" aria-labelledby="deleteRequirementTitle">
        <p class="eyebrow">Confirm Delete</p>
        <h2 id="deleteRequirementTitle">Delete Structured Requirement?</h2>
        <p class="msg">
          This will remove <b>{{ pendingRequirementDelete.label }}</b> from the QRA requirement draft.
          Save Changes afterward to use the updated requirements for generation.
        </p>
        <div class="confirm-actions">
          <button class="ghost small-btn" @click="cancelDeleteRequirementRow">Cancel</button>
          <button class="danger small-btn" @click="confirmDeleteRequirementRow">Confirm Delete</button>
        </div>
      </section>
    </div>

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
