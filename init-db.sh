#!/bin/bash
set -e

# Create ace_service database if it doesn't exist
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname="postgres" <<-EOSQL
    SELECT 'CREATE DATABASE ace_service'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'ace_service')\gexec
EOSQL
