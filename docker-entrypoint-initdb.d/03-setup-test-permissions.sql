-- PostgreSQL initialization for testing support
-- This script ensures proper permissions for Django test database creation

-- Ensure postgres user has a password and proper permissions
ALTER USER postgres WITH PASSWORD 'postgres';
ALTER USER postgres CREATEDB;

-- Ensure myhours_user has all necessary permissions (should already have them)
ALTER USER myhours_user CREATEDB;
ALTER USER myhours_user CREATEROLE;

-- Create a dedicated test user with all permissions needed for Django tests
DROP USER IF EXISTS django_test_user;
CREATE USER django_test_user WITH 
    SUPERUSER 
    CREATEDB 
    CREATEROLE 
    PASSWORD 'django_test_password';

-- Grant necessary privileges
GRANT ALL PRIVILEGES ON DATABASE myhours_db TO django_test_user;
GRANT ALL PRIVILEGES ON DATABASE myhours_db TO myhours_user;

-- Create template databases for testing (these will be used as templates)
DROP DATABASE IF EXISTS template_test;
CREATE DATABASE template_test OWNER myhours_user;

-- Show final user permissions
SELECT 
    rolname,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolcanlogin
FROM pg_roles 
WHERE rolname IN ('postgres', 'myhours_user', 'django_test_user')
ORDER BY rolname;