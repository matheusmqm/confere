-- Executado uma vez, na primeira criação do volume, conectado ao banco `confere`.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Banco dedicado aos testes marcados `db`, com as mesmas extensões.
CREATE DATABASE confere_test;
\connect confere_test
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
