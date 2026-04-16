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
    ALTER TABLE generation_records ALTER COLUMN quality_score SET NOT NULL;
    ALTER TABLE generation_records ALTER COLUMN tokens_estimate SET NOT NULL;
    ALTER TABLE generation_records ALTER COLUMN created_at SET NOT NULL;
  `;

  await pool.query(createSql);
  await pool.query(alterSql);
}

export async function insertGenerationRecord(sourceType, sourceSummary, generatedCases, metrics = {}) {
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
      quality_score,
      tokens_estimate
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    RETURNING id, source_type, technique, model_name, prompt_version, quality_score, tokens_estimate, created_at
  `;

  const modelName = generatedCases?.model || "unknown";
  const promptVersion = generatedCases?.promptVersion || "unknown";
  const promptUsed = String(generatedCases?.promptUsed || "").slice(0, 12000);
  const llmRawOutput = String(generatedCases?.llmRawOutput || "").slice(0, 40000);
  const cases = generatedCases?.testcases || [];
  const qualityScore = Number(metrics.qualityScore ?? (cases.length >= 3 ? 1.0 : 0.7));
  const tokensEstimate = Number(metrics.tokensEstimate ?? 0);
  const values = [
    sourceType,
    "black-box",
    sourceSummary,
    modelName,
    promptVersion,
    promptUsed,
    llmRawOutput,
    JSON.stringify(cases),
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
