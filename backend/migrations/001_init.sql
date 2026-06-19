-- Инициализация схемы для облачного PostgreSQL (Neon / Supabase).
-- Запуск: psql "$DATABASE_URL" -f migrations/001_init.sql

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS template_articles (
    id           SERIAL PRIMARY KEY,
    article_code VARCHAR(64) NOT NULL,
    name         TEXT        NOT NULL,
    section_name TEXT        NOT NULL,
    embedding    VECTOR(768)
);

CREATE INDEX IF NOT EXISTS idx_template_articles_code
    ON template_articles (article_code);

-- Индекс для быстрого поиска ближайших соседей по косинусной дистанции.
-- IVFFlat требует наличия данных перед построением; lists подбирается под объём.
CREATE INDEX IF NOT EXISTS idx_template_articles_embedding
    ON template_articles
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
