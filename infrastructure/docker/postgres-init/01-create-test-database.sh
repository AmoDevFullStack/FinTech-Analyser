#!/bin/sh
# Create the test database alongside the development one.
#
# tests/conftest.py creates and drops every table, so it must never point at the
# development database — it refuses to run unless the target name ends in _test. This
# script makes that database exist so the refusal is not the default experience.
#
# Postgres runs everything in /docker-entrypoint-initdb.d ONLY when initialising an empty
# data directory. An existing stack therefore needs it once, by hand:
#
#     docker compose exec postgres createdb -U fdt fdt_test
#
set -eu

TEST_DB="${POSTGRES_DB:-fdt}_test"

# createdb is not idempotent, so ask first rather than relying on an error being benign.
if psql -U "${POSTGRES_USER:-fdt}" -tAc "SELECT 1 FROM pg_database WHERE datname = '${TEST_DB}'" | grep -q 1; then
    echo "database ${TEST_DB} already exists, leaving it alone"
else
    createdb -U "${POSTGRES_USER:-fdt}" "${TEST_DB}"
    echo "created database ${TEST_DB}"
fi
