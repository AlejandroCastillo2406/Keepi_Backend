-- Roles: solo id y nombre (PostgreSQL).
-- Ejecutar una vez contra la base de datos del proyecto.

CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE
);

INSERT INTO roles (name) VALUES
    ('DOCTOR'),
    ('USER'),
    ('PATIENT')
ON CONFLICT (name) DO NOTHING;

-- Columnas en users (ajusta si ya existen)
ALTER TABLE users ADD COLUMN IF NOT EXISTS role_id INTEGER REFERENCES roles(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS created_by_user_id UUID REFERENCES users(id);

-- Usuarios existentes sin rol → USER
UPDATE users
SET role_id = (SELECT id FROM roles WHERE name = 'USER' LIMIT 1)
WHERE role_id IS NULL;

ALTER TABLE users ALTER COLUMN role_id SET NOT NULL;
