-- Migración para BDs ya existentes (p. ej. Render) donde create_all no añade columnas nuevas.
-- Ejecutar una vez contra el Postgres de producción (Shell de Render / psql / cliente SQL).
-- Orden: medical_specialties → tablas de cuestionario → users.specialty_id (FK).

BEGIN;

-- 1) Especialidades médicas (requeridas por users.specialty_id y plantillas)
CREATE TABLE IF NOT EXISTS public.medical_specialties (
    id UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(64) NOT NULL,
    name_es VARCHAR(255) NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_medical_specialties_code
    ON public.medical_specialties (code);

-- 2) Catálogo de cuestionarios
CREATE TABLE IF NOT EXISTS public.questionnaire_templates (
    id UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    slug VARCHAR(128) NOT NULL,
    scope VARCHAR(32) NOT NULL,
    owner_user_id UUID NULL REFERENCES public.users (id) ON DELETE CASCADE,
    medical_specialty_id UUID NULL REFERENCES public.medical_specialties (id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_questionnaire_templates_slug
    ON public.questionnaire_templates (slug);

CREATE INDEX IF NOT EXISTS ix_questionnaire_templates_owner_user_id
    ON public.questionnaire_templates (owner_user_id);

CREATE INDEX IF NOT EXISTS ix_questionnaire_templates_medical_specialty_id
    ON public.questionnaire_templates (medical_specialty_id);

CREATE TABLE IF NOT EXISTS public.questionnaire_versions (
    id UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id UUID NOT NULL REFERENCES public.questionnaire_templates (id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1,
    is_published BOOLEAN NOT NULL DEFAULT false,
    published_at TIMESTAMP WITH TIME ZONE NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_qv_template_version
    ON public.questionnaire_versions (template_id, version);

CREATE INDEX IF NOT EXISTS ix_questionnaire_versions_template_id
    ON public.questionnaire_versions (template_id);

CREATE TABLE IF NOT EXISTS public.questionnaire_questions (
    id UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id UUID NOT NULL REFERENCES public.questionnaire_versions (id) ON DELETE CASCADE,
    order_index INTEGER NOT NULL DEFAULT 0,
    section_key VARCHAR(64) NULL,
    prompt TEXT NOT NULL,
    help_text TEXT NULL,
    response_type VARCHAR(64) NOT NULL,
    config JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_questionnaire_questions_version_id
    ON public.questionnaire_questions (version_id);

CREATE TABLE IF NOT EXISTS public.questionnaire_question_options (
    id UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id UUID NOT NULL REFERENCES public.questionnaire_questions (id) ON DELETE CASCADE,
    value VARCHAR(255) NOT NULL,
    label VARCHAR(512) NOT NULL,
    icon_key VARCHAR(64) NULL,
    order_index INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_questionnaire_question_options_question_id
    ON public.questionnaire_question_options (question_id);

CREATE TABLE IF NOT EXISTS public.doctor_questionnaire_settings (
    doctor_id UUID NOT NULL PRIMARY KEY REFERENCES public.users (id) ON DELETE CASCADE,
    medical_specialty_id UUID NULL REFERENCES public.medical_specialties (id) ON DELETE SET NULL,
    mode VARCHAR(32) NOT NULL DEFAULT 'system_composed',
    include_base_in_custom BOOLEAN NOT NULL DEFAULT true,
    active_version_id UUID NULL REFERENCES public.questionnaire_versions (id) ON DELETE SET NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_doctor_questionnaire_settings_active_version_id
    ON public.doctor_questionnaire_settings (active_version_id);

CREATE TABLE IF NOT EXISTS public.questionnaire_responses (
    id UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
    version_id UUID NOT NULL REFERENCES public.questionnaire_versions (id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    submitted_at TIMESTAMP WITH TIME ZONE NULL,
    created_by_doctor_id UUID NULL REFERENCES public.users (id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_questionnaire_responses_patient_id
    ON public.questionnaire_responses (patient_id);

CREATE INDEX IF NOT EXISTS ix_questionnaire_responses_version_id
    ON public.questionnaire_responses (version_id);

CREATE INDEX IF NOT EXISTS ix_questionnaire_responses_created_by_doctor_id
    ON public.questionnaire_responses (created_by_doctor_id);

CREATE TABLE IF NOT EXISTS public.questionnaire_answers (
    id UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    response_id UUID NOT NULL REFERENCES public.questionnaire_responses (id) ON DELETE CASCADE,
    question_id UUID NOT NULL REFERENCES public.questionnaire_questions (id) ON DELETE CASCADE,
    value JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_questionnaire_answers_response_id
    ON public.questionnaire_answers (response_id);

CREATE INDEX IF NOT EXISTS ix_questionnaire_answers_question_id
    ON public.questionnaire_answers (question_id);

-- 3) Columna nueva en users (el error en Render)
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS specialty_id UUID NULL;

ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_specialty_id_fkey;

ALTER TABLE public.users
    ADD CONSTRAINT users_specialty_id_fkey
    FOREIGN KEY (specialty_id) REFERENCES public.medical_specialties (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_users_specialty_id ON public.users (specialty_id);

COMMIT;
