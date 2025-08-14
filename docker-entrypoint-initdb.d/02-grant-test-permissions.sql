-- Grant CREATE DB permission to myhours_user for running tests
-- This allows Django to create test databases during pytest runs
ALTER USER myhours_user CREATEDB;

-- Also grant the user permission to create roles if needed for advanced testing
-- ALTER USER myhours_user CREATEROLE;

-- Show granted permissions
SELECT rolname, rolcreatedb, rolcreaterole, rolsuper 
FROM pg_roles 
WHERE rolname = 'myhours_user';