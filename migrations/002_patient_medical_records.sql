-- Expediente médico: un registro por paciente (usuario rol PATIENT).
-- El médico lo rellena al dar de alta; el paciente puede actualizarlo después.

CREATE TABLE IF NOT EXISTS patient_medical_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    date_of_birth DATE,
    sex VARCHAR(32),
    blood_type VARCHAR(16),
    allergies TEXT,
    chronic_conditions TEXT,
    current_medications TEXT,
    medical_notes TEXT,
    emergency_contact_name VARCHAR(255),
    emergency_contact_phone VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_patient_medical_records_patient
    ON patient_medical_records(patient_user_id);
