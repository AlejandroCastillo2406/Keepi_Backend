-- ============================================================
-- Script para crear tablas de Keepi (PostgreSQL) - V3 (Planes Dinámicos Integrados)
-- Ejecutar después de borrar las tablas existentes.
-- Uso: psql -U postgres -d keepi -f create_tables.sql
-- ============================================================

-- Eliminar tablas en orden (por dependencias FK) para limpiar la base de datos
DROP TABLE IF EXISTS notifications_logs CASCADE;
DROP TABLE IF EXISTS notifications CASCADE;
DROP TABLE IF EXISTS oauth_credentials CASCADE;
DROP TABLE IF EXISTS subscriptions CASCADE;
DROP TABLE IF EXISTS plan_features CASCADE;  -- Se elimina por la nueva arquitectura
DROP TABLE IF EXISTS plans CASCADE;          
DROP TABLE IF EXISTS user_configs CASCADE;
DROP TABLE IF EXISTS documents CASCADE;
DROP TABLE IF EXISTS folders CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- ============================================================
-- 1. users
-- ============================================================
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255),
    refresh_token VARCHAR(500),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
CREATE INDEX ix_users_email ON users (email);

-- ============================================================
-- 2. user_configs
-- ============================================================
CREATE TABLE user_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id),
    cloud_provider VARCHAR(50) NOT NULL DEFAULT 'not_configured',
    notification_preferences JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- ============================================================
-- 3. folders
-- ============================================================
CREATE TABLE folders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    parent_folder_id UUID REFERENCES folders(id) ON DELETE SET NULL,
    drive_folder_id VARCHAR(255) NOT NULL,
    drive_parent_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- ============================================================
-- 4. documents
-- ============================================================
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    description TEXT,
    file_url TEXT,
    file_name VARCHAR(255),
    file_size INTEGER,
    file_type VARCHAR(100),
    expiry_date TIMESTAMP WITH TIME ZONE,
    document_metadata JSONB DEFAULT '{}',
    tags TEXT[] DEFAULT '{}',
    drive_file_id VARCHAR(255),
    cloud_provider VARCHAR(50),
    s3_key VARCHAR(500),
    extracted_text TEXT,
    ai_analysis JSONB DEFAULT '{}',
    folder_id UUID REFERENCES folders(id) ON DELETE SET NULL,
    is_archived BOOLEAN NOT NULL DEFAULT false,
    is_favorite BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- ============================================================
-- 5. notifications y 5.1 logs
-- ============================================================
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    type VARCHAR(50) NOT NULL DEFAULT 'info',
    target_date DATE,
    payload JSONB DEFAULT '{}'::jsonb,
    read BOOLEAN NOT NULL DEFAULT false,
    read_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE notifications_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    notification_type VARCHAR(50) NOT NULL,
    target_date DATE NOT NULL,
    days_before INTEGER,
    email_to VARCHAR(255),
    ses_message_id VARCHAR(255),
    sent_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_notifications_logs ON notifications_logs (user_id, document_id, notification_type, target_date);

-- ============================================================
-- 6. oauth_credentials
-- ============================================================
CREATE TABLE oauth_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    provider VARCHAR(50) NOT NULL DEFAULT 'google',
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_uri VARCHAR(255) NOT NULL DEFAULT 'https://oauth2.googleapis.com/token',
    client_id VARCHAR(255),
    client_secret VARCHAR(255),
    scopes JSONB DEFAULT '[]',
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- ============================================================
-- 7. NUEVO: plans (Catálogo de Planes Dinámico)
-- ============================================================
CREATE TABLE plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(50) NOT NULL UNIQUE,  
    name VARCHAR(100) NOT NULL,
    description TEXT,
    price INTEGER NOT NULL DEFAULT 0, 
    currency VARCHAR(10) NOT NULL DEFAULT 'MXN',
    interval VARCHAR(50) NOT NULL DEFAULT 'month',
    stripe_price_id VARCHAR(255),
    analysis_limit INTEGER NOT NULL DEFAULT 2, -- -1 para ilimitado
    features JSONB DEFAULT '[]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT true,
    recommended BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
CREATE INDEX ix_plans_code ON plans (code);

-- ============================================================
-- 8. subscriptions (ACTUALIZADA para Planes Dinámicos)
-- ============================================================
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id),
    plan_id UUID REFERENCES plans(id), -- LLAVE FORÁNEA A PLANS
    stripe_customer_id VARCHAR(255),
    stripe_subscription_id VARCHAR(255),
    stripe_price_id VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'inactive',
    trial_end TIMESTAMP WITH TIME ZONE,
    current_period_start TIMESTAMP WITH TIME ZONE,
    current_period_end TIMESTAMP WITH TIME ZONE,
    analysis_limit INTEGER NOT NULL DEFAULT 2,
    analysis_used INTEGER NOT NULL DEFAULT 0,
    extra_metadata TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    canceled_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX ix_subscriptions_user_id ON subscriptions (user_id);
CREATE INDEX ix_subscriptions_plan_id ON subscriptions (plan_id);


-- ============================================================
-- 9. INYECCIÓN DE DATOS INICIALES (Planes por defecto)
-- ============================================================

-- Plan Gratuito (Usamos un UUID específico para que el código pueda referenciarlo si lo necesita, aunque usamos 'code' principalmente)
INSERT INTO plans (id, code, name, description, price, interval, analysis_limit, features, is_active, recommended) 
VALUES (
    '11111111-1111-1111-1111-111111111111', 
    'free', 
    'Plan Gratuito', 
    'Plan básico con límites', 
    0, 
    'lifetime', 
    2, 
    '["2 análisis de documentos", "Almacenamiento básico", "Soporte por email"]'::jsonb, 
    true, 
    false
);

-- Plan Premium
INSERT INTO plans (id, code, name, description, stripe_price_id, price, interval, analysis_limit, features, is_active, recommended) 
VALUES (
    '22222222-2222-2222-2222-222222222222', 
    'premium', 
    'Plan Premium', 
    'Análisis Ilimitados de documentos', 
    'price_AQUI_TU_ID_STRIPE', 
    49, 
    'month', 
    -1, 
    '["Análisis ilimitados de documentos", "Almacenamiento ampliado (10GB)", "Integración con Google Drive", "Soporte prioritario", "Análisis avanzados con IA"]'::jsonb, 
    true, 
    true
);