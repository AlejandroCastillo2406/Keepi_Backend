-- Expediente médico: un registro por paciente (usuario rol PATIENT).
-- Ejecutar después de 001_roles_and_users_fk.sql

CREATE TABLE IF NOT EXISTS patient_medical_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    birth_date DATE,
    sex VARCHAR(20),
    blood_type VARCHAR(16),
    allergies TEXT,
    chronic_conditions TEXT,
    medications TEXT,
    surgical_history TEXT,
    family_history TEXT,
    notes TEXT,
    emergency_contact_name VARCHAR(255),
    emergency_contact_phone VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS ix_patient_medical_records_patient_user_id
    ON patient_medical_records (patient_user_id);

CREATE INDEX IF NOT EXISTS ix_patient_medical_records_created_by_user_id
    ON patient_medical_records (created_by_user_id);
