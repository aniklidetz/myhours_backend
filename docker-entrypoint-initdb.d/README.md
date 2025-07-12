# PostgreSQL Initialization Directory

This directory contains scripts and SQL files that will be executed when PostgreSQL container is first initialized.

## How it works:

1. When PostgreSQL container starts for the first time (no data volume), it executes all `.sh` and `.sql` files in alphabetical order
2. The `01-restore-backup.sh` script checks if database is empty and restores the latest backup if found
3. Place your backup file here named as `postgres_YYYYMMDD_HHMMSS.sql`

## To update the initial data:

1. Create a new backup: `make backup` or `docker exec myhours_postgres pg_dump -U myhours_user -d myhours_db > backups/postgres_$(date +%Y%m%d_%H%M%S).sql`
2. Copy it here: `cp backups/postgres_LATEST.sql docker-entrypoint-initdb.d/`
3. Next time you run `make fresh` or start with clean volumes, this data will be loaded

## Note:
- These scripts only run on fresh database initialization
- If postgres_data volume already exists, these scripts are ignored
- To force re-initialization: `docker-compose down -v` (WARNING: deletes all data)