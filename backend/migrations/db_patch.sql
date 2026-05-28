DO $$
DECLARE
    schema_record RECORD;
    original_search_path TEXT;
BEGIN
    -- Save the original search_path
    SHOW search_path INTO original_search_path;

    -- Loop through all non-system schemas
    FOR schema_record IN
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast', 'pg_temp_1', 'pg_toast_temp_1')
        ORDER BY schema_name
    LOOP
        -- Set search_path to current schema
        EXECUTE format('SET search_path TO %I', schema_record.schema_name);

        RAISE NOTICE 'Processing schema: %', schema_record.schema_name;

        -- ============================================
        -- START OF PATCH OPERATIONS FOR CURRENT SCHEMA
        -- ============================================

        -- Process optimization (alembic 03dafa6a220a):
        -- add auth_config JSONB to agent_tools and configurations (idempotent)

        ALTER TABLE IF EXISTS configurations
            ADD COLUMN IF NOT EXISTS auth_config JSONB;

        ALTER TABLE IF EXISTS agent_tools
            ADD COLUMN IF NOT EXISTS auth_config JSONB;

        -- Stamp alembic_version so `alembic upgrade` treats this schema as up-to-date
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = schema_record.schema_name
              AND table_name = 'alembic_version'
        ) THEN
            EXECUTE 'UPDATE alembic_version SET version_num = ''03dafa6a220a''';
        END IF;

        -- ============================================
        -- END OF PATCH OPERATIONS FOR CURRENT SCHEMA
        -- ============================================

    END LOOP;

    -- Restore the original search_path safely
    EXECUTE 'SET search_path TO ' || quote_literal(original_search_path);

    RAISE NOTICE 'Patch completed for all schemas';

EXCEPTION
    WHEN OTHERS THEN
        -- Restore search_path even if error occurs
        EXECUTE 'SET search_path TO ' || quote_literal(original_search_path);
        RAISE;
END $$;
