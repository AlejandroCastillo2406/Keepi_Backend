-- ============================================================
-- Fix producción: ON CONFLICT en notifications_logs
-- Error que corrige:
--   there is no unique or exclusion constraint matching the ON CONFLICT specification
--
-- Uso:
--   psql -U <user> -d <db> -f scripts/fix_notifications_logs_unique_index.sql
-- ============================================================

BEGIN;

-- 1) Eliminar duplicados existentes para permitir índice UNIQUE.
--    Conserva el registro más reciente por (user_id, document_id, target_date).
WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY user_id, document_id, target_date
            ORDER BY sent_at DESC, id DESC
        ) AS rn
    FROM notifications_logs
)
DELETE FROM notifications_logs n
USING ranked r
WHERE n.id = r.id
  AND r.rn > 1;

-- 2) Crear índice único esperado por ON CONFLICT.
CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_logs
ON notifications_logs (user_id, document_id, target_date);

COMMIT;

