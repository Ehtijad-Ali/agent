#!/bin/sh
# Runs once, on the first start of an empty Postgres volume: a separate
# database and user for n8n, so its tables never mix with Signal's.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE USER n8n WITH PASSWORD '${N8N_DB_PASSWORD}';
CREATE DATABASE n8n OWNER n8n;
SQL
