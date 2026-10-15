-- Deployment proposal only. Applied exclusively to disposable PostgreSQL in tests.
CREATE SCHEMA IF NOT EXISTS review_approval;
REVOKE ALL ON SCHEMA review_approval FROM PUBLIC;
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='review_approval_runtime') THEN
    CREATE ROLE review_approval_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
END $$;
CREATE TABLE IF NOT EXISTS review_approval.items(id text PRIMARY KEY,payload text NOT NULL);
CREATE TABLE IF NOT EXISTS review_approval.cards(id text PRIMARY KEY,payload text NOT NULL);
CREATE TABLE IF NOT EXISTS review_approval.events(id text PRIMARY KEY,payload text NOT NULL);
CREATE TABLE IF NOT EXISTS review_approval.intents(id text PRIMARY KEY,payload text NOT NULL);
REVOKE ALL ON ALL TABLES IN SCHEMA review_approval FROM PUBLIC;
GRANT USAGE ON SCHEMA review_approval TO review_approval_runtime;
GRANT SELECT,INSERT,UPDATE ON ALL TABLES IN SCHEMA review_approval TO review_approval_runtime;
CREATE OR REPLACE VIEW review_approval.source_cache WITH (security_barrier=true) AS
SELECT cache_key,payload,updated_at FROM public.telegram_api_cache WHERE starts_with(cache_key,'reviews:');
CREATE OR REPLACE VIEW review_approval.source_journal WITH (security_barrier=true) AS
SELECT feedback_id,state,error FROM public.review_replies;
REVOKE ALL ON review_approval.source_cache,review_approval.source_journal FROM PUBLIC;
GRANT SELECT ON review_approval.source_cache,review_approval.source_journal TO review_approval_runtime;
-- Do not expose review_approval in PostgREST. No grants to anon/authenticated.
-- Views intentionally read as their trusted migration owner and expose only reviews.
-- Runtime gets NO base-table access, no view updates, no source queue writes.
-- Verify view owner can read source under existing RLS; provision dedicated login
-- and role membership only during separately approved deployment.
