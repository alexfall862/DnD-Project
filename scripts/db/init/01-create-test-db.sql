-- Runs once on first container start. The integration suite uses a real PostgreSQL
-- database (docs/testing/testing-strategy.md §4), kept separate from the dev database.
CREATE DATABASE ttrpg_test OWNER ttrpg;
