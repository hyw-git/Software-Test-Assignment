import pg from "pg";

const { Pool } = pg;

const databaseUrl = process.env.DATABASE_URL;

if (!databaseUrl) {
  throw new Error("DATABASE_URL is required");
}

export const pool = new Pool({
  connectionString: databaseUrl
});

export async function ensureSchema() {
  const createSql = `
    CREATE TABLE IF NOT EXISTS generation_records (
      id SERIAL PRIMARY KEY,
      source_type VARCHAR(20) NOT NULL,
      technique VARCHAR(20) NOT NULL DEFAULT 'black-box',
      source_summary TEXT NOT NULL,
      model_name VARCHAR(80) NOT NULL DEFAULT 'unknown',
      prompt_version VARCHAR(80) NOT NULL DEFAULT 'unknown',
      prompt_used TEXT NOT NULL DEFAULT '',
      llm_raw_output TEXT NOT NULL DEFAULT '',
      generated_cases JSONB NOT NULL,
      structured_requirements JSONB NOT NULL DEFAULT '[]'::jsonb,
      coverage_items JSONB NOT NULL DEFAULT '[]'::jsonb,
      risk_items JSONB NOT NULL DEFAULT '[]'::jsonb,
      state_model JSONB NOT NULL DEFAULT '{}'::jsonb,
      suite_optimization JSONB NOT NULL DEFAULT '{}'::jsonb,
      traceability JSONB NOT NULL DEFAULT '[]'::jsonb,
      test_strategies JSONB NOT NULL DEFAULT '[]'::jsonb,
      engine_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
      engine_ms INTEGER NOT NULL DEFAULT 0,
      llm_ms INTEGER NOT NULL DEFAULT 0,
      total_ms INTEGER NOT NULL DEFAULT 0,
      quality_score NUMERIC(4,2) NOT NULL DEFAULT 0.00,
      tokens_estimate INTEGER NOT NULL DEFAULT 0,
      created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
  `;

  const alterSql = `
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) DEFAULT 'requirements';
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS technique VARCHAR(20) DEFAULT 'black-box';
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS source_summary TEXT DEFAULT '';
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS model_name VARCHAR(80) DEFAULT 'unknown';
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS prompt_version VARCHAR(80) DEFAULT 'unknown';
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS prompt_used TEXT DEFAULT '';
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS llm_raw_output TEXT DEFAULT '';
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS generated_cases JSONB DEFAULT '[]'::jsonb;
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS structured_requirements JSONB DEFAULT '[]'::jsonb;
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS coverage_items JSONB DEFAULT '[]'::jsonb;
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS risk_items JSONB DEFAULT '[]'::jsonb;
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS state_model JSONB DEFAULT '{}'::jsonb;
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS suite_optimization JSONB DEFAULT '{}'::jsonb;
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS traceability JSONB DEFAULT '[]'::jsonb;
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS test_strategies JSONB DEFAULT '[]'::jsonb;
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS engine_metadata JSONB DEFAULT '{}'::jsonb;
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS engine_ms INTEGER DEFAULT 0;
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS llm_ms INTEGER DEFAULT 0;
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS total_ms INTEGER DEFAULT 0;
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS quality_score NUMERIC(4,2) DEFAULT 0.00;
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS tokens_estimate INTEGER DEFAULT 0;
    ALTER TABLE generation_records ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();

    ALTER TABLE generation_records ALTER COLUMN source_type SET NOT NULL;
    ALTER TABLE generation_records ALTER COLUMN technique SET NOT NULL;
    ALTER TABLE generation_records ALTER COLUMN source_summary SET NOT NULL;
    ALTER TABLE generation_records ALTER COLUMN model_name SET NOT NULL;
    ALTER TABLE generation_records ALTER COLUMN prompt_version SET NOT NULL;
    ALTER TABLE generation_records ALTER COLUMN prompt_used SET NOT NULL;
    ALTER TABLE generation_records ALTER COLUMN llm_raw_output SET NOT NULL;
    ALTER TABLE generation_records ALTER COLUMN generated_cases SET NOT NULL;
    ALTER TABLE generation_records ALTER COLUMN structured_requirements SET NOT NULL;
    ALTER TABLE generation_records ALTER COLUMN coverage_items SET NOT NULL;
    ALTER TABLE generation_records ALTER COLUMN risk_items SET NOT NULL;
    ALTER TABLE generation_records ALTER COLUMN state_model SET NOT NULL;
    ALTER TABLE generation_records ALTER COLUMN suite_optimization SET NOT NULL;
    ALTER TABLE generation_records ALTER COLUMN traceability SET NOT NULL;
    ALTER TABLE generation_records ALTER COLUMN quality_score SET NOT NULL;
    ALTER TABLE generation_records ALTER COLUMN tokens_estimate SET NOT NULL;
    ALTER TABLE generation_records ALTER COLUMN created_at SET NOT NULL;
  `;

  await pool.query(createSql);
  await pool.query(alterSql);
}

