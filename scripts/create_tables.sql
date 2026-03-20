-- ============================================================
-- Script para crear tablas de Keepi (PostgreSQL)
-- Ejecutar después de borrar las tablas existentes.
-- Uso: psql -U postgres -d keepi -f create_tables.sql
-- ============================================================

-- Eliminar tablas en orden (por dependencias FK)
DROP TABLE IF EXISTS notifications CASCADE;
DROP TABLE IF EXISTS notifications_logs CASCADE;
DROP TABLE IF EXISTS oauth_credentials CASCADE;
DROP TABLE IF EXISTS subscriptions CASCADE;
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
CREATE INDEX ix_users_id ON users (id);

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
CREATE INDEX ix_user_configs_user_id ON user_configs (user_id);
CREATE INDEX ix_user_configs_id ON user_configs (id);

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
CREATE INDEX ix_folders_user_id ON folders (user_id);
CREATE INDEX ix_folders_parent_folder_id ON folders (parent_folder_id);
CREATE INDEX ix_folders_id ON folders (id);

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
CREATE INDEX ix_documents_user_id ON documents (user_id);
CREATE INDEX ix_documents_folder_id ON documents (folder_id);
CREATE INDEX ix_documents_id ON documents (id);

-- ============================================================
-- 5. notifications
-- ============================================================
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL DEFAULT 'info',

    target_date DATE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
CREATE INDEX ix_notifications_user_id ON notifications (user_id);
CREATE INDEX ix_notifications_id ON notifications (id);
CREATE INDEX ix_notifications_document_id ON notifications (document_id);
CREATE INDEX ix_notifications_target_date ON notifications (target_date);

-- ============================================================
-- 5.1 notifications_logs (para deduplicación y trazabilidad)
-- ============================================================
CREATE TABLE notifications_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,

    target_date DATE NOT NULL,              -- día-calendario que dispara el envío

    days_before INTEGER,                    -- opcional (ej: 3)
    ses_message_id VARCHAR(255),          -- opcional

    sent_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_notifications_logs
ON notifications_logs (user_id, document_id, target_date);

CREATE INDEX ix_notifications_logs_user_target
ON notifications_logs (user_id, target_date);

CREATE INDEX ix_notifications_logs_document
ON notifications_logs (document_id);

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
CREATE INDEX ix_oauth_credentials_user_id ON oauth_credentials (user_id);
CREATE INDEX ix_oauth_credentials_id ON oauth_credentials (id);

-- ============================================================
-- 7. subscriptions
-- ============================================================
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id),
    stripe_customer_id VARCHAR(255),
    stripe_subscription_id VARCHAR(255),
    stripe_price_id VARCHAR(255),
    plan VARCHAR(50) NOT NULL DEFAULT 'free',
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
CREATE INDEX ix_subscriptions_stripe_customer_id ON subscriptions (stripe_customer_id);
CREATE INDEX ix_subscriptions_stripe_subscription_id ON subscriptions (stripe_subscription_id);
CREATE INDEX ix_subscriptions_id ON subscriptions (id);
