-- ============================================================================
-- Schema: acervo de documentos do MAVI (busca híbrida: lexical + semântica)
-- ============================================================================

-- Extensão para busca semântica (embeddings)
CREATE EXTENSION IF NOT EXISTS vector;

-- Extensão para busca lexical "fuzzy" (opcional, ajuda em erros de digitação)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS documentos (
    id              SERIAL PRIMARY KEY,

    -- De onde esse registro veio (rastreabilidade)
    fonte           TEXT NOT NULL,          -- ex: "equipes_2026.xlsx"
    tipo_origem     TEXT NOT NULL DEFAULT 'planilha',
    linha_origem    INTEGER,                -- número da linha na planilha original

    -- Dado estruturado original (as colunas da planilha, preservadas)
    metadados       JSONB NOT NULL,

    -- Texto "narrativizado" da linha — usado para as duas buscas abaixo
    conteudo_texto  TEXT NOT NULL,

    -- Busca LEXICAL: gerado automaticamente a partir de conteudo_texto
    conteudo_tsv    TSVECTOR GENERATED ALWAYS AS (
                        to_tsvector('portuguese', conteudo_texto)
                    ) STORED,

    -- Busca SEMÂNTICA: embedding gerado pelo provider escolhido em embeddings.py
    -- Dimensão precisa bater com o provider (ajuste aqui se trocar):
    --   local (padrão, sem API/internet - TF-IDF+SVD)   -> 256
    --   OpenAI text-embedding-3-small                    -> 1536
    --   Voyage AI voyage-3                                -> 1024
    --   Google Gemini (gratuito, gemini-embedding-001)    -> 768 (reduzido de 3072)
    -- Limite tecnico: o indice HNSW nao aceita mais de 2000 dimensoes.
    embedding       VECTOR(256),

    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Índice para busca lexical rápida
CREATE INDEX IF NOT EXISTS idx_documentos_tsv
    ON documentos USING GIN (conteudo_tsv);

-- Índice para busca "fuzzy" por trecho de palavra (ex: nomes com erro de digitação)
CREATE INDEX IF NOT EXISTS idx_documentos_trgm
    ON documentos USING GIN (conteudo_texto gin_trgm_ops);

-- Índice para busca semântica (HNSW é o recomendado atualmente pelo pgvector)
CREATE INDEX IF NOT EXISTS idx_documentos_embedding
    ON documentos USING hnsw (embedding vector_cosine_ops);

-- Índices em campos de metadados usados com frequência em filtros
-- (ajuste os campos conforme as colunas reais das planilhas do Ramo)
CREATE INDEX IF NOT EXISTS idx_documentos_metadados
    ON documentos USING GIN (metadados);

-- Evita duplicar o mesmo registro se o script rodar de novo sobre a mesma planilha
CREATE UNIQUE INDEX IF NOT EXISTS idx_documentos_fonte_linha
    ON documentos (fonte, linha_origem);