export async function insertGenerationRecord(sourceType, sourceSummary, generatedCases, metrics = {}, technique = "black-box") {
  const query = `
    INSERT INTO generation_records (
      source_type,
      technique,
      source_summary,
      model_name,
      prompt_version,
      prompt_used,
      llm_raw_output,
      generated_cases,
      structured_requirements,
      coverage_items,
      risk_items,
      state_model,
      suite_optimization,
      traceability,
      test_strategies,
      engine_metadata,
      engine_ms,
      llm_ms,
      total_ms,
      quality_score,
      tokens_estimate
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21)
    RETURNING id, source_type, technique, model_name, prompt_version, quality_score, tokens_estimate, created_at
  `;

  const modelName = generatedCases?.model || "unknown";
  const promptVersion = generatedCases?.promptVersion || "unknown";
  const promptUsed = String(generatedCases?.promptUsed || "").slice(0, 12000);
  const llmRawOutput = String(generatedCases?.llmRawOutput || "").slice(0, 40000);
  const cases = generatedCases?.testcases || [];
  const artifacts = generatedCases?.artifacts || {};
  const structuredRequirements = artifacts?.requirementsStructured || [];
  const coverageItems = artifacts?.coverageItems || [];
  const riskItems = artifacts?.riskItems || [];
  const stateModel = artifacts?.stateModel || {};
  const suiteOptimization = artifacts?.testSuiteOptimization || {};
  const traceability = artifacts?.traceability || [];
  const testStrategies = artifacts?.testStrategies || [];
  const engineMetadata = generatedCases?.engineMetadata || artifacts?.engineMetadata || {};
  const timing = generatedCases?.timingMetrics || artifacts?.timingMetrics || {};
  const engineMs = Number(timing.engineMs ?? metrics.engineMs ?? 0);
  const llmMs = Number(timing.llmMs ?? metrics.llmMs ?? 0);
  const totalMs = Number(timing.totalMs ?? metrics.totalMs ?? engineMs + llmMs);
  const qualityScore = Number(metrics.qualityScore ?? (cases.length >= 3 ? 1.0 : 0.7));
  const tokensEstimate = Number(metrics.tokensEstimate ?? 0);
  const values = [
    sourceType,
    technique,
    sourceSummary,
    modelName,
    promptVersion,
    promptUsed,
    llmRawOutput,
    JSON.stringify(cases),
    JSON.stringify(structuredRequirements),
    JSON.stringify(coverageItems),
    JSON.stringify(riskItems),
    JSON.stringify(stateModel),
    JSON.stringify(suiteOptimization),
    JSON.stringify(traceability),
    JSON.stringify(testStrategies),
    JSON.stringify(engineMetadata),
    engineMs,
    llmMs,
    totalMs,
    qualityScore,
    tokensEstimate
  ];
  const result = await pool.query(query, values);
  return result.rows[0];
}

export async function getRecentGenerationRecords(limit = 200) {
  const sql = `
    SELECT
      id,
      source_type,
      technique,
      source_summary,
      model_name,
      prompt_version,
      prompt_used,
      llm_raw_output,
      generated_cases,
      structured_requirements,
      coverage_items,
      risk_items,
      state_model,
      suite_optimization,
      traceability,
      test_strategies,
      engine_metadata,
      engine_ms,
      llm_ms,
      total_ms,
      quality_score,
      tokens_estimate,
      created_at
    FROM generation_records
    ORDER BY created_at DESC
    LIMIT $1
  `;

  const result = await pool.query(sql, [limit]);
  return result.rows;
}

export async function deleteGenerationRecordById(id) {
  const sql = `
    DELETE FROM generation_records
    WHERE id = $1
    RETURNING id
  `;

  const result = await pool.query(sql, [id]);
  return result.rows[0] || null;
}
