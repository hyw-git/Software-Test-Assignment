CREATE TABLE IF NOT EXISTS generation_records (
    id SERIAL PRIMARY KEY,
    source_type VARCHAR(20) NOT NULL,
    technique VARCHAR(20) NOT NULL DEFAULT 'black-box',
    source_summary TEXT NOT NULL,
    model_name VARCHAR(80) NOT NULL DEFAULT 'unknown',
    generated_cases JSONB NOT NULL,
    quality_score NUMERIC(4,2) NOT NULL DEFAULT 0.00,
    tokens_estimate INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
