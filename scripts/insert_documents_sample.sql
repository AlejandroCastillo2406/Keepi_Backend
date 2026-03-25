-- ============================================================
-- Inserta un documento de ejemplo en documents
-- Uso:
--   psql -U postgres -d keepi -f scripts/insert_documents_sample.sql
-- Nota:
--   Toma el primer usuario existente en la tabla users.
-- ============================================================

INSERT INTO documents (
    user_id,
    name,
    category,
    description,
    file_name,
    file_type,
    file_size,
    tags,
    is_archived,
    is_favorite
)
SELECT
    u.id,
    'Poliza de seguro auto',
    'seguros',
    'Documento de prueba insertado por script SQL',
    'poliza_auto_2026.pdf',
    'application/pdf',
    245760,
    ARRAY['seguro', 'auto', 'anual'],
    false,
    false
FROM users u
LIMIT 1;
