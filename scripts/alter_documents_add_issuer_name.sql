-- ============================================================
-- Agrega campo "issuer_name" a documents
-- Uso:
--   psql -U postgres -d keepi -f scripts/alter_documents_add_issuer_name.sql
-- ============================================================

ALTER TABLE documents
ADD COLUMN IF NOT EXISTS issuer_name VARCHAR(255);

COMMENT ON COLUMN documents.issuer_name IS
'Nombre del emisor del documento (empresa/institucion/proveedor).';

CREATE INDEX IF NOT EXISTS ix_documents_issuer_name
ON documents (issuer_name);
