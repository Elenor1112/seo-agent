-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- for fast LIKE searches on URLs/queries

-- Alembic will run migrations; this just ensures extensions exist.
