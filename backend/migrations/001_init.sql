-- Инициализация схемы для облачного PostgreSQL (Neon / Supabase).
-- Запуск: psql "$DATABASE_URL" -f migrations/001_init.sql

-- Включаем расширение pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Создаём основную таблицу справочника
CREATE TABLE IF NOT EXISTS template_articles
(
    id           SERIAL PRIMARY KEY,

    -- Self FK: ссылка на родительский раздел.
    -- У корневых разделов (например, "(2.) Котлован") здесь будет NULL.
    -- ON DELETE CASCADE: при удалении раздела удаляются и его подразделы/работы.
    parent_id    INTEGER REFERENCES template_articles (id) ON DELETE CASCADE,

    -- Уникальный код статьи (например, "(17.5.3.)")
    article_code VARCHAR(64) UNIQUE NOT NULL,

    -- Наименование раздела или работы
    name         TEXT NOT NULL,

    -- Векторное представление (768 для text-embedding-004).
    -- У разделов-контейнеров обычно NULL: матчатся только листья-работы.
    embedding    VECTOR(768),

    created_at   TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Индекс для быстрого векторного поиска (HNSW: строится на пустой таблице,
-- не требует обучения lists в отличие от IVFFlat).
CREATE INDEX IF NOT EXISTS idx_template_articles_embedding
    ON template_articles
    USING hnsw (embedding vector_cosine_ops);

-- Индекс по внешнему ключу для быстрых JOIN'ов и построения дерева на фронтенде.
CREATE INDEX IF NOT EXISTS idx_template_articles_parent_id
    ON template_articles (parent_id);

-- Автообновление updated_at при UPDATE (DEFAULT срабатывает только на INSERT).
CREATE OR REPLACE FUNCTION set_updated_at()
    RETURNS TRIGGER AS
$$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_template_articles_updated_at ON template_articles;
CREATE TRIGGER trg_template_articles_updated_at
    BEFORE UPDATE ON template_articles
    FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
